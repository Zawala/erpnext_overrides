# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Which payslip layout employees get.

Frappe HR's /hrms "Download PDF" and the payslip emailed on submit both print with
Salary Slip's default print format ("Standard" when none is set). HR picks it as
Payroll Settings → Payslip format (custom field, patch payslip_format_2026_10), and
saving Payroll Settings makes it that default.
"""
import frappe
from frappe import _
from frappe.utils import flt

FIELD = "payslip_print_format"


def employee_format():
	"""The print format employees' payslips come out in."""
	return frappe.get_meta("Salary Slip").default_print_format or "Standard"


def validate_payroll_settings(doc, method=None):
	pf = doc.meta.has_field(FIELD) and doc.get(FIELD)
	if pf and frappe.db.get_value("Print Format", pf, "doc_type") != "Salary Slip":
		frappe.throw(_("{0} isn't a Salary Slip print format.").format(pf))


def sync_default_format(doc, method=None):
	if not doc.meta.has_field(FIELD):  # before the patch has run
		return
	pf = doc.get(FIELD) or ""
	if (frappe.get_meta("Salary Slip").default_print_format or "") == pf:
		return
	sync_to(pf)


# ── "Standard Payslip": the official payslip layout ────────────────────────────

STANDARD_PAYSLIP = "Standard Payslip"
TEMPLATE = "templates/print_formats/standard_payslip.html"
# what the official payslip calls a component; anything else prints under its own name
LABELS = {"Basic": "Basic Salary", "Income Tax": "PAYE"}


def _label(component):
	return LABELS.get(component) or component


def _logo(company):
	"""The company's own logo (Company → Company Logo), embedded so wkhtmltopdf needn't fetch it."""
	import base64

	url = frappe.get_cached_value("Company", company, "company_logo")
	if not url:
		return None
	try:
		content = frappe.get_doc("File", {"file_url": url}).get_content()
	except Exception:
		return None
	mime = "image/png" if url.lower().endswith(".png") else "image/jpeg"
	return f"data:{mime};base64," + base64.b64encode(content).decode()


def _period(doc):
	from frappe.utils import get_first_day, get_last_day, getdate

	start, end = getdate(doc.start_date), getdate(doc.end_date)
	if start == get_first_day(start) and end == get_last_day(start):
		return start.strftime("%B %Y")
	return f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"


def _tax_charges(doc):
	"""[(label, percent)] charged on the tax itself (the AIDS levy), from the tax bands of the
	employee's salary assignment. HRMS puts them inside the Income Tax line."""
	slab = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": doc.employee, "salary_structure": doc.salary_structure, "docstatus": 1,
		 "from_date": ["<=", doc.start_date]}, "income_tax_slab", order_by="from_date desc")
	if not slab:
		return []
	# "AIDS levy" → "AIDS Levy": capitalise words, leave acronyms alone
	title = lambda s: " ".join(w if w.isupper() else w.capitalize() for w in s.split())  # noqa: E731
	return [(title(c.description), flt(c.percent))
	        for c in frappe.get_all("Income Tax Slab Other Charges", filters={"parent": slab},
	                                fields=["description", "percent"], order_by="idx") if flt(c.percent)]


def _cost_centre(doc):
	ssa = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": doc.employee, "docstatus": 1, "from_date": ["<=", doc.start_date]}, "name", order_by="from_date desc")
	cc = ssa and frappe.db.get_value("Employee Cost Center", {"parent": ssa}, "cost_center", order_by="percentage desc")
	if not cc:
		emp = frappe.db.get_value("Employee", doc.employee, ["payroll_cost_center", "department"], as_dict=True) or {}
		cc = emp.get("payroll_cost_center") or (emp.get("department") and frappe.db.get_value(
			"Department", emp["department"], "payroll_cost_center"))
	return cc and (frappe.db.get_value("Cost Center", cc, "cost_center_name") or cc)


