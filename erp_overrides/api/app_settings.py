# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Settings pages for the three PWAs (/sales, /hrms-admin, /accounts).

Each app shows a chosen set of ERPNext / app settings to its managers only, and
who changed what. Changes are saved through the documents themselves, so
Frappe's Version log records the user, and edits made in desk show up in the same
history.
"""
import frappe
from frappe import _
from frappe.utils import cint, cstr

SYSTEM = "System Manager"
LAYOUT = ("Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading")


def _company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")


# app → manager role and sections of (label, doctype, docname or None for a Single, fields)
REGISTRY = {
	"sales": dict(role="Sales Manager", sections=[
		("Approval limits", "Custom Selling Settings", None, ["sales_order_limit", "discount_limit", "payment_entry_limit"]),
		("Selling", "Selling Settings", None, ["selling_price_list", "so_required", "dn_required", "maintain_same_sales_rate",
		                                       "allow_multiple_items", "validate_selling_price", "customer_group", "territory"]),
		("Stock", "Stock Settings", None, ["allow_negative_stock", "default_warehouse"]),
	]),
	"hr": dict(role="HR Manager", sections=[
		("Leave and attendance", "HR Settings", None, [
			"leave_approver_mandatory_in_leave_application", "expense_approver_mandatory_in_expense_claim",
			"send_leave_notification", "restrict_backdated_leave_application",
			"role_allowed_to_create_backdated_leave_application", "standard_working_hours",
			"allow_employee_checkin_from_mobile_app", "retirement_age", "emp_created_by"]),
		("Payroll", "Payroll Settings", None, [
			"payroll_based_on", "include_holidays_in_total_working_days", "email_salary_slip_to_employee",
			"payslip_print_format", "encrypt_salary_slips_in_emails", "daily_wages_fraction_for_half_day"]),
	]),
	"accounts": dict(role="Accounts Manager", sections=[
		("Petty cash", "App Accounts Settings", None, ["petty_cash_boxes", "cash_over_short_account"]),
		("Bank reconciliation", "App Accounts Settings", None, ["transfer_tolerance", "stale_line_days"]),
		("Bank reconciliation", "Accounts Settings", None, ["enable_fuzzy_matching"]),
		("Invoices and payments", "Accounts Settings", None, [
			"over_billing_allowance", "credit_controller", "check_supplier_invoice_uniqueness",
			"unlink_payment_on_cancellation_of_invoice"]),
		("Closing the books", "Company", _company, ["accounts_frozen_till_date", "role_allowed_for_frozen_entries"]),
		("Exchange rates", "Currency Exchange Settings", None, ["service_provider", "api_endpoint"]),
	]),
	"sysadmin": dict(role=SYSTEM, sections=[
		("Default selling price list", "Selling Settings", None, ["selling_price_list"]),
		("Price lists", "Buying Settings", None, ["buying_price_list"]),
		("Items and stock", "Stock Settings", None, ["item_naming_by", "stock_uom", "default_warehouse", "allow_negative_stock"]),
	]),
}


def is_settings_manager(app, user=None):
	conf = REGISTRY.get(app)
	return bool(conf and {conf["role"], SYSTEM} & set(frappe.get_roles(user)))


def _require_manager(app):
	if app not in REGISTRY:
		frappe.throw(_("Unknown app {0}.").format(app))
	if not is_settings_manager(app):
		frappe.throw(_("Only a {0} can see or change these settings.").format(REGISTRY[app]["role"]), frappe.PermissionError)


def _sections(app):
	"""(label, doctype, docname, [docfields]) for what exists on this site."""
	out = []
	for label, doctype, docname, fields in REGISTRY[app]["sections"]:
		if not frappe.db.exists("DocType", doctype):
			continue
		name = docname() if callable(docname) else (docname or doctype)
		if not name or not frappe.db.exists(doctype, name) and not frappe.get_meta(doctype).issingle:
			continue
		meta = frappe.get_meta(doctype)
		present = [meta.get_field(f) for f in fields if meta.get_field(f)]
		if present:
			out.append((label, doctype, name, present))
	return out


def _columns(df):
	return [f for f in frappe.get_meta(df.options).fields if f.fieldtype not in LAYOUT and not f.hidden]


def _field(df, value):
	out = dict(fieldname=df.fieldname, label=_(df.label), type=df.fieldtype, description=_(df.description or ""),
	           options=df.options, reqd=df.reqd)
	if df.fieldtype == "Select":
		out["options"] = (df.options or "").split("\n")
	if df.fieldtype == "Link" and df.get("link_filters"):
		# [[doctype, field, op, value], ...] → {field: [op, value]} for the link picker
		out["filters"] = {f[1]: [f[2], f[3]] for f in frappe.parse_json(df.link_filters) if len(f) >= 4}
	if df.fieldtype == "Table":
		out["columns"] = [_field(c, None) for c in _columns(df)]
		out["value"] = [dict(name=r.name, **{c.fieldname: r.get(c.fieldname) for c in _columns(df)}) for r in value or []]
	else:
		out["value"] = value
	return out


@frappe.whitelist()
def get_settings(app: str):
	_require_manager(app)
	sections = {}  # by label: one section can hold fields from several documents
	for label, doctype, name, fields in _sections(app):
		doc = frappe.get_doc(doctype, name)
		section = sections.setdefault(label, dict(label=label, fields=[]))
		section["fields"] += [dict(_field(df, doc.get(df.fieldname)), doctype=doctype) for df in fields]
	return dict(app=app, role=REGISTRY[app]["role"], sections=list(sections.values()))


@frappe.whitelist(methods=["POST"])
def save_settings(app: str, changes: list | str):
	"""`changes`: [{doctype, fieldname, value}]. Only fields on this app's page are
	accepted. Each document is saved once; its Version records who changed what."""
	_require_manager(app)
	changes = frappe.parse_json(changes) if isinstance(changes, str) else changes
	allowed = {(dt, df.fieldname): (name, df) for _label, dt, name, fields in _sections(app) for df in fields}
	per_doc = {}
	for c in changes or []:
		key = (c.get("doctype"), c.get("fieldname"))
		if key not in allowed:
			frappe.throw(_("{0} isn't a setting on this page.").format(c.get("fieldname")), frappe.PermissionError)
		name, df = allowed[key]
		_check_link(df, c.get("value"))
		per_doc.setdefault((key[0], name), []).append((df, c.get("value")))

	for (doctype, name), items in per_doc.items():
		doc = frappe.get_doc(doctype, name)
		before = frappe.get_doc(doc.as_dict())
		for df, value in items:
			if df.fieldtype == "Table":
				_set_rows(doc, df, value or [])
			else:
				doc.set(df.fieldname, value)
		doc.flags.ignore_permissions = True  # the manager role was checked above
		doc.save(ignore_version=False)  # always log who changed it (Frappe skips Versions in tests by default)
		if not frappe.get_meta(doctype).track_changes:
			# Custom Selling Settings before the patch, or any untracked doctype: log it anyway
			version = frappe.new_doc("Version")
			if version.update_version_info(before, doc):
				version.insert(ignore_permissions=True)
	return get_settings(app)


def _check_link(df, value):
	"""A setting can't point at a disabled record (e.g. a disabled price list)."""
	if df.fieldtype != "Link" or not value:
		return
	meta = frappe.get_meta(df.options)
	if meta.get_field("enabled") and not cint(frappe.db.get_value(df.options, value, "enabled")) \
			or meta.get_field("disabled") and cint(frappe.db.get_value(df.options, value, "disabled")):
		frappe.throw(_("{0} {1} is disabled.").format(_(df.options), value))


