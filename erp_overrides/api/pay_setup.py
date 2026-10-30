# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Pay setup for the HR app (/hrms-admin/pay-setup): salary components, salary
structures and the PAYE bands, in plain language.

A structure row is edited as a choice — fixed amount, % of the salary, % with a
cap, from the tax bands, or an advanced formula — and turned into the HRMS fields
(`amount_based_on_formula`, `formula`, …) here. Employer costs (levies) are
deduction rows left out of the totals and the ledger.

HRMS locks a submitted structure or tax slab, and neither can be cancelled while
an assignment uses it. So one nobody uses is replaced in place, and one in use is
saved as a new version ("Staff 2026 (v2)") that people are then moved to
from a date (`move_people`): past payslips keep the old version.

Every edit can be priced first: `preview` submits the draft inside a savepoint,
works out a month's payslip with HRMS's own calculation, and rolls back.
"""
import ast
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, nowdate

from erp_overrides.api.hr import _company, _preview_slip, _priced, _require_hr, _tax_component, save_salaries

MANAGER_ROLES = ("HR Manager", "System Manager")
METHODS = ("fixed", "percent", "capped", "tax", "formula")
KINDS = ("earning", "deduction", "employer")
# what a formula may use besides the abbreviations above it (HRMS evaluates slip fields and these helpers)
FORMULA_NAMES = {
	"base", "variable", "gross_pay", "payment_days", "total_working_days", "leave_without_pay", "absent_days",
	"int", "float", "round", "rounded", "min", "max", "abs", "ceil", "floor", "flt", "getdate", "date",
	"get_first_day", "get_last_day", "True", "False", "None",
}
NUM = r"(\d+(?:\.\d+)?)"
PERCENT = re.compile(rf"^(base|gross_pay)(?:\s*\*\s*{NUM})?$")
CAPPED = re.compile(rf"^(base|gross_pay)\s*\*\s*{NUM}\s+if\s+\1\s*\*\s*{NUM}\s*<\s*{NUM}\s+else\s+{NUM}$")
VERSION = re.compile(r"\s*\(v(\d+)\)$")


def _require_manager():
	_require_hr()
	if not set(frappe.get_roles()) & set(MANAGER_ROLES):
		frappe.throw(_("Only an HR Manager can change pay setup."), frappe.PermissionError)


def _num(x):
	return f"{flt(x, 6):g}"


# ── Plain choices ↔ HRMS rows ────────────────────────────────────────────────

def from_row(d, parentfield):
	"""A Salary Detail row as the editor shows it."""
	kind = "earning" if parentfield == "earnings" else ("employer" if cint(d.do_not_include_in_total) else "deduction")
	row = dict(component=d.salary_component, abbr=d.abbr, kind=kind, method="formula", of="base", rate=None, cap=None,
	           amount=None, formula=(d.formula or "").strip(), condition=d.condition or "",
	           depends_on_payment_days=cint(d.depends_on_payment_days), is_tax_applicable=cint(d.is_tax_applicable),
	           exempted_from_income_tax=cint(d.exempted_from_income_tax))
	formula = " ".join(row["formula"].split())
	if cint(d.variable_based_on_taxable_salary):
		row["method"] = "tax"
	elif not cint(d.amount_based_on_formula):
		row.update(method="fixed", amount=flt(d.amount))
	elif m := CAPPED.match(formula):
		of, r1, r2, c1, c2 = m.groups()
		if r1 == r2 and flt(c1) == flt(c2):
			row.update(method="capped", of=of, rate=flt(flt(r1) * 100, 6), cap=flt(c1))
	elif m := PERCENT.match(formula):
		row.update(method="percent", of=m.group(1), rate=flt(flt(m.group(2) or 1) * 100, 6))
	return row


def to_row(r):
	"""Editor row → Salary Detail fields."""
	method = r.get("method")
	of = r.get("of") if r.get("of") in ("base", "gross_pay") else "base"
	out = dict(salary_component=r["component"], abbr=r.get("abbr"), condition=r.get("condition") or None,
	           amount_based_on_formula=0, formula=None, amount=0, variable_based_on_taxable_salary=0,
	           depends_on_payment_days=cint(r.get("depends_on_payment_days")),
	           is_tax_applicable=cint(r.get("is_tax_applicable")),
	           exempted_from_income_tax=cint(r.get("exempted_from_income_tax")),
	           do_not_include_in_total=1 if r.get("kind") == "employer" else 0,
	           do_not_include_in_accounts=1 if r.get("kind") == "employer" else 0)
	if method == "fixed":
		out["amount"] = flt(r.get("amount"), 2)
	elif method == "percent":
		rate = flt(r.get("rate")) / 100
		out.update(amount_based_on_formula=1, formula=of if rate == 1 else f"{of} * {_num(rate)}")
	elif method == "capped":
		rate, cap = _num(flt(r.get("rate")) / 100), f"{flt(r.get('cap')):.2f}"
		out.update(amount_based_on_formula=1, formula=f"{of} * {rate} if {of} * {rate} < {cap} else {cap}")
	elif method == "tax":
		out.update(variable_based_on_taxable_salary=1, depends_on_payment_days=0)
	else:
		out.update(amount_based_on_formula=1, formula=(r.get("formula") or "").strip())
	return out


def _formula_names(formula):
	try:
		tree = ast.parse(formula, mode="eval")
	except SyntaxError as e:
		raise ValueError(_("isn't a valid formula ({0})").format(e.msg)) from None
	return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def validate_rows(rows):
	"""Friendly checks before HRMS sees the structure."""
	if not any(r.get("kind") == "earning" for r in rows):
		frappe.throw(_("A structure needs at least one earning, such as Basic."))
	if sum(1 for r in rows if r.get("method") == "tax") > 1:
		frappe.throw(_("Only one line can come from the tax bands."))
	types = dict(frappe.get_all("Salary Component", fields=["name", "type"], as_list=True))
	seen_components, defined = set(), set()
	# HRMS works out every earning before any deduction
	ordered = [r for r in rows if r.get("kind") == "earning"] + [r for r in rows if r.get("kind") != "earning"]
	for r in ordered:
		name = r.get("component")
		if not name or name not in types:
			frappe.throw(_("Pick a component for every line."))
		if name in seen_components:
			frappe.throw(_("{0} is on the structure twice.").format(name))
		seen_components.add(name)
		want = "Earning" if r["kind"] == "earning" else "Deduction"
		if types[name] != want:
			frappe.throw(_("{0} is {1}, so it can't be under {2}.").format(
				name, _("an earning") if types[name] == "Earning" else _("a deduction"),
				_("earnings") if want == "Earning" else _("deductions or employer costs")))
		if r.get("method") not in METHODS:
			frappe.throw(_("Choose how {0} is worked out.").format(name))
		if r["method"] == "tax" and r["kind"] != "deduction":
			frappe.throw(_("{0}: only a deduction can come from the tax bands.").format(name))
		if r["kind"] == "earning" and r["method"] in ("percent", "capped") and r.get("of") == "gross_pay":
			frappe.throw(_("{0}: an earning can be a % of the base salary, not of gross pay (gross is the earnings added up).")
			             .format(name))
		if r["method"] in ("percent", "capped") and flt(r.get("rate")) <= 0:
			frappe.throw(_("{0}: enter the percentage.").format(name))
		if r["method"] == "capped" and flt(r.get("cap")) <= 0:
			frappe.throw(_("{0}: enter the most it can be.").format(name))
		if r["method"] == "fixed" and flt(r.get("amount")) <= 0:
			frappe.throw(_("{0}: enter the amount.").format(name))
		formula = to_row(r)["formula"]
		for text, what in ((formula, _("formula")), (r.get("condition"), _("condition"))):
			if not text:
				continue
			try:
				unknown = _formula_names(text) - FORMULA_NAMES - defined
				if r["kind"] == "earning" and "gross_pay" in _formula_names(text):
					unknown.add("gross_pay")
			except ValueError as e:
				frappe.throw(_("{0}: the {1} {2}.").format(name, what, e))
			if unknown:
				frappe.throw(_("{0}: the {1} uses {2}, which isn't worked out before it.").format(
					name, what, ", ".join(sorted(unknown))))
		if r.get("abbr"):
			defined.add(r["abbr"])


# ── Reading ──────────────────────────────────────────────────────────────────

def _latest_assignments(on_date=None):
	"""{employee: latest submitted assignment from on or before `on_date`} for active staff."""
	company = _company()
	out = {}
	for a in frappe.get_all(
			"Salary Structure Assignment",
			filters={"docstatus": 1, "company": company, "from_date": ["<=", on_date or nowdate()]},
			fields=["name", "employee", "employee_name", "salary_structure", "income_tax_slab", "base", "agreed_net_pay",
			        "from_date"], order_by="from_date asc, creation asc"):
		out[a.employee] = a
	active = set(frappe.get_all("Employee", filters={"company": company, "status": "Active"}, pluck="name"))
	return {e: a for e, a in out.items() if e in active}


def _in_use(doctype, name):
	"""A structure or slab HRMS won't let us cancel: an assignment or a payslip refers to it."""
	field = "salary_structure" if doctype == "Salary Structure" else "income_tax_slab"
	if frappe.db.exists("Salary Structure Assignment", {field: name, "docstatus": ["<", 2]}):
		return True
	return doctype == "Salary Structure" and bool(
		frappe.db.exists("Salary Slip", {"salary_structure": name, "docstatus": ["<", 2]}))


