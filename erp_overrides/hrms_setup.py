"""Configure Frappe HR: holidays, payroll basis, leave visibility, payslip
encryption and the approval hierarchy.

1. Holiday Lists per country, "<Country> <Year>", for this year and next: Sundays
   off plus the public holidays from the ``holidays`` package (the same source as the
   Holiday List "Add Local Holidays" button), including "(observed)" Mondays.
   Existing lists only gain missing dates; nothing is removed.
2. Payroll is based on Leave, not Attendance, and no Salary Structure is based on
   Timesheets, so attendance and timesheets don't change pay.
3. Leave notifications on, with the standard templates, and the Leave Application
   calendar shows the whole department, so colleagues can see who is away
   (/app/leave-application/view/calendar).
4. Salary slips emailed as password-protected PDFs (``PAYSLIP_PASSWORD_POLICY``).
5. Each employee gets a Holiday List for their company's country, both on the
   Employee and as submitted Holiday List Assignments (what HRMS v16 reads) for
   the company and every active employee, this year and next. A ``validate``
   hook fills new employees' field and the company assignment covers them; the
   monthly job creates next year's lists and assignments.
6. Approvers: ``reports_to`` plus leave/expense/shift approver per employee
   (``HIERARCHY``), department approver lists (``DEPARTMENT_APPROVERS``), linked
   user logins (``EMPLOYEE_USERS``) and the approver roles.

People are matched by employee name (case- and whitespace-insensitive), not ID, so
the same script runs on the local bench and on production.

Nothing is written unless ``apply`` is set:

    bench --site demo.localhost execute erp_overrides.hrms_setup.run
    bench --site demo.localhost execute erp_overrides.hrms_setup.run --kwargs "{'apply': 1}"
"""

import re

import frappe
from frappe.utils import flt, getdate, today
from hrms.utils.holiday_list import get_assigned_holiday_list

OK, FIX, FAIL, INFO = "OK", "FIXED", "ACTION", "INFO"

WEEKLY_OFF = "Sunday"

# str.format over the Employee's fields (hrms generate_password_for_pdf), so the PDF
# password is the employee's date of birth as DDMMYYYY, e.g. 15111984.
PAYSLIP_PASSWORD_POLICY = "{date_of_birth.day:02d}{date_of_birth.month:02d}{date_of_birth.year}"

# Employee -> (department, reports to). Their approver is the reports-to person's
# login. Department None leaves the current one alone. The people are the fictional
# staff of the demo company (erp_overrides.demo); list your own here.
HIERARCHY = {
	"Grace Dube": ("Management - DTL", None),
	"Tinashe Banda": ("Sales - DTL", "Grace Dube"),
	"Rumbi Phiri": ("Sales - DTL", "Tinashe Banda"),
	"Farai Ncube": ("Sales - DTL", "Tinashe Banda"),
	"Peter Mlambo": ("Operations - DTL", "Grace Dube"),
	"Chipo Sibanda": ("Operations - DTL", "Peter Mlambo"),
	"Ruth Mutasa": ("Human Resources - DTL", "Grace Dube"),
	"Daniel Zulu": ("Accounts - DTL", "Grace Dube"),
	"Lindiwe Khumalo": ("Accounts - DTL", "Daniel Zulu"),
}

# Department -> head. The head goes first in its leave/expense/shift approver lists:
# the first leave approver is the fallback for staff without their own approver.
DEPARTMENT_APPROVERS = {
	"Management - DTL": "Grace Dube",
	"Sales - DTL": "Tinashe Banda",
	"Operations - DTL": "Peter Mlambo",
	"Accounts - DTL": "Daniel Zulu",
}

DEPARTMENT_APPROVER_TABLES = ("leave_approvers", "expense_approvers", "shift_request_approver")

APPROVER_ROLES = ("Leave Approver", "Expense Approver")

# Payslips and HR mail go to the company mailbox. An employee whose login is on this
# domain uses the login as their company email.
COMPANY_EMAIL_DOMAIN = "example.com"

