# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""UBL 2.1 invoice XML for ZATCA, built from a plain dict.

Pure module (lxml only). Field names and rules come from the Electronic Invoice XML
Implementation Standard v1.2 (May 2023); BR-KSA-* refer to its business rules.

The input dict (see `mapping.py` for how a Sales Invoice is turned into one):

	{
	  "kind": "standard" | "simplified",          # B2B (clearance) or B2C (reporting)
	  "type": "invoice" | "credit" | "debit",
	  "id": "ACC-SINV-2026-00001", "uuid": "…",
	  "issue_date": "2026-11-11", "issue_time": "14:05:00",
	  "supply_date": "2026-11-11",                 # KSA-5, required on standard invoices
	  "currency": "SAR",
	  "icv": 7, "pih": "<base64 hash of the previous document>",
	  "billing_reference": "ACC-SINV-…",           # credit/debit notes: the original invoice
	  "reason": "Goods returned",                  # credit/debit notes: KSA-10
	  "payment_means": "10",                       # UNTDID 4461: 10 cash, 30 credit, 42 bank, 48 card
	  "seller": {name, vat, crn, street, building, district, city, postal_code},
	  "buyer": {name, vat, street, building, district, city, postal_code} | None,
	  "lines": [{name, qty, rate, unit?, tax_category, tax_percent, exemption_code?, exemption_reason?}],
	}

