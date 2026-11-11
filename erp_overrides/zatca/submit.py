# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Sales Invoice → ZATCA.

before_submit (inside the submit transaction):
	check the invoice, take the next ICV and the previous hash under a row lock, build and
	sign the XML, and record a Pending ZATCA Submission. If the submit rolls back, so does the
	counter, so the chain never has gaps.
on_submit:
	queue `send` to run after the commit.
send:
	clearance (standard) or reporting (simplified). Network or auth failures leave the
	submission Failed and `retry` resends the same signed XML. A rejection is final for that
	document: once the cause is fixed, `retry` signs a new document with a new ICV and UUID,
	and the rejected one stays in the chain (ZATCA records rejected hashes too).
"""

import base64
import json
import uuid

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from erp_overrides.zatca import client, crypto, document, mapping

SETTINGS = "ZATCA Settings"
DONE = ("Cleared", "Reported", "Accepted with warnings")


def settings_for(company):
	"""ZATCA Settings if they cover this company and are switched on, else None."""
	if not frappe.db.get_single_value(SETTINGS, "enabled"):
		return None
	s = frappe.get_cached_doc(SETTINGS)
	return s if s.company == company else None


# --- doc events ---------------------------------------------------------------------------------


def before_submit(doc, method=None):
	settings = settings_for(doc.company)
	if not settings:
		return
	if not settings.get_password("production_token", raise_exception=False):
		frappe.throw(_("ZATCA onboarding isn't done yet. Open ZATCA Settings and click Onboard."))
	problems = mapping.check(doc, settings)
	if problems:
		frappe.throw("<br>".join(problems), title=_("Not ready for ZATCA"))
	sub = _new_submission(doc, settings)
	doc.zatca_submission = sub.name
	doc.zatca_uuid = sub.uuid
	doc.zatca_status = sub.status
	doc.zatca_qr = sub.qr


def on_submit(doc, method=None):
	if doc.get("zatca_submission"):
		frappe.enqueue(send, queue="short", submission=doc.zatca_submission, enqueue_after_commit=True)


def before_cancel(doc, method=None):
	if doc.get("zatca_status") in DONE:
		frappe.throw(
			_("This invoice is already with ZATCA ({0}). Issue a credit note instead of cancelling it.").format(
				doc.zatca_status
			)
		)


# --- the chain ----------------------------------------------------------------------------------


def _next_in_chain() -> tuple[int, str]:
	"""Lock the settings' chain values for the rest of this transaction and return (next ICV, PIH)."""
	rows = frappe.db.sql(
		"""select field, value from `tabSingles`
		where doctype=%s and field in ('last_icv', 'last_hash') for update""",
		SETTINGS,
	)
	values = dict(rows)
	return cint(values.get("last_icv")) + 1, values.get("last_hash") or crypto.FIRST_PIH


def _new_submission(doc, settings):
	icv, pih = _next_in_chain()
	inv = mapping.to_dict(doc, settings, icv=icv, pih=pih, uuid=str(uuid.uuid4()))
	cert = crypto.certificate_from_token(settings.get_password("production_token"))
	signed = document.make(inv, settings.get_password("private_key"), cert)
	frappe.db.set_single_value(SETTINGS, {"last_icv": icv, "last_hash": signed["invoice_hash"]})
	return frappe.get_doc(
		dict(
			doctype="ZATCA Submission",
			sales_invoice=doc.name,
			company=doc.company,
			kind="Clearance" if inv["kind"] == "standard" else "Reporting",
			status="Pending",
			icv=icv,
			uuid=inv["uuid"],
			invoice_hash=signed["invoice_hash"],
			pih=pih,
			qr=signed["qr"],
			signed_xml=signed["xml"].decode(),
		)
	).insert(ignore_permissions=True)


# --- talking to ZATCA ---------------------------------------------------------------------------


def _client(settings) -> client.Client:
	return client.Client(
		settings.environment, settings.get_password("production_token"), settings.get_password("production_secret")
	)


