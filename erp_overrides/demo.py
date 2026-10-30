# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt

"""A demo company with fictional data, so every app has something to show.

On a fresh site with erpnext, hrms and erp_overrides installed:

    bench --site demo.localhost execute erp_overrides.demo.seed

Runs the setup wizard (company "Demo Trading Ltd", USD, Zimbabwe), adds a small
numbered chart, payroll, leave and accounts settings, then customers,
suppliers, items, a sales pipeline at every stage, nine employees with logins and
approvers, leave, a payroll run, bi-weekly reviews, bank lines and petty cash.
Every demo user's password is ``demo1234``. Every name and figure is made up.

Re-running skips what already exists.
"""

import random

import frappe
from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate, nowdate

COMPANY = "Demo Trading Ltd"
ABBR = "DTL"
CURRENCY = "USD"
PASSWORD = "demo1234"

# (number, name, parent, is_group, account type[, currency])
ACCOUNTS = [
	("2100", "Payroll and Tax Liabilities", "Current Liabilities", 1, ""),
	("2150", "PAYE Payable", "2100", 0, "Tax"),
	("2160", "Pension Payable", "2100", 0, "Tax"),
	("2210", "Payroll Payable", "2100", 0, "Payable"),
	("2220", "Expense Claims Payable", "2100", 0, "Payable"),
	("2230", "Levy Payable", "2100", 0, "Tax"),
	("6400", "Operating Expenses", "Indirect Expenses", 1, ""),
	("6120", "Sales Commission", "6400", 0, "Expense Account"),
	("6405", "Salaries and Wages", "6400", 0, "Expense Account"),
	("6545", "Cash Over and Short", "6400", 0, "Expense Account"),
	("6280", "Internet", "6400", 0, "Expense Account"),
	("6460", "Telephone", "6400", 0, "Expense Account"),
	("6510", "Bank Charges", "6400", 0, "Expense Account"),
	("6540", "Other Expense", "6400", 0, "Expense Account"),
	("6580", "Transaction Tax", "6400", 0, "Tax"),
	("6700", "Meals and Entertainment", "6400", 0, "Expense Account"),
	("6740", "Medical", "6400", 0, "Expense Account"),
	("6800", "Transport", "6400", 0, "Expense Account"),
	("6810", "Travel", "6400", 0, "Expense Account"),
	("1110", "Main Bank USD", "Bank Accounts", 0, "Bank"),
	("1120", "Main Bank ZWG", "Bank Accounts", 0, "Bank", "ZWG"),
	("1200", "Petty Cash", "Cash In Hand", 0, "Cash"),
	("1290", "Temporary Opening - ZWG", "Current Assets", 0, "Temporary", "ZWG"),
	("4110", "Sales - Computers", "Direct Income", 0, "Income Account"),
	("4120", "Sales - Networking", "Direct Income", 0, "Income Account"),
	("4130", "Sales - Printers and UPS", "Direct Income", 0, "Income Account"),
	("4200", "Training and Certification", "Direct Income", 0, "Income Account"),
	("5110", "Cost of Sales - Computers", "Direct Expenses", 0, "Cost of Goods Sold"),
	("5120", "Cost of Sales - Networking", "Direct Expenses", 0, "Cost of Goods Sold"),
	("5130", "Cost of Sales - Printers and UPS", "Direct Expenses", 0, "Cost of Goods Sold"),
]

# name: (department, designation, gender, date of birth, joined, monthly net pay)
STAFF = {
	"Grace Dube": ("Management", "Managing Director", "Female", "1979-03-14", "2018-02-01", 3200),
	"Tinashe Banda": ("Sales", "Sales Manager", "Male", "1986-07-22", "2019-05-06", 1900),
	"Rumbi Phiri": ("Sales", "Account Manager", "Female", "1993-11-02", "2022-01-10", 1100),
	"Farai Ncube": ("Sales", "Account Manager", "Male", "1995-04-18", "2023-08-01", 1000),
	"Peter Mlambo": ("Operations", "Operations Manager", "Male", "1984-09-30", "2019-09-02", 1800),
	"Chipo Sibanda": ("Operations", "Engineer", "Female", "1996-01-25", "2024-02-12", 950),
	"Ruth Mutasa": ("Human Resources", "HR Officer", "Female", "1990-06-08", "2021-03-15", 1200),
	"Daniel Zulu": ("Accounts", "Finance Manager", "Male", "1982-12-11", "2020-01-06", 2000),
	"Lindiwe Khumalo": ("Accounts", "Accounts Clerk", "Female", "1998-08-19", "2025-04-01", 800),
}

