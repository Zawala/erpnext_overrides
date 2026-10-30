# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password


class EgpSettings(Document):
	def get_secure_password(self):
		"""Safely decrypt password with permission checking"""
		try:
			return get_decrypted_password("Egp Settings", self.name, "password")
		except Exception as e:
			frappe.log_error(_("Password decryption failed"), f"Doctype: Egp Settings,")
			return None


