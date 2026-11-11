# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""One call from invoice dict to signed, QR-stamped XML. Pure module (no frappe)."""

from erp_overrides.zatca import crypto, qr, ubl


def make(inv: dict, private_key_pem: str, cert_b64: str) -> dict:
	"""→ {xml, invoice_hash, signature, qr}. `inv` is the dict `ubl.build` takes."""
	signed = crypto.sign(ubl.build(inv), private_key_pem, cert_b64)
	t = ubl.totals(inv["lines"])
	code = qr.build(
		seller_name=inv["seller"]["name"],
		vat_number=inv["seller"]["vat"],
		timestamp=f"{inv['issue_date']}T{inv['issue_time']}",
		total_with_vat=f"{t['total']:.2f}",
		vat_total=f"{t['vat_total']:.2f}",
		invoice_hash=signed["invoice_hash"],
		signature=signed["signature"],
		public_key=crypto.public_key_der(cert_b64),
		# tag 9 is for simplified documents; standard ones get ZATCA's QR on clearance
		certificate_signature=crypto.certificate_signature(cert_b64) if inv["kind"] == "simplified" else None,
	)
	return {**signed, "xml": crypto.set_qr(signed["xml"], code), "qr": code}
