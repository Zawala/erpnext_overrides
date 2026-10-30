# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""HR staff must not be limited to their own employee record.

ERPNext's Employee "Create User Permission" (on by default) gives the linked user an
Employee User Permission for their own record that applies to every doctype. For
staff that's the point; for HR it hides every payroll run, payslip, leave and
employee page that names someone else (a 403 in the HR app). So anyone with an HR
role has those permissions lifted, and the box stays unticked on their record.
"""
import frappe

ROLES = ("HR Manager", "HR User")  # not System Manager: an IT admin isn't automatically HR


def hr_users():
	return set(frappe.get_all("Has Role", filters={"role": ["in", ROLES], "parenttype": "User"}, pluck="parent"))


def restricted_hr_users():
	"""{user: [employee, ...]} for HR users limited by an Employee User Permission."""
	hr = hr_users()
	out = {}
	for p in frappe.get_all("User Permission", filters={"allow": "Employee"}, fields=["user", "for_value"]):
		if p.user in hr:
			out.setdefault(p.user, []).append(p.for_value)
	return out


def lift(user):
	for name in frappe.get_all("User Permission", filters={"user": user, "allow": "Employee"}, pluck="name"):
		frappe.delete_doc("User Permission", name, ignore_permissions=True, force=True)
	for emp in frappe.get_all("Employee", filters={"user_id": user, "create_user_permission": 1}, pluck="name"):
		frappe.db.set_value("Employee", emp, "create_user_permission", 0, update_modified=False)


def keep_hr_unrestricted(doc, method=None):
	"""Employee validate: no self-restriction for an HR user's own record."""
	if doc.user_id and doc.create_user_permission and doc.user_id in hr_users():
		doc.create_user_permission = 0  # ERPNext's on_update then removes the permission


def lift_on_hr_role(doc, method=None):
	"""User on_update: given an HR role → lift any Employee restriction."""
	if {r.role for r in doc.get("roles")} & set(ROLES):
		lift(doc.name)