# Employee -> login. Approvers need one to approve; everyone needs one for self service.
EMPLOYEE_USERS = {
	"Grace Dube": "grace@example.com",
	"Tinashe Banda": "tinashe@example.com",
	"Rumbi Phiri": "rumbi@example.com",
	"Farai Ncube": "farai@example.com",
	"Peter Mlambo": "peter@example.com",
	"Chipo Sibanda": "chipo@example.com",
	"Ruth Mutasa": "ruth@example.com",
	"Daniel Zulu": "daniel@example.com",
	"Lindiwe Khumalo": "lindiwe@example.com",
}

HR_SETTINGS = {
	"send_leave_notification": 1,
	"leave_approval_notification_template": "Leave Approval Notification",
	"leave_status_notification_template": "Leave Status Notification",
	"show_leaves_of_all_department_members_in_calendar": 1,
	"leave_approver_mandatory_in_leave_application": 1,
	"expense_approver_mandatory_in_expense_claim": 1,
}

PAYROLL_SETTINGS = {
	"payroll_based_on": "Leave",
	"max_working_hours_against_timesheet": 0,
	"email_salary_slip_to_employee": 1,
	"encrypt_salary_slips_in_emails": 1,
	"password_policy": PAYSLIP_PASSWORD_POLICY,
}


def run(apply: bool = False) -> None:
	apply = bool(int(apply))
	results = []

	def report(item, status, detail):
		results.append((item, status, detail))

	year = getdate(today()).year
	for country in _company_countries():
		for y in (year, year + 1):
			_ensure_holiday_list(country, y, apply, report)
	_assign_holiday_lists(year, apply, report)
	_check_settings("Payroll Settings", PAYROLL_SETTINGS, "2/5. Payroll", apply, report)
	_check_timesheet_structures(report)
	_check_settings("HR Settings", HR_SETTINGS, "4. Leave notifications", apply, report)

	# Logins before approvers: an approver field needs the approver's user.
	employees = _resolve_employees(report)
	_link_users(employees, apply, report)
	_set_company_emails(apply, report)
	_check_payslip_recipients(report)
	_set_hierarchy(employees, apply, report)
	_set_department_approvers(employees, apply, report)
	_grant_approver_roles(employees, apply, report)
	_report_unlisted(employees, report)

	if apply:
		frappe.db.commit()
	_print(results, apply)


# --- holidays -----------------------------------------------------------------


def _company_countries():
	return sorted({c for c in frappe.get_all("Company", pluck="country") if c})


def _country_code(country):
	return (frappe.db.get_value("Country", country, "code") or "").upper()


def holiday_list_name(country, year):
	return f"{country} {year}"


def _ensure_holiday_list(country, year, apply, report):
	item = "1. Holiday list"
	name = holiday_list_name(country, year)
	code = _country_code(country)
	if not code:
		report(item, FAIL, f"{country}: no country code, cannot load public holidays")
		return

	exists = frappe.db.exists("Holiday List", name)
	if exists:
		doc = frappe.get_doc("Holiday List", name)
	else:
		doc = frappe.new_doc("Holiday List")
		doc.holiday_list_name = name
		doc.from_date = f"{year}-01-01"
		doc.to_date = f"{year}-12-31"
		doc.weekly_off = WEEKLY_OFF
		doc.get_weekly_off_dates()

	before = {getdate(h.holiday_date) for h in doc.holidays}
	doc.country = code
	doc.get_local_holidays()  # appends only dates not already in the list
	added = [h for h in doc.holidays if getdate(h.holiday_date) not in before]
	added_desc = ", ".join(f"{getdate(h.holiday_date):%d %b} {h.description}" for h in added)

	if exists and not added:
		public = sum(1 for h in doc.holidays if not h.weekly_off)
		report(item, OK, f"{name}: {public} public holidays")
		return
	if not apply:
		verb = f"would add to {name}" if exists else f"would create {name} with"
		report(item, FAIL, f"{verb}: {added_desc}")
		return

	doc.sort_holidays()
	doc.save()
	verb = f"added to {name}" if exists else f"created {name} with"
	report(item, FIX, f"{verb}: {added_desc}")


def _target_holiday_list(company, year):
	country = frappe.get_cached_value("Company", company, "country")
	if not country:
		return None
	name = holiday_list_name(country, year)
	return name if frappe.db.exists("Holiday List", name) else None