# login: roles
USER_ROLES = {
	"grace@example.com": ["System Manager", "Sales Manager", "HR Manager", "Accounts Manager"],
	"tinashe@example.com": ["Sales Manager", "Sales User"],
	"rumbi@example.com": ["Sales User"],
	"farai@example.com": ["Sales User"],
	"peter@example.com": ["Purchase Manager", "Stock User"],
	"chipo@example.com": ["Stock User"],
	"ruth@example.com": ["HR Manager", "HR User"],
	"daniel@example.com": ["Accounts Manager", "Accounts User"],
	"lindiwe@example.com": ["Accounts User"],
}

CUSTOMERS = [
	("Riverside Clinic", "Commercial"), ("Kopje Logistics", "Commercial"), ("Msasa Engineering", "Commercial"),
	("Highveld Schools Trust", "Non Profit"), ("Baobab Insurance", "Commercial"), ("Lakeview Hotel", "Commercial"),
]
SUPPLIERS = [("Northgate Distributors", "Hardware"), ("Cloudline Networks", "Hardware"), ("Certify Academy", "Services")]

# Payroll: a monthly structure whose gross is all Basic, an income tax slab (example
# monthly USD bands, with a 3% levy charged on the tax), a capped pension deduction that comes off before tax, and an
# employer levy that shows on the payslip but isn't deducted.
STRUCTURE = "Staff 2026"
SLAB = "Income Tax USD 2026"
BANDS = [(0, 100, 0), (100, 300, 20), (300, 1000, 25), (1000, 2000, 30), (2000, 3000, 35), (3000, 0, 40)]
PENSION = "Pension (Capped)"
LEVY = "Employer Levy"
# component: (abbr, type, account number, extra fields)
COMPONENTS = {
	"Basic": ("B", "Earning", "6405", {"is_tax_applicable": 1}),
	"Income Tax": ("IT", "Deduction", "2150", {"variable_based_on_taxable_salary": 1, "depends_on_payment_days": 0}),
	PENSION: ("PEN", "Deduction", "2160", {"exempted_from_income_tax": 1}),
	LEVY: ("LEVY", "Deduction", "2230", {"do_not_include_in_total": 1, "do_not_include_in_accounts": 1}),
	"Housing": ("HSE", "Earning", "6405", {"is_tax_applicable": 1}),
	"Transport": ("TR", "Earning", "6800", {"is_tax_applicable": 1}),
}
LEAVE = {"Vacation Leave": 20, "Sick Leave": 30, "Casual Leave": 10}
LEAVE_POLICY = "Standard Leave 2026"

# item: (group, rate, buying rate, stock item)
ITEMS = {
	"Laptop 14in Core i7 16GB": ("Laptops & Desktops", 1150, 940, 1),
	"Desktop Core i5 8GB": ("Laptops & Desktops", 720, 580, 1),
	"24-port Gigabit Switch": ("Networking Equipment", 410, 320, 1),
	"Wi-Fi 6 Access Point": ("Networking Equipment", 230, 170, 1),
	"Laser Printer A4": ("Printers, UPS & Accessories", 380, 300, 1),
	"UPS 1500VA": ("Printers, UPS & Accessories", 260, 195, 1),
	"Cloud Fundamentals Course": ("Training", 450, 300, 0),
	"Project Management Course": ("Training", 650, 420, 0),
	"Certification Exam Voucher": ("Training", 300, 240, 0),
	"Network Installation (per day)": ("Services", 180, 0, 0),
}
GROUP_ACCOUNTS = {
	"Laptops & Desktops": ("4110", "5110"), "Networking Equipment": ("4120", "5120"),
	"Printers, UPS & Accessories": ("4130", "5130"), "Training": ("4200", None), "Services": ("4200", None),
}