def _set_rows(doc, df, rows):
	"""Update table rows in place (matched by name) so the history shows row edits,
	not a remove-and-add of every row."""
	cols = {c.fieldname for c in _columns(df)}
	existing = {r.name: r for r in doc.get(df.fieldname)}
	keep = []
	for r in rows:
		data = {k: v for k, v in r.items() if k in cols}
		row = existing.get(r.get("name"))
		if row:
			row.update(data)
		else:
			row = doc.append(df.fieldname, data)
		keep.append(row)
	doc.set(df.fieldname, keep)
	for i, row in enumerate(keep, 1):
		row.idx = i


def _readable(df, value):
	if value in (None, ""):
		return "—"
	if df and df.fieldtype == "Check":
		return _("Yes") if cint(value) else _("No")
	return cstr(value)


@frappe.whitelist()
def get_history(app: str, start: int = 0, page_length: int = 30, section: str | None = None):
	"""Who changed what on this app's settings, newest first: one entry per changed
	setting, with the old and new value."""
	_require_manager(app)
	sections = [s for s in _sections(app) if not section or s[0] == section]
	if not sections:
		return dict(entries=[], next_start=None)
	fields = {}  # (doctype, fieldname) → (section, docfield)
	for label, doctype, _name, dfs in sections:
		for df in dfs:
			fields[(doctype, df.fieldname)] = (label, df)
	docs = {f"{dt}::{name}" for _l, dt, name, _f in sections}
	versions = frappe.db.sql(
		"""select name, ref_doctype, docname, owner, creation, data from tabVersion
		   where concat(ref_doctype, '::', docname) in %(docs)s
		   order by creation desc limit %(start)s, %(page_length)s""",
		dict(docs=tuple(docs), start=cint(start), page_length=cint(page_length)), as_dict=True)
	names, entries = {}, []
	for v in versions:
		data = frappe.parse_json(v.data or "{}")
		who = dict(user=v.owner, by=names.setdefault(v.owner, frappe.utils.get_fullname(v.owner)), when=v.creation,
		           version=v.name)
		for fieldname, old, new in data.get("changed") or []:
			if (v.ref_doctype, fieldname) in fields:
				label, df = fields[(v.ref_doctype, fieldname)]
				entries.append(dict(who, kind="changed", section=label, setting=_(df.label),
				                    old=_readable(df, old), new=_readable(df, new)))
		for kind in ("added", "removed"):
			for fieldname, row in data.get(kind) or []:
				if (v.ref_doctype, fieldname) in fields:
					label, df = fields[(v.ref_doctype, fieldname)]
					entries.append(dict(who, kind=kind, section=label, setting=_(df.label), row=_row_label(df, row)))
		for change in data.get("row_changed") or []:
			fieldname, a, b, diffs = change
			row_name = b if isinstance(a, int) else a
			if (v.ref_doctype, fieldname) not in fields:
				continue
			label, df = fields[(v.ref_doctype, fieldname)]
			child = {c.fieldname: c for c in _columns(df)}
			row = frappe.db.get_value(df.options, row_name, list(child)[:1], as_dict=True) if child else None
			for f, old, new in diffs:
				entries.append(dict(who, kind="row_changed", section=label, setting=_(df.label),
				                    row=_row_label(df, row) if row else _("a row"),
				                    field=_(child[f].label) if f in child else f,
				                    old=_readable(child.get(f), old), new=_readable(child.get(f), new)))
	return dict(entries=entries, next_start=cint(start) + len(versions) if len(versions) == cint(page_length) else None)


def _row_label(df, row):
	cols = _columns(df)
	return cstr((row or {}).get(cols[0].fieldname)) if cols else ""
