# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Salary Structure Assignment → Agreed net pay: the take-home pay agreed with the person, which
the HR app's Salaries page works the gross out from and later checks payslips against."""
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields({"Salary Structure Assignment": [dict(
		fieldname="agreed_net_pay", label="Agreed net pay", fieldtype="Currency", options="currency",
		insert_after="base", read_only=1, allow_on_submit=1,
		description="The take-home pay agreed with the employee; the base was worked out from it.",
	)]}, update=True)
