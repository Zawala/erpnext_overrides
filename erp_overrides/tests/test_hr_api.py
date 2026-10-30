# Copyright (c) 2026, Kelvin Zawala and contributors
# See license.txt
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, get_first_day, get_last_day, getdate, nowdate

from erp_overrides.api import hr

COMPANY = None


def company():
	global COMPANY
	COMPANY = COMPANY or frappe.db.get_single_value("Global Defaults", "default_company")
	return COMPANY


def make_employee(first_name, **kw):
	doc = frappe.get_doc(dict(
		doctype="Employee", first_name=first_name, last_name="HRTest", gender="Female", status="Active",
		date_of_birth="1990-01-01", company=company(), **{"date_of_joining": "2024-01-01", **kw},
	))
	doc.flags.ignore_mandatory = True  # sites add their own mandatory fields (e.g. passport number)
	return doc.insert(ignore_permissions=True)


def leave_type(name="HRTest Leave"):
	if not frappe.db.exists("Leave Type", name):
		frappe.get_doc(dict(doctype="Leave Type", leave_type_name=name, include_holiday=0)).insert(ignore_permissions=True)
	return name


def leave_period():
	today = getdate()
	existing = frappe.db.get_value("Leave Period", {"company": company(), "from_date": ["<=", today],
	                                                "to_date": [">=", today]}, "name")
	if existing:
		return frappe.get_doc("Leave Period", existing)
	return frappe.get_doc(dict(doctype="Leave Period", from_date=get_first_day(today).replace(month=1),
	                           to_date=get_last_day(today).replace(month=12, day=31), is_active=1,
	                           company=company())).insert(ignore_permissions=True)


