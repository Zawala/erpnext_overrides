# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Tests for the pure ZATCA modules: no frappe, no network.

	pytest erp_overrides/zatca/tests          (needs lxml, cryptography, requests)

Fixtures are ZATCA's own worked examples where the documents give one (the QR example in the
Technical Guideline §6, the API response bodies in the sandbox API reference); otherwise a
throwaway self-signed secp256k1 certificate stands in for ZATCA's.
"""

import base64
import datetime
import hashlib
import re
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from lxml import etree

from erp_overrides.zatca import client, crypto, document, qr, ubl
from erp_overrides.zatca.crypto import NS

SELLER = dict(
	name="Demo Trading Co", vat="399999999900003", crn="1010010000", street="King Fahd Rd",
	building="1234", district="Al Olaya", city="Riyadh", postal_code="12345",
)
BUYER = dict(
	name="Fictional Buyer LLC", vat="399999999800003", street="Prince Sultan St", building="5678",
	district="Al Rawdah", city="Jeddah", postal_code="23456",
)


def invoice(kind="simplified", doc_type="invoice", **over):
	inv = dict(
		kind=kind, type=doc_type, id="TEST-1", uuid="3cf5ee18-ee25-44ea-a444-2c37ba7f28be",
		issue_date="2026-11-11", issue_time="10:00:00", supply_date="2026-11-11", icv=1,
		pih=crypto.FIRST_PIH, billing_reference="TEST-0", reason="Returned",
		seller=SELLER, buyer=BUYER if kind == "standard" else None,
		lines=[
			dict(name="Widget", qty=3, rate=19.99, tax_category="S", tax_percent=15),
			dict(name="Medicine", qty=1, rate=10, tax_category="Z", tax_percent=0,
			     exemption_code="VATEX-SA-35", exemption_reason="Medicines and medical equipment"),
		],
	)
	inv.update(over)
	return inv


def self_signed() -> tuple[str, str]:
	"""(private key PEM, certificate base64 DER) standing in for a ZATCA-issued CSID."""
	key_pem = crypto.new_private_key()
	key = crypto.load_private_key(key_pem)
	name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test EGS")])
	now = datetime.datetime.now(datetime.UTC)
	cert = (
		x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
		.serial_number(4242).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
		.sign(key, hashes.SHA256())
	)
	return key_pem, base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()


class TestQR(unittest.TestCase):
	def test_guideline_example(self):
		# Technical Guideline §6, "Representation of the QR code Data Examples" (tags 1-5)
		self.assertEqual(
			qr.encode({1: "Bobs Records", 2: "310122393500003", 3: "2022-04-25T15:30:00Z", 4: "1000.00", 5: "150.00"}),
			"AQxCb2JzIFJlY29yZHMCDzMxMDEyMjM5MzUwMDAwMwMUMjAyMi0wNC0yNVQxNTozMDowMFoEBzEwMDAuMDAFBjE1MC4wMA==",
		)

	def test_round_trip_and_utf8_length(self):
		code = qr.encode({1: "شركة", 8: b"\x00\x01"})
		self.assertEqual(qr.decode(code), {1: "شركة".encode(), 8: b"\x00\x01"})

	def test_value_too_long(self):
		with self.assertRaises(ValueError):
			qr.encode({1: "x" * 256})


class TestUBL(unittest.TestCase):
	def test_totals_round_per_line_and_category(self):
		t = ubl.totals(invoice()["lines"])
		self.assertEqual(str(t["lines"][0]["net"]), "59.97")
		self.assertEqual(str(t["lines"][0]["vat"]), "9.00")  # 8.9955 rounds half-up
		self.assertEqual(str(t["line_total"]), "69.97")
		self.assertEqual(str(t["vat_total"]), "9.00")
		self.assertEqual(str(t["total"]), "78.97")

	def test_type_codes_and_references(self):
		root = etree.fromstring(ubl.build(invoice("standard", "credit")))
		code = root.find("cbc:InvoiceTypeCode", NS)
		self.assertEqual((code.text, code.get("name")), ("381", "0100000"))
		self.assertEqual(root.findtext("cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID", namespaces=NS), "TEST-0")
		self.assertEqual(root.findtext("cac:PaymentMeans/cbc:InstructionNote", namespaces=NS), "Returned")
		self.assertEqual(root.findtext("cac:AdditionalDocumentReference[cbc:ID='ICV']/cbc:UUID", namespaces=NS), "1")

	def test_simplified_invoice_has_no_billing_reference(self):
		root = etree.fromstring(ubl.build(invoice()))
		self.assertEqual(root.find("cbc:InvoiceTypeCode", NS).get("name"), "0200000")
		self.assertIsNone(root.find("cac:BillingReference", NS))

	def test_exemption_only_on_zero_rated_subtotal(self):
		root = etree.fromstring(ubl.build(invoice()))
		subs = root.findall("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory", NS)
		self.assertEqual([s.findtext("cbc:ID", namespaces=NS) for s in subs], ["S", "Z"])
		self.assertIsNone(subs[0].find("cbc:TaxExemptionReasonCode", NS))
		self.assertEqual(subs[1].findtext("cbc:TaxExemptionReasonCode", namespaces=NS), "VATEX-SA-35")


class TestSigning(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.key, cls.cert = self_signed()

	def test_first_pih(self):
		self.assertEqual(
			crypto.FIRST_PIH,
			"NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ==",
		)

	def test_hash_ignores_signature_and_qr_but_not_content(self):
		unsigned = ubl.build(invoice())
		doc = document.make(invoice(), self.key, self.cert)
		self.assertEqual(crypto.invoice_hash(unsigned), doc["invoice_hash"])
		self.assertEqual(crypto.invoice_hash(doc["xml"]), doc["invoice_hash"])
		self.assertNotEqual(crypto.invoice_hash(doc["xml"].replace(b"Widget", b"Wodget")), doc["invoice_hash"])

	def test_signature_verifies_over_the_hash(self):
		doc = document.make(invoice(), self.key, self.cert)
		public = crypto.load_certificate(self.cert).public_key()
		public.verify(
			base64.b64decode(doc["signature"]), base64.b64decode(doc["invoice_hash"]), ec.ECDSA(hashes.SHA256())
		)  # raises if it doesn't

	def test_signed_properties_digest_matches_document_text(self):
		root = etree.fromstring(document.make(invoice(), self.key, self.cert)["xml"])
		sp = root.find(".//xades:SignedProperties", NS)
		# ZATCA's form (accepted by the sandbox's reporting API): the element's text as it sits in the
		# document, whitespace and self-closing tags kept (so *not* C14N, which would expand
		# <ds:DigestMethod/>), with xmlns:xades on the element and xmlns:ds on each ds:* element;
		# then base64 of the hex SHA-256.
		text = etree.tostring(sp).decode()
		text = re.sub(r' xmlns(:\w+)?="[^"]*"', "", text)  # lxml copies every in-scope namespace onto it
		text = text.replace("<xades:SignedProperties", f'<xades:SignedProperties xmlns:xades="{NS["xades"]}"', 1)
		for tag in ("DigestMethod", "DigestValue", "X509IssuerName", "X509SerialNumber"):
			text = text.replace(f"<ds:{tag}", f'<ds:{tag} xmlns:ds="{NS["ds"]}"')
		digest = base64.b64encode(hashlib.sha256(text.encode()).hexdigest().encode()).decode()
		self.assertEqual(
			root.findtext(".//ds:Reference[@URI='#xadesSignedProperties']/ds:DigestValue", namespaces=NS), digest
		)
		self.assertIn("\n" + " " * 36 + "<xades:SignedSignatureProperties>", etree.tostring(sp).decode())

	def test_qr_fields(self):
		doc = document.make(invoice(), self.key, self.cert)
		tags = qr.decode(doc["qr"])
		self.assertEqual(tags[1].decode(), "Demo Trading Co")
		self.assertEqual(tags[3].decode(), "2026-11-11T10:00:00")
		self.assertEqual((tags[4].decode(), tags[5].decode()), ("78.97", "9.00"))
		self.assertEqual(tags[6].decode(), doc["invoice_hash"])
		self.assertEqual(tags[7].decode(), doc["signature"])
		self.assertEqual(tags[8], crypto.public_key_der(self.cert))
		self.assertIn(9, tags)  # simplified: the CA's signature over the certificate
		root = etree.fromstring(doc["xml"])
		self.assertEqual(
			root.findtext("cac:AdditionalDocumentReference[cbc:ID='QR']/cac:Attachment/cbc:EmbeddedDocumentBinaryObject",
			              namespaces=NS),
			doc["qr"],
		)

	def test_standard_qr_has_no_tag_9(self):
		self.assertNotIn(9, qr.decode(document.make(invoice("standard"), self.key, self.cert)["qr"]))


class TestCSR(unittest.TestCase):
	def test_fields(self):
		key = crypto.new_private_key()
		pem = base64.b64decode(crypto.make_csr(
			key, common_name="EGS-1", organization="Demo Trading Co", organization_unit="Riyadh",
			vat_number="399999999900003", serial="1-A|2-B|3-C", invoice_types="1100", address="Riyadh",
			business_category="Trading",
		))
		csr = x509.load_pem_x509_csr(pem)
		self.assertTrue(csr.is_signature_valid)
		self.assertIsInstance(csr.public_key().curve, ec.SECP256K1)
		san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
		dn = san.get_values_for_type(x509.DirectoryName)[0]
		self.assertEqual(dn.get_attributes_for_oid(NameOID.USER_ID)[0].value, "399999999900003")
		self.assertEqual(dn.get_attributes_for_oid(NameOID.TITLE)[0].value, "1100")
		template = csr.extensions.get_extension_for_oid(x509.ObjectIdentifier("1.3.6.1.4.1.311.20.2")).value
		self.assertEqual(template.value, b"\x13\x15TSTZATCA-Code-Signing")


class TestResponse(unittest.TestCase):
	"""Bodies from ZATCA's sandbox API reference (Sandbox Release 2.1.0)."""

	def test_top_level_errors(self):
		r = client.Response(400, {"errors": [{"code": "Invalid-OTP", "message": "The provided OTP is invalid"}]})
		self.assertEqual(r.messages(), ["Invalid-OTP: The provided OTP is invalid"])
		self.assertEqual(r.summary(), "HTTP 400: Invalid-OTP: The provided OTP is invalid")

	def test_validation_errors(self):
		r = client.Response(400, {"validationResults": {"errorMessages": [
			{"type": "ERROR", "code": "BR-KSA-37", "message": "The seller address building number must contain 4 digits."}
		], "warningMessages": [], "status": "ERROR"}, "reportingStatus": "NOT_REPORTED"})
		self.assertFalse(r.ok)
		self.assertEqual(r.messages(), ["BR-KSA-37: The seller address building number must contain 4 digits."])

	def test_409_message_without_code(self):
		r = client.Response(409, {"validationResults": {"errorMessages": [
			{"type": "ERROR", "code": None, "message": "Invoice was already Reported successfully earlier."}
		]}, "reportingStatus": "NOT_REPORTED"})
		self.assertEqual(r.messages(), ["Invoice was already Reported successfully earlier."])

	def test_303_and_500_bare_messages(self):
		r = client.Response(303, {"message": "Clearance is deactiviated. Please use the /invoices/reporting/single endpoint instead."})
		self.assertIn("Clearance is deactiviated", r.summary())
		r = client.Response(500, {"category": "HTTP-Errors", "code": "500", "message": "Something went wrong"})
		self.assertEqual(r.messages(), ["500: Something went wrong"])

	def test_plain_text_body(self):
		self.assertEqual(client.Response(400, {"raw": "Invalid Request"}).summary(), "HTTP 400: Invalid Request")

	def test_compliance_info_as_single_object(self):
		r = client.Response(200, {"validationResults": {"infoMessages": {"type": "INFO", "code": "XSD_ZATCA_VALID",
		                                                                  "message": "Complied"}}})
		self.assertTrue(r.ok)
		self.assertEqual(r.messages("infoMessages"), ["XSD_ZATCA_VALID: Complied"])
		self.assertEqual(r.messages(), [])


if __name__ == "__main__":
	unittest.main()