def seed():
	random.seed(7)
	frappe.flags.mute_emails = True
	_setup_wizard()
	_accounts()
	_rates()
	_settings()
	_parties()
	_items()
	_users_and_staff()
	_bank()
	_hr()
	_sales()
	_buying()
	frappe.db.commit()
	print("Demo data ready. Log in as Administrator, or as any of", ", ".join(USER_ROLES), "with the password", PASSWORD)


def _log(message):
	print(message)


def _setup_wizard():
	if frappe.db.exists("Company", COMPANY):
		return
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = getdate().year
	setup_complete(dict(
		language="English", country="Zimbabwe", timezone="Africa/Harare", currency=CURRENCY,
		full_name="Demo Admin", email="admin@example.com", password=PASSWORD,
		company_name=COMPANY, company_abbr=ABBR, chart_of_accounts="Standard",
		fy_start_date=f"{year}-01-01", fy_end_date=f"{year}-12-31", setup_demo=0,
	))
	frappe.db.set_single_value("System Settings", "enable_password_policy", 0)
	_log(f"Company {COMPANY} created")


def _account(number):
	return frappe.db.get_value("Account", {"company": COMPANY, "account_number": number}, "name")


def _accounts():
	if not frappe.db.exists("Currency", "ZWG"):
		frappe.get_doc(dict(doctype="Currency", currency_name="ZWG", symbol="ZiG", fraction="Cent",
		                    fraction_units=100, enabled=1)).insert(ignore_permissions=True)
	frappe.db.set_value("Currency", "ZWG", "enabled", 1)
	for number, name, parent, is_group, account_type, *currency in ACCOUNTS:
		if _account(number):
			continue
		parent_name = _account(parent) or f"{parent} - {ABBR}"
		frappe.get_doc(dict(
			doctype="Account", company=COMPANY, account_number=number, account_name=name, parent_account=parent_name,
			is_group=is_group, account_type=account_type, account_currency=currency[0] if currency else CURRENCY,
		)).insert(ignore_permissions=True)
	frappe.db.set_value("Company", COMPANY, "default_expense_account", _account("6540"))


def _settings():
	"""The app's own setup steps (skipped on a fresh install, so run here) and the demo's settings."""
	from erp_overrides.patches.v1_0 import (
		launcher_landing_2026_10, payslip_standard_2026_10, reviews_setup_2026_10, supplier_terms_2026_10,
		three_way_2026_10,
	)

	for module in (launcher_landing_2026_10, supplier_terms_2026_10, three_way_2026_10, reviews_setup_2026_10,
	               payslip_standard_2026_10):
		module.execute()
	frappe.db.set_single_value("Selling Settings", "cust_master_name", "Customer Name")
	frappe.db.set_single_value("Buying Settings", "supp_master_name", "Supplier Name")
	frappe.db.set_value("Company", COMPANY, {
		"default_payroll_payable_account": _account("2210"),
		"default_expense_claim_payable_account": _account("2220"),
	})
	# Accounts app: one petty cash box, the cash count account, reconciliation defaults
	settings = frappe.get_single("App Accounts Settings")
	if not settings.petty_cash_boxes:
		settings.append("petty_cash_boxes", dict(account=_account("1200")))
	settings.cash_over_short_account = settings.cash_over_short_account or _account("6545")
	settings.transfer_tolerance = settings.transfer_tolerance or 3
	settings.stale_line_days = settings.stale_line_days or 60
	settings.save(ignore_permissions=True)