def _structure(name):
	doc = frappe.get_doc("Salary Structure", name)
	rows = [from_row(d, "earnings") for d in doc.earnings] + [from_row(d, "deductions") for d in doc.deductions]
	return dict(name=doc.name, currency=doc.currency, payroll_frequency=doc.payroll_frequency, is_active=doc.is_active,
	            docstatus=doc.docstatus, rows=rows, in_use=_in_use("Salary Structure", doc.name))


def _bands(slab):
	"""Tax slab rows as the tax authority publishes them: HRMS taxes (income - from + 1), so each
	band after the first is stored from its edge + 1."""
	return [dict(from_amount=flt(s.from_amount) - 1 if flt(s.from_amount) > 0 else 0, to_amount=flt(s.to_amount) or None,
	             percent=flt(s.percent_deduction)) for s in sorted(slab.slabs, key=lambda s: flt(s.from_amount))]


def _slab(name):
	doc = frappe.get_doc("Income Tax Slab", name)
	return dict(name=doc.name, effective_from=doc.effective_from, currency=doc.currency, disabled=cint(doc.disabled),
	            allow_tax_exemption=cint(doc.allow_tax_exemption), bands=_bands(doc),
	            charges=[dict(description=c.description, percent=flt(c.percent)) for c in doc.other_taxes_and_charges],
	            in_use=_in_use("Income Tax Slab", doc.name))


