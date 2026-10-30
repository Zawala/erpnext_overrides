# Copyright (c) 2026, Kelvin Zawala and contributors
# See license.txt
import frappe
from frappe.tests import IntegrationTestCase

from erp_overrides.www import launcher


def tiles(user):
	frappe.set_user(user)
	try:
		return [t["title"] for t in launcher.get_context(frappe._dict()).tiles]
	finally:
		frappe.set_user("Administrator")


def user(email, roles):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True)
	doc = frappe.get_doc(dict(doctype="User", email=email, first_name="Launcher", send_welcome_email=0, user_type="System User"))
	doc.append_roles(*roles)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestLauncher(IntegrationTestCase):
	def test_system_manager_sees_every_app_and_desk(self):
		self.assertEqual(tiles(user("launcher-sm@example.com", ["System Manager"])), ["Sales", "HR", "Accounts", "Admin", "Desk"])

	def test_tiles_follow_each_apps_own_check(self):
		# a sales user: the sales app and desk, not HR, Accounts or Admin
		self.assertEqual(tiles(user("launcher-sales@example.com", ["Sales User"])), ["Sales", "Desk"])
		# an accounts user also reads Sales Invoice, so the sales app opens for them too
		self.assertIn("Accounts", tiles(user("launcher-acc@example.com", ["Accounts User"])))
		self.assertNotIn("Admin", tiles("launcher-acc@example.com"))

	def test_employees_get_frappe_hr(self):
		email = user("launcher-emp@example.com", ["Employee"])
		emp = frappe.get_doc(dict(doctype="Employee", first_name="Launcher", last_name="Employee", gender="Male",
		                          date_of_birth="1990-01-01", date_of_joining="2024-01-01", user_id=email, passport_number="LAUNCHER-TEST",
		                          company=frappe.db.get_single_value("Global Defaults", "default_company")
		                          or frappe.get_all("Company", pluck="name", limit=1)[0])).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Employee", emp.name, force=True)
		self.assertIn("My HR", tiles(email))
		self.assertIn("Who's off", tiles(email))
		self.assertEqual(launcher.home_page(email), "launcher")
		emp.db_set("status", "Left")
		self.assertNotIn("My HR", tiles(email))
		self.assertNotIn("Who's off", tiles(email))

	def test_guest_goes_to_login(self):
		frappe.set_user("Guest")
		try:
			self.assertRaises(frappe.Redirect, launcher.get_context, frappe._dict())
		finally:
			frappe.set_user("Administrator")

	def test_everyone_with_an_app_lands_here(self):
		self.assertEqual(launcher.home_page(user("launcher-sm@example.com", ["System Manager"])), "launcher")
		self.assertEqual(launcher.home_page(user("launcher-sales@example.com", ["Sales User"])), "launcher")
		self.assertIsNone(launcher.home_page("Guest"))

	def test_website_user_keeps_frappes_home(self):
		email = "launcher-web@example.com"
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True)
		frappe.get_doc(dict(doctype="User", email=email, first_name="Web", send_welcome_email=0, user_type="Website User")).insert(ignore_permissions=True)
		self.assertIsNone(launcher.home_page(email))
