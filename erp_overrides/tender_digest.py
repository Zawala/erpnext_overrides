# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt

"""Consolidated tender notifications - one digest email per country.

Tenders used to email one-at-a-time from ``after_insert``, so a scrape run that
found 20 tenders produced 20 emails. Instead, a freshly inserted tender is left
with ``notification_sent = 0`` and the scheduled digest below collects every
pending tender into a single email per source:

    Zimbabwe -> Egp Tender      (recipients from Egp Settings)
    Zambia   -> Eprocure Tender (recipients from Eprocure Settings)

Within an email tenders are grouped by category, one table per category. Rows
are only marked as notified once the mail has actually been handed off, so a
failed run repeats rather than silently swallowing a batch.
"""

import frappe
from frappe.utils import escape_html, format_date, format_datetime, get_datetime, now_datetime


# Palette - kept in one place so both digests look like one product.
NAVY = "#0F2A5F"
SECTION_BG = "#003366"
TEXT = "#334155"
MUTED = "#64748B"
BORDER = "#DDDDDD"
HEAD_BG = "#F0F0F0"
LINK = "#0073AA"
FONT = "Arial, Helvetica, sans-serif"

URGENT = "#C0392B"
SOON = "#B9770E"


def _esc(value):
	"""HTML-escape a field value, rendering empty/None as an em dash."""
	if value is None:
		return "&mdash;"
	text = str(value).strip()
	return escape_html(text) if text else "&mdash;"


def _link(url, label):
	if not url:
		return "&mdash;"
	return (
		f'<a href="{escape_html(str(url))}" target="_blank" '
		f'style="color:{LINK};text-decoration:none;">{escape_html(str(label))}</a>'
	)


def _closing(deadline):
	"""Closing date cell, e.g. 'October 16, 2026 4:00 pm'."""
	if not deadline:
		return "&mdash;"
	return escape_html(format_datetime(deadline, "MMMM d, yyyy h:mm a"))


