# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Backend for the /hrms-admin PWA (HR and approvers).

Follows how Frappe HR is set up: leave runs Holiday List → Period → Policy → Allocation →
Application → Ledger, payroll runs Structure → Assignment → Entry → Slips → Journal,
and almost every problem is a missing link (User ID, approver, allocation,
assignment). `get_health` lists those links; everything else wraps HRMS's own
functions so validation and side effects are exactly desk's.

HR roles see everyone. Leave/Expense Approvers see only their team: employees whose
leave/expense approver or Reports To is them, or in a department they approve for.
"""
import re
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, fmt_money, formatdate, get_first_day, get_last_day, getdate, nowdate

HR_ROLES = ("HR Manager", "HR User", "System Manager")
APPROVER_ROLES = ("Leave Approver", "Expense Approver")

HR_DOCTYPES = (
	"Employee", "Leave Application", "Leave Allocation", "Leave Period", "Leave Policy",
	"Leave Policy Assignment", "Expense Claim", "Attendance", "Attendance Request",
	"Salary Structure Assignment", "Payroll Entry", "Salary Slip", "Employee Promotion",
	"Employee Transfer", "Employee Separation",
)

# The payroll run's steps, in order. Nothing else can be run on a Payroll Entry from here.
PAYROLL_STEPS = ("get_employees", "create_slips", "submit_slips", "bank_entry")

# Employee fields a Promotion/Transfer may change, as in desk's "Add Employee Property"
# but curated to what the business actually moves.
PROPERTY_FIELDS = (
	"designation", "grade", "department", "branch", "employment_type", "reports_to",
	"leave_approver", "expense_approver", "holiday_list", "company",
)

DEPARTMENT_APPROVER_FIELDS = {"leave": "leave_approvers", "expense": "expense_approvers"}


# ── Who is asking ────────────────────────────────────────────────────────────

def is_hr(user=None):
	return bool(set(frappe.get_roles(user or frappe.session.user)) & set(HR_ROLES))


def is_approver(user=None):
	return bool(set(frappe.get_roles(user or frappe.session.user)) & set(APPROVER_ROLES))


def _require_hr():
	if not is_hr():
		frappe.throw(_("Only HR can do this."), frappe.PermissionError)


def _require_access():
	if not (is_hr() or is_approver()):
		frappe.throw(_("This app is for HR and approvers."), frappe.PermissionError)


def get_team(user=None):
	"""Employees a supervisor approves for. None means "everyone" (HR)."""
	user = user or frappe.session.user
	if is_hr(user):
		return None
	me = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
	emp = frappe.qb.DocType("Employee")
	cond = (emp.leave_approver == user) | (emp.expense_approver == user)
	if me:
		cond = cond | (emp.reports_to == me)
	team = set(frappe.qb.from_(emp).select(emp.name).where(cond & (emp.status == "Active")).run(pluck=True))

	departments = frappe.get_all(
		"Department Approver", filters={"approver": user, "parenttype": "Department"}, pluck="parent"
	)
	if departments:
		team.update(frappe.get_all("Employee", filters={"department": ["in", departments], "status": "Active"},
		                           pluck="name"))
	team.discard(me)
	return sorted(team)


def _scoped(filters, field="employee"):
	"""Restrict `filters` to the caller's team (no-op for HR)."""
	team = get_team()
	if team is not None:
		filters[field] = ["in", team or ["__none__"]]
	return filters


def _check_in_scope(employee):
	team = get_team()
	if team is not None and employee not in team:
		frappe.throw(_("{0} is not in your team.").format(employee), frappe.PermissionError)


def _company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


# ── Health check ─────────────────────────────────────────────────────────────

def _issue(group, check, message, fix, employee=None, employee_name=None, severity="error"):
	return dict(group=group, check=check, message=message, fix=fix, employee=employee,
	            employee_name=employee_name, severity=severity)


@frappe.whitelist()
def get_health():
	"""The missing links behind the usual HR support questions ("I can't apply", "no payslip", …)."""
	_require_hr()
	from hrms.api import get_department_approvers
	from hrms.utils.holiday_list import get_holiday_list_for_employee

	today = getdate()
	company = _company()
	issues = []

	# Company-wide setup, in the order it has to be set up
	if not frappe.db.exists("Leave Period", {"from_date": ["<=", today], "to_date": [">=", today], "is_active": 1}):
		issues.append(_issue("leave", "leave_period", "No active Leave Period covers today, so nothing can be allocated.",
		                     {"route": "/leave?tab=setup"}))
	if not frappe.db.exists("Leave Policy", {"docstatus": 1}):
		issues.append(_issue("leave", "leave_policy", "There is no submitted Leave Policy. Build one per grade (e.g. Casual 12, Sick 10).",
		                     {"route": "/leave?tab=setup"}))
	holiday_types = frappe.get_all("Leave Type", filters={"include_holiday": 1, "is_lwp": 0}, pluck="name")
	if holiday_types:
		issues.append(_issue(
			"leave", "include_holiday",
			_("{0}: public holidays inside a leave request are charged as leave (\"it charged me for the holiday\").").format(", ".join(holiday_types)),
			{"desk_url": "/app/leave-type"}, severity="warning"))
	if not frappe.db.exists("Income Tax Slab", {"docstatus": 1, "disabled": 0}):
		issues.append(_issue("payroll", "tax_slab", "No Income Tax Slab, so PAYE computes as zero for everyone.",
		                     {"route": "/pay-setup?tab=tax"}))
	for ss in frappe.get_all("Salary Structure", filters={"docstatus": 1, "is_active": "Yes"}, pluck="name"):
		lines = frappe.db.count("Salary Detail", {"parenttype": "Salary Structure", "parent": ss})
		if not lines:
			issues.append(_issue("payroll", "empty_structure", _("Salary Structure {0} has no earnings or deductions — slips come out at zero.").format(ss),
			                     {"route": "/pay-setup"}))
	if company and not frappe.get_cached_value("Company", company, "default_payroll_payable_account"):
		issues.append(_issue("payroll", "payable_account", _("{0} has no Default Payroll Payable Account.").format(company),
		                     {"desk_url": f"/app/company/{company}"}))
	if company:
		with_account = set(frappe.get_all("Expense Claim Account", filters={"company": company, "default_account": ["is", "set"]},
		                                  pluck="parent"))
		missing = [t for t in frappe.get_all("Expense Claim Type", pluck="name") if t not in with_account]
		if missing:
			issues.append(_issue("payroll", "claim_accounts",
			                     _("Expense Claim Types without an expense account for {0}: {1}. Claims of these types can't be approved.").format(company, ", ".join(missing)),
			                     {"desk_url": "/app/expense-claim-type"}))
		if not frappe.get_cached_value("Company", company, "default_expense_claim_payable_account"):
			issues.append(_issue("payroll", "claim_payable", _("{0} has no Default Expense Claim Payable Account.").format(company),
			                     {"desk_url": f"/app/company/{company}"}))
	if not cint(frappe.db.get_single_value("Payroll Settings", "encrypt_salary_slips_in_emails")):
		issues.append(_issue("payroll", "payslip_encryption", "Payslips are emailed without a password.",
		                     {"desk_url": "/app/payroll-settings"}, severity="warning"))

	from erp_overrides.hr_access import restricted_hr_users

	for user, emps in restricted_hr_users().items():
		issues.append(_issue("access", "hr_restricted",
		                     _("{0} has an HR role but is limited to employee {1} by a User Permission — the HR app refuses "
		                       "everyone else's records.").format(frappe.utils.get_fullname(user), ", ".join(emps)),
		                     {"desk_url": f"/app/user-permission?user={user}&allow=Employee"}))

	# Per employee
	employees = frappe.get_all(
		"Employee", filters={"status": "Active"},
		fields=["name", "employee_name", "user_id", "leave_approver", "expense_approver", "reports_to", "department", "company"],
		order_by="employee_name asc",
	)
	allocated = set(frappe.get_all(
		"Leave Allocation", filters={"docstatus": 1, "from_date": ["<=", today], "to_date": [">=", today]}, pluck="employee"))
	assigned = set(frappe.get_all(
		"Salary Structure Assignment", filters={"docstatus": 1, "from_date": ["<=", today], "base": [">", 0]}, pluck="employee"))
	draft_assignments = set(frappe.get_all("Salary Structure Assignment", filters={"docstatus": 0}, pluck="employee"))
	currency = company and frappe.get_cached_value("Company", company, "default_currency")
	latest_assignment = {
		a.employee: a for a in frappe.get_all(
			"Salary Structure Assignment", filters={"docstatus": 1, "from_date": ["<=", today]},
			fields=["employee", "salary_structure", "from_date", "agreed_net_pay"], order_by="from_date asc")
	}
	dept_approvers = {}
	managers = {e.reports_to for e in employees if e.reports_to}

	def dept_has(dept, kind):
		key = (dept, kind)
		if key not in dept_approvers:
			dept_approvers[key] = bool(dept and get_department_approvers(dept, DEPARTMENT_APPROVER_FIELDS[kind]))
		return dept_approvers[key]

	for e in employees:
		fix = {"route": f"/people/{e.name}"}
		add = lambda group, check, msg, severity="error", fix=fix: issues.append(  # noqa: E731
			_issue(group, check, msg, fix, e.name, e.employee_name, severity))
		if not e.user_id:
			add("access", "user_id", "No User ID — \"it won't let me log in\".")
		if not e.leave_approver and not dept_has(e.department, "leave"):
			add("access", "leave_approver", "No leave approver — \"I can't submit my leave\".")
		if not e.expense_approver and not dept_has(e.department, "expense"):
			add("access", "expense_approver", "No expense approver — claims wait for nobody.")
		# the top of the tree (people report to them, they report to nobody) is fine
		if not e.reports_to and e.name not in managers:
			add("access", "reports_to", "No Reports To — no supervisor in the approval chain or org chart.", "warning")
		if not get_holiday_list_for_employee(e.name, raise_exception=False, as_on=today):
			add("leave", "holiday_list", "No holiday list — leave days are counted with nothing to exclude.")
		if e.name not in allocated:
			add("leave", "allocation", "No leave allocation for this period — \"it says I have 0 days\".")
		if e.name not in assigned:
			msg = ("Salary Structure Assignment is still a draft — \"no payslip this month\"."
			       if e.name in draft_assignments else
			       "No submitted Salary Structure Assignment with a base — \"no payslip this month\".")
			add("payroll", "assignment", msg, fix={"route": f"/salaries?employee={e.name}"})
		elif drift := _drift(e.name, latest_assignment.get(e.name)):
			add("payroll", "net_drift",
			    _("Net pay drifted: agreed {0}, the {1} payslip paid {2}.").format(
			        fmt_money(latest_assignment[e.name].agreed_net_pay, currency=currency),
			        drift["start_date"].strftime("%B"), fmt_money(drift["net_pay"], currency=currency)),
			    "warning", fix={"route": f"/salaries?employee={e.name}"})

	counts = {}
	for i in issues:
		counts[i["group"]] = counts.get(i["group"], 0) + 1
	return dict(issues=issues, counts=counts, employees=len(employees))


