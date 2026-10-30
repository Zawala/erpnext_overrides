# Copyright (c) 2026, Kelvin Zawala and contributors
# See license.txt
import frappe
from frappe.tests import IntegrationTestCase

from erp_overrides.api import app_settings


def user_with(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(dict(doctype="User", email=email, first_name=email.split("@")[0], send_welcome_email=0,
		                    roles=[{"role": r} for r in roles])).insert(ignore_permissions=True)
	return email


def field(settings, fieldname):
	return next(f for s in settings["sections"] for f in s["fields"] if f["fieldname"] == fieldname)


class TestAppSettings(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_manager_saves_and_history_names_them(self):
		manager = user_with("hrtest-hrmanager@example.com", "HR Manager")
		frappe.set_user(manager)
		before = field(app_settings.get_settings("hr"), "standard_working_hours")["value"] or 0
		app_settings.save_settings("hr", [{"doctype": "HR Settings", "fieldname": "standard_working_hours", "value": before + 1}])
		self.assertEqual(frappe.db.get_single_value("HR Settings", "standard_working_hours"), before + 1)
		top = app_settings.get_history("hr")["entries"][0]
		self.assertEqual((top["user"], top["setting"], top["kind"]), (manager, "Standard Working Hours", "changed"))
		self.assertEqual((float(top["old"]) if top["old"] != "—" else 0, float(top["new"])), (before, before + 1))

	def test_other_roles_are_refused(self):
		for app, role in (("sales", "Sales User"), ("hr", "HR User"), ("accounts", "Accounts User")):
			frappe.set_user(user_with(f"hrtest-{role.replace(' ', '').lower()}@example.com", role))
			with self.assertRaises(frappe.PermissionError):
				app_settings.get_settings(app)
			with self.assertRaises(frappe.PermissionError):
				app_settings.save_settings(app, [])
			with self.assertRaises(frappe.PermissionError):
				app_settings.get_history(app)
			frappe.set_user("Administrator")

	def test_fields_off_the_page_are_refused(self):
		with self.assertRaises(frappe.PermissionError):
			app_settings.save_settings("hr", [{"doctype": "HR Settings", "fieldname": "retirement_age_secret", "value": 1}])
		with self.assertRaises(frappe.PermissionError):
			# a real Selling Settings field, but on the sales page — not HR's
			app_settings.save_settings("hr", [{"doctype": "Selling Settings", "fieldname": "dn_required", "value": "Yes"}])

	def test_table_row_edit_shows_in_history(self):
		if not frappe.db.exists("DocType", "App Accounts Settings"):
			self.skipTest("run erp_overrides.demo.seed first")
		boxes = field(app_settings.get_settings("accounts"), "petty_cash_boxes")["value"]
		if not boxes:
			self.skipTest("no petty cash box")
		boxes[0]["float_amount"] = (boxes[0]["float_amount"] or 0) + 123
		app_settings.save_settings("accounts", [{"doctype": "App Accounts Settings", "fieldname": "petty_cash_boxes",
		                                         "value": boxes}])
		saved = field(app_settings.get_settings("accounts"), "petty_cash_boxes")["value"]
		self.assertEqual([b["name"] for b in saved], [b["name"] for b in boxes])  # edited in place
		top = app_settings.get_history("accounts", section="Petty cash")["entries"][0]
		self.assertEqual((top["kind"], top["field"], top["row"]), ("row_changed", "Float", boxes[0]["account"]))

	def test_sales_limit_change_is_tracked(self):
		if not frappe.db.exists("DocType", "Custom Selling Settings"):
			self.skipTest("no Custom Selling Settings on this site")
		limit = field(app_settings.get_settings("sales"), "discount_limit")["value"] or 0
		app_settings.save_settings("sales", [{"doctype": "Custom Selling Settings", "fieldname": "discount_limit", "value": limit + 5}])
		top = app_settings.get_history("sales", section="Approval limits")["entries"][0]
		self.assertEqual((top["setting"], top["user"]), ("Discount Limit", "Administrator"))
