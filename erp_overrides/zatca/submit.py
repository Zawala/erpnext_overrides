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

The outbox: the ZATCA Submission row is written in the same transaction as the invoice, so a
submitted invoice always has one. The queued job is only the fast path; `sweep` (every 5
minutes) sends anything the job never got to (Redis down, a worker killed) and retries Failed
sends on a backoff schedule. `check_overdue` (hourly) flags simplified invoices that are close
to ZATCA's 24-hour reporting deadline.
"""

import base64
import json
import uuid

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from erp_overrides.zatca import client, crypto, document, mapping

SETTINGS = "ZATCA Settings"
DONE = ("Cleared", "Reported", "Accepted with warnings")

# Failed sends are retried by the sweeper after 1, 5, 15, 60 minutes, then hourly, up to
# MAX_ATTEMPTS in all; after that a person has to look (the "Send to ZATCA again" button).
BACKOFF_MINUTES = (1, 5, 15, 60)
MAX_ATTEMPTS = 10
# A Pending submission this old was never picked up by its queued job.
STALE_PENDING_MINUTES = 3
SWEEP_BATCH = 50
# Simplified documents must be reported within 24 hours of issue; warn well before that.
REPORTING_WARN_HOURS = 20


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


def _lock(submission: str) -> bool:
	"""Row-lock the submission for the rest of this transaction. False if another sender holds it."""
	return bool(
		frappe.db.sql(
			"select name from `tabZATCA Submission` where name=%s for update skip locked", submission
		)
	)


def _schedule_retry(sub):
	"""After a Failed send: when the sweeper should try again, or never (then it's left for a person)."""
	attempts = cint(sub.attempts)
	sub.next_attempt = (
		add_to_date(now_datetime(), minutes=BACKOFF_MINUTES[min(attempts, len(BACKOFF_MINUTES)) - 1])
		if attempts < MAX_ATTEMPTS
		else None
	)


def send(submission: str):
	"""Send one ZATCA Submission and record ZATCA's answer on it and on its invoice.

	Safe to call from anywhere at any time (the queued job, the sweeper, the retry button):
	the row lock makes sure only one of them talks to ZATCA about a submission at once, and a
	submission that's already settled is left alone.
	"""
	frappe.db.commit()  # start a fresh transaction, so the lock is held only for this send
	if not _lock(submission):
		return "Busy"
	sub = frappe.get_doc("ZATCA Submission", submission)  # read after locking: it may just have changed
	if sub.status in DONE or sub.status in ("Rejected", "Superseded"):
		frappe.db.commit()
		return sub.status
	settings = frappe.get_cached_doc(SETTINGS)
	sub.attempts = cint(sub.attempts) + 1
	sub.last_attempt = now_datetime()
	invoice_update = {}
	notes = []
	xml = sub.signed_xml.encode()
	try:
		api = _client(settings)
		if sub.kind == "Clearance":
			r = api.clear(xml, sub.invoice_hash, sub.uuid)
			if r.status_code == client.CLEARANCE_OFF:
				# ZATCA has switched clearance off: standard documents are reported instead
				notes.append(_("Clearance is switched off at ZATCA, so this standard invoice was reported instead."))
				r = api.report(xml, sub.invoice_hash, sub.uuid)
		else:
			r = api.report(xml, sub.invoice_hash, sub.uuid)
	except Exception as e:  # network, DNS, timeouts: worth retrying as is
		sub.status = "Failed"
		sub.errors = f"{type(e).__name__}: {e}"
	else:
		sub.response = json.dumps(r.data, indent=1, ensure_ascii=False)
		sub.errors = "\n".join(r.messages("errorMessages")) or None
		warnings = r.messages("warningMessages")
		reported = "reportingStatus" in r.data or r.status_code == client.ALREADY_REPORTED
		if r.ok or r.status_code in (client.ALREADY_CLEARED, client.ALREADY_REPORTED):
			sub.status = "Accepted with warnings" if r.status_code == 202 else ("Reported" if reported else "Cleared")
			sub.errors = None
			if r.status_code == client.ALREADY_CLEARED:
				notes.append(_("ZATCA had already cleared this document (HTTP 208); its stamped copy is kept."))
			if r.status_code == client.ALREADY_REPORTED:
				notes.append(_("ZATCA had already reported this document (HTTP 409)."))
			if r.data.get("clearedInvoice"):
				cleared = base64.b64decode(r.data["clearedInvoice"])
				sub.cleared_xml = cleared.decode()
				# the stamped invoice carries ZATCA's own QR; that's the one to print
				invoice_update["zatca_qr"] = _qr_from_xml(cleared) or sub.qr
		elif r.status_code == client.REJECTED:
			sub.status = "Rejected"
		else:  # 401, 406, 429, 5xx: the document itself wasn't judged, so it can be sent again as is
			sub.status = "Failed"
			sub.errors = (
				_("ZATCA refused the credentials (HTTP 401). Renew the CSID in ZATCA Settings, then send again.")
				if r.status_code == client.UNAUTHORIZED
				else r.summary()
			)
		sub.warnings = "\n".join(notes + warnings) or None
	if sub.status == "Failed":
		_schedule_retry(sub)
	else:
		sub.next_attempt = None
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
	pyqrcode.create(doc.zatca_qr, error="M").svg(buf, scale=2, omithw=False, xmldecl=False)
	return buf.getvalue().decode()


# --- the outbox sweeper -------------------------------------------------------------------------


def due() -> list[str]:
	"""Submissions waiting to be sent: Pending ones their job never sent, and Failed ones due a retry."""
	now = now_datetime()
	return frappe.db.sql_list(
		"""select name from `tabZATCA Submission`
		where (status='Pending' and creation <= %(stale)s)
		   or (status='Failed' and next_attempt is not null and next_attempt <= %(now)s)
		order by icv limit %(limit)s""",
		dict(stale=add_to_date(now, minutes=-STALE_PENDING_MINUTES), now=now, limit=SWEEP_BATCH),
	)


def sweep():
	"""Scheduler, every 5 minutes: send whatever is due, oldest invoice first."""
	if not frappe.db.get_single_value(SETTINGS, "enabled"):
		return
	for name in due():
		try:
			send(name)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"ZATCA sweep: {name}")


