# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""ZATCA FATOORA API client (Accept-Version V2). Pure module: requests only, no frappe.

Written from ZATCA's sandbox API reference (Swagger, Sandbox Release 2.1.0).

Environments (base URL suffix of https://gw-fatoora.zatca.gov.sa/e-invoicing/):
  developer-portal  public sandbox, no taxpayer account needed, OTP 123345
  simulation        a taxpayer's simulation environment (OTP from the Fatoora simulation portal)
  core              production

Status codes:
  200  accepted (cleared / reported / CSID issued)
  202  accepted with warnings
  208  clearance: this invoice hash was already submitted; the body still has clearedInvoice
  303  clearance: clearance is switched off, send the document to /invoices/reporting/single
  400  rejected: validationResults.errorMessages, or top-level "errors" on the CSID endpoints
  401  wrong or missing credentials
  406  missing or unsupported Accept-Version
  409  reporting: this invoice was already reported successfully
  428  renewal: NOT_COMPLIANT; the body carries a compliance CSID, so run the compliance checks with it
  5xx  ZATCA-side failure; worth retrying
"""

import base64
from dataclasses import dataclass

import requests

GATEWAY = "https://gw-fatoora.zatca.gov.sa/e-invoicing"
TIMEOUT = 60

ACCEPTED = (200, 202)
ALREADY_CLEARED = 208
CLEARANCE_OFF = 303
REJECTED = 400
UNAUTHORIZED = 401
ALREADY_REPORTED = 409
NOT_COMPLIANT = 428


@dataclass
class Response:
	status_code: int
	data: dict

	@property
	def ok(self) -> bool:
		return self.status_code in ACCEPTED

	@property
	def validation(self) -> dict:
		return self.data.get("validationResults") or {}

	def messages(self, kind: str = "errorMessages") -> list[str]:
		"""kind: errorMessages | warningMessages | infoMessages → "CODE: message" lines.

		Error messages also take in the shapes outside validationResults: the CSID endpoints'
		top-level "errors" list, a 500's {category, code, message}, and the bare {"message"}
		of 303 and 406 replies.
		"""
		items = self.validation.get(kind) or []
		if isinstance(items, dict):  # the compliance endpoint sometimes sends one object, not a list
			items = [items]
		if kind == "errorMessages":
			items = [*items, *(self.data.get("errors") or [])]
			if not items and self.data.get("message") and self.status_code not in ACCEPTED:
				items = [self.data]
		return [f"{m['code']}: {m.get('message')}" if m.get("code") else str(m.get("message")) for m in items]

	def summary(self) -> str:
		"""One readable line: the HTTP status and ZATCA's first few errors (or the raw body)."""
		errors = self.messages("errorMessages")
		detail = "; ".join(errors[:3]) if errors else (self.data.get("raw") or "")
		return f"HTTP {self.status_code}" + (f": {str(detail)[:500]}" if detail else "")


class Client:
	def __init__(self, environment: str = "developer-portal", username: str = "", secret: str = ""):
		self.base = f"{GATEWAY}/{environment}"
		self.auth = (username, secret) if username else None

	def _send(self, method: str, path: str, body: dict, **headers) -> Response:
		r = requests.request(
			method,
			self.base + path,
			json=body,
			auth=self.auth,
			headers={"Accept-Version": "V2", "Accept-Language": "en", "Accept": "application/json", **headers},
			timeout=TIMEOUT,
			allow_redirects=False,  # a 303 means "use reporting", not a redirect to follow
		)
		try:
			data = r.json()
		except ValueError:
			data = {"raw": r.text}
		return Response(r.status_code, data if isinstance(data, dict) else {"raw": data})

	# --- onboarding and renewal -----------------------------------------------------------------

	def compliance_csid(self, csr_b64: str, otp: str) -> Response:
		"""CSR + OTP → compliance CSID (binarySecurityToken, secret, requestID)."""
		return self._send("POST", "/compliance", {"csr": csr_b64}, OTP=otp)

	def compliance_check(self, signed_xml: bytes, invoice_hash: str, uuid: str) -> Response:
		"""Run one sample document through the compliance checks (compliance CSID auth)."""
		return self._send("POST", "/compliance/invoices", _invoice_body(signed_xml, invoice_hash, uuid))

	def production_csid(self, compliance_request_id: str) -> Response:
		"""Compliance request ID → production CSID (compliance CSID auth)."""
		return self._send("POST", "/production/csids", {"compliance_request_id": str(compliance_request_id)})

	def renew_csid(self, csr_b64: str, otp: str) -> Response:
		"""New CSR + OTP → a renewed production CSID (auth: the *current* production CSID).

		200 issues it. 428 NOT_COMPLIANT returns a compliance CSID instead: run the compliance
		checks with it, then call `production_csid` with its requestID, as in onboarding.
		"""
		return self._send("PATCH", "/production/csids", {"csr": csr_b64}, OTP=otp)

	# --- documents ----------------------------------------------------------------------------

	def clear(self, signed_xml: bytes, invoice_hash: str, uuid: str) -> Response:
		"""Standard (B2B) documents. A cleared response carries ZATCA's stamped XML in clearedInvoice."""
		return self._send(
			"POST", "/invoices/clearance/single", _invoice_body(signed_xml, invoice_hash, uuid),
			**{"Clearance-Status": "1"},
		)

	def report(self, signed_xml: bytes, invoice_hash: str, uuid: str) -> Response:
		"""Simplified (B2C) documents within 24 hours of issue, or standard ones while clearance is off."""
		return self._send(
			"POST", "/invoices/reporting/single", _invoice_body(signed_xml, invoice_hash, uuid),
			**{"Clearance-Status": "0"},
		)


def _invoice_body(signed_xml: bytes, invoice_hash: str, uuid: str) -> dict:
	return {"invoiceHash": invoice_hash, "uuid": uuid, "invoice": base64.b64encode(signed_xml).decode()}
