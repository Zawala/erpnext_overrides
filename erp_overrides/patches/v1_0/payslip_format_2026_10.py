"""Payroll Settings → Payslip format: the layout employees download in /hrms and get by email
(erp_overrides.payslip). Starts on whatever Salary Slip's default print format is now."""
import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from erp_overrides.payslip import FIELD


def execute():
	create_custom_fields({"Payroll Settings": [dict(
		fieldname=FIELD, label="Payslip format", fieldtype="Link", options="Print Format",
		insert_after="email_salary_slip_to_employee",
		link_filters=json.dumps([["Print Format", "doc_type", "=", "Salary Slip"], ["Print Format", "disabled", "=", 0]]),
		description="What employees get when they download a payslip in the HR app or receive it by email. Empty means Standard.",
	)]})
	current = frappe.get_meta("Salary Slip").default_print_format
	if current and frappe.db.exists("Print Format", current):
		frappe.db.set_single_value("Payroll Settings", FIELD, current)
