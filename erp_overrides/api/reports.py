# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""The desk reports a PWA lists: a curated set with plain-English descriptions, then every
other enabled report in the app's modules, so nothing is missing as ERPNext adds reports.
Only reports the user may open are returned (the same rule as Report.is_permitted)."""
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import quoted, slug


def _url(name, report_type, ref_doctype):
	if report_type == "Report Builder":
		return f"/desk/{quoted(slug(ref_doctype))}/view/report/{quoted(name)}"
	return f"/desk/query-report/{quoted(name)}"


def _allowed_roles(names):
	"""{report: roles} for the reports that restrict roles; a report with none is open to all."""
	allowed = defaultdict(set)
	for r in frappe.get_all("Has Role", filters={"parenttype": "Report", "parent": ["in", names]}, fields=["parent", "role"]):
		allowed[r.parent].add(r.role)
	# a Custom Role replaces the report's own roles
	for c in frappe.get_all("Custom Role", filters={"report": ["in", names]}, fields=["name", "report"]):
		allowed[c.report] = set(frappe.get_all("Has Role", filters={"parenttype": "Custom Role", "parent": c.name}, pluck="role"))
	return allowed


def report_groups(curated, modules=(), other_label=None):
	"""curated: {group: [(report name, description)]}; modules: every other enabled report in
	these modules goes into one last group. Returns [{group, reports: [{name, description, url}]}]."""
	curated_names = [n for reports in curated.values() for n, _d in reports]
	filters = {"disabled": 0}
	or_filters = {"name": ["in", curated_names]}
	if modules:
		or_filters["module"] = ["in", list(modules)]
	rows = frappe.get_all("Report", filters=filters, or_filters=or_filters,
	                      fields=["name", "report_type", "ref_doctype", "module"], order_by="name")
	if not rows:
		return []

	roles = set(frappe.get_roles())
	allowed = _allowed_roles([r.name for r in rows])
	found = {r.name: r for r in rows if not allowed.get(r.name) or allowed[r.name] & roles}

	def entry(name, description):
		r = found[name]
		return dict(name=name, description=_(description) if description else "", url=_url(name, r.report_type, r.ref_doctype))

	groups = []
	for group, reports in curated.items():
		items = [entry(n, d) for n, d in reports if n in found]
		if items:
			groups.append(dict(group=_(group), reports=items))
	listed = set(curated_names)
	rest = [entry(n, None) for n, r in found.items() if n not in listed and r.module in modules]
	if rest:
		groups.append(dict(group=other_label or _("Other reports"), reports=rest))
	return groups