def _payroll_setup():
	for comp, (abbr, kind, number, extra) in COMPONENTS.items():
		if not frappe.db.exists("Salary Component", comp):
			frappe.get_doc(dict(doctype="Salary Component", salary_component=comp, salary_component_abbr=abbr,
			                    type=kind, **extra, accounts=[dict(company=COMPANY, account=_account(number))])).insert()
			continue
		# Frappe HR ships some (Basic, Income Tax): give them the same settings and account
		doc = frappe.get_doc("Salary Component", comp)
		doc.update(extra)
		if not any(a.company == COMPANY for a in doc.accounts):
			doc.append("accounts", dict(company=COMPANY, account=_account(number)))
		doc.save()
	if not frappe.db.exists("Income Tax Slab", {"name": SLAB, "docstatus": 1}):
		# HRMS taxes a band as (income - from + 1), so each band after the first starts at its edge + 1
		frappe.get_doc(dict(
			doctype="Income Tax Slab", __newname=SLAB, effective_from="2026-01-01", currency=CURRENCY, company=COMPANY,
			allow_tax_exemption=1,
			slabs=[dict(from_amount=lo + 1 if lo else 0, to_amount=hi, percent_deduction=pct) for lo, hi, pct in BANDS],
			other_taxes_and_charges=[dict(description="AIDS levy", percent=3)],
		)).insert().submit()
	# monthly payroll periods, so tax is worked out month by month
	year = getdate().year
	for y in (year, year + 1):
		for m in range(1, 13):
			start = getdate(f"{y}-{m:02d}-01")
			if not frappe.db.exists("Payroll Period", {"company": COMPANY, "start_date": start}):
				frappe.get_doc(dict(doctype="Payroll Period", __newname=f"{COMPANY} {y}-{m:02d}", company=COMPANY,
				                    start_date=start, end_date=get_last_day(start))).insert()
	if not frappe.db.exists("Salary Structure", {"name": STRUCTURE, "docstatus": 1}):
		frappe.get_doc(dict(
			doctype="Salary Structure", __newname=STRUCTURE, company=COMPANY, payroll_frequency="Monthly",
			currency=CURRENCY, is_active="Yes",
			earnings=[dict(salary_component="Basic", abbr="B", amount_based_on_formula=1, formula="base",
			               depends_on_payment_days=1)],
			deductions=[
				dict(salary_component=PENSION, abbr="PEN", amount_based_on_formula=1,
				     formula="base * 0.05 if base * 0.05 < 40 else 40", depends_on_payment_days=1),
				dict(salary_component="Income Tax", abbr="IT", variable_based_on_taxable_salary=1),
				dict(salary_component=LEVY, abbr="LEVY", amount_based_on_formula=1, formula="base * 0.01",
				     do_not_include_in_total=1, do_not_include_in_accounts=1),
			],
		)).insert().submit()


def _leave_setup():
	from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import create_assignment

	for leave_type, days in LEAVE.items():
		if not frappe.db.exists("Leave Type", leave_type):
			frappe.get_doc(dict(doctype="Leave Type", leave_type_name=leave_type, max_leaves_allowed=days)).insert()
	year = getdate().year
	start, end = getdate(f"{year}-01-01"), getdate(f"{year}-12-31")
	period = frappe.db.get_value("Leave Period", {"company": COMPANY, "from_date": start}) or frappe.get_doc(dict(
		doctype="Leave Period", company=COMPANY, from_date=start, to_date=end, is_active=1)).insert().name
	policy = frappe.db.get_value("Leave Policy", {"title": LEAVE_POLICY, "docstatus": 1})
	if not policy:
		doc = frappe.get_doc(dict(doctype="Leave Policy", title=LEAVE_POLICY, leave_policy_details=[
			{"leave_type": lt, "annual_allocation": days} for lt, days in LEAVE.items()])).insert()
		doc.submit()
		policy = doc.name
	for emp in frappe.get_all("Employee", filters={"company": COMPANY, "status": "Active"}, pluck="name"):
		if frappe.db.exists("Leave Policy Assignment", {"employee": emp, "docstatus": 1}):
			continue
		try:
			create_assignment(emp, frappe._dict(leave_policy=policy, assignment_based_on="Leave Period",
			                                    leave_period=period, effective_from=start, effective_to=end)).submit()
		except frappe.ValidationError as e:  # already holds allocations for the period
			_log(f"Leave policy not assigned to {emp}: {e}")