def _is_ours(holiday_list, country):
	"""A list this script manages: "<Country>" or "<Country> <year>"."""
	return bool(holiday_list) and re.fullmatch(rf"{re.escape(country)}( \d{{4}})?", holiday_list)


def _assign_holiday_lists(year, apply, report):
	item = "5. Employee holiday list"
	for company in frappe.get_all("Company", fields=["name", "country", "default_holiday_list"]):
		if not company.country:
			report(item, FAIL, f"{company.name}: no Country set, no holiday list to assign")
			continue
		target = _target_holiday_list(company.name, year)
		if not target:
			if apply:
				continue  # the list failed to save; reported under "1. Holiday list"
			# Dry run before the list exists: preview against the name it will get.
			target = holiday_list_name(company.country, year)

		if company.default_holiday_list != target and (
			not company.default_holiday_list or _is_ours(company.default_holiday_list, company.country)
		):
			if apply:
				frappe.db.set_value("Company", company.name, "default_holiday_list", target)
			report(item, FIX if apply else FAIL, f"{company.name} default -> {target}")

		moved, kept = [], []
		for emp in frappe.get_all(
			"Employee",
			filters={"company": company.name, "status": "Active"},
			fields=["name", "employee_name", "holiday_list"],
		):
			if emp.holiday_list == target:
				continue
			if emp.holiday_list and not _is_ours(emp.holiday_list, company.country):
				kept.append(f"{emp.employee_name} ({emp.holiday_list})")
				continue
			moved.append(emp.employee_name)
			if apply:
				frappe.db.set_value("Employee", emp.name, "holiday_list", target)

		if moved:
			verb = "set" if apply else "would set"
			report(item, FIX if apply else FAIL, f"{verb} {target} on {len(moved)}: {', '.join(moved)}")
		else:
			report(item, OK, f"{company.name}: all active employees on {target}")
		for k in kept:
			report(item, INFO, f"left on a custom list: {k}")

		_assign_via_hla(company, year, apply, report)


def _assign_via_hla(company, year, apply, report):
	"""Submitted Holiday List Assignments, which is what HRMS v16 reads.

	v16 ignores Employee.holiday_list and Company.default_holiday_list: holidays come
	from the latest submitted assignment for the employee, else for their company.
	The company gets one per year so new joiners are covered; each active employee
	gets one too, since an old employee-level assignment would beat the company's.
	Next year's assignment starts on 1 January, so it takes over by itself.
	"""
	item = "5. Holiday List Assignment"
	lists = [holiday_list_name(company.country, y) for y in (year, year + 1)]
	lists = [hl for hl in lists if frappe.db.exists("Holiday List", hl)] or (
		[] if apply else [holiday_list_name(company.country, year)]
	)

	pending = [("Company", company.name, company.name, hl) for hl in lists]
	for emp in frappe.get_all(
		"Employee",
		filters={"company": company.name, "status": "Active"},
		fields=["name", "employee_name"],
		order_by="employee_name",
	):
		current = get_assigned_holiday_list(emp.name)
		if current and not _is_ours(current, company.country):
			report(item, INFO, f"left on a custom assignment: {emp.employee_name} ({current})")
			continue
		pending += [("Employee", emp.name, emp.employee_name, hl) for hl in lists]

	done = {}
	for applicable_for, assigned_to, label, hl in pending:
		if frappe.db.exists(
			"Holiday List Assignment", {"assigned_to": assigned_to, "holiday_list": hl, "docstatus": 1}
		):
			continue
		if apply and not _submit_hla(applicable_for, assigned_to, company.name, hl, label, item, report):
			continue
		done.setdefault(hl, []).append(label)

	for hl, labels in done.items():
		verb = "assigned" if apply else "would assign"
		report(item, FIX if apply else FAIL, f"{verb} {hl} to {len(labels)}: {', '.join(labels)}")
	if not done:
		report(item, OK, f"{company.name}: company and active employees assigned {', '.join(lists)}")