# ── Dashboard ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard():
	_require_access()
	today = getdate()
	month_start, month_end = get_first_day(today), get_last_day(today)

	def on_leave(start, end):
		return len(set(frappe.get_list(
			"Leave Application",
			filters=_scoped({"docstatus": 1, "status": "Approved", "from_date": ["<=", end], "to_date": [">=", start]}),
			pluck="employee",
		)))

	holidays, next_holiday = [], None
	from hrms.utils.holiday_list import get_assigned_holiday_list

	company = _company()
	holiday_list = company and (get_assigned_holiday_list(company, today)
	                            or frappe.get_cached_value("Company", company, "default_holiday_list"))
	if holiday_list:
		holidays = frappe.get_all(
			"Holiday", filters={"parent": holiday_list, "holiday_date": ["between", [month_start, month_end]], "weekly_off": 0},
			fields=["holiday_date", "description"], order_by="holiday_date asc",
		)
		upcoming = frappe.get_all(
			"Holiday", filters={"parent": holiday_list, "holiday_date": [">=", today], "weekly_off": 0},
			fields=["holiday_date", "description"], order_by="holiday_date asc", limit=1,
		)
		next_holiday = upcoming[0] if upcoming else None

	out = dict(
		on_leave_today=on_leave(today, today),
		on_leave_month=on_leave(month_start, month_end),
		holidays=holidays,
		next_holiday=next_holiday,
		pending=dict(
			leave=len(_leave_inbox_names()),
			expense=len(_expense_inbox_names()),
			attendance=len(_attendance_inbox(names_only=True)),
		),
	)
	if is_hr():
		out["unpaid"] = _unpaid_total()
		out["payroll"] = _payroll_month_status(month_start, month_end)
	return out


def _unpaid_total():
	rows = frappe.get_list(
		"Expense Claim",
		filters={"docstatus": 1, "approval_status": "Approved", "status": "Unpaid"},
		fields=["grand_total", "total_amount_reimbursed", "total_advance_amount"],
	)
	return dict(count=len(rows), amount=sum(
		flt(r.grand_total) - flt(r.total_amount_reimbursed) - flt(r.total_advance_amount) for r in rows))


def _payroll_month_status(start, end):
	entry = frappe.get_list(
		"Payroll Entry",
		filters={"docstatus": ["<", 2], "start_date": ["<=", end], "end_date": [">=", start]},
		fields=["name"], order_by="creation desc", limit=1,
	)
	if not entry:
		return dict(state="none", label="Not started")
	return dict(name=entry[0].name, **_payroll_state(frappe.get_doc("Payroll Entry", entry[0].name)))


# ── Leave ────────────────────────────────────────────────────────────────────

def _leave_inbox_names():
	filters = {"docstatus": 0, "status": "Open"}
	if not is_hr():
		team = get_team()
		return frappe.get_list(
			"Leave Application", filters=filters,
			or_filters={"leave_approver": frappe.session.user, "employee": ["in", team or ["__none__"]]},
			pluck="name",
		)
	return frappe.get_list("Leave Application", filters=filters, pluck="name")


@frappe.whitelist()
def get_leave_inbox():
	_require_access()
	names = _leave_inbox_names()
	if not names:
		return []
	rows = frappe.get_list(
		"Leave Application", filters={"name": ["in", names]},
		fields=["name", "employee", "employee_name", "department", "leave_type", "from_date", "to_date", "half_day",
		        "total_leave_days", "leave_balance", "description", "leave_approver", "posting_date", "modified"],
		order_by="from_date asc",
	)
	unpaid = set(frappe.get_all("Leave Type", filters={"is_lwp": 1}, pluck="name"))
	for r in rows:
		r.is_lwp = r.leave_type in unpaid
		r.balance_after = flt(r.leave_balance) - flt(r.total_leave_days)
		r.overlaps = frappe.get_all(
			"Leave Application",
			filters={"department": r.department, "employee": ["!=", r.employee], "docstatus": ["<", 2],
			         "status": ["in", ["Open", "Approved"]], "from_date": ["<=", r.to_date], "to_date": [">=", r.from_date]},
			fields=["employee_name", "from_date", "to_date", "status"],
		) if r.department else []
	return rows


@frappe.whitelist(methods=["POST"])
def decide_leave(name: str, status: str, comment: str | None = None):
	"""Approve or reject, then submit — HRMS only lets Approved/Rejected through."""
	_require_access()
	if status not in ("Approved", "Rejected"):
		frappe.throw(_("A leave application can only be Approved or Rejected."))
	doc = frappe.get_doc("Leave Application", name)
	if doc.docstatus != 0 or doc.status != "Open":
		frappe.throw(_("{0} has already been decided ({1}).").format(name, doc.status))
	if not is_hr() and doc.leave_approver != frappe.session.user:
		_check_in_scope(doc.employee)
	doc.status = status
	doc.save()
	doc.submit()
	if comment:
		doc.add_comment("Comment", comment)
	return dict(name=doc.name, status=doc.status)


@frappe.whitelist()
def get_balances(department: str | None = None, employee: str | None = None):
	"""One row per person, every leave type across — the Leave Balance Summary."""
	_require_access()
	from hrms.hr.doctype.leave_application.leave_application import get_leave_details

	filters = _scoped({"status": "Active"}, "name")
	if department:
		filters["department"] = department
	if employee:
		filters["name"] = employee
	employees = frappe.get_all("Employee", filters=filters, fields=["name", "employee_name", "department"],
	                           order_by="employee_name asc")
	today = nowdate()
	types, rows = [], []
	for e in employees:
		try:
			alloc = get_leave_details(e.name, today).get("leave_allocation", {})
		except frappe.PermissionError:
			continue
		for t in alloc:
			if t not in types:
				types.append(t)
		rows.append(dict(employee=e.name, employee_name=e.employee_name, department=e.department, balances=alloc))
	return dict(types=sorted(types), rows=rows)