def _parties():
	for name, group in CUSTOMERS:
		if not frappe.db.exists("Customer", name):
			frappe.get_doc(dict(doctype="Customer", customer_name=name, customer_type="Company",
			                    customer_group=group if frappe.db.exists("Customer Group", group) else "Commercial",
			                    territory="All Territories")).insert()
	for name, group in SUPPLIERS:
		if not frappe.db.exists("Supplier Group", group):
			frappe.get_doc(dict(doctype="Supplier Group", supplier_group_name=group, parent_supplier_group="All Supplier Groups")).insert()
		if not frappe.db.exists("Supplier", name):
			frappe.get_doc(dict(doctype="Supplier", supplier_name=name, supplier_group=group,
			                    payment_terms=frappe.db.exists("Payment Terms Template", "30 days"))).insert()


def _items():
	from erp_overrides.stock_light import HARDWARE

	warehouse = f"Stores - {ABBR}"
	if not frappe.db.exists("Item Group", HARDWARE):
		frappe.get_doc(dict(doctype="Item Group", item_group_name=HARDWARE, parent_item_group="All Item Groups",
		                    is_group=1)).insert()
	for group, (income, cogs) in GROUP_ACCOUNTS.items():
		if not frappe.db.exists("Item Group", group):
			parent = HARDWARE if cogs else "All Item Groups"
			frappe.get_doc(dict(doctype="Item Group", item_group_name=group, parent_item_group=parent,
			                    item_group_defaults=[dict(company=COMPANY, default_warehouse=warehouse,
			                                              income_account=_account(income),
			                                              expense_account=_account(cogs) if cogs else None)])).insert()
	for code, (group, rate, buying, stock) in ITEMS.items():
		if not frappe.db.exists("Item", code):
			frappe.get_doc(dict(doctype="Item", item_code=code, item_name=code, item_group=group, stock_uom="Nos",
			                    is_stock_item=stock, allow_negative_stock=stock, include_item_in_manufacturing=0)).insert()
		for price_list, value in (("Standard Selling", rate), ("Standard Buying", buying)):
			if value and not frappe.db.exists("Item Price", {"item_code": code, "price_list": price_list}):
				frappe.get_doc(dict(doctype="Item Price", item_code=code, price_list=price_list, price_list_rate=value)).insert()


def _department(name):
	full = f"{name} - {ABBR}"
	if not frappe.db.exists("Department", full):
		frappe.get_doc(dict(doctype="Department", department_name=name, company=COMPANY,
		                    parent_department="All Departments")).insert()
	return full


def _users_and_staff():
	logins = dict(zip(STAFF, USER_ROLES))
	for name, (dept, designation, gender, dob, joined, _net) in STAFF.items():
		email = logins[name]
		first, last = name.split(" ", 1)
		if not frappe.db.exists("User", email):
			user = frappe.get_doc(dict(doctype="User", email=email, first_name=first, last_name=last,
			                           send_welcome_email=0, new_password=PASSWORD))
			user.append_roles(*USER_ROLES[email], "Employee")
			user.insert(ignore_permissions=True)
		if not frappe.db.exists("Designation", designation):
			frappe.get_doc(dict(doctype="Designation", designation_name=designation)).insert()
		if not frappe.db.exists("Employee", {"employee_name": name}):
			frappe.get_doc(dict(doctype="Employee", first_name=first, last_name=last, gender=gender,
			                    date_of_birth=dob, date_of_joining=joined, company=COMPANY,
			                    department=_department(dept), designation=designation, status="Active",
			                    user_id=email, company_email=email, salary_mode="Bank", bank_name="Main Bank",
			                    bank_ac_no=f"10{random.randint(10000000, 99999999)}")).insert()
	from erp_overrides import hrms_setup

	hrms_setup.run(apply=1)


def _employee(name):
	return frappe.db.get_value("Employee", {"employee_name": name}, "name")


