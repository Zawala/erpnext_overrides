# Copyright (c) 2026, Kelvin Zawala and contributors
# See license.txt
"""Who's off (erp_overrides.api.leave_calendar)."""
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from erp_overrides.api import leave_calendar
from erp_overrides.tests.test_hr_api import company, leave_type, make_employee


def make_user(email, roles=()):
	if frappe.db.exists("User", email):
		return email
	doc = frappe.get_doc(dict(doctype="User", email=email, first_name="Cal", send_welcome_email=0))
	doc.append_roles("Employee", *roles)
	return doc.insert(ignore_permissions=True).name


def weekday(n=1):
	day = add_days(nowdate(), n)
	while getdate(day).weekday() >= 5:
		day = add_days(day, 1)
	return day


def apply(employee, from_date, to_date=None, status="Open", **kw):
	doc = frappe.get_doc(dict(doctype="Leave Application", employee=employee, leave_type=leave_type(),
	                          from_date=from_date, to_date=to_date or from_date, company=company(), status=status,
	                          leave_approver="Administrator", **kw))
	doc.flags.ignore_validate = True  # no allocation needed: only the calendar is under test
	return doc.insert(ignore_permissions=True)


def calendar_as(user, **kw):
	frappe.set_user(user)
	try:
		return leave_calendar.get_calendar(nowdate(), add_days(nowdate(), 30), **kw)
	finally:
		frappe.set_user("Administrator")


class TestLeaveCalendar(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.viewer = make_user("cal-viewer@example.com")
		if not frappe.db.exists("Employee", {"user_id": cls.viewer}):
			make_employee("Viewer", user_id=cls.viewer)
		cls.approver = make_user("cal-approver@example.com", ["Leave Approver"])
		cls.day = weekday(2)

	def setUp(self):
		# a fresh colleague per test, so one test's leave doesn't show in another's
		self.away = make_employee("Away", leave_approver=self.approver)

	def test_employee_sees_everyone_but_not_the_leave_type(self):
		apply(self.away.name, self.day)
		row = next(l for l in calendar_as(self.viewer)["leave"] if l.employee == self.away.name)
		self.assertIsNone(row.leave_type)
		self.assertIsNone(row.name)
		self.assertTrue(row.pending)

	def test_hr_and_the_approver_see_the_leave_type(self):
		apply(self.away.name, self.day)
		for user in ("Administrator", self.approver):
			row = next(l for l in calendar_as(user)["leave"] if l.employee == self.away.name)
			self.assertEqual(row.leave_type, leave_type())

	def test_rejected_and_cancelled_leave_is_left_out(self):
		apply(self.away.name, self.day, status="Rejected")
		apply(self.away.name, weekday(5), status="Cancelled")
		self.assertFalse([l for l in calendar_as(self.viewer)["leave"] if l.employee == self.away.name])

	def test_half_days_and_people(self):
		apply(self.away.name, self.day, half_day=1, half_day_date=self.day)
		data = calendar_as(self.viewer)
		row = next(l for l in data["leave"] if l.employee == self.away.name)
		self.assertEqual((row.half_day, str(row.half_day_date)), (1, str(self.day)))
		self.assertIn(self.away.name, [p.name for p in data["people"]])

	def test_holidays_are_included(self):
		data = calendar_as(self.viewer)
		self.assertIsInstance(data["holidays"], list)
		for h in data["holidays"]:
			self.assertTrue(h["date"] and "weekly_off" in h)

	def test_today(self):
		apply(self.away.name, nowdate(), status="Approved")
		frappe.set_user(self.viewer)
		try:
			out = leave_calendar.get_today()
		finally:
			frappe.set_user("Administrator")
		self.assertIn(self.away.name, [l.employee for l in out["off"]])
		self.assertEqual(out["available"], out["people"] - len({l.employee for l in out["off"]}))

	def test_a_user_with_no_employee_is_refused(self):
		stranger = make_user("cal-stranger@example.com")
		with self.assertRaises(frappe.PermissionError):
			calendar_as(stranger)

	def test_range_is_limited(self):
		with self.assertRaises(frappe.ValidationError):
			leave_calendar.get_calendar(nowdate(), add_days(nowdate(), 200))