@frappe.whitelist()
def get_leave_setup():
	_require_hr()
	today = getdate()
	periods = frappe.get_all("Leave Period", fields=["name", "from_date", "to_date", "is_active", "company"],
	                         order_by="from_date desc")
	policies = frappe.get_all("Leave Policy", filters={"docstatus": ["<", 2]}, fields=["name", "title", "docstatus"],
	                          order_by="creation desc")
	for p in policies:
		p.details = frappe.get_all("Leave Policy Detail", filters={"parent": p.name},
		                           fields=["leave_type", "annual_allocation"], order_by="idx")
	leave_types = frappe.get_all(
		"Leave Type",
		fields=["name", "max_leaves_allowed", "max_continuous_days_allowed", "include_holiday", "is_carry_forward",
		        "maximum_carry_forwarded_leaves", "expire_carry_forwarded_leaves_after_days", "is_earned_leave",
		        "earned_leave_frequency", "allocate_on_day", "allow_encashment", "allow_negative", "is_lwp", "is_compensatory"],
		order_by="name asc",
	)
	holiday_lists = frappe.get_all("Holiday List", fields=["name", "from_date", "to_date", "total_holidays", "weekly_off"],
	                               order_by="to_date desc")
	active_period = next((p for p in periods if p.is_active and getdate(p.from_date) <= today <= getdate(p.to_date)), None)
	allocations = frappe.db.count("Leave Allocation", {"docstatus": 1, "from_date": ["<=", today], "to_date": [">=", today]})
	applications = frappe.db.count("Leave Application", {"docstatus": 1})
	steps = [
		dict(key="holiday_list", label="Holiday List", hint="which days are not working days",
		     done=any(h.total_holidays for h in holiday_lists)),
		dict(key="leave_period", label="Leave Period", hint="the year leave is counted in", done=bool(active_period)),
		dict(key="leave_policy", label="Leave Policy", hint="how many days per type",
		     done=any(p.docstatus == 1 for p in policies)),
		dict(key="allocation", label="Leave Allocation", hint="days put in each balance", done=allocations > 0,
		     count=allocations),
		dict(key="application", label="Leave Application", hint="the request against the balance",
		     done=applications > 0, count=applications),
		dict(key="ledger", label="Leave Ledger", hint="every movement, automatically",
		     done=allocations > 0, desk_url="/app/query-report/Leave Ledger"),
	]
	return dict(periods=periods, policies=policies, leave_types=leave_types, holiday_lists=holiday_lists,
	            active_period=active_period and active_period.name, steps=steps)


@frappe.whitelist(methods=["POST"])
def create_leave_policy(title: str, allocations: dict | str):
	"""Insert and submit a Leave Policy from {leave_type: days}."""
	_require_hr()
	allocations = frappe.parse_json(allocations) if isinstance(allocations, str) else allocations
	rows = [{"leave_type": t, "annual_allocation": flt(d)} for t, d in allocations.items() if flt(d) > 0]
	if not rows:
		frappe.throw(_("Give at least one leave type a number of days."))
	doc = frappe.get_doc(dict(doctype="Leave Policy", title=title, leave_policy_details=rows)).insert()
	doc.submit()
	return doc.name


@frappe.whitelist()
def get_policy_candidates(leave_period: str):
	"""Active employees and whether they already have a policy for this period."""
	_require_hr()
	period = frappe.get_doc("Leave Period", leave_period)
	existing = {
		r.employee: r.leave_policy for r in frappe.get_all(
			"Leave Policy Assignment",
			filters={"docstatus": 1, "effective_from": ["<=", period.to_date], "effective_to": [">=", period.from_date]},
			fields=["employee", "leave_policy"])
	}
	employees = frappe.get_all("Employee", filters={"status": "Active", "company": period.company},
	                           fields=["name", "employee_name", "department", "grade", "designation"],
	                           order_by="employee_name asc")
	for e in employees:
		e.current_policy = existing.get(e.name)
	return employees


@frappe.whitelist(methods=["POST"])
def assign_policy(leave_policy: str, leave_period: str, employees: list | str, carry_forward: int = 0):
	"""Leave Policy Assignment for many people; HRMS creates the allocations on submit."""
	_require_hr()
	from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
		create_assignment_for_multiple_employees,
	)

	employees = frappe.parse_json(employees) if isinstance(employees, str) else employees
	period = frappe.get_doc("Leave Period", leave_period)
	already = set(frappe.get_all(
		"Leave Policy Assignment",
		filters={"docstatus": 1, "employee": ["in", employees or ["__none__"]],
		         "effective_from": ["<=", period.to_date], "effective_to": [">=", period.from_date]},
		pluck="employee"))
	todo = [e for e in employees if e not in already]
	created = []
	if todo:
		created = create_assignment_for_multiple_employees(todo, {
			"assignment_based_on": "Leave Period",
			"leave_policy": leave_policy,
			"leave_period": leave_period,
			"effective_from": period.from_date,
			"effective_to": period.to_date,
			"carry_forward": cint(carry_forward),
		})
	submitted = frappe.get_all("Leave Policy Assignment", filters={"name": ["in", created or ["__none__"]], "docstatus": 1},
	                           pluck="name")
	return dict(created=len(submitted), failed=len(created) - len(submitted), skipped=sorted(already))


# ── Expenses ─────────────────────────────────────────────────────────────────

def _expense_inbox_names():
	filters = {"docstatus": 0, "approval_status": "Draft"}
	if not is_hr():
		filters["expense_approver"] = frappe.session.user
	return frappe.get_list("Expense Claim", filters=filters, pluck="name")


@frappe.whitelist()
def get_expense_inbox():
	_require_access()
	names = _expense_inbox_names()
	if not names:
		return []
	rows = frappe.get_list(
		"Expense Claim", filters={"name": ["in", names]},
		fields=["name", "employee", "employee_name", "department", "posting_date", "currency", "total_claimed_amount",
		        "total_sanctioned_amount", "expense_approver", "remark", "modified"],
		order_by="posting_date asc",
	)
	for r in rows:
		r.expenses = frappe.get_all(
			"Expense Claim Detail", filters={"parent": r.name, "parenttype": "Expense Claim"},
			fields=["name", "expense_date", "expense_type", "description", "amount", "sanctioned_amount"], order_by="idx")
		r.attachments = frappe.get_all(
			"File", filters={"attached_to_doctype": "Expense Claim", "attached_to_name": r.name},
			fields=["file_name", "file_url", "is_private"])
	return rows


@frappe.whitelist(methods=["POST"])
def decide_expense(name: str, status: str, sanctioned: dict | str | None = None, comment: str | None = None):
	"""Set the sanctioned amount line by line (the approver can reduce, not raise), then submit."""
	_require_access()
	if status not in ("Approved", "Rejected"):
		frappe.throw(_("An expense claim can only be Approved or Rejected."))
	sanctioned = (frappe.parse_json(sanctioned) if isinstance(sanctioned, str) else sanctioned) or {}
	doc = frappe.get_doc("Expense Claim", name)
	if doc.docstatus != 0 or doc.approval_status != "Draft":
		frappe.throw(_("{0} has already been decided ({1}).").format(name, doc.approval_status))
	if not is_hr() and doc.expense_approver != frappe.session.user:
		frappe.throw(_("You are not the expense approver for {0}.").format(name), frappe.PermissionError)
	# desk's form fills these from the company on load; a claim saved elsewhere may lack them
	doc.cost_center = doc.cost_center or frappe.get_cached_value("Company", doc.company, "cost_center")
	for row in doc.expenses:
		row.cost_center = row.cost_center or doc.cost_center
		if status == "Rejected":
			row.sanctioned_amount = 0
		elif row.name in sanctioned:
			amount = flt(sanctioned[row.name])
			if amount < 0 or amount > flt(row.amount):
				frappe.throw(_("Row {0}: sanctioned amount must be between 0 and the claimed {1}.").format(row.idx, row.amount))
			row.sanctioned_amount = amount
		elif not flt(row.sanctioned_amount):
			row.sanctioned_amount = row.amount
	doc.approval_status = status
	doc.save()
	doc.submit()
	if comment:
		doc.add_comment("Comment", comment)
	return dict(name=doc.name, status=doc.status, total_sanctioned_amount=doc.total_sanctioned_amount)


@frappe.whitelist()
def get_unpaid_claims():
	_require_hr()
	rows = frappe.get_list(
		"Expense Claim",
		filters={"docstatus": 1, "approval_status": "Approved", "status": "Unpaid"},
		fields=["name", "employee", "employee_name", "posting_date", "currency", "grand_total", "total_sanctioned_amount",
		        "total_amount_reimbursed", "total_advance_amount"],
		order_by="posting_date asc",
	)
	for r in rows:
		r.outstanding = flt(r.grand_total) - flt(r.total_amount_reimbursed) - flt(r.total_advance_amount)
	return rows


# ── Attendance ───────────────────────────────────────────────────────────────

DECLINED = "Declined: "


