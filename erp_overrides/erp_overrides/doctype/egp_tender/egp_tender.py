# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from frappe.utils import format_date, get_datetime, format_datetime




class EgpTender(Document):
	def after_insert(self):
		# Tenders are notified in bulk by erp_overrides.tender_digest, not one
		# email per insert. A fresh tender keeps notification_sent = 0 and is
		# picked up by the next digest run.
		if self.flags.get("skip_notification"):
			self.db_set("notification_sent", 1, update_modified=False)

	def send_tender_notification(self):
		"""Email the full detail of this single tender.

		No longer fired automatically - the scheduled digest handles routine
		notification. Kept for sending one tender on demand.
		"""
		# Format dates for better readability
		egp_settings=frappe.get_doc("Egp Settings")
		publish_date = format_date(self.publish_date) if self.publish_date else "Not specified"
		closing_date = format_datetime(self.closing_date) if self.closing_date else "Not specified"
		
		# Determine urgency based on closing date
		urgency = ""
		if self.closing_date:
			days_remaining = (get_datetime(self.closing_date) - get_datetime()).days
			if days_remaining <= 3:
				urgency = "<span style='color:red;font-weight:bold;'> (URGENT - Closing soon!)</span>"
			elif days_remaining <= 7:
				urgency = "<span style='color:orange;font-weight:bold;'> (Approaching deadline)</span>"
		
		# Build the tender details table
		tender_details = f"""
		<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
			<tr style="background-color: #f2f2f2;">
				<th style="width: 30%;">Field</th>
				<th>Details</th>
			</tr>
			<tr>
				<td><strong>Tender ID</strong></td>
				<td>{self.id}</td>
			</tr>
			<tr>
				<td><strong>Title</strong></td>
				<td>{self.title}</td>
			</tr>
			<tr>
				<td><strong>Procurement Method</strong></td>
				<td>{self.method}</td>
			</tr>
			<tr>
				<td><strong>Category</strong></td>
				<td>{self.categories}</td>
			</tr>
			<tr>
				<td><strong>Procuring Entity</strong></td>
				<td>{self.entity}</td>
			</tr>
			<tr>
				<td><strong>Scope</strong></td>
				<td>{self.scope}</td>
			</tr>
			<tr>
				<td><strong>Published Date</strong></td>
				<td>{publish_date}</td>
			</tr>
			<tr>
				<td><strong>Closing Date</strong></td>
				<td>{closing_date}{urgency}</td>
			</tr>
			<tr>
				<td><strong>Status</strong></td>
				<td>{self.status}</td>
			</tr>
			<tr>
				<td><strong>Tender Type</strong></td>
				<td>{"Limited" if self.is_limited else "Open"}</td>
			</tr>
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
			
			<p class="header">New Tender Opportunity Notification</p>
			
			{tender_details}
			
			<p><strong>Action Required:</strong> Please review this tender opportunity and take appropriate action.</p>
			<p>View full tender details: <a href="{self.link}">Click here to access the tender</a></p>
			
			
		</body>
		</html>
		"""
		
		# Send the email
		email = egp_settings.email
		if not email:
			frappe.log_error(title="EGP Tender: No email configured", message=f"Tender {self.id} - no email in Egp Settings")
			return
		try:
			recipients = [e.strip() for e in email.replace(";", ",").split(",") if e.strip()]
			frappe.sendmail(
				recipients=recipients,
				subject=f"New Tender Opportunity: {self.title[:50]}... (ID: {self.id})",
				message=message,
				header="Tender Opportunity Alert",
				now=True,
			)
		except Exception as e:
			frappe.log_error(title="EGP Tender: Email send failed", message=str(e))
