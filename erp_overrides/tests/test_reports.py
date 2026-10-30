# Copyright (c) 2026, Kelvin Zawala and contributors
# See license.txt
import frappe
from frappe.tests import IntegrationTestCase

from erp_overrides.api import accounts, reports, sales
from erp_overrides.tests.test_sales_api import seller


def names(groups):
	return [r["name"] for g in groups for r in g["reports"]]


class TestReportGroups(IntegrationTestCase):
	def test_curated_first_then_every_other_report_in_the_modules(self):
		groups = reports.report_groups({"Mine": [("Sales Register", "Every invoice")]}, ("Selling",), "Rest")
		self.assertEqual(groups[0], dict(group="Mine", reports=[dict(name="Sales Register", description="Every invoice",
		                                                               url="/desk/query-report/Sales%20Register")]))
		self.assertEqual(groups[-1]["group"], "Rest")
		selling = set(frappe.get_all("Report", filters={"module": "Selling", "disabled": 0}, pluck="name"))
		self.assertEqual(set(names(groups[1:])), selling)

	def test_missing_and_disabled_reports_are_left_out(self):
		frappe.db.set_value("Report", "Quotation Trends", "disabled", 1)
		self.addCleanup(frappe.db.set_value, "Report", "Quotation Trends", "disabled", 0)
		groups = reports.report_groups({"G": [("Quotation Trends", ""), ("No Such Report", ""), ("Sales Analytics", "")]})
		self.assertEqual(names(groups), ["Sales Analytics"])

	def test_report_builder_links_to_the_list_report_view(self):
		self.assertEqual(reports._url("Item-wise Price List Rate", "Report Builder", "Item Price"),
		                 "/desk/item-price/view/report/Item-wise%20Price%20List%20Rate")

	def test_only_reports_the_user_may_open(self):
		user = seller("reports-sales@example.com", ["Sales User"])
		frappe.set_user(user)
		try:
			listed = names(sales.get_reports())
		finally:
			frappe.set_user("Administrator")
		self.assertIn("Quotation Trends", listed)
		# the ledger is for accounts roles only
		self.assertNotIn("General Ledger", listed)


class TestAppReports(IntegrationTestCase):
	def test_accounts_lists_every_accounts_report(self):
		listed = set(names(accounts.get_reports()))
		every = set(frappe.get_all("Report", filters={"module": "Accounts", "disabled": 0}, pluck="name"))
		self.assertEqual(every - listed, set())
		self.assertEqual(accounts.get_reports()[0]["group"], "Financial statements")

	def test_sales_lists_every_selling_and_crm_report(self):
		listed = set(names(sales.get_reports()))
		every = set(frappe.get_all("Report", filters={"module": ["in", ["Selling", "CRM"]], "disabled": 0}, pluck="name"))
		self.assertEqual(every - listed, set())
