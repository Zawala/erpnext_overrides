# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""/launcher becomes the landing page: the apps-screen default for a logged-in user who opens
/login, and (through the get_website_user_home_page hook) the page after login."""
import frappe


def execute():
	if not frappe.db.get_single_value("System Settings", "default_app"):
		frappe.db.set_single_value("System Settings", "default_app", "erp_overrides")
	# get_home_page() is cached per user
	frappe.cache.delete_key("home_page")
