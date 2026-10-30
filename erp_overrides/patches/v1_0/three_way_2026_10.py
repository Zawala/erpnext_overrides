# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Three-way match before a supplier is paid (erp_overrides.three_way):
Payment Entry → "Approved unmatched payment", which only Accounts Managers may tick
(permission level 1)."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, update_permission_property

from erp_overrides.three_way import OVERRIDE_FIELD


def execute():
	create_custom_fields({"Payment Entry": [dict(
		fieldname=OVERRIDE_FIELD, label="Approved unmatched payment", fieldtype="Check", permlevel=1,
		insert_after="references", allow_on_submit=0,
		description="Pay supplier bills that aren't matched to what was ordered and received. Accounts Managers only.",
	)]})
	for role, write in (("Accounts Manager", 1), ("Accounts User", 0)):
		add_permission("Payment Entry", role, 1)
		update_permission_property("Payment Entry", role, 1, "write", write)