def standard_payslip(doc):
	"""Everything the Standard Payslip prints, as display strings (jinja method)."""
	symbol = frappe.db.get_value("Currency", doc.currency, "symbol") or doc.currency or ""

	def money(v):
		v = flt(v, 2)
		return f"{'-' if v < 0 else ''}{symbol}{abs(v):,.2f}"

	emp = frappe.db.get_value(
		"Employee", doc.employee,
		["designation", "grade", "bank_name", "bank_ac_no", "health_insurance_provider", "health_insurance_no"]
		+ (["bank_branch"] if frappe.get_meta("Employee").has_field("bank_branch") else []), as_dict=True) or {}
	days = f"{flt(doc.payment_days):g} / {flt(doc.total_working_days):g}"

	earnings = [d for d in doc.earnings if flt(d.amount) and not d.statistical_component]
	deductions = [d for d in doc.deductions if flt(d.amount) and not d.statistical_component and not d.do_not_include_in_total]
	before_tax = [d for d in deductions if d.exempted_from_income_tax]
	tax = [d for d in deductions if d.variable_based_on_taxable_salary]
	other = [d for d in deductions if d not in before_tax and d not in tax]
	taxable = sum(flt(d.amount) for d in earnings if d.is_tax_applicable) - sum(flt(d.amount) for d in before_tax)

	rows = [dict(label=_label(d.salary_component), amount=money(d.amount)) for d in before_tax]
	if tax:
		rows.append(dict(label="Taxable Income", amount=money(taxable)))
	charges = _tax_charges(doc)
	for d in tax:
		# split the levy back out of the tax line: tax = paye × (1 + Σ levy%)
		total = flt(d.amount, 2)
		paye = total / (1 + sum(p for _, p in charges) / 100)
		levies = [(label, flt(paye * p / 100, 2)) for label, p in charges]
		rows.append(dict(label=_label(d.salary_component), amount=money(total - sum(a for _, a in levies))))
		rows += [dict(label=label, amount=money(a)) for label, a in levies]
	rows += [dict(label=_label(d.salary_component), amount=money(d.amount)) for d in other]

	medical = emp.get("health_insurance_provider")
	if medical and emp.get("health_insurance_no"):
		medical = f"{medical} ({emp['health_insurance_no']})"
	company = doc.company
	return frappe._dict(
		logo=_logo(company), company=company, period=_period(doc),
		details=[("Employee Name", doc.employee_name), ("Position", emp.get("designation") or "—"),
		         ("Grade", emp.get("grade") or "—"), ("Cost Centre", _cost_centre(doc) or "—"),
		         ("Days Worked / Total Days", days)],
		earnings=[dict(label=_label(d.salary_component), amount=money(d.amount)) for d in earnings],
		gross=money(doc.gross_pay), deductions=rows, total_deductions=money(doc.total_deduction),
		net=money(doc.net_pay),
		banking=[("Bank", emp.get("bank_name") or "—"), ("Bank Branch", emp.get("bank_branch") or "—"),
		         ("Bank Account Number", emp.get("bank_ac_no") or "—"), ("Medical Aid", medical or "Not enrolled")],
		# filled by HRMS when Payroll Settings shows leave balances on payslips
		leave=[(d.leave_type, f"{flt(d.used_leaves):g}", f"{flt(d.available_leaves):g}")
		       for d in doc.get("leave_details") or [] if flt(d.total_allocated_leaves) or flt(d.used_leaves)],
	)


def install_standard_payslip():
	"""The Standard Payslip print format (from the template file), Employee → Bank Branch, and
	Standard Payslip as the payslip employees get. Re-running refreshes the layout only."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	if not frappe.db.exists("DocType", "Salary Slip"):
		return  # HRMS isn't installed
	create_custom_fields({"Employee": [dict(
		fieldname="bank_branch", label="Bank Branch", fieldtype="Data", insert_after="bank_name",
		depends_on="eval:doc.salary_mode == 'Bank'")]})
	html = frappe.read_file(frappe.get_app_path("erp_overrides", TEMPLATE))
	if frappe.db.exists("Print Format", STANDARD_PAYSLIP):
		frappe.db.set_value("Print Format", STANDARD_PAYSLIP, {"html": html, "disabled": 0})
	else:
		frappe.get_doc(dict(
			doctype="Print Format", name=STANDARD_PAYSLIP, doc_type="Salary Slip", module="Erp Overrides",
			standard="No", custom_format=1, print_format_type="Jinja", html=html, disabled=0,
			margin_top=12.7, margin_bottom=12.7, margin_left=19.05, margin_right=19.05,  # the .docx's margins
		)).insert(ignore_permissions=True)
	if not frappe.get_meta("Payroll Settings").has_field(FIELD):  # a fresh install skips that patch too
		from erp_overrides.patches.v1_0.payslip_format_2026_10 import execute

		execute()
		frappe.clear_cache(doctype="Payroll Settings")
	settings = frappe.get_single("Payroll Settings")
	if settings.get(FIELD) != STANDARD_PAYSLIP:
		settings.set(FIELD, STANDARD_PAYSLIP)
		settings.flags.ignore_permissions = True
		settings.save()  # sync_default_format makes it Salary Slip's default
	elif frappe.get_meta("Salary Slip").default_print_format != STANDARD_PAYSLIP:
		sync_to(STANDARD_PAYSLIP)


def sync_to(pf):
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	make_property_setter("Salary Slip", None, "default_print_format", pf, "Data", for_doctype=True)
	frappe.clear_cache(doctype="Salary Slip")