Amounts are worked out here, from the lines, so the XML always adds up the way the
validator checks it: line net = qty × rate, line VAT = round(net × %), category VAT =
round(taxable × %), totals summed from those.
"""

from decimal import ROUND_HALF_UP, Decimal

from lxml import etree

from erp_overrides.zatca.crypto import NS

TYPE_CODE = {"invoice": "388", "credit": "381", "debit": "383"}
# KSA-2: positions 1-2 are 01 standard / 02 simplified; the rest flag third-party, nominal,
# export, summary and self-billed documents, none of which this POC issues.
SUBTYPE = {"standard": "0100000", "simplified": "0200000"}

CENT = Decimal("0.01")


def money(value) -> Decimal:
	return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _el(parent, tag, text=None, **attrs):
	prefix, local = tag.split(":")
	el = etree.SubElement(parent, f"{{{NS[prefix]}}}{local}", {k: str(v) for k, v in attrs.items()})
	if text is not None:
		el.text = str(text)
	return el


def _amount(parent, tag, value, currency):
	return _el(parent, tag, f"{money(value):.2f}", currencyID=currency)


def totals(lines: list[dict]) -> dict:
	"""Line, category and document totals, all rounded to 2 decimals."""
	out_lines, categories = [], {}
	for line in lines:
		net = money(Decimal(str(line["qty"])) * money(line["rate"]))
		pct = Decimal(str(line["tax_percent"]))
		vat = money(net * pct / 100)
		out_lines.append({**line, "net": net, "vat": vat})
		key = (line["tax_category"], pct, line.get("exemption_code"), line.get("exemption_reason"))
		categories[key] = categories.get(key, Decimal(0)) + net
	subtotals = [
		{
			"category": cat,
			"percent": pct,
			"exemption_code": code,
			"exemption_reason": reason,
			"taxable": money(taxable),
			"vat": money(taxable * pct / 100),
		}
		for (cat, pct, code, reason), taxable in categories.items()
	]
	line_total = money(sum((l["net"] for l in out_lines), Decimal(0)))
	vat_total = money(sum((s["vat"] for s in subtotals), Decimal(0)))
	return {
		"lines": out_lines,
		"subtotals": subtotals,
		"line_total": line_total,
		"vat_total": vat_total,
		"total": line_total + vat_total,
	}


def _party(parent, party: dict, *, seller: bool):
	p = _el(parent, "cac:Party")
	if party.get("crn"):
		ident = _el(p, "cac:PartyIdentification")
		_el(ident, "cbc:ID", party["crn"], schemeID="CRN")
	if party.get("street") or seller:
		addr = _el(p, "cac:PostalAddress")
		_el(addr, "cbc:StreetName", party.get("street", ""))
		_el(addr, "cbc:BuildingNumber", party.get("building", ""))
		_el(addr, "cbc:CitySubdivisionName", party.get("district", ""))
		_el(addr, "cbc:CityName", party.get("city", ""))
		_el(addr, "cbc:PostalZone", party.get("postal_code", ""))
		country = _el(addr, "cac:Country")
		_el(country, "cbc:IdentificationCode", party.get("country", "SA"))
	if party.get("vat"):
		scheme = _el(p, "cac:PartyTaxScheme")
		_el(scheme, "cbc:CompanyID", party["vat"])
		_el(_el(scheme, "cac:TaxScheme"), "cbc:ID", "VAT")
	legal = _el(p, "cac:PartyLegalEntity")
	_el(legal, "cbc:RegistrationName", party["name"])


def _tax_category(parent, tag, category, percent, code=None, reason=None):
	cat = _el(parent, tag)
	_el(cat, "cbc:ID", category, schemeID="UN/ECE 5305", schemeAgencyID="6")
	_el(cat, "cbc:Percent", f"{Decimal(str(percent)):.2f}")
	if code:
		_el(cat, "cbc:TaxExemptionReasonCode", code)
		_el(cat, "cbc:TaxExemptionReason", reason or code)
	_el(_el(cat, "cac:TaxScheme"), "cbc:ID", "VAT", schemeID="UN/ECE 5153", schemeAgencyID="6")


def build(inv: dict) -> bytes:
	"""The unsigned invoice: an empty ext:UBLExtensions and a QR placeholder, ready for `crypto.sign`."""
	cur = inv.get("currency", "SAR")
	t = totals(inv["lines"])

	root = etree.Element(
		f"{{{NS['inv']}}}Invoice",
		nsmap={None: NS["inv"], "cac": NS["cac"], "cbc": NS["cbc"], "ext": NS["ext"]},
	)
	_el(root, "ext:UBLExtensions")
	_el(root, "cbc:ProfileID", "reporting:1.0")
	_el(root, "cbc:ID", inv["id"])
	_el(root, "cbc:UUID", inv["uuid"])
	_el(root, "cbc:IssueDate", inv["issue_date"])
	_el(root, "cbc:IssueTime", inv["issue_time"])
	_el(root, "cbc:InvoiceTypeCode", TYPE_CODE[inv["type"]], name=SUBTYPE[inv["kind"]])
	_el(root, "cbc:DocumentCurrencyCode", cur)
	_el(root, "cbc:TaxCurrencyCode", "SAR")

	if inv["type"] != "invoice":
		ref = _el(_el(root, "cac:BillingReference"), "cac:InvoiceDocumentReference")
		_el(ref, "cbc:ID", inv["billing_reference"])

	icv = _el(root, "cac:AdditionalDocumentReference")
	_el(icv, "cbc:ID", "ICV")
	_el(icv, "cbc:UUID", inv["icv"])
	for ref_id, value in (("PIH", inv["pih"]), ("QR", "")):
		ref = _el(root, "cac:AdditionalDocumentReference")
		_el(ref, "cbc:ID", ref_id)
		_el(_el(ref, "cac:Attachment"), "cbc:EmbeddedDocumentBinaryObject", value, mimeCode="text/plain")

	signature = _el(root, "cac:Signature")
	_el(signature, "cbc:ID", "urn:oasis:names:specification:ubl:signature:Invoice")
	_el(signature, "cbc:SignatureMethod", "urn:oasis:names:specification:ubl:dsig:enveloped:xades")

	_party(_el(root, "cac:AccountingSupplierParty"), inv["seller"], seller=True)
	_party(_el(root, "cac:AccountingCustomerParty"), inv.get("buyer") or {"name": ""}, seller=False)

	if inv.get("supply_date"):
		_el(_el(root, "cac:Delivery"), "cbc:ActualDeliveryDate", inv["supply_date"])

	means = _el(root, "cac:PaymentMeans")
	_el(means, "cbc:PaymentMeansCode", inv.get("payment_means", "10"))
	if inv["type"] != "invoice":
		_el(means, "cbc:InstructionNote", inv.get("reason") or "Adjustment")

	# BR-KSA-EN16931-09: one TaxTotal in the tax currency without subtotals, one with them
	_amount(_el(root, "cac:TaxTotal"), "cbc:TaxAmount", t["vat_total"], "SAR")
	tax_total = _el(root, "cac:TaxTotal")
	_amount(tax_total, "cbc:TaxAmount", t["vat_total"], cur)
	for s in t["subtotals"]:
		sub = _el(tax_total, "cac:TaxSubtotal")
		_amount(sub, "cbc:TaxableAmount", s["taxable"], cur)
		_amount(sub, "cbc:TaxAmount", s["vat"], cur)
		_tax_category(sub, "cac:TaxCategory", s["category"], s["percent"], s["exemption_code"], s["exemption_reason"])

	lmt = _el(root, "cac:LegalMonetaryTotal")
	_amount(lmt, "cbc:LineExtensionAmount", t["line_total"], cur)
	_amount(lmt, "cbc:TaxExclusiveAmount", t["line_total"], cur)
	_amount(lmt, "cbc:TaxInclusiveAmount", t["total"], cur)
	_amount(lmt, "cbc:AllowanceTotalAmount", 0, cur)
	_amount(lmt, "cbc:PrepaidAmount", 0, cur)
	_amount(lmt, "cbc:PayableAmount", t["total"], cur)

	for n, line in enumerate(t["lines"], 1):
		il = _el(root, "cac:InvoiceLine")
		_el(il, "cbc:ID", n)
		_el(il, "cbc:InvoicedQuantity", f"{Decimal(str(line['qty'])):.6f}", unitCode=line.get("unit", "PCE"))
		_amount(il, "cbc:LineExtensionAmount", line["net"], cur)
		lt = _el(il, "cac:TaxTotal")
		_amount(lt, "cbc:TaxAmount", line["vat"], cur)
		_amount(lt, "cbc:RoundingAmount", line["net"] + line["vat"], cur)
		item = _el(il, "cac:Item")
		_el(item, "cbc:Name", line["name"])
		_tax_category(item, "cac:ClassifiedTaxCategory", line["tax_category"], line["tax_percent"])
		price = _el(il, "cac:Price")
		_amount(price, "cbc:PriceAmount", line["rate"], cur)

	return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
