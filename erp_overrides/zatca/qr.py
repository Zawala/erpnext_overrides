# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""ZATCA QR code: base64 of Tag-Length-Value fields (Technical Guideline §6, Security Features §4).

Pure module, no frappe import, so it can be unit-tested anywhere.

Tags 1-5 are the Phase 1 fields; 6-9 were added for Phase 2:
  1 seller name, 2 seller VAT number, 3 timestamp, 4 total with VAT, 5 VAT total,
  6 invoice hash, 7 ECDSA signature, 8 ECDSA public key,
  9 (simplified documents only) the CA's signature over the stamp certificate.
"""

import base64


def _tlv(tag: int, value: bytes) -> bytes:
	if len(value) > 255:
		raise ValueError(f"QR tag {tag} is {len(value)} bytes; a TLV length is one byte")
	return bytes([tag, len(value)]) + value


def encode(fields: dict[int, str | bytes]) -> str:
	"""{tag: value} → base64 TLV string. Strings are UTF-8 encoded; bytes go in as they are."""
	out = b""
	for tag in sorted(fields):
		value = fields[tag]
		out += _tlv(tag, value.encode() if isinstance(value, str) else value)
	return base64.b64encode(out).decode()


def decode(qr: str) -> dict[int, bytes]:
	"""base64 TLV string → {tag: raw bytes}."""
	data, out, i = base64.b64decode(qr), {}, 0
	while i < len(data):
		tag, length = data[i], data[i + 1]
		out[tag] = data[i + 2 : i + 2 + length]
		i += 2 + length
	return out


def build(
	seller_name: str,
	vat_number: str,
	timestamp: str,
	total_with_vat: str,
	vat_total: str,
	invoice_hash: str,
	signature: str,
	public_key: bytes,
	certificate_signature: bytes | None = None,
) -> str:
	"""The Phase 2 QR. Hash and signature go in as their base64 text; the key and CA signature as raw bytes."""
	fields = {
		1: seller_name,
		2: vat_number,
		3: timestamp,
		4: total_with_vat,
		5: vat_total,
		6: invoice_hash,
		7: signature,
		8: public_key,
	}
	if certificate_signature is not None:
		fields[9] = certificate_signature
	return encode(fields)