def _hr():
	_leave_setup()
	_payroll_setup()
	today = getdate()
	# salaries: base worked out roughly from the agreed net
	for name, (*_, net) in STAFF.items():
		emp = _employee(name)
		if not frappe.db.exists("Salary Structure Assignment", {"employee": emp, "docstatus": 1}):
			ssa = frappe.get_doc(dict(doctype="Salary Structure Assignment", employee=emp, company=COMPANY,
			                          salary_structure=STRUCTURE, currency=CURRENCY,
			                          from_date=get_first_day(add_months(today, -3)), base=round(net * 1.3, -1),
			                          income_tax_slab=SLAB,
			                          payroll_payable_account=_account("2210")))
			ssa.insert()
			ssa.submit()
	# leave: some taken, some waiting for a manager
	leave = [
		("Rumbi Phiri", "Vacation Leave", 12, 3, "Approved"), ("Farai Ncube", "Sick Leave", -20, 2, "Approved"),
		("Chipo Sibanda", "Vacation Leave", 9, 5, "Open"), ("Lindiwe Khumalo", "Casual Leave", 4, 1, "Open"),
		("Peter Mlambo", "Vacation Leave", 25, 4, "Open"), ("Tinashe Banda", "Vacation Leave", -40, 5, "Approved"),
	]
	for name, leave_type, offset, days, status in leave:
		emp = _employee(name)
		start = add_days(today, offset)
		if frappe.db.exists("Leave Application", {"employee": emp, "from_date": start}):
			continue
		la = frappe.get_doc(dict(doctype="Leave Application", employee=emp, leave_type=leave_type, from_date=start,
		                         to_date=add_days(start, days - 1), status=status, description="Demo leave",
		                         leave_approver=frappe.db.get_value("Employee", emp, "leave_approver")))
		la.flags.ignore_permissions = True
		try:
			la.insert()
			if status == "Approved":
				la.submit()
		except Exception as e:
			_log(f"Leave for {name} skipped: {e}")
	# last month's payroll, submitted, so the payroll pages have a run to show
	start = get_first_day(add_months(today, -1))
	if not frappe.db.exists("Payroll Entry", {"start_date": start, "company": COMPANY}):
		pe = frappe.get_doc(dict(doctype="Payroll Entry", company=COMPANY, posting_date=get_last_day(start),
		                         payroll_frequency="Monthly", start_date=start, end_date=get_last_day(start),
		                         currency=CURRENCY, exchange_rate=1, payroll_payable_account=_account("2210"),
		                         cost_center=f"Main - {ABBR}", payment_account=_bank_account_ledger()))
		pe.insert()
		pe.fill_employee_details()
		pe.save()
		try:
			pe.create_salary_slips()
		except Exception as e:
			_log(f"Payroll run left as a draft: {e}")
	# a review schedule for the sales team
	_reviews()


def _reviews():
	from erp_overrides import reviews

	if not frappe.db.exists("Review Schedule", {"title": "Sales team check-ins"}):
		_review_schedule()
	# what the daily job would have opened over the last month
	for offset in (-28, -14, 0):
		reviews.open_reviews(add_days(nowdate(), offset))


def _review_schedule():
	meta = frappe.get_meta("Review Schedule")
	doc = frappe.new_doc("Review Schedule")
	values = dict(title="Sales team check-ins", review_form="Bi-weekly check-in", frequency="Every 2 weeks",
	              first_period_start=add_days(get_first_day(nowdate()), -28), window_days=5, active=1, company=COMPANY)
	doc.update({k: v for k, v in values.items() if meta.has_field(k)})
	table = next((f for f in meta.get_table_fields() if f.options == "Review Schedule Employee"), None)
	if table:
		for name in ("Rumbi Phiri", "Farai Ncube"):
			doc.append(table.fieldname, {"employee": _employee(name)})
	try:
		doc.insert(ignore_permissions=True)
	except Exception as e:
		_log(f"Review schedule skipped: {e}")


