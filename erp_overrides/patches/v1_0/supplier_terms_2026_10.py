# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Starter payment terms, so the supplier upload (api.suppliers) has terms to name: the
upload requires them and a site may have none. Finance can rename, edit or add to them.
A template that already exists is left alone."""
import frappe

TERMS = {
	# template: credit days after the invoice date
	"Due on receipt": 0,
	"7 days": 7,
	"30 days": 30,
}


def execute():
	for name, days in TERMS.items():
		if frappe.db.exists("Payment Terms Template", name):
			continue
		if not frappe.db.exists("Payment Term", name):
			frappe.get_doc(dict(doctype="Payment Term", payment_term_name=name, invoice_portion=100,
			                    due_date_based_on="Day(s) after invoice date", credit_days=days)).insert(ignore_permissions=True)
		frappe.get_doc(dict(doctype="Payment Terms Template", template_name=name, terms=[dict(
			payment_term=name, invoice_portion=100, due_date_based_on="Day(s) after invoice date", credit_days=days)],
		)).insert(ignore_permissions=True)
		print(f"Payment Terms Template {name} created")