def _submit_hla(applicable_for, assigned_to, company, holiday_list, label, item, report):
	frappe.db.savepoint("hrms_setup_hla")
	try:
		doc = frappe.new_doc("Holiday List Assignment")
		doc.applicable_for = applicable_for
		doc.assigned_to = assigned_to
		doc.holiday_list = holiday_list
		doc.from_date = frappe.db.get_value("Holiday List", holiday_list, "from_date")
		if applicable_for == "Employee":
			doc.employee_company = company
		doc.insert()
		doc.submit()
		return True
	except frappe.ValidationError as e:
		frappe.db.rollback(save_point="hrms_setup_hla")
		frappe.clear_messages()
		report(item, FAIL, f"{label} / {holiday_list}: not assigned, {frappe.utils.strip_html(str(e))}")
		return False


def set_employee_holiday_list(doc, method=None):
	"""Employee ``validate`` hook: new or unassigned employees get their country's list."""
	if doc.holiday_list or not doc.company:
		return
	target = _target_holiday_list(doc.company, getdate(today()).year)
	if target:
		doc.holiday_list = target


def roll_holiday_lists():
	"""Monthly: keep this year's and next year's lists present and employees current."""
	year = getdate(today()).year
	noop = lambda *a: None  # noqa: E731
	for country in _company_countries():
		for y in (year, year + 1):
			_ensure_holiday_list(country, y, True, noop)
	_assign_holiday_lists(year, True, noop)
	frappe.db.commit()


# --- payroll / HR settings ------------------------------------------------------


def _check_settings(doctype, wanted, item, apply, report):
	changes = {}
	for field, value in wanted.items():
		current = frappe.db.get_single_value(doctype, field)
		same = flt(current) == value if isinstance(value, int | float) else (current or "") == value
		if not same:
			changes[field] = (current, value)

	if not changes:
		report(item, OK, f"{doctype}: {len(wanted)} settings as expected")
		return
	for field, (current, value) in changes.items():
		if apply:
			frappe.db.set_single_value(doctype, field, value)
		report(item, FIX if apply else FAIL, f"{field}: {current!r} -> {value!r}")


def _check_timesheet_structures(report):
	item = "2. Timesheet-based pay"
	based = frappe.get_all(
		"Salary Structure",
		filters={"salary_slip_based_on_timesheet": 1, "docstatus": 1, "is_active": "Yes"},
		pluck="name",
	)
	if based:
		# Submitted structures can't be edited; they need cancel + amend by HR.
		report(item, FAIL, f"cancel and amend without timesheets: {', '.join(based)}")
	else:
		report(item, OK, "no active Salary Structure is based on timesheets")


def _set_company_emails(apply, report):
	"""Preferred email = company email, and company email = the company login."""
	item = "5. Company email"
	owner = {u.lower(): _norm(n) for n, u in EMPLOYEE_USERS.items()}
	for emp in frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "user_id", "company_email", "prefered_contact_email"],
		order_by="employee_name",
	):
		wanted = {"prefered_contact_email": "Company Email"}
		login = (emp.user_id or "").lower()
		if owner.get(login, _norm(emp.employee_name)) != _norm(emp.employee_name):
			login = ""  # moving to its rightful owner in this run 
		if login.endswith("@" + COMPANY_EMAIL_DOMAIN):
			wanted["company_email"] = emp.user_id
		changes = {f: v for f, v in wanted.items() if (emp.get(f) or "") != v}
		if not changes:
			continue

		detail = []
		if "company_email" in changes:
			was = f" (was {emp.company_email})" if emp.company_email else ""
			detail.append(f"company email {changes['company_email']}{was}")
		if "prefered_contact_email" in changes:
			detail.append("preferred = company email")
		if apply:
			doc = frappe.get_doc("Employee", emp.name)
			doc.update(changes)
			# save() recomputes prefered_email from the company email
			if not _save(doc, item, emp.employee_name, report):
				continue
		verb = "" if apply else "would set "
		report(item, FIX if apply else FAIL, f"{emp.employee_name}: {verb}{', '.join(detail)}")