def _sales():
	today = getdate()
	if frappe.db.count("Lead"):
		leads = []
	else:
		leads = [("Tatenda Gumbo", "Granite Mining Co"), ("Alice Mhlanga", "Sunrise Bakeries"), ("Brian Chuma", "Eastgate Pharmacy"),
	         ("Nomsa Dlamini", "Valley Farms"), ("Kuda Marufu", "Summit Law Chambers")]
	for i, (person, org) in enumerate(leads):
		first, last = person.split()
		frappe.get_doc(dict(doctype="Lead", first_name=first, last_name=last, company_name=org,
		                    email_id=f"{first.lower()}@example.org", status=("Lead", "Open", "Replied", "Interested", "Lead")[i],
		                    lead_owner="tinashe@example.com" if i % 2 else "rumbi@example.com")).insert()

	def rows(*codes):
		return [dict(item_code=c, qty=q, rate=ITEMS[c][1]) for c, q in codes]

	deals = [
		("Riverside Clinic", rows(("Laptop 14in Core i7 16GB", 6), ("UPS 1500VA", 6)), "order+invoice+paid"),
		("Kopje Logistics", rows(("24-port Gigabit Switch", 2), ("Wi-Fi 6 Access Point", 8), ("Network Installation (per day)", 3)), "order+invoice"),
		("Highveld Schools Trust", rows(("Desktop Core i5 8GB", 20), ("Laser Printer A4", 4)), "order"),
		("Baobab Insurance", rows(("Project Management Course", 5), ("Certification Exam Voucher", 5)), "order+invoice+paid"),
		("Msasa Engineering", rows(("Cloud Fundamentals Course", 4)), "quote"),
		("Lakeview Hotel", rows(("Wi-Fi 6 Access Point", 12), ("Network Installation (per day)", 2)), "draft"),
	]
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
	from erpnext.selling.doctype.quotation.quotation import make_sales_order
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	for n, (customer, items, stage) in enumerate(deals):
		if frappe.db.exists("Quotation", {"party_name": customer, "docstatus": ["<", 2]}):
			continue
		date = add_days(today, -45 + n * 7)
		q = frappe.get_doc(dict(doctype="Quotation", quotation_to="Customer", party_name=customer, company=COMPANY,
		                        transaction_date=date, valid_till=add_days(today, 30), currency=CURRENCY, items=items))
		q.insert()
		if stage == "draft":
			continue
		q.submit()
		if stage == "quote":
			continue
		so = make_sales_order(q.name)
		so.delivery_date = add_days(date, 14)
		so.transaction_date = date
		so.insert()
		so.submit()
		if "invoice" not in stage:
			continue
		si = make_sales_invoice(so.name)
		si.posting_date = add_days(date, 3)
		si.set_posting_time = 1
		si.due_date = add_days(si.posting_date, 30)
		si.insert()
		si.submit()
		if "paid" in stage:
			pe = get_payment_entry("Sales Invoice", si.name, bank_account=_bank_account_ledger())
			pe.reference_no, pe.reference_date = f"TRF{1000 + n}", add_days(si.posting_date, 10)
			pe.posting_date = pe.reference_date
			pe.insert()
			pe.submit()


def _buying():
	if frappe.db.count("Purchase Order", {"company": COMPANY}):
		return
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	today = getdate()
	orders = [
		("Northgate Distributors", [("Laptop 14in Core i7 16GB", 6), ("UPS 1500VA", 6)], True),
		("Cloudline Networks", [("24-port Gigabit Switch", 2), ("Wi-Fi 6 Access Point", 8)], False),
	]
	for supplier, items, received in orders:
		po = frappe.get_doc(dict(doctype="Purchase Order", supplier=supplier, company=COMPANY, currency=CURRENCY,
		                         transaction_date=add_days(today, -30), schedule_date=add_days(today, -20),
		                         items=[dict(item_code=c, qty=q, rate=ITEMS[c][2], warehouse=f"Stores - {ABBR}")
		                                for c, q in items]))
		po.insert()
		po.submit()
		if received:
			pr = make_purchase_receipt(po.name)
			pr.insert()
			pr.submit()