@frappe.whitelist()
def get_pay_setup():
	_require_hr()
	company = _company()
	latest = _latest_assignments()
	people = {}
	for a in latest.values():
		people.setdefault(("s", a.salary_structure), []).append(a.employee_name)
		if a.income_tax_slab:
			people.setdefault(("t", a.income_tax_slab), []).append(a.employee_name)
	structures = []
	for s in frappe.get_all("Salary Structure", filters={"docstatus": 1, "company": company},
	                        fields=["name"], order_by="is_active desc, creation desc"):
		st = _structure(s.name)
		st["people"] = sorted(people.get(("s", s.name), []))
		structures.append(st)
	slabs = []
	for t in frappe.get_all("Income Tax Slab", filters={"docstatus": 1}, fields=["name"],
	                        order_by="disabled asc, effective_from desc"):
		sl = _slab(t.name)
		sl["people"] = sorted(people.get(("t", t.name), []))
		slabs.append(sl)
	used_in = {}
	for d in frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure"}, fields=["salary_component", "parent"]):
		used_in.setdefault(d.salary_component, set()).add(d.parent)
	active = {s["name"] for s in structures if s["is_active"] == "Yes"}
	components = frappe.get_all(
		"Salary Component",
		fields=["name", "salary_component_abbr as abbr", "type", "description", "disabled", "is_tax_applicable",
		        "exempted_from_income_tax", "depends_on_payment_days", "variable_based_on_taxable_salary",
		        "do_not_include_in_total"], order_by="type desc, name asc")
	for c in components:
		c.used_in = sorted(used_in.get(c.name, set()) & active)
	return dict(structures=structures, slabs=slabs, components=components, currency=frappe.get_cached_value(
		"Company", company, "default_currency"), can_edit=bool(set(frappe.get_roles()) & set(MANAGER_ROLES)),
		sample_employee=_sample_employee(), formula_names=sorted(FORMULA_NAMES - {"True", "False", "None"}))


def _sample_employee():
	return frappe.db.get_value("Employee", {"company": _company(), "status": "Active"}, "name", order_by="date_of_joining asc")