def _attendance_inbox(names_only=False):
	rows = frappe.get_list(
		"Attendance Request", filters=_scoped({"docstatus": 0}),
		fields=["name", "employee", "employee_name", "department", "from_date", "to_date", "half_day", "half_day_date",
		        "reason", "explanation", "include_holidays", "modified"],
		order_by="from_date asc",
	)
	if not rows:
		return rows
	# A declined request stays a draft with the employee; it comes back once they change it.
	declined = {}
	for c in frappe.get_all(
		"Comment",
		filters={"reference_doctype": "Attendance Request", "reference_name": ["in", [r.name for r in rows]],
		         "comment_type": "Comment", "content": ["like", f"{DECLINED}%"]},
		fields=["reference_name", "creation"],
	):
		declined[c.reference_name] = max(declined.get(c.reference_name, c.creation), c.creation)
	rows = [r for r in rows if not (r.name in declined and declined[r.name] >= r.modified)]
	return [r.name for r in rows] if names_only else rows


@frappe.whitelist()
def get_attendance_inbox():
	_require_access()
	return _attendance_inbox()


@frappe.whitelist(methods=["POST"])
def decide_attendance_request(name: str, approve: int, comment: str | None = None):
	"""Approve = submit (HRMS marks the attendance). The doctype has no reject, so
	declining leaves a comment, hands it back to the employee and hides it until changed."""
	_require_access()
	doc = frappe.get_doc("Attendance Request", name)
	_check_in_scope(doc.employee)
	if doc.docstatus != 0:
		frappe.throw(_("{0} has already been decided.").format(name))
	if cint(approve):
		doc.submit()
		if comment:
			doc.add_comment("Comment", comment)
		return dict(name=name, status="Approved")
	if not comment:
		frappe.throw(_("Say why you are declining, so the employee can fix it."))
	doc.add_comment("Comment", DECLINED + comment)
	user = frappe.db.get_value("Employee", doc.employee, "user_id")
	if user:
		from frappe.desk.form.assign_to import add as assign

		try:
			assign({"assign_to": [user], "doctype": "Attendance Request", "name": name,
			        "description": DECLINED + comment})
		except frappe.DuplicateToDoError:
			pass
	return dict(name=name, status="Declined")


@frappe.whitelist()
def get_unmarked(date: str, department: str | None = None, branch: str | None = None):
	_require_hr()
	from hrms.hr.doctype.employee_attendance_tool.employee_attendance_tool import get_employees

	return get_employees(date=date, department=department, branch=branch, company=_company())


@frappe.whitelist(methods=["POST"])
def mark_attendance(date: str, status: str, employees: list | str, late_entry: int = 0, early_exit: int = 0,
                    leave_type: str | None = None):
	_require_hr()
	from hrms.hr.doctype.employee_attendance_tool.employee_attendance_tool import mark_employee_attendance

	if status not in ("Present", "Absent", "Half Day", "On Leave", "Work From Home"):
		frappe.throw(_("Unknown attendance status {0}").format(status))
	employees = frappe.parse_json(employees) if isinstance(employees, str) else employees
	if not employees:
		frappe.throw(_("Pick at least one employee."))
	mark_employee_attendance(employees, status, date, leave_type=leave_type, company=_company(),
	                         late_entry=cint(late_entry), early_exit=cint(early_exit))
	return len(employees)


# ── Payroll ──────────────────────────────────────────────────────────────────

def _payroll_state(doc):
	"""Where a Payroll Entry is in the run, in plain words."""
	if doc.docstatus == 2:
		return dict(state="cancelled", label="Cancelled")
	if doc.status in ("Queued", "Failed"):
		return dict(state=doc.status.lower(), label=doc.status, error=doc.error_message)
	if doc.docstatus == 0:
		return dict(state="employees" if doc.employees else "draft",
		            label=f"{len(doc.employees)} employees, slips not created" if doc.employees else "Draft — get employees")
	if not doc.salary_slips_created:
		return dict(state="employees", label="Submitted — slips not created")
	if not doc.salary_slips_submitted:
		return dict(state="slips", label="Draft slips — review, then submit")
	bank = _bank_entries(doc.name)
	if not bank:
		return dict(state="submitted", label="Slips submitted — make the bank entry")
	return dict(state="paid" if all(b.docstatus == 1 for b in bank) else "bank_draft",
	            label="Paid" if all(b.docstatus == 1 for b in bank) else "Bank entry drafted — finance to submit",
	            bank_entries=[b.name for b in bank])


def _bank_entries(payroll_entry):
	jea = frappe.qb.DocType("Journal Entry Account")
	je = frappe.qb.DocType("Journal Entry")
	return (
		frappe.qb.from_(je).join(jea).on(jea.parent == je.name)
		.select(je.name, je.docstatus)
		.where((jea.reference_type == "Payroll Entry") & (jea.reference_name == payroll_entry)
		       & (je.voucher_type == "Bank Entry") & (je.docstatus < 2))
		.distinct()
	).run(as_dict=True)


@frappe.whitelist()
def get_payroll_overview():
	_require_hr()
	from hrms.payroll.doctype.payroll_entry.payroll_entry import get_start_end_dates

	company = _company()
	dates = get_start_end_dates("Monthly", nowdate(), company)
	entries = frappe.get_list(
		"Payroll Entry", filters={"docstatus": ["<", 2]},
		fields=["name", "posting_date", "start_date", "end_date", "number_of_employees", "docstatus", "status"],
		order_by="start_date desc", limit=12,
	)
	for e in entries:
		e.update(_payroll_state(frappe.get_doc("Payroll Entry", e.name)))
	return dict(
		company=company,
		currency=frappe.get_cached_value("Company", company, "default_currency"),
		start_date=dates.start_date,
		end_date=dates.end_date,
		payroll_payable_account=frappe.get_cached_value("Company", company, "default_payroll_payable_account"),
		entries=entries,
	)


@frappe.whitelist()
def get_payroll_readiness(start_date: str, end_date: str):
	"""Who will get a slip, and who won't ("no payslip", "my net is zero")."""
	_require_hr()
	company = _company()
	employees = frappe.get_all(
		"Employee",
		filters={"company": company, "status": "Active", "date_of_joining": ["<=", end_date]},
		fields=["name", "employee_name", "department", "date_of_joining"], order_by="employee_name asc",
	)
	ssa = frappe.qb.DocType("Salary Structure Assignment")
	assignments = {}
	for a in (
		frappe.qb.from_(ssa)
		.select(ssa.name, ssa.employee, ssa.salary_structure, ssa.base, ssa.from_date, ssa.docstatus,
		        ssa.payroll_payable_account)
		.where((ssa.docstatus < 2) & (ssa.from_date <= end_date) & (ssa.company == company))
		.orderby(ssa.docstatus).orderby(ssa.from_date)
	).run(as_dict=True):
		assignments[a.employee] = a  # submitted, latest from_date wins
	empty = {
		s for s in frappe.get_all("Salary Structure", filters={"docstatus": 1}, pluck="name")
		if not frappe.db.count("Salary Detail", {"parenttype": "Salary Structure", "parent": s})
	}
	payable = frappe.get_cached_value("Company", company, "default_payroll_payable_account")
	rows = []
	for e in employees:
		a = assignments.get(e.name)
		problem = None
		if not a:
			problem = "No Salary Structure Assignment — no slip will be made"
		elif a.docstatus == 0:
			problem = "Assignment is a draft — no slip will be made"
		elif not flt(a.base):
			problem = "Base is 0 — net pay will be zero"
		elif a.salary_structure in empty:
			problem = "Structure has no components — net pay will be zero"
		elif starts := _starts_after(e.name, start_date, e.date_of_joining):
			problem = f"Salary starts {formatdate(starts)}, after this run starts — no slip will be made"
		elif a.payroll_payable_account and payable and a.payroll_payable_account != payable:
			problem = f"Assignment posts to {a.payroll_payable_account}, the run to {payable} — no slip will be made"
		rows.append(dict(employee=e.name, employee_name=e.employee_name, department=e.department,
		                 assignment=a and a.name, salary_structure=a and a.salary_structure,
		                 base=a and a.base, problem=problem))
	return dict(rows=rows, ready=sum(1 for r in rows if not r["problem"]), total=len(rows))


def _tax_component(structure):
	from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import get_tax_component

	return get_tax_component(structure)


# ── Salaries: enter take-home pay, get the base ──────────────────────────────
# HR agrees net pay with people; HRMS needs a base. The base is found by pricing
# trial payslips with HRMS's own calculation (formulas, pension, PAYE from the tax
# slab), so the real slip nets what was agreed.

@contextmanager
def _trial_assignment(ssa):
	"""Make every Salary Slip computed inside this block use `ssa` (an unsaved
	Salary Structure Assignment) instead of looking one up. Patched on the class
	because HRMS copies the slip while computing tax."""
	from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

	# HRMS 16.13 also loads the assignment document through _get_ssa_doc; earlier
	# releases (the test site) read only what set_salary_structure_assignment sets
	has_doc_getter = hasattr(SalarySlip, "_get_ssa_doc")
	original_set = SalarySlip.set_salary_structure_assignment
	original_get = SalarySlip._get_ssa_doc if has_doc_getter else None

	def set_assignment(slip):
		slip._salary_structure_assignment = frappe._dict(ssa.as_dict())

	SalarySlip.set_salary_structure_assignment = set_assignment
	if has_doc_getter:
		SalarySlip._get_ssa_doc = lambda slip: ssa
	try:
		yield
	finally:
		SalarySlip.set_salary_structure_assignment = original_set
		if has_doc_getter:
			SalarySlip._get_ssa_doc = original_get