def overdue() -> list[dict]:
	"""Simplified (reported) documents not yet accepted, issued more than REPORTING_WARN_HOURS ago."""
	return frappe.db.sql(
		"""select sub.name, sub.sales_invoice, sub.status, si.posting_date, si.posting_time
		from `tabZATCA Submission` sub join `tabSales Invoice` si on si.name = sub.sales_invoice
		where sub.kind='Reporting' and sub.status in ('Pending', 'Failed', 'Rejected')
		  and timestamp(si.posting_date, si.posting_time) <= %s
		order by sub.icv""",
		add_to_date(now_datetime(), hours=-REPORTING_WARN_HOURS),
		as_dict=True,
	)


def check_overdue():
	"""Scheduler, hourly: one Error Log entry listing simplified invoices near or past the 24-hour limit."""
	if not frappe.db.get_single_value(SETTINGS, "enabled"):
		return
	late = overdue()
	if late:
		frappe.log_error(
			title=f"ZATCA: {len(late)} simplified invoice(s) not reported within {REPORTING_WARN_HOURS} hours",
			message="\n".join(f"{r.sales_invoice} ({r.status}), issued {r.posting_date} {r.posting_time}" for r in late),
		)


@frappe.whitelist()
def backlog() -> dict:
	"""Counts for the ZATCA Settings page."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	counts = dict(
		frappe.db.sql(
			"""select status, count(*) from `tabZATCA Submission`
			where status in ('Pending', 'Failed', 'Rejected') group by status"""
		)
	)
	return dict(
		pending=counts.get("Pending", 0),
		failed=counts.get("Failed", 0),
		rejected=counts.get("Rejected", 0),
		gave_up=frappe.db.count("ZATCA Submission", {"status": "Failed", "next_attempt": ["is", "not set"]}),
		overdue=len(overdue()),
	)