# ── Building documents ───────────────────────────────────────────────────────

def _structure_doc(data, name):
	rows = data.get("rows") or []
	abbrs = dict(frappe.get_all("Salary Component", fields=["name", "salary_component_abbr"], as_list=True))
	for r in rows:
		r["abbr"] = abbrs.get(r.get("component"))  # the component's, whatever the browser sent
	validate_rows(rows)
	earnings = [to_row(r) for r in rows if r.get("kind") == "earning"]
	deductions = [to_row(r) for r in rows if r.get("kind") != "earning"]
	company = _company()
	return frappe.get_doc(dict(
		doctype="Salary Structure", __newname=name, company=company, is_active="Yes",
		payroll_frequency=data.get("payroll_frequency") or "Monthly",
		currency=data.get("currency") or frappe.get_cached_value("Company", company, "default_currency"),
		earnings=earnings, deductions=deductions))


def _slab_doc(data, name):
	bands = sorted(data.get("bands") or [], key=lambda b: flt(b.get("from_amount")))
	if not bands:
		frappe.throw(_("Add at least one tax band."))
	for i, b in enumerate(bands):
		if flt(b.get("percent")) < 0 or flt(b.get("percent")) > 100:
			frappe.throw(_("Band {0}: the rate must be between 0 and 100%.").format(i + 1))
		top = flt(b.get("to_amount"))
		if top and top <= flt(b.get("from_amount")):
			frappe.throw(_("Band {0}: \"up to\" must be more than \"from\".").format(i + 1))
		if not top and i < len(bands) - 1:
			frappe.throw(_("Only the last band can be open-ended (\"and above\")."))
		if i and flt(bands[i - 1].get("to_amount")) != flt(b.get("from_amount")):
			frappe.throw(_("Band {0} should start where band {1} ends ({2}).").format(
				i + 1, i, _num(bands[i - 1].get("to_amount"))))
	company = _company()
	return frappe.get_doc(dict(
		doctype="Income Tax Slab", __newname=name, company=company, effective_from=data.get("effective_from") or nowdate(),
		currency=data.get("currency") or frappe.get_cached_value("Company", company, "default_currency"),
		allow_tax_exemption=1 if data.get("allow_tax_exemption") is None else cint(data.get("allow_tax_exemption")),
		slabs=[dict(from_amount=flt(b.get("from_amount")) + 1 if flt(b.get("from_amount")) else 0,
		            to_amount=flt(b.get("to_amount")), percent_deduction=flt(b.get("percent"))) for b in bands],
		other_taxes_and_charges=[dict(description=c.get("description"), percent=flt(c.get("percent")))
		                         for c in data.get("charges") or [] if c.get("description")]))


def _next_version(doctype, name):
	stem = VERSION.sub("", name)
	n = 2
	while frappe.db.exists(doctype, f"{stem} (v{n})"):
		n += 1
	return f"{stem} (v{n})"


def _replace_or_version(doctype, data, build):
	"""Save `data` as `data.name`: replaced in place when nothing uses it, else as a new version."""
	name = (data.get("name") or "").strip()
	original = data.get("original")
	if not name:
		frappe.throw(_("Give it a name."))
	if original and frappe.db.exists(doctype, original) and _in_use(doctype, original):
		target = name if name != original and not frappe.db.exists(doctype, name) else _next_version(doctype, original)
		versioned_from = original
	else:
		if original and name != original and frappe.db.exists(doctype, name):
			frappe.throw(_("There's already a {0} called {1}.").format(_(doctype).lower(), name))
		if original and frappe.db.exists(doctype, original):
			old = frappe.get_doc(doctype, original)
			if old.docstatus == 1:
				old.flags.ignore_permissions = True
				old.cancel()
			frappe.delete_doc(doctype, original, ignore_permissions=True, force=True)
		elif frappe.db.exists(doctype, name):
			frappe.throw(_("There's already a {0} called {1}.").format(_(doctype).lower(), name))
		target, versioned_from = name, None
	doc = build(data, target)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name, versioned_from


