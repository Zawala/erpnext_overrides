# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Keys, CSR, invoice hash and XAdES signing for ZATCA Phase 2.

Pure module (lxml + cryptography, no frappe), written from:
  - E-invoicing Detailed Technical Guideline v2, §5 "Signing Process"
  - Electronic Invoice Security Features Implementation Standards v1.2 (2023)

Signing follows the Guideline's steps:
  1. invoice hash: drop UBLExtensions, the QR reference and cac:Signature, canonicalise, SHA-256
  2. ECDSA-sign the invoice hash with the EGS private key
  3. hash the certificate
  4-5. fill in and hash the XAdES SignedProperties
  6. write the signature, certificate and both digests into ext:UBLExtensions
"""

import base64
import hashlib
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ObjectIdentifier
from lxml import etree

NS = {
	"inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
	"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
	"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
	"ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
	"sig": "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2",
	"sac": "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2",
	"sbc": "urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2",
	"ds": "http://www.w3.org/2000/09/xmldsig#",
	"xades": "http://uri.etsi.org/01903/v1.3.2#",
}

# The PIH of an EGS unit's first document: base64 of the hex SHA-256 of "0".
FIRST_PIH = base64.b64encode(hashlib.sha256(b"0").hexdigest().encode()).decode()

# Certificate template name (OID 1.3.6.1.4.1.311.20.2) per ZATCA environment.
TEMPLATE_NAME = {
	"developer-portal": "TSTZATCA-Code-Signing",
	"simulation": "PREZATCA-Code-Signing",
	"core": "ZATCA-Code-Signing",
}
_TEMPLATE_OID = ObjectIdentifier("1.3.6.1.4.1.311.20.2")
_REGISTERED_ADDRESS = ObjectIdentifier("2.5.4.26")


# --- keys and CSR -------------------------------------------------------------------------------


def new_private_key() -> str:
	"""A fresh secp256k1 key as PEM (the curve ZATCA requires)."""
	key = ec.generate_private_key(ec.SECP256K1())
	return key.private_bytes(
		serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
	).decode()


def load_private_key(pem: str) -> ec.EllipticCurvePrivateKey:
	return serialization.load_pem_private_key(pem.encode(), password=None)


def make_csr(
	private_key_pem: str,
	*,
	common_name: str,
	organization: str,
	organization_unit: str,
	vat_number: str,
	serial: str,
	invoice_types: str,
	address: str,
	business_category: str,
	environment: str = "developer-portal",
) -> str:
	"""The onboarding CSR, as the base64 of its PEM text (what the /compliance API takes).

	`serial` is "1-<solution name>|2-<model or version>|3-<serial number>".
	`invoice_types` is the four-digit TSCZ flag: standard, simplified, then two reserved digits ("1100" = both).
	"""
	key = load_private_key(private_key_pem)
	template = TEMPLATE_NAME[environment].encode()
	san = x509.DirectoryName(
		x509.Name(
			[
				x509.NameAttribute(NameOID.SURNAME, serial),
				x509.NameAttribute(NameOID.USER_ID, vat_number),
				x509.NameAttribute(NameOID.TITLE, invoice_types),
				x509.NameAttribute(_REGISTERED_ADDRESS, address),
				x509.NameAttribute(NameOID.BUSINESS_CATEGORY, business_category),
			]
		)
	)
	csr = (
		x509.CertificateSigningRequestBuilder()
		.subject_name(
			x509.Name(
				[
					x509.NameAttribute(NameOID.COUNTRY_NAME, "SA"),
					x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, organization_unit),
					x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
					x509.NameAttribute(NameOID.COMMON_NAME, common_name),
				]
			)
		)
		# DER PrintableString: tag 0x13, length, value
		.add_extension(
			x509.UnrecognizedExtension(_TEMPLATE_OID, bytes([0x13, len(template)]) + template), critical=False
		)
		.add_extension(x509.SubjectAlternativeName([san]), critical=False)
		.sign(key, hashes.SHA256())
	)
	return base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode()


# --- certificates -------------------------------------------------------------------------------


def certificate_from_token(binary_security_token: str) -> str:
	"""ZATCA's binarySecurityToken is base64 of the certificate's base64 body; return that body."""
	return base64.b64decode(binary_security_token).decode()


def load_certificate(cert_b64: str) -> x509.Certificate:
	return x509.load_der_x509_certificate(base64.b64decode(cert_b64))


def issuer_name(cert: x509.Certificate) -> str:
	"""Issuer as "CN=…, DC=…, DC=…" (RFC 4514 order, comma-space separated)."""
	return ", ".join(rdn.rfc4514_string() for rdn in reversed(cert.issuer.rdns))


# --- hashing ------------------------------------------------------------------------------------


def _hash_input(xml: bytes) -> bytes:
	"""The canonical bytes the invoice hash is taken over (Guideline §5.2 step 1)."""
	root = etree.fromstring(xml)
	strip = [
		*root.xpath("ext:UBLExtensions", namespaces=NS),
		*root.xpath("cac:Signature", namespaces=NS),
		*root.xpath("cac:AdditionalDocumentReference[normalize-space(cbc:ID)='QR']", namespaces=NS),
	]
	for el in strip:
		el.getparent().remove(el)
	# lxml has C14N 1.0, not the 1.1 the spec names. They differ only in xml:id/xml:base handling,
	# which UBL invoices don't use, so the output is the same.
	return etree.tostring(root, method="c14n")


def invoice_hash(xml: bytes) -> str:
	"""base64 of the SHA-256 digest (raw bytes) of the canonical invoice."""
	return base64.b64encode(hashlib.sha256(_hash_input(xml)).digest()).decode()


def _b64_hex_sha256(data: bytes) -> str:
	"""base64 of the *hex text* of a SHA-256: the form ZATCA uses for the cert and SignedProperties digests."""
	return base64.b64encode(hashlib.sha256(data).hexdigest().encode()).decode()


# --- signing ------------------------------------------------------------------------------------

_SIGNATURE_BLOCK = """<ext:UBLExtension>\
<ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI>\
<ext:ExtensionContent>\
<sig:UBLDocumentSignatures xmlns:sig="{sig}" xmlns:sac="{sac}" xmlns:sbc="{sbc}">\
<sac:SignatureInformation>\
<cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID>\
<sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID>\
<ds:Signature xmlns:ds="{ds}" Id="signature">\
<ds:SignedInfo>\
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>\
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"/>\
<ds:Reference Id="invoiceSignedData" URI="">\
<ds:Transforms>\
<ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116"><ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath></ds:Transform>\
<ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116"><ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath></ds:Transform>\
<ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116"><ds:XPath>not(//ancestor-or-self::cac:AdditionalDocumentReference[cbc:ID='QR'])</ds:XPath></ds:Transform>\
<ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>\
</ds:Transforms>\
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>\
<ds:DigestValue>{invoice_hash}</ds:DigestValue>\
</ds:Reference>\
<ds:Reference Type="http://www.w3.org/2000/09/xmldsig#SignatureProperties" URI="#xadesSignedProperties">\
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>\
<ds:DigestValue>{props_hash}</ds:DigestValue>\
</ds:Reference>\
</ds:SignedInfo>\
<ds:SignatureValue>{signature}</ds:SignatureValue>\
<ds:KeyInfo><ds:X509Data><ds:X509Certificate>{certificate}</ds:X509Certificate></ds:X509Data></ds:KeyInfo>\
<ds:Object>\
<xades:QualifyingProperties xmlns:xades="{xades}" Target="signature">\
{signed_properties}\
</xades:QualifyingProperties>\
</ds:Object>\
</ds:Signature>\
</sac:SignatureInformation>\
</sig:UBLDocumentSignatures>\
</ext:ExtensionContent>\
</ext:UBLExtension>"""

# ZATCA's validator recomputes this digest over the SignedProperties text with *this* layout:
# the element in the document must carry exactly this whitespace, and the digest is taken over
# the same text with the xades/ds namespace declarations written in (exclusive-C14N style).
# A compact (unindented) block is rejected with "signed-properties-hashing", even though it's
# equivalent XML. Found by testing against the developer-portal reporting API.
_SIGNED_PROPERTIES = """<xades:SignedProperties{xades_ns} Id="xadesSignedProperties">
                                    <xades:SignedSignatureProperties>
                                        <xades:SigningTime>{signing_time}</xades:SigningTime>
                                        <xades:SigningCertificate>
                                            <xades:Cert>
                                                <xades:CertDigest>
                                                    <ds:DigestMethod{ds_ns} Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                                    <ds:DigestValue{ds_ns}>{cert_hash}</ds:DigestValue>
                                                </xades:CertDigest>
                                                <xades:IssuerSerial>
                                                    <ds:X509IssuerName{ds_ns}>{issuer}</ds:X509IssuerName>
                                                    <ds:X509SerialNumber{ds_ns}>{serial}</ds:X509SerialNumber>
                                                </xades:IssuerSerial>
                                            </xades:Cert>
                                        </xades:SigningCertificate>
                                    </xades:SignedSignatureProperties>
                                </xades:SignedProperties>"""


def sign_hash(invoice_hash_b64: str, private_key_pem: str) -> str:
	"""ECDSA (SHA-256) signature over the raw invoice-hash bytes, base64 DER."""
	key = load_private_key(private_key_pem)
	sig = key.sign(base64.b64decode(invoice_hash_b64), ec.ECDSA(hashes.SHA256()))
	return base64.b64encode(sig).decode()


def sign(xml: bytes, private_key_pem: str, cert_b64: str, signing_time: datetime | None = None) -> dict:
	"""Sign an unsigned invoice (one with an empty ext:UBLExtensions).

	Returns {xml, invoice_hash, signature}. The QR is not touched here: it needs the signature,
	so the caller builds it afterwards and calls `set_qr` (the QR is outside the hash).
	"""
	from xml.sax.saxutils import escape

	cert = load_certificate(cert_b64)
	inv_hash = invoice_hash(xml)
	signature = sign_hash(inv_hash, private_key_pem)
	when = (signing_time or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%S")

	values = dict(
		signing_time=when,
		cert_hash=_b64_hex_sha256(cert_b64.encode()),
		issuer=escape(issuer_name(cert)),
		serial=cert.serial_number,
	)
	props = _SIGNED_PROPERTIES.format(xades_ns="", ds_ns="", **values)
	props_hash = _b64_hex_sha256(
		_SIGNED_PROPERTIES.format(xades_ns=f' xmlns:xades="{NS["xades"]}"', ds_ns=f' xmlns:ds="{NS["ds"]}"', **values).encode()
	)
	block = _SIGNATURE_BLOCK.format(
		**{k: NS[k] for k in ("sig", "sac", "sbc", "ds", "xades")},
		invoice_hash=inv_hash,
		props_hash=props_hash,
		signature=signature,
		certificate=cert_b64,
		signed_properties=props,
	)

	root = etree.fromstring(xml)
	exts = root.find("ext:UBLExtensions", NS)
	# parse the block in the context of the document's namespaces (ext, cbc are declared on the root)
	wrapper = etree.fromstring(
		f'<w xmlns:ext="{NS["ext"]}" xmlns:cbc="{NS["cbc"]}" xmlns:cac="{NS["cac"]}">{block}</w>'
	)
	exts.append(wrapper[0])

	return {
		"xml": etree.tostring(root, xml_declaration=True, encoding="UTF-8"),
		"invoice_hash": inv_hash,
		"signature": signature,
	}


def public_key_der(cert_b64: str) -> bytes:
	"""The certificate's public key as DER SubjectPublicKeyInfo (QR tag 8)."""
	return (
		load_certificate(cert_b64)
		.public_key()
		.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
	)


def certificate_signature(cert_b64: str) -> bytes:
	"""The issuing CA's signature over the certificate (QR tag 9)."""
	return load_certificate(cert_b64).signature


def set_qr(xml: bytes, qr: str) -> bytes:
	"""Write the QR into cac:AdditionalDocumentReference[ID=QR]. Doesn't change the invoice hash."""
	root = etree.fromstring(xml)
	node = root.find(
		"cac:AdditionalDocumentReference[cbc:ID='QR']/cac:Attachment/cbc:EmbeddedDocumentBinaryObject", NS
	)
	node.text = qr
	return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
