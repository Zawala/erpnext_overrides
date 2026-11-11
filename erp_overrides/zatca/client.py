# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""ZATCA FATOORA API client (Accept-Version V2). Pure module: requests only, no frappe.

Environments (base URL suffix of https://gw-fatoora.zatca.gov.sa/e-invoicing/):
  developer-portal  public sandbox, no taxpayer account needed, OTP 123345
  simulation        a taxpayer's simulation environment (OTP from the Fatoora simulation portal)
  core              production
"""

import base64
from dataclasses import dataclass

import requests

GATEWAY = "https://gw-fatoora.zatca.gov.sa/e-invoicing"
TIMEOUT = 60


@dataclass
class Response:
	status_code: int
	data: dict

	@property
	def ok(self) -> bool:
		# 200 accepted, 202 accepted with warnings
		return self.status_code in (200, 202)

	@property
	def validation(self) -> dict:
		return self.data.get("validationResults") or {}

	def messages(self, kind: str) -> list[str]:
		"""kind: errorMessages | warningMessages | infoMessages → "CODE: message" lines."""
		return [f"{m.get('code')}: {m.get('message')}" for m in self.validation.get(kind) or []]


class Client:
	def __init__(self, environment: str = "developer-portal", username: str = "", secret: str = ""):
		self.base = f"{GATEWAY}/{environment}"
		self.auth = (username, secret) if username else None

	def _post(self, path: str, body: dict, **headers) -> Response:
		r = requests.post(
			self.base + path,
			json=body,
			auth=self.auth,
			headers={"Accept-Version": "V2", "Accept-Language": "en", "Accept": "application/json", **headers},
			timeout=TIMEOUT,
		)
		try:
			data = r.json()
		except ValueError:
			data = {"raw": r.text}
		return Response(r.status_code, data if isinstance(data, dict) else {"raw": data})

	# --- onboarding ---------------------------------------------------------------------------

	def compliance_csid(self, csr_b64: str, otp: str) -> Response:
		"""CSR + OTP → compliance CSID (binarySecurityToken, secret, requestID)."""
		return self._post("/compliance", {"csr": csr_b64}, OTP=otp)

	def compliance_check(self, signed_xml: bytes, invoice_hash: str, uuid: str) -> Response:
		"""Run one sample document through the compliance checks (compliance CSID auth)."""
		return self._post("/compliance/invoices", _invoice_body(signed_xml, invoice_hash, uuid))

	def production_csid(self, compliance_request_id: str) -> Response:
		"""Compliance request ID → production CSID (compliance CSID auth)."""
		return self._post("/production/csids", {"compliance_request_id": str(compliance_request_id)})

	# --- documents ----------------------------------------------------------------------------

	def clear(self, signed_xml: bytes, invoice_hash: str, uuid: str) -> Response:
		"""Standard (B2B) documents. A cleared response carries ZATCA's stamped XML in clearedInvoice."""
		return self._post(
			"/invoices/clearance/single", _invoice_body(signed_xml, invoice_hash, uuid), **{"Clearance-Status": "1"}
		)

	def report(self, signed_xml: bytes, invoice_hash: str, uuid: str) -> Response:
		"""Simplified (B2C) documents, within 24 hours of issue."""
		return self._post(
			"/invoices/reporting/single", _invoice_body(signed_xml, invoice_hash, uuid), **{"Clearance-Status": "0"}
		)


def _invoice_body(signed_xml: bytes, invoice_hash: str, uuid: str) -> dict:
	return {"invoiceHash": invoice_hash, "uuid": uuid, "invoice": base64.b64encode(signed_xml).decode()}
