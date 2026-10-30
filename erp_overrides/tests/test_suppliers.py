# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Supplier upload (erp_overrides.api.suppliers)."""
import base64

import frappe
from frappe.tests import IntegrationTestCase

from erp_overrides.api import suppliers


def csv_content(rows):
	text = "\n".join(",".join(f'"{v}"' for v in r) for r in rows)
	return base64.b64encode(text.encode()).decode()


class TestSupplierUpload(IntegrationTestCase):
	def setUp(self):
		self.terms = frappe.db.get_value("Payment Terms Template", {}, "name")
		if not self.terms:
			self.terms = frappe.get_doc(dict(doctype="Payment Terms Template", template_name="SUPTEST 30 days",
			                                 terms=[dict(invoice_portion=100, credit_days=30, due_date_based_on="Day(s) after invoice date")])
			                            ).insert(ignore_permissions=True).name
		name = frappe.db.get_value("Supplier", {"supplier_name": "SUPTEST Existing Ltd"})
		self.existing = frappe.get_doc("Supplier", name) if name else frappe.get_doc(dict(
			doctype="Supplier", supplier_name="SUPTEST Existing Ltd", supplier_group="All Supplier Groups")).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", self.existing.name, {"default_currency": None, "payment_terms": None})
		for n in frappe.get_all("Supplier", filters={"supplier_name": ["like", "SUPTEST New%"]}, pluck="name"):
			frappe.delete_doc("Supplier", n, force=True, ignore_permissions=True)

	def preview(self, rows):
		return suppliers.preview_import("s.csv", csv_content([list(suppliers.COLUMNS), *rows]))

	def test_preview_flags_missing_currency_and_terms(self):
		p = self.preview([["SUPTEST New A", "", "", "", "", "", "", "", "", ""],
		                  ["SUPTEST New B", "", "", "USD", "No Such Terms", "", "", "", "", ""]])
		a, b = p["rows"]
		self.assertEqual((a["status"], b["status"]), ("error", "error"))
		self.assertIn("Billing currency is required", a["errors"])
		self.assertIn("Payment terms is required", a["errors"])
		self.assertTrue(any("doesn't exist" in e for e in b["errors"]))

	def test_apply_updates_existing_and_creates_new(self):
		p = self.preview([["suptest existing ltd", "", "", "usd", self.terms, "", "", "", "", ""],
		                  ["SUPTEST New C", "", "Zimbabwe", "USD", self.terms, "", "c@example.com", "", "1 Test Road", "Harare"]])
		self.assertEqual([r["status"] for r in p["rows"]], ["changed", "new"])
		out = suppliers.apply_import(p["token"])
		self.assertEqual((out["created"], out["updated"], out["failed"]), (1, 1, 0))
		self.assertEqual(frappe.db.get_value("Supplier", self.existing.name, ["default_currency", "payment_terms"]), ("USD", self.terms))
		new = frappe.get_doc("Supplier", {"supplier_name": "SUPTEST New C"})
		self.assertEqual(new.default_currency, "USD")
		self.assertTrue(new.supplier_primary_address)
		self.assertEqual(self.preview([["SUPTEST New C", "", "Zimbabwe", "USD", self.terms, "", "", "", "", ""]])["rows"][0]["status"], "unchanged")
