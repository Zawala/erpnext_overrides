# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, format_datetime, escape_html


def _fix_mojibake(s):
	"""Repair UTF-8 text that was mis-decoded (e.g. 'â€™' -> '’').

	Tries Latin-1 then Windows-1252 (the two common mangling encodings) and
	falls back to the original string when it isn't actually mojibake.
	"""
	for enc in ("latin-1", "cp1252"):
		try:
			return s.encode(enc).decode("utf-8")
		except (UnicodeEncodeError, UnicodeDecodeError):
			continue
	return s


def _format_eligibility_html(raw):
	"""Render ZPPA's flat eligibility text as grouped HTML sections/bullets.

	The source repeats this shape (the 'Type = file, Threshold = N' part is
	internal noise that we drop):

	    Section ]: <section name>
	       *Criterion[Type = file, Threshold = 100]: <requirement>
	"""
	if not raw:
		return ""

	sections = []  # list of [title, [criteria]]
	current = None
	for line in _fix_mojibake(raw).splitlines():
		line = line.strip()
		if not line:
			continue
		if line.startswith("Section"):
			title = line.split(":", 1)[1].strip() if ":" in line else line
			current = [title or "Requirements", []]
			sections.append(current)
		elif line.startswith("*Criterion"):
			crit = line.split(":", 1)[1].strip() if ":" in line else line
			if current is None:
				current = ["Requirements", []]
				sections.append(current)
			if crit:
				current[1].append(crit)
		elif current and current[1]:
			# wrapped continuation of the previous criterion line
			current[1][-1] += " " + line

	if not sections:
		return ""

	parts = ['<div style="margin-top:8px;">']
	for title, crits in sections:
		parts.append(
			f'<p style="margin:12px 0 4px; font-weight:bold; color:#2c3e50;">{escape_html(title)}</p>'
		)
		if crits:
			parts.append('<ul style="margin:0 0 8px; padding-left:20px;">')
			for c in crits:
				parts.append(f'<li style="margin-bottom:4px;">{escape_html(c)}</li>')
			parts.append("</ul>")
	parts.append("</div>")
	return "".join(parts)