def _preview_slip(employee, structure, base, from_date, income_tax_slab=None):
	"""A full month's payslip for `employee` on `structure` at `base`, nothing saved."""
	company = _company()
	start = get_first_day(from_date)
	end = get_last_day(from_date)
	ssa = frappe.get_doc(dict(
		doctype="Salary Structure Assignment", name="__preview__", docstatus=1, employee=employee,
		salary_structure=structure, company=company, from_date=getdate(from_date), base=flt(base, 2),
		currency=frappe.get_cached_value("Salary Structure", structure, "currency"), income_tax_slab=income_tax_slab,
	))
	slip = frappe.new_doc("Salary Slip")
	slip.update(dict(employee=employee, salary_structure=structure, company=company, currency=ssa.currency,
	                 payroll_frequency="Monthly", posting_date=end, start_date=start, end_date=end))
	with _trial_assignment(ssa):
		slip.process_salary_structure(for_preview=1)
	return slip


@frappe.whitelist()
def preview_payslip(employee: str, month: str | None = None, print_format: str | None = None,
                    letterhead: str | None = None, no_letterhead: int = 0):
	"""This month's payslip for `employee` from their salary assignment, printed as
	employees get it — before any payroll run. A full month, nothing saved."""
	_require_hr()
	from frappe.www.printview import get_html_and_style
	from frappe.utils.jinja_globals import bundled_asset

	from erp_overrides.api.sales import _print_format
	from erp_overrides.payslip import employee_format

	month = getdate(month or nowdate())
	ssa = frappe.get_all("Salary Structure Assignment",
	                     filters={"employee": employee, "docstatus": 1, "from_date": ["<=", get_last_day(month)]},
	                     fields=["salary_structure", "base", "income_tax_slab"], order_by="from_date desc", limit=1)
	if not ssa or not flt(ssa[0].base):
		frappe.throw(_("{0} has no salary assignment with a base yet, so there is no payslip to show.")
		             .format(frappe.db.get_value("Employee", employee, "employee_name") or employee))
	try:
		slip = _preview_slip(employee, ssa[0].salary_structure, ssa[0].base, get_first_day(month), ssa[0].income_tax_slab)
	except frappe.ValidationError as e:
		frappe.clear_messages()
		reason = re.sub(r"<[^>]+>", "", str(e)).replace("__preview__", "").strip(" :")
		frappe.throw(_("The payroll run would stop on this payslip too: {0}. Fix it on the Salaries page.").format(reason))
	slip.name = _("Trial payslip")
	# a real slip fetches these on save: name, department, designation, bank...
	emp = frappe.get_cached_doc("Employee", employee)
	for df in slip.meta.fields:
		if (df.fetch_from or "").startswith("employee.") and not slip.get(df.fieldname):
			slip.set(df.fieldname, emp.get(df.fetch_from.split(".", 1)[1]))
	slip.add_leave_balances()  # a real slip fills them in validate (when Payroll Settings shows them)
	out = get_html_and_style(slip.as_dict(), print_format=_print_format("Salary Slip", print_format or employee_format()),
	                         no_letterhead=cint(no_letterhead), letterhead=letterhead or None)
	out["css"] = [bundled_asset("print.bundle.css")]
	return out


def _priced(slip):
	lines = [dict(component=d.salary_component, amount=flt(d.amount),
	              kind="earning" if d.parentfield == "earnings" else ("employer" if d.do_not_include_in_total else "deduction"))
	         for d in slip.earnings + slip.deductions if flt(d.amount)]
	return dict(base=flt(slip._salary_structure_assignment.base, 2), gross=flt(slip.gross_pay), net=flt(slip.net_pay),
	            deductions=flt(slip.total_deduction), lines=lines)


def _solve_base(employee, structure, from_date, income_tax_slab, target):
	"""The base whose payslip nets `target`. Net rises with base, piecewise
	linearly (one slope per tax band), so false-position steps between a base that
	nets too little and one that nets too much land in a few tries; halving keeps it
	moving if a step stalls."""
	target = flt(target, 2)
	if target <= 0:
		frappe.throw(_("Net pay must be more than 0."))
	net = lambda base: flt(_preview_slip(employee, structure, base, from_date, income_tax_slab).net_pay)  # noqa: E731
	lo, hi = target, target * 2
	f_lo, f_hi = net(lo) - target, net(hi) - target
	while f_hi < 0:
		if hi > target * 64:
			frappe.throw(_("No base on {0} pays a net of {1}.").format(structure, target))
		lo, f_lo = hi, f_hi
		hi *= 2
		f_hi = net(hi) - target
	best = (abs(f_lo), lo) if abs(f_lo) < abs(f_hi) else (abs(f_hi), hi)
	for step in range(40):
		if best[0] < 0.005 or hi - lo <= 0.01:
			break
		base = flt(lo + (hi - lo) * -f_lo / (f_hi - f_lo), 2) if step % 3 != 2 else flt((lo + hi) / 2, 2)
		if not lo < base < hi:
			base = flt((lo + hi) / 2, 2)
		diff = net(base) - target
		best = min(best, (abs(diff), base))
		if diff < 0:
			lo, f_lo = base, diff
		else:
			hi, f_hi = base, diff
	return best[1]


def _salary_inputs(structure, from_date, income_tax_slab):
	company = _company()
	ss = frappe.db.get_value("Salary Structure", structure, ["company", "docstatus"], as_dict=True)
	if not ss or ss.docstatus != 1 or ss.company != company:
		frappe.throw(_("Pick a submitted salary structure of {0}.").format(company))
	tax = _tax_component(structure)
	if tax and not income_tax_slab:
		frappe.throw(_("{0} deducts {1}, so pick an Income Tax Slab.").format(structure, tax))
	period = frappe.db.get_value("Payroll Period", {"company": company, "start_date": ["<=", get_first_day(from_date)],
	                                                "end_date": [">=", get_last_day(from_date)]}, ["start_date", "end_date"])
	if tax and not period:
		frappe.throw(_("No Payroll Period covers {0}, so PAYE can't be worked out.").format(getdate(from_date).strftime("%B %Y")))


@frappe.whitelist()
def get_structure_setup():
	"""What the Salaries page needs: structures, tax slabs, the payable account."""
	_require_hr()
	company = _company()
	structures = frappe.get_all(
		"Salary Structure", filters={"docstatus": 1, "is_active": "Yes", "company": company},
		fields=["name", "currency"], order_by="creation desc")
	for s in structures:
		s.lines = frappe.db.count("Salary Detail", {"parenttype": "Salary Structure", "parent": s.name})
		s.tax_component = _tax_component(s.name)
	return dict(
		structures=structures,
		tax_slabs=frappe.get_all("Income Tax Slab", filters={"docstatus": 1, "disabled": 0},
		                         fields=["name", "currency", "effective_from"], order_by="effective_from desc"),
		payroll_payable_account=frappe.get_cached_value("Company", company, "default_payroll_payable_account"),
	)


def _drift(employee, assignment):
	"""The latest full-month slip under this assignment, if it netted something other than agreed."""
	if not assignment or not flt(assignment.agreed_net_pay):
		return None
	slip = frappe.get_all(
		"Salary Slip", filters={"employee": employee, "docstatus": 1, "salary_structure": assignment.salary_structure,
		                        "start_date": [">=", assignment.from_date]},
		fields=["name", "net_pay", "payment_days", "total_working_days", "start_date"], order_by="start_date desc", limit=1)
	if slip and flt(slip[0].payment_days) >= flt(slip[0].total_working_days) \
			and abs(flt(slip[0].net_pay) - flt(assignment.agreed_net_pay)) > 0.01:
		return dict(slip=slip[0].name, net_pay=flt(slip[0].net_pay), start_date=slip[0].start_date)
	return None