def _qr_from_xml(xml: bytes) -> str | None:
	from lxml import etree

	node = etree.fromstring(xml).find(
		"cac:AdditionalDocumentReference[cbc:ID='QR']/cac:Attachment/cbc:EmbeddedDocumentBinaryObject", crypto.NS
	)
	return node.text if node is not None else None


def send(submission: str):
	"""Send one ZATCA Submission and record ZATCA's answer on it and on its invoice."""
	sub = frappe.get_doc("ZATCA Submission", submission)
	if sub.status in DONE or sub.status in ("Rejected", "Superseded"):
		return sub.status
	settings = frappe.get_cached_doc(SETTINGS)
	sub.attempts = cint(sub.attempts) + 1
	sub.last_attempt = now_datetime()
	invoice_update = {}
	try:
		api = _client(settings)
		post = api.clear if sub.kind == "Clearance" else api.report
		r = post(sub.signed_xml.encode(), sub.invoice_hash, sub.uuid)
	except Exception as e:  # network, DNS, timeouts: worth retrying as is
		sub.status = "Failed"
		sub.errors = f"{type(e).__name__}: {e}"
	else:
		sub.response = json.dumps(r.data, indent=1, ensure_ascii=False)
		sub.errors = "\n".join(r.messages("errorMessages")) or None
		sub.warnings = "\n".join(r.messages("warningMessages")) or None
		if r.ok:
			sub.status = "Accepted with warnings" if r.status_code == 202 else (
				"Cleared" if sub.kind == "Clearance" else "Reported"
			)
			if r.data.get("clearedInvoice"):
				cleared = base64.b64decode(r.data["clearedInvoice"])
				sub.cleared_xml = cleared.decode()
				# the stamped invoice carries ZATCA's own QR; that's the one to print
				invoice_update["zatca_qr"] = _qr_from_xml(cleared) or sub.qr
		elif r.status_code == 400:
			sub.status = "Rejected"
		else:  # 401 bad credentials, 429, 5xx: the document itself wasn't judged
			sub.status = "Failed"
			sub.errors = sub.errors or f"HTTP {r.status_code}: {json.dumps(r.data)[:500]}"
	sub.save(ignore_permissions=True)
	frappe.db.set_value(
		"Sales Invoice", sub.sales_invoice, {"zatca_status": sub.status, **invoice_update}, update_modified=False
	)
	frappe.db.commit()
	return sub.status


# --- desk actions -------------------------------------------------------------------------------


@frappe.whitelist()
def retry(invoice: str):
	"""Send the invoice's ZATCA document again (Failed/Pending), or re-sign it as a new document (Rejected)."""
	doc = frappe.get_doc("Sales Invoice", invoice)
	doc.check_permission("submit")
	sub = frappe.get_doc("ZATCA Submission", doc.zatca_submission)
	if sub.status == "Rejected":
		settings = settings_for(doc.company)
		problems = mapping.check(doc, settings)
		if problems:
			frappe.throw("<br>".join(problems), title=_("Not ready for ZATCA"))
		new = _new_submission(doc, settings)
		sub.db_set("status", "Superseded")
		frappe.db.set_value(
			"Sales Invoice",
			doc.name,
			{"zatca_submission": new.name, "zatca_uuid": new.uuid, "zatca_status": new.status, "zatca_qr": new.qr},
			update_modified=False,
		)
		frappe.db.commit()
		sub = new
	return send(sub.name)


@frappe.whitelist()
def qr_svg(invoice: str) -> str | None:
	"""The invoice's ZATCA QR as an SVG, for the form and print formats."""
	import io

	import pyqrcode

	doc = frappe.get_doc("Sales Invoice", invoice)
	doc.check_permission("read")
	if not doc.get("zatca_qr"):
		return None
	buf = io.BytesIO()
	pyqrcode.create(doc.zatca_qr, error="M").svg(buf, scale=3, omithw=False, xmldecl=False)
	return buf.getvalue().decode()