def _check_payslip_recipients(report):
	"""An encrypted slip needs an email to go to and a date of birth for its password."""
	item = "5. Payslip delivery"
	for emp in frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["employee_name", "prefered_email", "date_of_birth", "user_id"],
	):
		if not emp.prefered_email:
			report(item, FAIL, f"{emp.employee_name}: no company email, payslip won't be sent")
		if not emp.date_of_birth:
			report(item, FAIL, f"{emp.employee_name}: no date of birth, payslip password can't be built")


def _save(doc, item, label, report):
	"""Save one record; on a validation error report it and keep going.

	Employee records here can carry mandatory custom fields nobody has filled
	(e.g. passport_number), and one incomplete record shouldn't stop the rest. The
	savepoint undoes only this record's partial writes.
	"""
	frappe.db.savepoint("hrms_setup_save")
	try:
		doc.save()
		return True
	except frappe.ValidationError as e:
		frappe.db.rollback(save_point="hrms_setup_save")
		frappe.clear_messages()
		report(item, FAIL, f"{label}: not saved, {frappe.utils.strip_html(str(e))}")
		return False


# --- approvers ------------------------------------------------------------------


def _norm(name):
	return " ".join((name or "").split()).lower()


def _resolve_employees(report):
	"""Map every name used in the configuration to its active Employee ID."""
	by_name = {}
	for emp in frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "employee_name"]):
		by_name.setdefault(_norm(emp.employee_name), []).append(emp.name)

	names = set(HIERARCHY) | set(EMPLOYEE_USERS) | set(DEPARTMENT_APPROVERS.values())
	names |= {r for _, r in HIERARCHY.values() if r}
	resolved = {}
	for name in sorted(names):
		ids = by_name.get(_norm(name), [])
		if len(ids) == 1:
			resolved[name] = ids[0]
		elif not ids:
			report("6. Employees", FAIL, f"{name}: no active Employee record, create one first")
		else:
			report("6. Employees", FAIL, f"{name}: {len(ids)} employees share this name ({', '.join(ids)})")
	return resolved


def _link_users(employees, apply, report):
	item = "6. Logins"
	# Unlink users that are about to move first, so a swap between two employees
	# doesn't trip Employee's one-user-per-employee check.
	pending = []
	for name, user in EMPLOYEE_USERS.items():
		emp = employees.get(name)
		if not emp:
			continue
		if not frappe.db.exists("User", user):
			report(item, FAIL, f"{name}: user {user} does not exist")
			continue
		current = frappe.db.get_value("Employee", emp, "user_id")
		if current == user:
			report(item, OK, f"{name} -> {user}")
			continue
		holder = frappe.db.get_value("Employee", {"user_id": user, "name": ["!=", emp]}, "employee_name")
		pending.append((name, emp, user, current, holder))

	if apply:
		for _, emp, user, _, holder in pending:
			if holder:
				frappe.db.set_value("Employee", {"user_id": user}, "user_id", None)
	for name, emp, user, current, holder in pending:
		note = f" (was {current})" if current else ""
		note += f"; taken from {holder}" if holder else ""
		if apply:
			doc = frappe.get_doc("Employee", emp)
			doc.user_id = user
			if not _save(doc, item, name, report):
				continue
		report(item, FIX if apply else FAIL, f"{name} -> {user}{note}")


def _approver_user(employees, name):
	emp = employees.get(name)
	return frappe.db.get_value("Employee", emp, "user_id") if emp else None


def _set_hierarchy(employees, apply, report):
	item = "6. Approvers"
	for name, (department, reports_to) in HIERARCHY.items():
		emp = employees.get(name)
		if not emp:
			continue
		wanted = {}
		if department:
			if not frappe.db.exists("Department", department):
				report(item, FAIL, f"{name}: department {department} does not exist")
				continue
			wanted["department"] = department
		if reports_to:
			boss, boss_user = employees.get(reports_to), _approver_user(employees, reports_to)
			if not boss:
				continue
			if not boss_user and not apply:
				# The login may be linked in this same run.
				boss_user = EMPLOYEE_USERS.get(reports_to)
			if not boss_user:
				report(item, FAIL, f"{name}: approver {reports_to} has no login")
				continue
			wanted.update(
				reports_to=boss,
				leave_approver=boss_user,
				expense_approver=boss_user,
				shift_request_approver=boss_user,
			)

		doc = frappe.get_doc("Employee", emp)
		changes = {f: v for f, v in wanted.items() if doc.get(f) != v}
		if not changes:
			report(item, OK, f"{name}: {_describe(wanted, reports_to)}")
			continue
		if apply:
			doc.update(changes)
			if not _save(doc, item, name, report):
				continue
		report(item, FIX if apply else FAIL, f"{name}: {_describe(wanted, reports_to)}")


