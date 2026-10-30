# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Who's off: the leave calendar for everyone in the company (/hrms-admin/calendar).

Desk's Leave Application calendar (HRMS `get_events`) shows only what the user may read.
Here every employee sees everyone's approved and pending leave, so anyone can tell who
is available. The leave type stays private: only HR, the person's approvers and the
person see it; everyone else sees "On leave".
"""
import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, nowdate

from erp_overrides.api.hr import get_team, is_approver, is_hr

MAX_DAYS = 62
STATUSES = ("Approved", "Open")


def my_employee(user=None):
	return frappe.db.get_value("Employee", {"user_id": user or frappe.session.user, "status": "Active"},
	                           ["name", "company", "department"], as_dict=True)


def can_view(user=None):
	return bool(is_hr(user) or is_approver(user) or my_employee(user))


def _require():
	if not can_view():
		frappe.throw(_("The leave calendar is for employees. Ask HR to link your user to your employee record."),
		             frappe.PermissionError)


def _company(me):
	return (me and me.company) or frappe.defaults.get_user_default("Company") \
		or frappe.db.get_single_value("Global Defaults", "default_company")


@frappe.whitelist()
def get_calendar(start: str, end: str, department: str | None = None):
	"""Leave, holidays and people between `start` and `end` (inclusive)."""
	_require()
	start, end = getdate(start), getdate(end)
	if end < start or date_diff(end, start) > MAX_DAYS:
		frappe.throw(_("Pick a range of up to {0} days.").format(MAX_DAYS))
	me = my_employee()
	company = _company(me)

	emp_filters = {"status": "Active", "company": company}
	if department:
		emp_filters["department"] = department
	people = frappe.get_all("Employee", filters=emp_filters,
	                        fields=["name", "employee_name", "department", "designation", "image"],
	                        order_by="employee_name asc")
	names = [p.name for p in people]

	leave = frappe.get_all(
		"Leave Application",
		filters={"employee": ["in", names or ["__none__"]], "status": ["in", STATUSES], "docstatus": ["<", 2],
		         "from_date": ["<=", end], "to_date": [">=", start]},
		fields=["name", "employee", "employee_name", "department", "leave_type", "from_date", "to_date",
		        "half_day", "half_day_date", "status", "total_leave_days"],
		order_by="from_date asc")
	team = None if is_hr() else set(get_team() or []) | ({me.name} if me else set())
	images = {p.name: p.image for p in people}
	for d in leave:
		d.pending = d.status == "Open"
		d.image = images.get(d.employee)
		if team is not None and d.employee not in team:
			d.leave_type = None
			d.name = None  # nothing to open
		d.pop("status")

	return dict(start=start, end=end, today=getdate(nowdate()), leave=leave, people=people,
	            holidays=_holidays(me, company, start, end),
	            departments=frappe.get_all("Department", filters={"company": company, "is_group": 0}, pluck="name",
	                                       order_by="name asc"))


def _holidays(me, company, start, end):
	from hrms.hr.utils import get_holidays_for_employee

	if me:
		rows = get_holidays_for_employee(me.name, start, end, raise_exception=False)
	else:
		holiday_list = frappe.get_cached_value("Company", company, "default_holiday_list")
		rows = frappe.get_all("Holiday", filters={"parent": holiday_list, "holiday_date": ["between", [start, end]]},
		                      fields=["holiday_date", "description", "weekly_off"]) if holiday_list else []
	return [dict(date=r.holiday_date, description=frappe.utils.strip_html(r.description or ""),
	             weekly_off=cint(r.get("weekly_off"))) for r in rows]


@frappe.whitelist()
def get_today():
	"""For Home: who is off today, who goes off later this week, who is back tomorrow."""
	_require()
	today = getdate(nowdate())
	data = get_calendar(str(today), str(add_days(today, 7)))
	off = [d for d in data["leave"] if getdate(d.from_date) <= today <= getdate(d.to_date)]
	later = [d for d in data["leave"] if getdate(d.from_date) > today]
	back = [d for d in off if getdate(d.to_date) == today]
	return dict(today=today, off=off, later=later, back_tomorrow=back,
	            people=len(data["people"]), available=len(data["people"]) - len({d.employee for d in off}))
