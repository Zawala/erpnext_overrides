# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Onboard or renew the EGS unit's CSID (Technical Guideline §3; sandbox API reference).

Onboarding: CSR → compliance CSID → compliance checks → production CSID. It starts a new
invoice chain.
Renewal: a new CSR → PATCH /production/csids, authenticated with the current production CSID.
If ZATCA answers 428 NOT_COMPLIANT, it hands back a compliance CSID: run the compliance checks
with it, then get the production CSID as in onboarding. The invoice chain carries on.

Run from the ZATCA Settings buttons, or:
	bench --site <site> execute erp_overrides.zatca.onboarding.run
	bench --site <site> execute erp_overrides.zatca.onboarding.renew
"""

import uuid

import frappe
from frappe import _
from frappe.utils import now_datetime

from erp_overrides.zatca import client, crypto, document, mapping
from erp_overrides.zatca.submit import SETTINGS

# Buyer on the standard (B2B) compliance samples. Fictional; the VAT number only has the right shape.
SAMPLE_BUYER = dict(
	name="Sample Buyer Co", vat="399999999800003", street="Prince Sultan St", building="5678",
	district="Al Rawdah", city="Jeddah", postal_code="23456",
)
DOCUMENTS = [(k, t) for k in ("standard", "simplified") for t in ("invoice", "credit", "debit")]
REQUIRED = ("company", "vat_number", "crn", "street", "building_number", "district", "city", "postal_code", "otp")


class _Log:
	"""Collects the steps and writes them to ZATCA Settings, including when a step fails."""

	def __init__(self, settings):
		self.s, self.lines = settings, []

	def __call__(self, line):
		self.lines.append(f"{now_datetime():%H:%M:%S} {line}")

	def fail(self, msg):
		self(msg)
		self.s.onboarding_status = "Failed"
		self.s.onboarding_log = "\n".join(self.lines)
		self.s.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.throw(msg, title=_("ZATCA onboarding"))


def _samples(settings, cert: str, key: str):
	"""One of each document type the EGS will issue, signed with the compliance certificate."""
	now = now_datetime()
	pih = crypto.FIRST_PIH
	for icv, (kind, doc_type) in enumerate(DOCUMENTS, 1):
		inv = dict(
			kind=kind, type=doc_type, id=f"COMPLIANCE-{icv}", uuid=str(uuid.uuid4()),
			issue_date=now.strftime("%Y-%m-%d"), issue_time=now.strftime("%H:%M:%S"),
			supply_date=now.strftime("%Y-%m-%d"), currency="SAR", icv=icv, pih=pih,
			billing_reference="COMPLIANCE-1", reason="Compliance check",
			seller=mapping.seller(settings), buyer=SAMPLE_BUYER if kind == "standard" else None,
			lines=[dict(name="Compliance sample", qty=1, rate=100, tax_category="S", tax_percent=15)],
		)
		signed = document.make(inv, key, cert)
		yield kind, doc_type, inv["uuid"], signed
		pih = signed["invoice_hash"]


def _settings_ready():
	frappe.only_for(("System Manager", "Accounts Manager"))
	s = frappe.get_doc(SETTINGS)
	for field in REQUIRED:
		if not s.get(field):
			frappe.throw(_("Fill in {0} first.").format(s.meta.get_label(field)))
	return s


def _new_key_and_csr(s) -> tuple[str, str]:
	key = crypto.new_private_key()
	csr = crypto.make_csr(
		key,
		common_name=f"EGS-{s.vat_number}",
		organization=frappe.get_cached_value("Company", s.company, "company_name"),
		organization_unit=s.city,
		vat_number=s.vat_number,
		serial=s.egs_serial,
		invoice_types="1100",  # standard and simplified
		address=f"{s.building_number} {s.street}, {s.district}, {s.city}",
		business_category=s.business_category or "Trading",
		environment=s.environment,
	)
	return key, csr


def _compliance_then_production(s, log, key: str, token: str, secret: str, request_id) -> client.Response:
	"""Run the six compliance checks with a compliance CSID, then exchange it for a production CSID."""
	cert = crypto.certificate_from_token(token)
	checker = client.Client(s.environment, token, secret)
	for kind, doc_type, doc_uuid, signed in _samples(s, cert, key):
		r = checker.compliance_check(signed["xml"], signed["invoice_hash"], doc_uuid)
		status = r.data.get("clearanceStatus") or r.data.get("reportingStatus")
		log(f"Compliance check {kind} {doc_type}: HTTP {r.status_code} {status} {r.validation.get('status')}")
		for m in r.messages("errorMessages") + r.messages("warningMessages"):
			log(f"    {m}")
		if not r.ok:
			log.fail(f"Compliance check failed for the {kind} {doc_type}; see the log.")
	r = checker.production_csid(request_id)
	if not r.ok:
		log.fail(f"Production CSID refused: {r.summary()}")
	return r


def _store(s, log, key: str, production: client.Response, *, what: str, compliance=None):
	cert = crypto.load_certificate(crypto.certificate_from_token(production.data["binarySecurityToken"]))
	s.private_key = key
	if compliance:
		s.compliance_token, s.compliance_secret, s.compliance_request_id = compliance
	s.production_token, s.production_secret = production.data["binarySecurityToken"], production.data["secret"]
	s.certificate_expiry = cert.not_valid_after_utc.date()
	s.onboarding_status = f"{what} on {now_datetime():%Y-%m-%d %H:%M} ({s.environment})"
	log(f"Production CSID issued (request {production.data.get('requestID')}), valid until {s.certificate_expiry}")
	s.onboarding_log = "\n".join(log.lines)
	s.save(ignore_permissions=True)
	frappe.db.commit()
	return s.onboarding_status


@frappe.whitelist()
def run():
	"""Onboard a new EGS unit. Starts a new invoice chain."""
	s = _settings_ready()
	log = _Log(s)
	key, csr = _new_key_and_csr(s)
	log(f"Generated a secp256k1 key and CSR for {s.environment}")

	r = client.Client(s.environment).compliance_csid(csr, s.otp)
	if not r.ok:
		log.fail(f"Compliance CSID refused: {r.summary()}")
	token, secret, request_id = r.data["binarySecurityToken"], r.data["secret"], r.data["requestID"]
	log(f"Compliance CSID issued (request {request_id})")

	production = _compliance_then_production(s, log, key, token, secret, request_id)
	# A new EGS unit starts a new chain.
	s.last_icv, s.last_hash = 0, crypto.FIRST_PIH
	return _store(s, log, key, production, what="Onboarded", compliance=(token, secret, str(request_id)))


@frappe.whitelist()
def renew():
	"""Renew the production CSID with a new key. The invoice chain carries on."""
	s = _settings_ready()
	current_token = s.get_password("production_token", raise_exception=False)
	if not current_token:
		frappe.throw(_("There's no production CSID to renew yet. Click Onboard first."))
	log = _Log(s)
	key, csr = _new_key_and_csr(s)
	log(f"Generated a new secp256k1 key and CSR for renewal ({s.environment})")

	r = client.Client(s.environment, current_token, s.get_password("production_secret")).renew_csid(csr, s.otp)
	if r.status_code == client.NOT_COMPLIANT:
		# ZATCA wants the compliance steps again, with the compliance CSID it just issued
		body = r.data.get("value") or r.data
		token, secret, request_id = body["binarySecurityToken"], body["secret"], body["requestID"]
		log(f"ZATCA answered NOT_COMPLIANT (428): running the compliance checks (request {request_id})")
		production = _compliance_then_production(s, log, key, token, secret, request_id)
		return _store(s, log, key, production, what="Renewed", compliance=(token, secret, str(request_id)))
	if not r.ok:
		log.fail(f"Renewal refused: {r.summary()}")
	return _store(s, log, key, r, what="Renewed")