@frappe.whitelist()
def get_salaries(from_date: str):
	"""Everyone active on `from_date`, what they're on now, and whether their last
	payslip still nets what was agreed. `locked`: they already have a submitted slip
	from that date on, so their assignment from that date can't be replaced."""
	_require_hr()
	company = _company()
	employees = frappe.get_all(
		"Employee", filters={"company": company, "status": "Active", "date_of_joining": ["<=", get_last_day(from_date)]},
		fields=["name", "employee_name", "department", "designation", "grade"], order_by="employee_name asc")
	current = {}
	for a in frappe.get_all(
		"Salary Structure Assignment", filters={"docstatus": 1, "company": company, "from_date": ["<=", from_date]},
		fields=["name", "employee", "salary_structure", "base", "from_date", "agreed_net_pay"], order_by="from_date asc"):
		current[a.employee] = a  # latest wins
	locked = set(frappe.get_all("Salary Slip", filters={"docstatus": 1, "start_date": [">=", from_date]}, pluck="employee"))
	for e in employees:
		a = current.get(e.name)
		e.assignment = a and a.name
		e.salary_structure = a and a.salary_structure
		e.base = a and flt(a.base)
		e.agreed_net_pay = a and flt(a.agreed_net_pay)
		e.assigned_from = a and a.from_date
		e.drift = _drift(e.name, a)
		e.locked = e.name in locked and bool(a and getdate(a.from_date) == getdate(from_date))
	return employees


@frappe.whitelist(methods=["POST"])
def price_salaries(salary_structure: str, from_date: str, rows: list | str, income_tax_slab: str | None = None):
	"""For each {employee, mode: net|gross, amount}: the base, and the payslip it gives."""
	_require_hr()
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	_salary_inputs(salary_structure, from_date, income_tax_slab)
	out = []
	for row in rows:
		try:
			amount = flt(row.get("amount"), 2)
			if amount <= 0:
				frappe.throw(_("Enter an amount above 0."))
			base = (_solve_base(row["employee"], salary_structure, from_date, income_tax_slab, amount)
			        if row.get("mode") == "net" else amount)
			priced = _priced(_preview_slip(row["employee"], salary_structure, base, from_date, income_tax_slab))
			out.append(dict(employee=row["employee"], mode=row.get("mode"), amount=amount, **priced))
		except frappe.ValidationError as e:
			frappe.clear_messages()
			out.append(dict(employee=row["employee"], error=str(e)))
	return out


@frappe.whitelist(methods=["POST"])
def save_salaries(salary_structure: str, from_date: str, rows: list | str, income_tax_slab: str | None = None):
	"""A submitted Salary Structure Assignment per {employee, base, agreed_net}, from
	`from_date`. One already starting that day is replaced unless a submitted slip
	has used it. One failure doesn't stop the rest; its reason comes back."""
	_require_hr()
	from hrms.payroll.doctype.salary_structure.salary_structure import create_salary_structure_assignment

	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	company = _company()
	_salary_inputs(salary_structure, from_date, income_tax_slab)
	if not frappe.get_cached_value("Company", company, "default_payroll_payable_account"):
		frappe.throw(_("Set a Default Payroll Payable Account on {0} first.").format(company))
	for row in rows:
		if flt(row.get("base")) <= 0:
			frappe.throw(_("Base for {0} is 0 — their net pay would be zero.").format(row.get("employee")))
	currency = frappe.get_cached_value("Salary Structure", salary_structure, "currency")
	locked = set(frappe.get_all("Salary Slip", filters={"docstatus": 1, "start_date": [">=", from_date]}, pluck="employee"))

	created, replaced, failed = [], [], []
	for row in rows:
		employee = row["employee"]
		same_day = frappe.get_all("Salary Structure Assignment", filters={
			"employee": employee, "from_date": from_date, "docstatus": ["<", 2]}, fields=["name", "docstatus"])
		if same_day and employee in locked:
			failed.append(dict(employee=employee, error=_("A submitted payslip already uses their salary from {0}; pick a later date.")
			                   .format(getdate(from_date).strftime("%d %b %Y"))))
			continue
		frappe.db.savepoint("save_salary")
		try:
			for old in same_day:
				doc = frappe.get_doc("Salary Structure Assignment", old.name)
				if doc.docstatus == 1:
					doc.cancel()
				frappe.delete_doc("Salary Structure Assignment", old.name, ignore_permissions=True)
			name = create_salary_structure_assignment(
				employee=employee, salary_structure=salary_structure, company=company, currency=currency,
				from_date=from_date, base=flt(row["base"], 2), income_tax_slab=income_tax_slab)
			if flt(row.get("agreed_net")):
				frappe.db.set_value("Salary Structure Assignment", name, "agreed_net_pay", flt(row["agreed_net"], 2))
			(replaced if same_day else created).append(employee)
		except Exception as e:
			frappe.db.rollback(save_point="save_salary")
			frappe.clear_messages()
			failed.append(dict(employee=employee, error=str(e)))
	return dict(created=len(created), replaced=len(replaced), failed=failed)


@frappe.whitelist()
def get_pay_report(from_date: str, to_date: str, department: str | None = None, employee: str | None = None,
                   include_drafts: int = 0):
	"""What each person earned, had deducted and was paid over a range of slips: one
	column per salary component, grouped as earnings, deductions, and components
	that don't touch pay (employer contributions, statistical). Each person carries
	their slips, so a total can be traced to the month it came from."""
	_require_hr()
	filters = {"start_date": [">=", from_date], "end_date": ["<=", to_date],
	           "docstatus": ["in", [0, 1] if cint(include_drafts) else [1]]}
	if department:
		filters["department"] = department
	if employee:
		filters["employee"] = employee
	slips = frappe.get_list(
		"Salary Slip", filters=filters,
		fields=["name", "employee", "employee_name", "department", "designation", "start_date", "end_date",
		        "currency", "gross_pay", "total_deduction", "net_pay", "payment_days", "total_working_days", "docstatus"],
		order_by="employee_name asc, start_date asc", limit_page_length=0)
	if not slips:
		return dict(groups=dict(earnings=[], deductions=[], other=[]), rows=[], totals={}, currency=None, slips=0)

	detail = frappe.qb.DocType("Salary Detail")
	lines = (
		frappe.qb.from_(detail)
		.select(detail.parent, detail.parentfield, detail.salary_component, detail.amount,
		        detail.do_not_include_in_total, detail.statistical_component)
		.where((detail.parenttype == "Salary Slip") & detail.parent.isin([s.name for s in slips]))
		.orderby(detail.idx)
	).run(as_dict=True)

	groups = dict(earnings=[], deductions=[], other=[])
	by_slip = {}
	for line in lines:
		group = "other" if (line.do_not_include_in_total or line.statistical_component) else line.parentfield
		if line.salary_component not in groups[group]:
			groups[group].append(line.salary_component)
		amounts = by_slip.setdefault(line.parent, {})
		amounts[line.salary_component] = amounts.get(line.salary_component, 0) + flt(line.amount)

	rows, people = [], {}
	for s in slips:
		row = people.get(s.employee)
		if not row:
			row = people[s.employee] = dict(employee=s.employee, employee_name=s.employee_name, department=s.department,
			                                designation=s.designation, amounts={}, gross_pay=0, total_deduction=0,
			                                net_pay=0, slips=[])
			rows.append(row)
		amounts = by_slip.get(s.name, {})
		for component, amount in amounts.items():
			row["amounts"][component] = row["amounts"].get(component, 0) + amount
		for f in ("gross_pay", "total_deduction", "net_pay"):
			row[f] += flt(s[f])
		row["slips"].append(dict(name=s.name, start_date=s.start_date, end_date=s.end_date, docstatus=s.docstatus,
		                         payment_days=s.payment_days, total_working_days=s.total_working_days,
		                         gross_pay=flt(s.gross_pay), total_deduction=flt(s.total_deduction),
		                         net_pay=flt(s.net_pay), amounts=amounts))

	totals = dict(amounts={}, gross_pay=0, total_deduction=0, net_pay=0)
	for row in rows:
		for component, amount in row["amounts"].items():
			totals["amounts"][component] = totals["amounts"].get(component, 0) + amount
		for f in ("gross_pay", "total_deduction", "net_pay"):
			totals[f] += row[f]
	currencies = {s.currency for s in slips}
	return dict(groups=groups, rows=rows, totals=totals, slips=len(slips),
	            currency=currencies.pop() if len(currencies) == 1 else None)


@frappe.whitelist(methods=["POST"])
def new_payroll_entry(posting_date: str, start_date: str, end_date: str, payment_account: str | None = None,
                      department: str | None = None):
	_require_hr()
	company = _company()
	payable = frappe.get_cached_value("Company", company, "default_payroll_payable_account")
	if not payable:
		frappe.throw(_("Set a Default Payroll Payable Account on {0} first.").format(company))
	doc = frappe.get_doc(dict(
		doctype="Payroll Entry",
		company=company,
		posting_date=posting_date,
		payroll_frequency="Monthly",
		start_date=start_date,
		end_date=end_date,
		currency=frappe.get_cached_value("Company", company, "default_currency"),
		exchange_rate=1,
		payroll_payable_account=payable,
		cost_center=frappe.get_cached_value("Company", company, "cost_center"),
		payment_account=payment_account,
		department=department,
	)).insert()
	return doc.name