class TestHealth(IntegrationTestCase):
	def test_reports_missing_links_for_a_bare_employee(self):
		emp = make_employee("Bare")
		mine = {i["check"] for i in hr.get_health()["issues"] if i["employee"] == emp.name}
		self.assertTrue({"user_id", "expense_approver", "reports_to", "allocation", "assignment"} <= mine, mine)

	def test_linked_employee_has_no_access_gaps(self):
		boss = make_employee("Boss")
		emp = make_employee("Linked", user_id="Administrator", reports_to=boss.name,
		                    leave_approver="Administrator", expense_approver="Administrator")
		mine = {i["check"] for i in hr.get_health()["issues"] if i["employee"] == emp.name}
		self.assertFalse(mine & {"user_id", "leave_approver", "expense_approver", "reports_to"}, mine)

	def test_health_is_hr_only(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				hr.get_health()
		finally:
			frappe.set_user("Administrator")


class TestHRAccess(IntegrationTestCase):
	"""ERPNext limits a linked user to their own Employee record; HR must not be."""

	def user(self, email, *roles):
		if not frappe.db.exists("User", email):
			frappe.get_doc(dict(doctype="User", email=email, first_name=email.split("@")[0], send_welcome_email=0,
			                    roles=[dict(role=r) for r in roles])).insert(ignore_permissions=True)
		return email

	def restricted(self, user):
		return frappe.db.exists("User Permission", {"user": user, "allow": "Employee"})

	def test_hr_user_sees_everyone_staff_only_themselves(self):
		hr_user = self.user("hraccess.hr@example.com", "HR Manager")
		staff = self.user("hraccess.staff@example.com", "Employee")
		hr_emp = make_employee("HRAccess", user_id=hr_user, create_user_permission=1)
		make_employee("StaffAccess", user_id=staff, create_user_permission=1)
		other = make_employee("Someone")
		self.assertFalse(self.restricted(hr_user))
		self.assertEqual(hr_emp.reload().create_user_permission, 0)
		self.assertTrue(self.restricted(staff))
		self.assertTrue(frappe.has_permission("Employee", "read", other.name, user=hr_user))
		self.assertFalse(frappe.has_permission("Employee", "read", other.name, user=staff))

		# staff promoted to HR: the restriction goes
		u = frappe.get_doc("User", staff)
		u.append("roles", dict(role="HR User"))
		u.save(ignore_permissions=True)
		self.assertFalse(self.restricted(staff))
		self.assertTrue(frappe.has_permission("Employee", "read", other.name, user=staff))

class TestScope(IntegrationTestCase):
	def test_approver_sees_only_their_team(self):
		user = frappe.get_doc(dict(doctype="User", email="hrtest.approver@example.com", first_name="Approver",
		                           send_welcome_email=0)).insert(ignore_permissions=True)
		user.add_roles("Leave Approver")
		mine = make_employee("Mine", leave_approver=user.name)
		other = make_employee("Other")
		frappe.set_user(user.name)
		try:
			team = hr.get_team()
			self.assertIn(mine.name, team)
			self.assertNotIn(other.name, team)
			with self.assertRaises(frappe.PermissionError):
				hr._check_in_scope(other.name)
			with self.assertRaises(frappe.PermissionError):
				hr.get_health()
		finally:
			frappe.set_user("Administrator")

	def test_hr_sees_everyone(self):
		self.assertIsNone(hr.get_team("Administrator"))


class TestLeave(IntegrationTestCase):
	def test_policy_assignment_creates_allocations_and_skips_repeats(self):
		lt = leave_type()
		period = leave_period()
		policy = hr.create_leave_policy("HRTest policy", {lt: 12})
		emp = make_employee("Alloc")
		first = hr.assign_policy(policy, period.name, [emp.name])
		self.assertEqual(first["created"], 1)
		self.assertEqual(frappe.db.get_value("Leave Allocation", {"employee": emp.name, "leave_type": lt, "docstatus": 1},
		                                     "new_leaves_allocated"), 12)
		again = hr.assign_policy(policy, period.name, [emp.name])
		self.assertEqual(again["created"], 0)
		self.assertEqual(again["skipped"], [emp.name])

	def test_decide_leave_only_approves_or_rejects(self):
		with self.assertRaises(frappe.ValidationError):
			hr.decide_leave("anything", "Cancelled")

	def test_approve_leave_submits_and_deducts(self):
		lt = leave_type()
		period = leave_period()
		policy = hr.create_leave_policy("HRTest policy 2", {lt: 10})
		emp = make_employee("Applies", leave_approver="Administrator")
		hr.assign_policy(policy, period.name, [emp.name])
		start = add_days(nowdate(), 1)
		while getdate(start).weekday() == 6:  # Sunday is the weekly off
			start = add_days(start, 1)
		app = frappe.get_doc(dict(doctype="Leave Application", employee=emp.name, leave_type=lt, from_date=start,
		                          to_date=start, leave_approver="Administrator", company=company(), status="Open")
		                     ).insert(ignore_permissions=True)
		self.assertIn(app.name, hr._leave_inbox_names())
		out = hr.decide_leave(app.name, "Approved", "enjoy")
		self.assertEqual(out["status"], "Approved")
		self.assertEqual(frappe.db.get_value("Leave Application", app.name, "docstatus"), 1)
		self.assertNotIn(app.name, hr._leave_inbox_names())
		balance = hr.get_balances(employee=emp.name)["rows"][0]["balances"][lt]
		self.assertEqual(balance["leaves_taken"], 1)


class TestPayroll(IntegrationTestCase):
	def test_unknown_step_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			hr.payroll_step("anything", "cancel")

	def test_readiness_flags_missing_assignment(self):
		emp = make_employee("Unpaid")
		today = getdate()
		rows = hr.get_payroll_readiness(str(get_first_day(today)), str(get_last_day(today)))["rows"]
		row = next(r for r in rows if r["employee"] == emp.name)
		self.assertIn("No Salary Structure Assignment", row["problem"])


class TestLifecycle(IntegrationTestCase):
	def test_prefilled_promotion_and_property_fields(self):
		emp = make_employee("Promoted")
		doc = hr.new_lifecycle_doc(emp.name, "Employee Promotion")
		self.assertEqual(doc["employee"], emp.name)
		self.assertEqual(doc["promotion_details"], [])
		fields = {f["fieldname"] for f in hr.get_property_fields(emp.name)}
		self.assertIn("designation", fields)

	def test_unknown_lifecycle_doctype_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			hr.new_lifecycle_doc("anything", "Employee")

	def test_mark_left_needs_a_separation(self):
		emp = make_employee("Leaving")
		with self.assertRaises(frappe.ValidationError):
			hr.mark_left(emp.name, nowdate())


def tax_slab():
	"""Any slip on a site with a variable-tax component needs one."""
	return frappe.db.get_value("Income Tax Slab", {"docstatus": 1, "disabled": 0, "currency": "USD"}, "name")


def payable_account():
	return frappe.db.get_value("Account", {"company": company(), "account_type": "Payable", "is_group": 0,
	                                       "account_currency": frappe.get_cached_value("Company", company(), "default_currency")}, "name")


class TestExpense(IntegrationTestCase):
	def make_claim(self, emp):
		expense_account = frappe.db.get_value("Account", {"company": company(), "root_type": "Expense", "is_group": 0}, "name")
		frappe.db.set_value("Company", company(), "default_expense_claim_payable_account", payable_account())
		for t in ("Travel", "Calls"):
			ect = frappe.get_doc("Expense Claim Type", t)
			ect.set("accounts", [{"company": company(), "default_account": expense_account}])
			ect.save(ignore_permissions=True)
		return frappe.get_doc(dict(
			doctype="Expense Claim", employee=emp.name, company=company(), expense_approver="Administrator",
			posting_date=nowdate(), approval_status="Draft", currency="USD", exchange_rate=1,
			expenses=[dict(expense_date=nowdate(), expense_type="Travel", amount=120),
			          dict(expense_date=nowdate(), expense_type="Calls", amount=50)],
		)).insert(ignore_permissions=True)

	def test_approver_can_reduce_a_line(self):
		emp = make_employee("Claims", expense_approver="Administrator")
		claim = self.make_claim(emp)
		self.assertIn(claim.name, [c.name for c in hr.get_expense_inbox()])
		travel = next(r.name for r in claim.expenses if r.expense_type == "Travel")
		out = hr.decide_expense(claim.name, "Approved", {travel: 100})
		self.assertEqual(out["total_sanctioned_amount"], 150)
		self.assertIn(claim.name, [c.name for c in hr.get_unpaid_claims()])

	def test_cannot_sanction_more_than_claimed(self):
		emp = make_employee("Greedy", expense_approver="Administrator")
		claim = self.make_claim(emp)
		travel = next(r.name for r in claim.expenses if r.expense_type == "Travel")
		with self.assertRaises(frappe.ValidationError):
			hr.decide_expense(claim.name, "Approved", {travel: 500})


class TestPayrollRun(IntegrationTestCase):
	def test_run_to_draft_slips_and_flags_zero_pay(self):
		if not frappe.in_test:
			# HRMS commits after creating slips unless it knows it is under test
			self.skipTest("needs the test runner (frappe.in_test), or the run would be committed")
		structure = frappe.db.get_value("Salary Structure", {"docstatus": 1, "is_active": "Yes", "company": company()}, "name")
		if not structure:
			self.skipTest("no submitted salary structure")
		frappe.db.set_value("Company", company(), "default_payroll_payable_account", payable_account())
		frappe.clear_document_cache("Company", company())
		today = getdate()
		start, end = str(get_first_day(today)), str(get_last_day(today))
		emp = make_employee("Payroll", date_of_joining=add_days(start, -60))
		ssa = frappe.get_doc(dict(doctype="Salary Structure Assignment", employee=emp.name, salary_structure=structure,
		                          company=company(), from_date=add_days(start, -30), base=1000,
		                          payroll_payable_account=payable_account(), currency="USD",
		                          income_tax_slab=tax_slab())).insert(ignore_permissions=True)
		ssa.submit()
		ready = {r["employee"]: r for r in hr.get_payroll_readiness(start, end)["rows"]}
		self.assertIsNone(ready[emp.name]["problem"])

		name = hr.new_payroll_entry(nowdate(), start, end, department=None)
		# only this employee: the site's real staff are not part of the test
		frappe.db.set_value("Payroll Entry", name, "department", None)
		pe = frappe.get_doc("Payroll Entry", name)
		pe.fill_employee_details()
		pe.set("employees", [e for e in pe.employees if e.employee == emp.name])
		pe.save()
		out = hr.payroll_step(name, "create_slips")
		self.assertEqual(out["state"]["state"], "slips")
		slip = next(s for s in out["slips"] if s.employee == emp.name)
		self.assertEqual(slip.docstatus, 0)
		# flagged exactly when the structure pays nothing
		self.assertEqual("Net pay is zero" in slip.flags, not slip.net_pay, slip)
		with self.assertRaises(frappe.ValidationError):
			hr.payroll_step(name, "bank_entry")  # slips not submitted yet


	def test_assignment_without_payable_account_is_still_paid(self):
		"""Assignments saved before the company had a Payroll Payable Account have none,
		and HRMS silently leaves them out ("No employees found")."""
		structure = frappe.db.get_value("Salary Structure", {"docstatus": 1, "is_active": "Yes", "company": company(),
		                                                     "currency": "USD", "payroll_frequency": "Monthly"}, "name")
		if not structure:
			self.skipTest("no submitted salary structure")
		frappe.db.set_value("Company", company(), "default_payroll_payable_account", payable_account())
		frappe.clear_document_cache("Company", company())
		today = getdate()
		start, end = str(get_first_day(today)), str(get_last_day(today))
		emp = make_employee("NoPayable", date_of_joining=add_days(start, -60))
		ssa = frappe.get_doc(dict(doctype="Salary Structure Assignment", employee=emp.name, salary_structure=structure,
		                          company=company(), from_date=add_days(start, -30), base=1000, currency="USD",
		                          income_tax_slab=tax_slab())).insert(ignore_permissions=True)
		ssa.submit()
		ssa.db_set("payroll_payable_account", None)

		name = hr.new_payroll_entry(nowdate(), start, end, department=None)
		frappe.db.set_value("Payroll Entry", name, "department", None)
		out = hr.payroll_step(name, "get_employees")
		self.assertIn(emp.name, [e["employee"] for e in out["doc"]["employees"]])
		self.assertEqual(frappe.db.get_value("Salary Structure Assignment", ssa.name, "payroll_payable_account"),
		                 payable_account())

		frappe.db.set_value("Payroll Entry", name, "department", "Nobody Here")
		with self.assertRaisesRegex(frappe.ValidationError, "no active employees"):
			hr.payroll_step(name, "get_employees")

	def test_salary_starting_after_the_run_is_caught_before_slips(self):
		"""A 15 Sep–15 Oct run with salaries saved from 1 Oct: HRMS takes the employees
		but fails every slip in the background ("assign a Salary Structure … from or before")."""
		structure = frappe.db.get_value("Salary Structure", {"docstatus": 1, "is_active": "Yes", "company": company(),
		                                                     "currency": "USD", "payroll_frequency": "Monthly"}, "name")
		if not structure:
			self.skipTest("no submitted salary structure")
		frappe.db.set_value("Company", company(), "default_payroll_payable_account", payable_account())
		frappe.clear_document_cache("Company", company())
		start, end = "2026-11-15", "2026-12-15"
		emp = make_employee("LateSalary", date_of_joining="2024-01-01")
		frappe.get_doc(dict(doctype="Salary Structure Assignment", employee=emp.name, salary_structure=structure,
		                    company=company(), from_date="2026-12-01", base=1000, currency="USD",
		                    income_tax_slab=tax_slab())).insert(ignore_permissions=True).submit()
		ready = {r["employee"]: r for r in hr.get_payroll_readiness(start, end)["rows"]}
		self.assertIn("after this run starts", ready[emp.name]["problem"])

		name = hr.new_payroll_entry(end, start, end, department=None)
		pe = frappe.get_doc("Payroll Entry", name)
		pe.department = None
		pe.append("employees", dict(employee=emp.name, employee_name=emp.employee_name))
		pe.save()
		with self.assertRaisesRegex(frappe.ValidationError, "salary starts"):
			hr.payroll_step(name, "create_slips")
		self.assertEqual(frappe.db.get_value("Payroll Entry", name, "docstatus"), 0)

class TestSalaries(IntegrationTestCase):
	"""Needs the demo payroll (erp_overrides.demo.seed): Staff 2026, its tax slab, monthly payroll periods."""
	STRUCTURE, SLAB, FROM = "Staff 2026", "Income Tax USD 2026", "2026-11-01"

	def setUp(self):
		if not frappe.db.exists("Salary Structure", {"name": self.STRUCTURE, "docstatus": 1}) or \
				not frappe.db.exists("Income Tax Slab", {"name": self.SLAB, "docstatus": 1}):
			self.skipTest("run erp_overrides.demo.seed first")
		frappe.db.set_value("Company", company(), "default_payroll_payable_account", payable_account())
		frappe.clear_document_cache("Company", company())

	def price(self, emp, mode, amount):
		row = hr.price_salaries(self.STRUCTURE, self.FROM, [{"employee": emp, "mode": mode, "amount": amount}], self.SLAB)[0]
		self.assertNotIn("error", row, row)
		return row

	def slip_net(self, emp):
		from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

		slip = make_salary_slip(self.STRUCTURE, employee=emp, posting_date=str(get_last_day(self.FROM)))
		slip.insert(ignore_permissions=True)
		return slip

	def test_net_round_trips_through_a_real_payslip(self):
		for net in (90, 250, 800, 1950, 2900, 5000):  # inside each band, either side of the pension cap
			emp = make_employee(f"Net{net}")
			row = self.price(emp.name, "net", net)
			self.assertAlmostEqual(row["net"], net, delta=0.01, msg=row)
			out = hr.save_salaries(self.STRUCTURE, self.FROM, [{"employee": emp.name, "base": row["base"], "agreed_net": net}], self.SLAB)
			self.assertEqual((out["created"], out["failed"]), (1, []))
			self.assertAlmostEqual(self.slip_net(emp.name).net_pay, net, delta=0.01)

	def test_paye_matches_the_bands(self):
		emp = make_employee("Paye")
		row = self.price(emp.name, "gross", 1000)
		paye = next(l["amount"] for l in row["lines"] if l["component"] == "Income Tax")
		taxable = 1000 - 40  # the capped pension comes off first
		self.assertAlmostEqual(paye, (200 * 0.20 + (taxable - 300) * 0.25) * 1.03, delta=0.01)
		self.assertEqual(row["base"], 1000)
		levy = next(l for l in row["lines"] if l["component"] == "Employer Levy")
		self.assertEqual(levy["kind"], "employer")
		self.assertAlmostEqual(row["net"], 1000 - 40 - paye, delta=0.01)

	def test_trial_payslip_before_any_run(self):
		emp = make_employee("Trial")
		row = self.price(emp.name, "net", 600)
		hr.save_salaries(self.STRUCTURE, self.FROM, [{"employee": emp.name, "base": row["base"], "agreed_net": 600}], self.SLAB)
		out = hr.preview_payslip(emp.name, month=self.FROM)
		self.assertIn(emp.employee_name, out["html"])
		self.assertIn("600.00", out["html"])
		self.assertFalse(frappe.db.exists("Salary Slip", {"employee": emp.name}))
		with self.assertRaisesRegex(frappe.ValidationError, "no salary assignment"):
			hr.preview_payslip(make_employee("NoSalary").name, month=self.FROM)

	def test_standard_payslip_is_the_payslip(self):
		"""The official layout: PAYE and the AIDS levy split out of HRMS's one Income Tax line."""
		from erp_overrides.payslip import STANDARD_PAYSLIP, employee_format

		if not frappe.db.exists("Print Format", STANDARD_PAYSLIP):
			self.skipTest("run the payslip_standard_2026_10 patch first")
		self.assertEqual(employee_format(), STANDARD_PAYSLIP)
		emp = make_employee("Official")
		row = self.price(emp.name, "net", 300)
		hr.save_salaries(self.STRUCTURE, self.FROM, [{"employee": emp.name, "base": row["base"], "agreed_net": 300}], self.SLAB)
		html = hr.preview_payslip(emp.name, month=self.FROM)["html"]
		tax = next(l["amount"] for l in row["lines"] if l["component"] == "Income Tax")
		paye = round(tax / 1.03, 2)
		for text in ("PAYSLIP", emp.employee_name, "Taxable Income", "AIDS Levy", "NET PAY", "$300.00",
		             f"${paye:,.2f}", f"${round(tax - paye, 2):,.2f}", f"${row['base']:,.2f}"):
			self.assertIn(text, html)

	def test_payslip_format_is_what_employees_get(self):
		from erp_overrides.api import app_settings
		from erp_overrides.payslip import FIELD, employee_format

		if not frappe.get_meta("Payroll Settings").has_field(FIELD):
			self.skipTest("run the payslip_format_2026_10 patch first")
		before = frappe.db.get_single_value("Payroll Settings", FIELD)
		self.addCleanup(lambda: frappe.get_single("Payroll Settings").update({FIELD: before}).save())
		# HRMS's own formats differ by branch (version-16: Compact/Classic…, master: Standard/Year to Date…)
		other = frappe.db.get_value("Print Format", {"doc_type": "Salary Slip", "standard": "Yes", "disabled": 0}, "name")
		app_settings.save_settings("hr", [{"doctype": "Payroll Settings", "fieldname": FIELD, "value": other}])
		self.assertEqual(employee_format(), other)
		app_settings.save_settings("hr", [{"doctype": "Payroll Settings", "fieldname": FIELD, "value": None}])
		self.assertEqual(employee_format(), "Standard")
		with self.assertRaisesRegex(frappe.ValidationError, "isn't a Salary Slip print format"):
			app_settings.save_settings("hr", [{"doctype": "Payroll Settings", "fieldname": FIELD,
			                                   "value": frappe.db.get_value("Print Format", {"doc_type": "Sales Invoice"})}])

	def test_bad_amount_comes_back_as_a_row_error(self):
		emp = make_employee("Zero")
		row = hr.price_salaries(self.STRUCTURE, self.FROM, [{"employee": emp.name, "mode": "net", "amount": 0}], self.SLAB)[0]
		self.assertIn("error", row)

	def test_resave_replaces_and_agreed_net_drift_is_flagged(self):
		emp = make_employee("Drift")
		first = self.price(emp.name, "net", 700)
		hr.save_salaries(self.STRUCTURE, self.FROM, [{"employee": emp.name, "base": first["base"], "agreed_net": 700}], self.SLAB)
		again = hr.save_salaries(self.STRUCTURE, self.FROM, [{"employee": emp.name, "base": first["base"] + 50, "agreed_net": 700}], self.SLAB)
		self.assertEqual((again["created"], again["replaced"]), (0, 1))
		self.assertEqual(frappe.db.count("Salary Structure Assignment", {"employee": emp.name, "docstatus": 1}), 1)
		self.slip_net(emp.name).submit()
		row = next(e for e in hr.get_salaries(self.FROM) if e.name == emp.name)
		self.assertTrue(row.drift and row.locked, row)
		self.assertIn("net_drift", {i["check"] for i in hr.get_health()["issues"] if i["employee"] == emp.name}) \
			if getdate(self.FROM) <= getdate() else None
		locked = hr.save_salaries(self.STRUCTURE, self.FROM, [{"employee": emp.name, "base": first["base"], "agreed_net": 700}], self.SLAB)
		self.assertEqual(len(locked["failed"]), 1)


def make_paid_structure(name="HRTest Structure"):
	"""A structure that pays something: Basic = base, a 4.5% pension, plus an employer line."""
	for comp, kind, abbr, extra in (("HRTest Basic", "Earning", "HTB", {}), ("HRTest Pension", "Deduction", "HTN", {}),
	                                ("HRTest Employer Pension", "Deduction", "HTE", {"do_not_include_in_total": 1})):
		if not frappe.db.exists("Salary Component", comp):
			frappe.get_doc(dict(doctype="Salary Component", salary_component=comp, salary_component_abbr=abbr, type=kind,
			                    **extra)).insert(ignore_permissions=True)
	ss = frappe.get_doc(dict(
		doctype="Salary Structure", name=name, company=company(), payroll_frequency="Monthly", currency="USD",
		is_active="Yes",
		earnings=[dict(salary_component="HRTest Basic", amount_based_on_formula=1, formula="base")],
		deductions=[dict(salary_component="HRTest Pension", amount_based_on_formula=1, formula="base * 0.045"),
		            dict(salary_component="HRTest Employer Pension", amount_based_on_formula=1, formula="base * 0.045",
		                 do_not_include_in_total=1)],
	)).insert(ignore_permissions=True)
	ss.submit()
	return ss.name


def make_slips(emp, structure, base, months):
	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

	frappe.db.set_value("Company", company(), "default_payroll_payable_account", payable_account())
	frappe.clear_document_cache("Company", company())
	ssa = frappe.get_doc(dict(doctype="Salary Structure Assignment", employee=emp.name, salary_structure=structure,
	                          company=company(), from_date=f"{months[0]}-01", base=base, currency="USD",
	                          income_tax_slab=tax_slab())).insert(ignore_permissions=True)
	ssa.submit()
	slips = []
	for month in months:
		slip = make_salary_slip(structure, employee=emp.name, posting_date=f"{month}-28")
		slip.insert(ignore_permissions=True)
		slip.submit()
		slips.append(slip)
	return slips


class TestPayReport(IntegrationTestCase):
	def test_totals_per_component_and_person(self):
		structure = make_paid_structure()
		emp = make_employee("Payslip", date_of_joining="2026-01-01")
		slips = make_slips(emp, structure, 1000, ["2026-08", "2026-09"])
		out = hr.get_pay_report("2026-08-01", "2026-09-30", employee=emp.name)
		row = out["rows"][0]
		self.assertEqual(len(row["slips"]), 2)
		self.assertIn("HRTest Basic", out["groups"]["earnings"])
		self.assertIn("HRTest Pension", out["groups"]["deductions"])
		self.assertIn("HRTest Employer Pension", out["groups"]["other"])
		self.assertAlmostEqual(row["amounts"]["HRTest Pension"], 2 * 1000 * 0.045)
		self.assertAlmostEqual(row["total_deduction"], sum(s.total_deduction for s in slips))
		self.assertAlmostEqual(row["net_pay"], sum(s.net_pay for s in slips))
		self.assertAlmostEqual(row["net_pay"], row["gross_pay"] - row["total_deduction"])
		self.assertEqual(hr.get_pay_report("2026-10-01", "2026-10-31", employee=emp.name)["rows"], [])

	def test_pay_report_is_hr_only(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				hr.get_pay_report("2026-01-01", "2026-12-31")
		finally:
			frappe.set_user("Administrator")