def _describe(wanted, reports_to):
	parts = []
	if wanted.get("department"):
		parts.append(wanted["department"])
	if reports_to:
		parts.append(f"approver {reports_to} ({wanted['leave_approver']})")
	return ", ".join(parts)


def _set_department_approvers(employees, apply, report):
	item = "6. Department approvers"
	for department, head in DEPARTMENT_APPROVERS.items():
		user = _approver_user(employees, head) or (EMPLOYEE_USERS.get(head) if not apply else None)
		if not frappe.db.exists("Department", department):
			report(item, FAIL, f"{department}: department does not exist")
			continue
		if not user:
			report(item, FAIL, f"{department}: {head} has no login")
			continue

		doc = frappe.get_doc("Department", department)
		changed = []
		for table in DEPARTMENT_APPROVER_TABLES:
			rows = [r.approver for r in doc.get(table)]
			if rows[:1] == [user]:
				continue
			# Head first; keep the other approvers as alternates rather than drop them.
			new = [user] + [a for a in rows if a != user]
			doc.set(table, [{"approver": a} for a in new])
			changed.append(table.replace("_", " "))

		if not changed:
			report(item, OK, f"{department}: {head} first")
			continue
		if apply and not _save(doc, item, department, report):
			continue
		verb = "set" if apply else "would set"
		report(item, FIX if apply else FAIL, f"{department}: {verb} {head} first in {', '.join(changed)}")


def _grant_approver_roles(employees, apply, report):
	item = "6. Approver roles"
	heads = {r for _, r in HIERARCHY.values() if r} | set(DEPARTMENT_APPROVERS.values())
	for head in sorted(heads):
		user = _approver_user(employees, head) or EMPLOYEE_USERS.get(head)
		if not user or not frappe.db.exists("User", user):
			continue
		have = set(frappe.get_roles(user))
		missing = [r for r in APPROVER_ROLES if r not in have]
		if not missing:
			report(item, OK, f"{user}: {', '.join(APPROVER_ROLES)}")
			continue
		if apply:
			frappe.get_doc("User", user).add_roles(*missing)
		report(item, FIX if apply else FAIL, f"{user}: {'added' if apply else 'would add'} {', '.join(missing)}")


def _report_unlisted(employees, report):
	"""Active staff outside HIERARCHY fall back to their department's first approver,
	which is the configured head once this runs."""
	listed = {employees[n] for n in HIERARCHY if n in employees}
	heads = {d: _approver_user(employees, h) or EMPLOYEE_USERS.get(h) for d, h in DEPARTMENT_APPROVERS.items()}
	for emp in frappe.get_all(
		"Employee",
		filters={"status": "Active", "name": ["not in", list(listed) or [""]]},
		fields=["employee_name", "department", "leave_approver"],
		order_by="employee_name",
	):
		approver = emp.leave_approver or heads.get(emp.department)
		if not approver and emp.department:
			approver = frappe.db.get_value(
				"Department Approver",
				{"parent": emp.department, "parentfield": "leave_approvers", "idx": 1},
				"approver",
			)
		where = emp.department or "no department"
		report("6. Not in the list", INFO, f"{emp.employee_name} ({where}): leave goes to {approver or 'nobody'}")


def _print(results, apply):
	print(f"\nHRMS configuration [{'APPLY' if apply else 'DRY RUN'}]\n")
	width = max(len(r[0]) for r in results)
	for item, status, detail in results:
		print(f"  {item:<{width}}  {status:<6}  {detail}")
	actions = sum(1 for r in results if r[1] == FAIL)
	print(f"\n{actions} item(s) need action.\n")