@frappe.whitelist()
def get_payroll_entry(name: str):
	_require_hr()
	doc = frappe.get_doc("Payroll Entry", name)
	doc.check_permission("read")
	slips = frappe.get_all(
		"Salary Slip", filters={"payroll_entry": name, "docstatus": ["<", 2]},
		fields=["name", "employee", "employee_name", "department", "docstatus", "status", "gross_pay", "total_deduction",
		        "net_pay", "payment_days", "total_working_days", "currency"],
		order_by="employee_name asc",
	)
	tax_components = set(frappe.get_all("Salary Component", filters={"variable_based_on_taxable_salary": 1}, pluck="name"))
	taxed = set()
	if slips and tax_components:
		taxed = set(frappe.get_all(
			"Salary Detail",
			filters={"parenttype": "Salary Slip", "parent": ["in", [s.name for s in slips]],
			         "salary_component": ["in", list(tax_components)], "amount": [">", 0]},
			pluck="parent"))
	for s in slips:
		flags = []
		if not flt(s.net_pay):
			flags.append("Net pay is zero")
		if flt(s.payment_days) < flt(s.total_working_days):
			flags.append(f"Paid {flt(s.payment_days):g} of {flt(s.total_working_days):g} days")
		if s.name not in taxed:
			flags.append("No PAYE deducted")
		s.flags = flags
	return dict(
		doc=dict(name=doc.name, company=doc.company, posting_date=doc.posting_date, start_date=doc.start_date,
		         end_date=doc.end_date, currency=doc.currency, payment_account=doc.payment_account,
		         payroll_payable_account=doc.payroll_payable_account, department=doc.department,
		         docstatus=doc.docstatus, status=doc.status,
		         employees=[dict(employee=e.employee, employee_name=e.employee_name, department=e.department)
		                    for e in doc.employees]),
		state=_payroll_state(doc),
		slips=slips,
		totals=dict(gross=sum(flt(s.gross_pay) for s in slips), deductions=sum(flt(s.total_deduction) for s in slips),
		            net=sum(flt(s.net_pay) for s in slips)),
	)


@frappe.whitelist(methods=["POST"])
def payroll_step(name: str, step: str, payment_account: str | None = None):
	"""The four clicks of the monthly run, in order."""
	_require_hr()
	if step not in PAYROLL_STEPS:
		frappe.throw(_("Unknown payroll step {0}").format(step))
	doc = frappe.get_doc("Payroll Entry", name)
	doc.check_permission("write")
	result = None
	if step == "get_employees":
		if doc.docstatus != 0:
			frappe.throw(_("Employees can only be fetched while the entry is a draft."))
		_fill_blank_payable(doc)
		try:
			doc.fill_employee_details()
		except frappe.ValidationError:
			if doc.employees:
				raise
			frappe.clear_messages()
			frappe.throw(_why_no_employees(doc), title=_("No employees for this run"))
		doc.save()
	elif step == "create_slips":
		if doc.docstatus == 0:
			if not doc.employees:
				frappe.throw(_("Get employees first."))
			_check_salaries_cover_start(doc)
			doc.submit()  # on_submit creates the draft slips
		elif not doc.salary_slips_created:
			doc.create_salary_slips()
	elif step == "submit_slips":
		if doc.docstatus != 1 or not doc.salary_slips_created:
			frappe.throw(_("Create the salary slips first."))
		doc.submit_salary_slips()
	elif step == "bank_entry":
		if not doc.salary_slips_submitted:
			frappe.throw(_("Submit the salary slips first."))
		if payment_account and payment_account != doc.payment_account:
			doc.db_set("payment_account", payment_account)
		if not doc.payment_account:
			frappe.throw(_("Pick the bank account the salaries are paid from."))
		je = doc.make_bank_entry()
		result = je and je.name
	return dict(result=result, **get_payroll_entry(name))



def _starts_after(employee, start_date, joining=None):
	"""The date this employee's salary starts if it's after their first day in the run
	(HRMS can't make a slip then: "assign a Salary Structure applicable from or before
	…"); None when a salary covers it or there is no salary at all."""
	first_day = max(getdate(start_date), getdate(joining or start_date))
	dates = frappe.get_all("Salary Structure Assignment", filters={"employee": employee, "docstatus": 1},
	                       pluck="from_date", order_by="from_date asc", limit=1)
	return dates[0] if dates and getdate(dates[0]) > first_day else None


def _check_salaries_cover_start(doc):
	late = []
	for e in doc.employees:
		joining = frappe.db.get_value("Employee", e.employee, "date_of_joining")
		if starts := _starts_after(e.employee, doc.start_date, joining):
			late.append(f"<li><strong>{frappe.utils.escape_html(e.employee_name)}</strong>: "
			            f"{_('salary starts {0}').format(formatdate(starts))}</li>")
	if late:
		frappe.throw(
			_("This run starts on {0}, but these salaries start later, so no payslip can be made for them:").format(
				formatdate(doc.start_date)) + "<ul>" + "".join(late) + "</ul>" +
			_("Save their salaries on the Salaries page from {0} or earlier, or start a new run that begins when the "
			  "salaries do.").format(formatdate(doc.start_date)),
			title=_("Salaries start after the run"))

def _fill_blank_payable(doc):
	"""HRMS only takes assignments whose Payroll Payable Account is this run's. An
	assignment saved before the company had a default has none, so give it the one
	HRMS would have filled in."""
	frappe.db.sql(
		"""update `tabSalary Structure Assignment` set payroll_payable_account = %s
		   where docstatus = 1 and company = %s and from_date <= %s
		   and ifnull(payroll_payable_account, '') = ''""",
		(doc.payroll_payable_account, doc.company, doc.end_date))


def _why_no_employees(doc):
	"""Why each active employee was left out of the run, in place of HRMS's list of criteria."""
	from hrms.payroll.doctype.payroll_entry.payroll_entry import get_salary_structure

	structures = set(get_salary_structure(doc.company, doc.currency, 0, doc.payroll_frequency))
	filters = {"company": doc.company, "status": "Active"}
	if doc.department:
		filters["department"] = doc.department
	employees = frappe.get_all("Employee", filters=filters, fields=["name", "employee_name", "date_of_joining"],
	                           order_by="employee_name asc")
	if not employees:
		return _("{0} has no active employees{1}.").format(
			doc.company, _(" in {0}").format(doc.department) if doc.department else "")
	latest = {}
	for a in frappe.get_all("Salary Structure Assignment",
	                        filters={"docstatus": 1, "company": doc.company, "from_date": ["<=", doc.end_date]},
	                        fields=["employee", "salary_structure", "payroll_payable_account"], order_by="from_date asc"):
		latest[a.employee] = a
	lines = []
	for e in employees:
		a = latest.get(e.name)
		if e.date_of_joining and getdate(e.date_of_joining) > getdate(doc.end_date):
			why = _("joins after {0}").format(doc.end_date)
		elif not a:
			why = _("no submitted salary assignment from before {0}").format(doc.end_date)
		elif a.salary_structure not in structures:
			why = _("salary structure {0} isn't an active, submitted, monthly {1} structure").format(
				a.salary_structure, doc.currency)
		elif a.payroll_payable_account != doc.payroll_payable_account:
			why = _("assignment posts to {0}, this run to {1}").format(a.payroll_payable_account, doc.payroll_payable_account)
		else:
			why = _("left out by HRMS for another reason")
		lines.append(f"<li><strong>{frappe.utils.escape_html(e.employee_name)}</strong>: {why}</li>")
	return _("Nobody can be paid in this run ({0} to {1}):").format(doc.start_date, doc.end_date) + \
		"<ul>" + "".join(lines) + "</ul>" + _("Fix the salary assignments on the Salaries page, then get employees again.")