def _remaining(deadline):
	"""Time-left cell: '24d 2h', '5h 30m', 'Closing today', 'Closed'.

	Colour-coded on the same thresholds the old per-tender emails used: red
	inside 3 days, amber inside 7.
	"""
	if not deadline:
		return "&mdash;"
	delta = get_datetime(deadline) - now_datetime()
	seconds = delta.total_seconds()
	if seconds <= 0:
		return f'<span style="color:{URGENT};font-weight:bold;">Closed</span>'

	days = int(seconds // 86400)
	hours = int((seconds % 86400) // 3600)
	minutes = int((seconds % 3600) // 60)
	if days:
		text = f"{days}d&nbsp;{hours}h"
	elif hours:
		text = f"{hours}h&nbsp;{minutes}m"
	else:
		text = f"{minutes}m"

	if days < 1:
		return f'<span style="color:{URGENT};font-weight:bold;">{text}</span>'
	if days <= 3:
		return f'<span style="color:{URGENT};font-weight:bold;">{text}</span>'
	if days <= 7:
		return f'<span style="color:{SOON};font-weight:bold;">{text}</span>'
	return text


def _money(amount, currency):
	if not amount:
		return "&mdash;"
	return escape_html(f"{amount:,.2f} {currency or ''}".strip())


def _table(columns, rows):
	"""Render one category's tenders. ``rows`` hold pre-escaped cell HTML."""
	head = "".join(
		f'<th style="border:1px solid {BORDER};padding:8px;text-align:left;'
		f'background:{HEAD_BG};font-size:14px;font-family:{FONT};color:{TEXT};">'
		f"{col}</th>"
		for col in columns
	)
	body = ""
	for row in rows:
		cells = "".join(
			f'<td style="border:1px solid {BORDER};padding:8px;vertical-align:top;'
			f'font-size:14px;font-family:{FONT};color:{TEXT};">{cell}</td>'
			for cell in row
		)
		body += f"<tr>{cells}</tr>"
	return (
		'<table cellspacing="0" cellpadding="0" '
		'style="width:100%;border-collapse:collapse;margin:0 0 6px;">'
		f"<tr>{head}</tr>{body}</table>"
	)


def _section(title, columns, rows):
	return (
		f'<h3 style="color:#ffffff;background:{SECTION_BG};padding:10px;margin:18px 0 8px;'
		f'font-size:15px;font-family:{FONT};font-weight:bold;">{escape_html(title)}</h3>'
		+ _table(columns, rows)
	)


def _wrap(heading, subheading, intro, sections_html, total, footer_note):
	"""Outer email shell - table-based so Outlook renders it faithfully."""
	return f"""<html>
<body style="margin:0;padding:0;background:#EEF2F7;">
<table cellspacing="0" cellpadding="0" role="presentation" style="width:100%;background:#EEF2F7;">
<tr>
<td align="center" style="padding:24px;">
<table cellspacing="0" cellpadding="0" role="presentation" style="width:100%;max-width:900px;background:#ffffff;border-radius:12px;">
<tr>
<td style="background:{NAVY};padding:28px 28px 20px;border-radius:12px 12px 0 0;">
<h1 style="color:#ffffff;font-size:24px;font-weight:800;text-align:center;margin:0;line-height:1.3;font-family:{FONT};">{escape_html(heading)}</h1>
<p style="color:#E5F2FF;font-size:14px;text-align:center;margin:8px 0 0;font-family:{FONT};">{escape_html(subheading)}</p>
</td>
</tr>
<tr>
<td style="padding:18px 28px 8px;color:{TEXT};font-family:{FONT};line-height:1.55;">
<p style="margin:0 0 10px;font-size:14px;">Dear Team,</p>
<p style="margin:0 0 16px;font-size:14px;">{intro}</p>
{sections_html}
<p style="margin:18px 0 0;font-size:14px;"><strong>Action required:</strong> review the {total} tender{'' if total == 1 else 's'} above and flag the ones worth bidding on.</p>
</td>
</tr>
<tr>
<td style="background:{NAVY};padding:18px 28px 24px;border-radius:0 0 12px 12px;">
<p style="color:#CDE7FF;font-size:12px;margin:0;font-family:{FONT};">{escape_html(footer_note)}</p>
<p style="color:#CDE7FF;font-size:12px;margin:6px 0 0;font-family:{FONT};">This is an automated notification. Please do not reply to this email.</p>
</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>"""


def _group_by_category(tenders, category_field):
	"""Bucket tenders by category, preserving the query's ordering."""
	groups = {}
	for tender in tenders:
		label = (tender.get(category_field) or "").strip() or "Uncategorised"
		groups.setdefault(label, []).append(tender)
	return sorted(groups.items(), key=lambda kv: kv[0].lower())


def _recipients(settings_doctype):
	email = frappe.db.get_single_value(settings_doctype, "email")
	if not email:
		return []
	return [part.strip() for part in email.split(",") if part.strip()]


def _mark_notified(doctype, names):
	if not names:
		return
	frappe.db.sql(
		f"update `tab{doctype}` set notification_sent = 1 where name in %(names)s",
		{"names": tuple(names)},
	)
	frappe.db.commit()


def _deliver(doctype, settings_doctype, names, subject, message, header):
	recipients = _recipients(settings_doctype)
	if not recipients:
		frappe.log_error(
			title=f"{doctype}: no digest recipient configured",
			message=f"{len(names)} pending tender(s) not sent - no email in {settings_doctype}.",
		)
		return {"sent": 0, "reason": "no recipients"}

	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		header=header,
		now=True,
	)
	# Only after the mail is away, so a failed run retries the same batch.
	_mark_notified(doctype, names)
	return {"sent": len(names), "recipients": recipients}


@frappe.whitelist()
def send_zimbabwe_tender_digest():
	"""One email covering every Egp Tender not yet notified."""
	tenders = frappe.get_all(
		"Egp Tender",
		filters={"notification_sent": 0},
		fields=[
			"name", "id", "title", "entity", "link", "method", "scope",
			"categories", "publish_date", "closing_date", "status", "is_limited",
		],
		order_by="closing_date asc",
	)
	if not tenders:
		return {"sent": 0, "reason": "nothing pending"}

	columns = [
		"Tender&nbsp;ID", "Procuring&nbsp;Entity", "Tender&nbsp;Title", "Method",
		"Type", "Published", "Closing&nbsp;Date&nbsp;&amp;&nbsp;Time",
		"Remaining&nbsp;Time", "View",
	]
	sections = ""
	for category, group in _group_by_category(tenders, "categories"):
		rows = [
			[
				_esc(t.id),
				_esc(t.entity),
				_esc(t.title),
				_esc(t.method),
				"Limited" if t.is_limited else "Open",
				escape_html(format_date(t.publish_date)) if t.publish_date else "&mdash;",
				_closing(t.closing_date),
				_remaining(t.closing_date),
				_link(t.link, "View"),
			]
			for t in group
		]
		sections += _section(category, columns, rows)

	message = _wrap(
		heading="New Tender Opportunities - Zimbabwe",
		subheading=f"Digest - {format_datetime(now_datetime(), 'EEE, d MMM yyyy')}",
		intro=(
			f"Here are the <strong>{len(tenders)}</strong> new tender"
			f"{'' if len(tenders) == 1 else 's'} published on the Zimbabwe e-GP "
			"portal that match your selected categories, grouped by category below."
		),
		sections_html=sections,
		total=len(tenders),
		footer_note="Source: Zimbabwe Electronic Government Procurement (e-GP).",
	)

	return _deliver(
		doctype="Egp Tender",
		settings_doctype="Egp Settings",
		names=[t.name for t in tenders],
		subject=f"Zimbabwe: {len(tenders)} new tender opportunit{'y' if len(tenders) == 1 else 'ies'}",
		message=message,
		header="Zimbabwe Tender Opportunities",
	)


@frappe.whitelist()
def send_zambia_tender_digest():
	"""One email covering every Eprocure Tender not yet notified."""
	tenders = frappe.get_all(
		"Eprocure Tender",
		filters={"notification_sent": 0},
		fields=[
			"name", "reference_id", "title", "procuring_entity", "tender_link",
			"category", "procedure", "status", "value_amount", "currency",
			"submission_deadline", "notice_pdf",
		],
		order_by="submission_deadline asc",
	)
	if not tenders:
		return {"sent": 0, "reason": "nothing pending"}

	columns = [
		"Reference&nbsp;ID", "Procuring&nbsp;Entity", "Tender&nbsp;Title",
		"Procedure", "Estimated&nbsp;Value", "Closing&nbsp;Date&nbsp;&amp;&nbsp;Time",
		"Remaining&nbsp;Time", "View", "Documents",
	]
	sections = ""
	for category, group in _group_by_category(tenders, "category"):
		rows = [
			[
				_esc(t.reference_id),
				_esc(t.procuring_entity),
				_esc(t.title),
				_esc(t.procedure),
				_money(t.value_amount, t.currency),
				_closing(t.submission_deadline),
				_remaining(t.submission_deadline),
				_link(t.tender_link, "View"),
				_link(t.notice_pdf, "PDF") if t.notice_pdf else "&mdash;",
			]
			for t in group
		]
		sections += _section(category, columns, rows)

	message = _wrap(
		heading="New Tender Opportunities - Zambia",
		subheading=f"Digest - {format_datetime(now_datetime(), 'EEE, d MMM yyyy')}",
		intro=(
			f"Here are the <strong>{len(tenders)}</strong> new tender"
			f"{'' if len(tenders) == 1 else 's'} published by the Zambia Public "
			"Procurement Authority that match your selected categories, grouped by "
			"category below."
		),
		sections_html=sections,
		total=len(tenders),
		footer_note="Source: Zambia Public Procurement Authority (ZPPA).",
	)

	return _deliver(
		doctype="Eprocure Tender",
		settings_doctype="Eprocure Settings",
		names=[t.name for t in tenders],
		subject=f"Zambia: {len(tenders)} new tender opportunit{'y' if len(tenders) == 1 else 'ies'}",
		message=message,
		header="Zambia Tender Opportunities",
	)


@frappe.whitelist()
def send_tender_digests():
	"""Scheduler entry point: two emails, one per country.

	Each country is isolated so a failure on one side still delivers the other.
	"""
	results = {}
	for key, fn in (("zimbabwe", send_zimbabwe_tender_digest), ("zambia", send_zambia_tender_digest)):
		try:
			results[key] = fn()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title=f"Tender digest failed: {key}",
				message=frappe.get_traceback(),
			)
			results[key] = {"sent": 0, "reason": "error"}
	return results