class EprocureTender(Document):
	def after_insert(self):
		# Tenders are notified in bulk by erp_overrides.tender_digest, not one
		# email per insert. Sources that opt out of notifications (e.g. an
		# un-filtered portal pull) are marked as already notified so the digest
		# skips them.
		if self.flags.get("skip_notification"):
			self.db_set("notification_sent", 1, update_modified=False)

	def send_tender_notification(self):
		"""Email the full detail of this single tender.

		No longer fired automatically - the scheduled digest handles routine
		notification. Kept for sending one tender on demand.
		"""
		try:
			# Format dates for better readability
			egp_settings = frappe.get_single("Eprocure Settings")
			closing_date = format_datetime(self.submission_deadline) if self.submission_deadline else "Not specified"
			enquiry_deadline = format_datetime(self.enquiry_deadline) if self.enquiry_deadline else "Not specified"
			tender_open = format_datetime(self.tender_open_date) if self.tender_open_date else "Not specified"

			# Estimated value with currency, if available
			if self.value_amount:
				estimated_value = f"{self.value_amount:,.2f} {self.currency or ''}".strip()
			else:
				estimated_value = "Not specified"

			# Determine urgency based on closing date
			urgency = ""
			if self.submission_deadline:
				days_remaining = (get_datetime(self.submission_deadline) - get_datetime()).days
				if days_remaining <= 3:
					urgency = "<span style='color:red;font-weight:bold;'> (URGENT - Closing soon!)</span>"
				elif days_remaining <= 7:
					urgency = "<span style='color:orange;font-weight:bold;'> (Approaching deadline)</span>"

			# Optional contact rows - only render the ones that carry a value
			contact_rows = ""
			for label, value in (
				("Contact Email", self.contact_email),
				("Contact Phone", self.contact_phone),
				("Entity Website", f'<a href="{self.entity_website}">{self.entity_website}</a>' if self.entity_website else ""),
				("Entity Address", self.entity_address),
			):
				if value:
					contact_rows += f"""
				<tr>
					<td><strong>{label}</strong></td>
					<td>{value}</td>
				</tr>"""

			# Eligibility criteria - parse ZPPA's flat text into readable sections
			eligibility_block = ""
			eligibility_html = _format_eligibility_html(self.eligibility_criteria)
			if eligibility_html:
				eligibility_block = f"""
			<p class="header">Eligibility Criteria</p>
			<div style="background:#f9f9f9; padding:10px 16px; border:1px solid #ddd;">{eligibility_html}</div>
			"""

			# Key points - highlighted summary pinned to the top of the email
			key_points = f"""
			<div style="border-left:4px solid #2c3e50; background:#f4f7fb; padding:12px 16px; margin-bottom:16px;">
				<p style="margin:0 0 8px; font-size:16px; font-weight:bold; color:#2c3e50;">{self.title}</p>
				<ul style="margin:0; padding-left:18px;">
					<li><strong>Reference:</strong> {self.reference_id}</li>
					<li><strong>Procuring Entity:</strong> {self.procuring_entity or 'Not specified'}</li>
					<li><strong>Category:</strong> {self.category or 'Not specified'}</li>
					<li><strong>Estimated Value:</strong> {estimated_value}</li>
					<li><strong>Closing Date:</strong> {closing_date}{urgency}</li>
				</ul>
				<p style="margin:10px 0 0;"><a href="{self.tender_link}" style="background:#2c3e50; color:#fff; padding:8px 14px; text-decoration:none; border-radius:4px;">Access the tender</a></p>
			</div>
			"""

			# Build the tender details table
			tender_details = f"""
			<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
				<tr style="background-color: #f2f2f2;">
					<th style="width: 30%;">Field</th>
					<th>Details</th>
				</tr>
				<tr>
					<td><strong>Reference ID</strong></td>
					<td>{self.reference_id}</td>
				</tr>
				<tr>
					<td><strong>Title</strong></td>
					<td>{self.title}</td>
				</tr>
				<tr>
					<td><strong>Procuring Entity</strong></td>
					<td>{self.procuring_entity}</td>
				</tr>
				<tr>
					<td><strong>Category</strong></td>
					<td>{self.category or 'Not specified'}</td>
				</tr>
				<tr>
					<td><strong>Description</strong></td>
					<td>{self.description or 'Not specified'}</td>
				</tr>
				<tr>
					<td><strong>Estimated Value</strong></td>
					<td>{estimated_value}</td>
				</tr>
				<tr>
					<td><strong>Procedure</strong></td>
					<td>{self.procedure}</td>
				</tr>
				<tr>
					<td><strong>Award Criteria</strong></td>
					<td>{self.award_criteria or 'Not specified'}</td>
				</tr>
				<tr>
					<td><strong>Submission Method</strong></td>
					<td>{self.submission_method or 'Not specified'}</td>
				</tr>
				<tr>
					<td><strong>Status</strong></td>
					<td>{self.status}</td>
				</tr>
				<tr>
					<td><strong>Enquiry Deadline</strong></td>
					<td>{enquiry_deadline}</td>
				</tr>
				<tr>
					<td><strong>Tender Open Date</strong></td>
					<td>{tender_open}</td>
				</tr>
				<tr>
					<td><strong>Closing Date</strong></td>
					<td>{closing_date}{urgency}</td>
				</tr>{contact_rows}
			</table>
			"""
			
			# Compose the email message
			message = f"""
			<html>
			<head>
				<style>
					body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
					.header {{ color: #2c3e50; font-size: 18px; }}
					.footer {{ font-size: 12px; color: #7f8c8d; }}
				</style>
			</head>
			<body>
				<p>Dear Team,</p>

				<p class="header">New Tender Opportunity from Zambia Public Procurement Authority</p>

				{key_points}

				<p class="header" style="font-size:15px;">Full Details</p>
				{tender_details}
				{eligibility_block}

				<p><strong>Action Required:</strong> Please review this tender opportunity and take appropriate action.</p>
				<p>View full tender details: <a href="{self.tender_link}">Click here to access the tender</a></p>
				
				{f'<p>Download tender documents: <a href="{self.notice_pdf}">Click here for PDF</a></p>' if self.notice_pdf else ''}
				
				<p class="footer">This is an automated notification. Please do not reply to this email.</p>
			</body>
			</html>
			"""
			
			# Send the email
			if egp_settings.email:
				frappe.sendmail(
					recipients=[e.strip() for e in egp_settings.email.replace(";", ",").split(",") if e.strip()],
					subject=f"New Zambia Tender: {self.title[:70]}... (Ref: {self.reference_id})",
					message=message,
					header="Zambia Tender Opportunity Alert",
					delayed=False,
					now=True
				)
				print(f"Sent notification for tender {self.reference_id}")
			else:
				frappe.log_error(title="Eprocure Tender: No email configured", message=f"Tender {self.reference_id} - no email in Eprocure Settings")

		except Exception as e:
			frappe.log_error(title="Eprocure Tender: Email send failed", message=str(e))
			print(f"Error sending notification for tender {self.reference_id}: {str(e)}")