# ── People ───────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_employee(name: str):
	"""The employee record as the spine of everything: links, balances, history."""
	_require_access()
	_check_in_scope(name)
	from hrms.api import get_department_approvers
	from hrms.hr.doctype.leave_application.leave_application import get_leave_details

	doc = frappe.get_doc("Employee", name)
	if is_hr():
		doc.check_permission("read")
	fields = ("name", "employee_name", "first_name", "last_name", "gender", "date_of_birth", "date_of_joining", "status",
	          "company", "department", "designation", "branch", "grade", "employment_type", "reports_to", "user_id",
	          "leave_approver", "expense_approver", "holiday_list", "company_email", "personal_email", "cell_number",
	          "ctc", "salary_currency", "relieving_date", "resignation_letter_date", "image")
	emp = {f: doc.get(f) for f in fields}
	emp["reports_to_name"] = doc.reports_to and frappe.db.get_value("Employee", doc.reports_to, "employee_name")
	dept_leave = get_department_approvers(doc.department, "leave_approvers") if doc.department else []
	dept_expense = get_department_approvers(doc.department, "expense_approvers") if doc.department else []

	today = getdate()
	assignment = frappe.get_all(
		"Salary Structure Assignment", filters={"employee": name, "docstatus": 1, "from_date": ["<=", today]},
		fields=["name", "salary_structure", "base", "from_date", "agreed_net_pay"], order_by="from_date desc", limit=1)
	try:
		balances = get_leave_details(name, nowdate()).get("leave_allocation", {})
	except frappe.PermissionError:
		balances = {}

	def recent(doctype, fields, order="modified desc", limit=5, **filters):
		if not frappe.has_permission(doctype, "read"):
			return []
		return frappe.get_list(doctype, filters={"employee": name, **filters}, fields=fields, order_by=order, limit=limit)

	links = [
		dict(key="user_id", label="User ID", value=doc.user_id, ok=bool(doc.user_id),
		     missing="Can't log in to the HR app"),
		dict(key="leave_approver", label="Leave approver",
		     value=doc.leave_approver or (dept_leave and f"{dept_leave[0].full_name} (department)"),
		     ok=bool(doc.leave_approver or dept_leave), missing="Leave can't be submitted"),
		dict(key="expense_approver", label="Expense approver",
		     value=doc.expense_approver or (dept_expense and f"{dept_expense[0].full_name} (department)"),
		     ok=bool(doc.expense_approver or dept_expense), missing="Claims wait for nobody"),
		dict(key="reports_to", label="Reports to", value=emp["reports_to_name"], ok=bool(doc.reports_to),
		     missing="No supervisor in the chain"),
		dict(key="holiday_list", label="Holiday list", value=doc.holiday_list, ok=bool(doc.holiday_list),
		     missing="Holidays counted as leave days"),
		dict(key="assignment", label="Salary assignment",
		     value=(f"net {flt(assignment[0].agreed_net_pay):,.2f} · gross {flt(assignment[0].base):,.2f}"
		            if assignment and flt(assignment[0].agreed_net_pay) else
		            f"{assignment[0].salary_structure} · base {flt(assignment[0].base):,.2f}" if assignment else None),
		     ok=bool(assignment and flt(assignment[0].base)), missing="No payslip this month"),
		dict(key="allocation", label="Leave balance", value=f"{len(balances)} leave types" if balances else None,
		     ok=bool(balances), missing="\"It says I have 0 days\""),
	]
	# what the earned-leave scheduler will add next, per leave type
	ela = frappe.qb.DocType("Leave Allocation")
	els = frappe.qb.DocType("Earned Leave Schedule")
	for row in (
		frappe.qb.from_(els).join(ela).on(els.parent == ela.name)
		.select(ela.leave_type, els.allocation_date, els.number_of_leaves)
		.where((ela.employee == name) & (ela.docstatus == 1) & (els.attempted == 0) & (els.allocation_date >= today))
		.orderby(els.allocation_date)
	).run(as_dict=True):
		if row.leave_type in balances and "next_accrual" not in balances[row.leave_type]:
			balances[row.leave_type]["next_accrual"] = dict(date=row.allocation_date, days=flt(row.number_of_leaves, 2))
	separation = frappe.get_all("Employee Separation", filters={"employee": name, "docstatus": ["<", 2]},
	                            fields=["name", "docstatus", "boarding_status", "boarding_begins_on"], limit=1)
	return dict(
		employee=emp,
		links=links,
		balances=balances,
		leave=recent("Leave Application", ["name", "leave_type", "from_date", "to_date", "total_leave_days", "status", "docstatus"]),
		claims=recent("Expense Claim", ["name", "posting_date", "total_claimed_amount", "total_sanctioned_amount", "status",
		                                "approval_status", "currency", "docstatus"]),
		slips=recent("Salary Slip", ["name", "start_date", "end_date", "net_pay", "currency", "status", "docstatus"],
		             order="start_date desc", docstatus=["<", 2]),
		history=_property_history(name),
		separation=separation[0] if separation else None,
		can_edit=bool(frappe.has_permission("Employee", "write", name)),
	)


def _property_history(employee):
	out = []
	for doctype, date_field, table in (("Employee Promotion", "promotion_date", "promotion_details"),
	                                   ("Employee Transfer", "transfer_date", "transfer_details")):
		if not frappe.has_permission(doctype, "read"):
			continue
		for d in frappe.get_list(doctype, filters={"employee": employee, "docstatus": ["<", 2]},
		                         fields=["name", date_field, "docstatus"], order_by=f"{date_field} desc"):
			changes = frappe.get_all("Employee Property History", filters={"parent": d.name, "parenttype": doctype},
			                         fields=["property", "current", "new"], order_by="idx")
			out.append(dict(doctype=doctype, name=d.name, date=d[date_field], docstatus=d.docstatus, changes=changes))
	return sorted(out, key=lambda r: str(r["date"]), reverse=True)


@frappe.whitelist()
def get_property_fields(employee: str):
	"""Fields a Promotion/Transfer can change, with the employee's current values."""
	_require_hr()
	from hrms.hr.utils import get_employee_field_property

	meta = frappe.get_meta("Employee")
	out = []
	for f in PROPERTY_FIELDS:
		df = meta.get_field(f)
		if not df:
			continue
		prop = get_employee_field_property(employee, f) or {}
		out.append(dict(fieldname=f, label=df.label, fieldtype=df.fieldtype, options=df.options,
		                current=prop.get("value")))
	return out


@frappe.whitelist()
def new_lifecycle_doc(employee: str, doctype: str):
	"""A prefilled, unsaved Promotion / Transfer / Separation — like desk's Create menu."""
	_require_hr()
	if doctype not in ("Employee Promotion", "Employee Transfer", "Employee Separation"):
		frappe.throw(_("Unknown document {0}").format(doctype))
	emp = frappe.get_doc("Employee", employee)
	emp.check_permission("read")
	doc = dict(doctype=doctype, employee=emp.name, employee_name=emp.employee_name, company=emp.company,
	           department=emp.department)
	today = nowdate()
	if doctype == "Employee Promotion":
		doc.update(promotion_date=today, current_ctc=emp.ctc, revised_ctc=emp.ctc,
		           salary_currency=emp.salary_currency, promotion_details=[])
	elif doctype == "Employee Transfer":
		doc.update(transfer_date=today, transfer_details=[])
	else:
		doc.update(boarding_begins_on=emp.relieving_date or today, resignation_letter_date=emp.resignation_letter_date,
		           designation=emp.designation, employee_grade=emp.grade, boarding_status="Pending", activities=[])
	return doc


@frappe.whitelist()
def get_separation_activities(template: str):
	_require_hr()
	from hrms.controllers.employee_boarding_controller import get_onboarding_details

	return get_onboarding_details(template, "Employee Separation Template")


@frappe.whitelist(methods=["POST"])
def mark_left(employee: str, relieving_date: str):
	"""Status Left stops payroll and leave for the person — only once an exit is on record."""
	_require_hr()
	if not frappe.db.exists("Employee Separation", {"employee": employee, "docstatus": ["<", 2]}):
		frappe.throw(_("Start the exit (Employee Separation) first, so the checklist is on record."))
	doc = frappe.get_doc("Employee", employee)
	doc.status = "Left"
	doc.relieving_date = relieving_date
	doc.save()
	return doc.status


# ── Reports ──────────────────────────────────────────────────────────────────

REPORTS = {
	"Leave": [
		("Employee Leave Balance", "Opening, taken, expired and closing per person per type"),
		("Employee Leave Balance Summary", "One row per person, all types across — the one managers ask for"),
		("Leave Ledger", "Every movement behind a balance"),
		("Employees working on a holiday", "Attendance recorded on a public holiday"),
	],
	"Attendance": [
		("Monthly Attendance Sheet", "A month at a glance, per person"),
		("Shift Attendance", "Check-ins against shifts"),
	],
	"Payroll": [
		("Salary Register", "Every slip in a period, component by component"),
		("Bank Remittance", "What goes to which bank account"),
		("Income Tax Computation", "PAYE per employee"),
		("Accrued Earnings Report", "Earnings accrued but not yet paid"),
		("Unpaid Expense Claim", "Approved claims not yet paid — run before every payment run"),
	],
	"People": [
		("Employee Information", "Everyone, with the fields you pick"),
		("Employee Analytics", "Headcount by department, grade, type"),
		("Employee Birthday", "Birthdays this month"),
		("Employee Exits", "Who left, when, and why"),
	],
	"Custom reports": [
		("HR Headcount vs Payroll Reconciliation", "Anyone active in HR but missing from payroll, or the reverse"),
		("Payroll GL Bank Reconciliation", "Payroll against the ledger against the bank"),
	],
}


@frappe.whitelist()
def get_reports():
	_require_hr()
	existing = set(frappe.get_all("Report", filters={"disabled": 0}, pluck="name"))
	return [
		dict(group=group, reports=[dict(name=n, description=d, url=f"/app/query-report/{n}") for n, d in reports
		                           if n in existing])
		for group, reports in REPORTS.items()
	]