@frappe.whitelist(methods=["POST"])
def save_structure(structure: dict | str):
	"""`structure`: {name, original?, rows: [...]} → {name, versioned_from, people}."""
	_require_manager()
	data = frappe.parse_json(structure)
	name, versioned_from = _replace_or_version("Salary Structure", data, _structure_doc)
	_sync_component_flags(data.get("rows") or [])
	return dict(name=name, versioned_from=versioned_from,
	            people=_people_on("salary_structure", versioned_from) if versioned_from else [])


@frappe.whitelist(methods=["POST"])
def save_slab(slab: dict | str):
	_require_manager()
	data = frappe.parse_json(slab)
	name, versioned_from = _replace_or_version("Income Tax Slab", data, _slab_doc)
	return dict(name=name, versioned_from=versioned_from,
	            people=_people_on("income_tax_slab", versioned_from) if versioned_from else [])


def _sync_component_flags(rows):
	"""The flags edited on a row are the component's defaults for the next structure too."""
	for r in rows:
		comp = frappe.get_doc("Salary Component", r["component"])
		changes = {f: cint(r.get(f)) for f in ("depends_on_payment_days", "is_tax_applicable", "exempted_from_income_tax")
		           if r.get("method") != "tax" and cint(comp.get(f)) != cint(r.get(f))}
		if changes:
			comp.update(changes)
			comp.flags.ignore_permissions = True
			comp.save()


@frappe.whitelist(methods=["POST"])
def save_component(component: dict | str):
	"""Create a salary component, or change one's abbreviation, flags, description or
	enabled state. The name can't change: HRMS uses it as the key everywhere."""
	_require_manager()
	c = frappe.parse_json(component)
	name = (c.get("name") or "").strip()
	abbr = (c.get("abbr") or "").strip()
	if not name or not abbr:
		frappe.throw(_("A component needs a name and a short code."))
	if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", abbr):
		frappe.throw(_("The short code is used in formulas: letters, digits and _ only, starting with a letter."))
	clash = frappe.db.get_value("Salary Component", {"salary_component_abbr": abbr, "name": ["!=", name]}, "name")
	if clash:
		frappe.throw(_("{0} already uses the short code {1}.").format(clash, abbr))
	exists = frappe.db.exists("Salary Component", name)
	doc = frappe.get_doc("Salary Component", name) if exists else frappe.new_doc("Salary Component")
	used = frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure", "salary_component": name},
	                      pluck="parent", distinct=True)
	if exists:
		if doc.salary_component_abbr != abbr and used:
			frappe.throw(_("{0} is on {1}; its short code can't change because formulas may use it.").format(
				name, ", ".join(used)))
		active = [s for s in used if frappe.db.get_value("Salary Structure", s, "is_active") == "Yes"]
		if cint(c.get("disabled")) and not cint(doc.disabled) and active:
			frappe.throw(_("{0} is on {1}. Take it off first.").format(name, ", ".join(active)))
	else:
		doc.salary_component = name
		doc.type = "Deduction" if c.get("type") == "Deduction" else "Earning"
	doc.update(dict(
		salary_component_abbr=abbr, description=c.get("description"), disabled=cint(c.get("disabled")),
		is_tax_applicable=cint(c.get("is_tax_applicable")) if doc.type == "Earning" else 0,
		exempted_from_income_tax=cint(c.get("exempted_from_income_tax")) if doc.type == "Deduction" else 0,
		depends_on_payment_days=cint(c.get("depends_on_payment_days")),
		do_not_include_in_total=cint(c.get("employer")) if doc.type == "Deduction" else 0,
		do_not_include_in_accounts=cint(c.get("employer")) if doc.type == "Deduction" else 0,
	))
	doc.flags.ignore_permissions = True
	doc.save()
	return get_pay_setup()


# ── Pricing a draft ──────────────────────────────────────────────────────────

