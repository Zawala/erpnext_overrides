# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Onboard the EGS unit (Technical Guideline §3): CSR → compliance CSID → compliance checks
→ production CSID. Run from the ZATCA Settings "Onboard" button or
`bench --site <site> execute erp_overrides.zatca.onboarding.run`.
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


@frappe.whitelist()
def run():
	frappe.only_for(("System Manager", "Accounts Manager"))
	s = frappe.get_doc(SETTINGS)
	log = []

	def say(line):
		log.append(f"{now_datetime():%H:%M:%S} {line}")

	def fail(msg):
		say(msg)
		s.onboarding_status = "Failed"
		s.onboarding_log = "\n".join(log)
		s.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.throw(msg, title=_("ZATCA onboarding"))

	for field in ("company", "vat_number", "crn", "street", "building_number", "district", "city", "postal_code", "otp"):
		if not s.get(field):
			frappe.throw(_("Fill in {0} first.").format(s.meta.get_label(field)))

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
	say(f"Generated a secp256k1 key and CSR for {s.environment}")

	api = client.Client(s.environment)
	r = api.compliance_csid(csr, s.otp)
	if not r.ok:
		fail(f"Compliance CSID refused (HTTP {r.status_code}): {r.data}")
	token, secret, request_id = r.data["binarySecurityToken"], r.data["secret"], r.data["requestID"]
	say(f"Compliance CSID issued (request {request_id})")

	cert = crypto.certificate_from_token(token)
	checker = client.Client(s.environment, token, secret)
	for kind, doc_type, doc_uuid, signed in _samples(s, cert, key):
		r = checker.compliance_check(signed["xml"], signed["invoice_hash"], doc_uuid)
		status = r.data.get("clearanceStatus") or r.data.get("reportingStatus")
		say(f"Compliance check {kind} {doc_type}: HTTP {r.status_code} {status} {r.validation.get('status')}")
		for m in r.messages("errorMessages") + r.messages("warningMessages"):
			say(f"    {m}")
		if not r.ok:
			fail(f"Compliance check failed for the {kind} {doc_type}; see the log.")

	r = checker.production_csid(request_id)
	if not r.ok:
		fail(f"Production CSID refused (HTTP {r.status_code}): {r.data}")
	say(f"Production CSID issued (request {r.data.get('requestID')})")

	s.private_key = key
	s.compliance_token, s.compliance_secret, s.compliance_request_id = token, secret, str(request_id)
	s.production_token, s.production_secret = r.data["binarySecurityToken"], r.data["secret"]
	# A new EGS unit starts a new chain.
	s.last_icv, s.last_hash = 0, crypto.FIRST_PIH
	s.onboarding_status = f"Onboarded on {now_datetime():%Y-%m-%d %H:%M} ({s.environment})"
	s.onboarding_log = "\n".join(log)
	s.save(ignore_permissions=True)
	frappe.db.commit()
	return s.onboarding_status