def _bank_account_ledger():
	return _account("1110")


def _rates():
	"""Illustrative daily USD/ZWG rates (both ways) from July, so ZWG lines and the Rates page have data."""
	day, end = getdate(f"{getdate().year}-07-01"), getdate()
	rate = 26.70
	while day <= end:
		if day.weekday() < 5:
			rate = round(rate + random.uniform(-0.03, 0.04), 4)
			for a, b, r in (("USD", "ZWG", rate), ("ZWG", "USD", round(1 / rate, 6))):
				if not frappe.db.exists("Currency Exchange", {"date": day, "from_currency": a, "to_currency": b}):
					frappe.get_doc(dict(doctype="Currency Exchange", date=day, from_currency=a, to_currency=b,
					                    exchange_rate=r, for_buying=1, for_selling=1)).insert(ignore_permissions=True)
		day = add_days(day, 1)


def _bank():
	if not frappe.db.exists("Bank", "Main Bank"):
		frappe.get_doc(dict(doctype="Bank", bank_name="Main Bank")).insert()
	for account_name, number, no in (("Main Bank USD", "1110", "1000200030"), ("Main Bank ZWG", "1120", "1000200040")):
		if not frappe.db.exists("Bank Account", f"{account_name} - Main Bank"):
			frappe.get_doc(dict(doctype="Bank Account", account_name=account_name, bank="Main Bank", is_company_account=1,
			                    company=COMPANY, account=_account(number), bank_account_no=no)).insert()
	name = "Main Bank USD - Main Bank"
	# two starter rules, so the Reconcile screen suggests where charges and tax go
	for rule_name, priority, pattern, number in (
		("Bank charges", 10, r"SERVICE CHARGE|SMS ALERTS? CHARGE|BANK CHARGE", "6510"),
		("Transaction tax", 20, r"MONEY TRANSFER TAX|TRANSACTION TAX", "6580"),
	):
		if not frappe.db.exists("Bank Transaction Rule", rule_name):
			frappe.get_doc(dict(doctype="Bank Transaction Rule", rule_name=rule_name, priority=priority, company=COMPANY,
			                    transaction_type="Withdrawal", classify_as="Bank Entry", bank_entry_type="Single Account",
			                    account=_account(number), description_rules=[dict(check="Regex", value=pattern)],
			                    )).insert(ignore_permissions=True)
	if frappe.db.count("Bank Transaction", {"bank_account": name}):
		from erpnext.accounts.doctype.bank_transaction_rule.bank_transaction_rule import _run_rule_evaluation

		_run_rule_evaluation(force_evaluate=True)
		return
	today = getdate()
	lines = [
		(-35, 0, 7820, "RTGS CREDIT RIVERSIDE CLINIC INV PAYMENT"),
		(-28, 12.5, 0, "SERVICE CHARGE"),
		(-21, 0, 4987.5, "TRANSFER FROM BAOBAB INSURANCE"),
		(-18, 2.3, 0, "SMS ALERTS CHARGE"),
		(-14, 640, 0, "POS PURCHASE OFFICE SUPPLIES"),
		(-10, 0, 1500, "CASH DEPOSIT BRANCH"),
		(-6, 11.8, 0, "INTERMEDIATED MONEY TRANSFER TAX"),
		(-3, 0, 2610, "TRANSFER FROM KOPJE LOGISTICS"),
	]
	for offset, withdrawal, deposit, narration in lines:
		bt = frappe.get_doc(dict(doctype="Bank Transaction", date=add_days(today, offset), bank_account=name,
		                         company=COMPANY, currency=CURRENCY, withdrawal=withdrawal, deposit=deposit,
		                         description=narration, reference_number=f"FT{abs(offset):03d}{int(deposit or withdrawal)}"))
		bt.insert()
		bt.submit()
	from erpnext.accounts.doctype.bank_transaction_rule.bank_transaction_rule import _run_rule_evaluation

	_run_rule_evaluation(force_evaluate=True)