@frappe.whitelist(methods=["POST"])
def preview(structure: dict | str | None = None, slab: dict | str | None = None, gross: float = 1000,
            month: str | None = None, employee: str | None = None, structure_name: str | None = None,
            slab_name: str | None = None):
	"""A month's payslip at `gross` on a draft (or saved) structure and tax bands, worked
	out by HRMS and thrown away. Problems come back as {error}, not a throw."""
	_require_hr()
	employee = employee or _sample_employee()
	month = str(get_first_day(month or nowdate()))
	if not employee:
		return dict(error=_("Add an employee first: a payslip is worked out for someone."))
	frappe.db.savepoint("pay_setup_preview")
	try:
		name = structure_name
		if structure:
			name = "__pay_setup_preview__"
			doc = _structure_doc(frappe.parse_json(structure), name)
			doc.insert(ignore_permissions=True)
			doc.submit()
		slab_used = slab_name
		if slab:
			slab_used = "__pay_setup_preview_slab__"
			doc = _slab_doc(frappe.parse_json(slab), slab_used)
			doc.insert(ignore_permissions=True)
			doc.submit()
		if not name:
			frappe.throw(_("Pick a structure."))
		tax = _tax_component(name)
		if tax and not slab_used:
			frappe.throw(_("{0} comes from the tax bands: pick them.").format(tax))
		out = _priced(_preview_slip(employee, name, flt(gross, 2), month, slab_used if tax else None))
		out.update(employee=employee, employee_name=frappe.db.get_value("Employee", employee, "employee_name"),
		           month=month)
		return out
	except frappe.ValidationError as e:
		frappe.clear_messages()
		return dict(error=_plain(str(e)))
	finally:
		frappe.db.rollback(save_point="pay_setup_preview")
		frappe.clear_document_cache("Salary Structure", "__pay_setup_preview__")
		frappe.clear_document_cache("Income Tax Slab", "__pay_setup_preview_slab__")
		frappe.clear_messages()  # HRMS's save-time notes about the throwaway draft


def _plain(message):
	return re.sub(r"<[^>]+>", "", message).strip()


# ── Moving people to a new version ───────────────────────────────────────────

def _people_on(field, name, on_date=None):
	return [dict(employee=a.employee, employee_name=a.employee_name, base=flt(a.base), agreed_net=flt(a.agreed_net_pay))
	        for a in _latest_assignments(on_date).values() if a.get(field) == name]


@frappe.whitelist(methods=["POST"])
def move_people(kind: str, old: str, new: str, from_date: str, confirm: int = 0):
	"""Everyone whose salary is on `old` (a structure, or tax bands when `kind` is "slab")
	moves to `new` from `from_date`, keeping their gross and agreed net. Without
	`confirm`: what each would net before and after, nothing saved."""
	_require_manager()
	field = "salary_structure" if kind == "structure" else "income_tax_slab"
	latest = [a for a in _latest_assignments(from_date).values() if a.get(field) == old]
	if not latest:
		return dict(rows=[], moved=0, failed=[])
	if not confirm:
		rows = []
		for a in latest:
			row = dict(employee=a.employee, employee_name=a.employee_name, base=flt(a.base), agreed_net=flt(a.agreed_net_pay))
			for key, structure, slab in (("net_now", a.salary_structure, a.income_tax_slab),
			                             ("net_new", new if kind == "structure" else a.salary_structure,
			                              a.income_tax_slab if kind == "structure" else new)):
				try:
					tax = _tax_component(structure)
					row[key] = flt(_preview_slip(a.employee, structure, a.base, from_date, slab if tax else None).net_pay)
				except frappe.ValidationError as e:
					frappe.clear_messages()
					row["error"] = _plain(str(e))
			rows.append(row)
		return dict(rows=rows)
	groups = {}
	for a in latest:
		structure = new if kind == "structure" else a.salary_structure
		slab = a.income_tax_slab if kind == "structure" else new
		groups.setdefault((structure, slab), []).append(dict(employee=a.employee, base=a.base, agreed_net=a.agreed_net_pay))
	moved, failed = 0, []
	for (structure, slab), rows in groups.items():
		out = save_salaries(structure, from_date, rows, slab if _tax_component(structure) else None)
		moved += out["created"] + out["replaced"]
		failed += out["failed"]
	return dict(moved=moved, failed=failed)


@frappe.whitelist(methods=["POST"])
def set_active(name: str, active: int):
	"""Retire a structure (or bring it back). Retired ones aren't offered on Salaries, and
	a payroll run leaves out anyone still on one, so it needs nobody on it."""
	_require_manager()
	if not cint(active):
		on = _people_on("salary_structure", name, on_date="2199-12-31")
		if on:
			frappe.throw(_("{0} still {1} on it. Move them first.").format(
				", ".join(p["employee_name"] for p in on[:5]) + ("…" if len(on) > 5 else ""), _("is") if len(on) == 1 else _("are")))
	frappe.db.set_value("Salary Structure", name, "is_active", "Yes" if cint(active) else "No")
	return get_pay_setup()
