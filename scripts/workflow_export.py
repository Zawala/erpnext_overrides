# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Export a Frappe Workflow (states, transitions and everything it depends on) as JSON.

For `bench console` / a shell on the server. The desk's System Console runs under
RestrictedPython and rejects this file (no imports, no file writes, no leading
underscores) — use scripts/system_console_export.py there instead.

Writes the JSON that scripts/workflow_import.py reads on the target site.

HOW TO RUN — pick one:

1. bench console — use %run -i, not a raw paste (IPython re-indents pasted
   blocks, and %run -i keeps the site connection this file needs):

	$ bench --site <site> console
	>>> %run -i apps/erp_overrides/scripts/workflow_export.py
	>>> list_workflows()                          # see what is on the site
	>>> export_workflow("<Workflow Name>")

2. straight from the bench directory:

	$ ./env/bin/python apps/erp_overrides/scripts/workflow_export.py \
		--site <site> --workflow "<Workflow Name>"

	Omit --workflow to list the workflows instead of exporting.

Writes workflow-<name>.json (override with --output / path=) and returns the
payload as a dict.
"""
import json
import os

import frappe
from frappe.utils import now

# fields that are meaningless (or actively harmful) on the target site
VOLATILE_FIELDS = (
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"doctype",
	"_user_tags",
	"_comments",
	"_assign",
	"_liked_by",
)

STATE_FIELDS = ("name", "icon", "style")

CUSTOM_FIELD_FIELDS = (
	"name",
	"dt",
	"fieldname",
	"label",
	"fieldtype",
	"options",
	"insert_after",
	"hidden",
	"read_only",
	"allow_on_submit",
	"no_copy",
	"print_hide",
	"in_standard_filter",
)


def clean(row, drop_name=False):
	"""Strip volatile fields and nulls from a doc/child row dict."""
	out = {}
	for key, value in row.items():
		if key in VOLATILE_FIELDS:
			continue
		if drop_name and key == "name":  # child row hashes
			continue
		if value is None or value == "":
			continue
		out[key] = value

	return out


def list_workflows(document_type=None):
	"""Every workflow on the site, printed and returned."""
	filters = {"document_type": document_type} if document_type else None
	workflows = frappe.get_all(
		"Workflow",
		filters=filters,
		fields=["name", "workflow_name", "document_type", "workflow_state_field", "is_active"],
		order_by="document_type asc, name asc",
	)

	print(f"{'Workflow':<45} {'DocType':<25} {'State field':<20} Active")
	for row in workflows:
		print(
			f"{row.name:<45} {row.document_type:<25} "
			f"{(row.workflow_state_field or 'workflow_state'):<20} {row.is_active}"
		)

	return workflows


def export_workflow(workflow=None, document_type=None, path=None, write=True):
	"""Dump `workflow` and its dependencies to JSON.

	workflow      exact Workflow name; if omitted and the site (or `document_type`)
	              has exactly one workflow, that one is used
	document_type only used to narrow the search when `workflow` is omitted
	path          output file or directory; defaults to ./workflow-<name>.json
	write         set False to get the payload back without touching the disk
	"""
	workflows = frappe.get_all(
		"Workflow",
		filters={"document_type": document_type} if document_type else None,
		fields=["name"],
	)
	names = [row.name for row in workflows]

	if not workflow:
		if len(names) == 1:
			workflow = names[0]
			print(f'Only one workflow found — exporting "{workflow}".')
		else:
			list_workflows(document_type)
			print("\nPass workflow=<name> (one of the above) and run again.")
			return None

	if workflow not in names and not frappe.db.exists("Workflow", workflow):
		frappe.throw(f'Workflow "{workflow}" not found on this site.')

	# ---- the workflow itself, with its child tables --------------------------
	doc = frappe.get_doc("Workflow", workflow)
	raw = doc.as_dict(convert_dates_to_str=True)

	exported = clean(raw)
	exported["states"] = [clean(row, drop_name=True) for row in raw.get("states") or []]
	exported["transitions"] = [clean(row, drop_name=True) for row in raw.get("transitions") or []]

	# ---- everything the workflow points at -----------------------------------
	state_names = sorted({row.get("state") for row in exported["states"] if row.get("state")})
	action_names = sorted({row.get("action") for row in exported["transitions"] if row.get("action")})
	roles = sorted(
		{row.get("allow_edit") for row in exported["states"] if row.get("allow_edit")}
		| {row.get("allowed") for row in exported["transitions"] if row.get("allowed")}
	)

	state_masters = [
		clean(row)
		for row in frappe.get_all(
			"Workflow State", filters={"name": ("in", state_names)}, fields=list(STATE_FIELDS)
		)
	] if state_names else []

	action_masters = [
		clean(row)
		for row in frappe.get_all(
			"Workflow Action Master", filters={"name": ("in", action_names)}, fields=["name"]
		)
	] if action_names else []

	# the state field is a Custom Field on the target doctype (Frappe recreates it,
	# but export it so any tweaks — label, hidden, print_hide — travel too)
	state_field = exported.get("workflow_state_field") or "workflow_state"
	custom_fields = [
		clean(row)
		for row in frappe.get_all(
			"Custom Field",
			filters={"dt": exported.get("document_type"), "fieldname": state_field},
			fields=list(CUSTOM_FIELD_FIELDS),
		)
	]

	payload = {
		"exported_at": now(),
		"source_site": frappe.local.site,
		"frappe_version": frappe.__version__,
		"workflow": exported,
		"state_masters": state_masters,
		"action_masters": action_masters,
		"roles": roles,
		"custom_fields": custom_fields,
	}

	_report(payload, state_field)

	if write:
		payload["_written_to"] = _write(payload, path)

	return payload


def _report(payload, state_field):
	workflow = payload["workflow"]
	print(
		f"\nWorkflow: {workflow.get('name')}  "
		f"({workflow.get('document_type')}, active={workflow.get('is_active')})"
	)
	print(f"State field: {state_field}\n")

	print("States:")
	for row in workflow["states"]:
		print(
			f"  {row.get('state') or '?':<25} docstatus={row.get('doc_status')} "
			f"edit={row.get('allow_edit') or '-'}"
		)

	print("\nTransitions:")
	for row in workflow["transitions"]:
		condition = f"  [{row.get('condition')}]" if row.get("condition") else ""
		print(
			f"  {row.get('state') or '?':<25} --{row.get('action')}--> "
			f"{row.get('next_state') or '?':<25} by {row.get('allowed')}{condition}"
		)

	print("\nRoles needed on the target site:", ", ".join(payload["roles"]) or "-")


def _write(payload, path=None):
	filename = "workflow-{}.json".format(
		"".join(c if c.isalnum() or c in "-._" else "_" for c in payload["workflow"]["name"])
	)

	if not path:
		path = os.path.join(os.getcwd(), filename)
	elif os.path.isdir(path):
		path = os.path.join(path, filename)

	with open(path, "w") as f:
		json.dump(payload, f, indent=2, default=str)

	print(f"\nWritten to {path}")
	return path


def _main():
	import argparse

	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--site", required=True, help="site to read the workflow from")
	parser.add_argument("--workflow", help="exact Workflow name; omit to list them")
	parser.add_argument("--document-type", help="narrow the listing, e.g. Quotation")
	parser.add_argument("--output", help="output file or directory")
	args = parser.parse_args()

	frappe.init(site=args.site)
	frappe.connect()
	try:
		if args.workflow:
			export_workflow(args.workflow, args.document_type, args.output)
		else:
			list_workflows(args.document_type)
	finally:
		frappe.destroy()


# `__name__` is "__main__" in bench console too, so also check that frappe has not
# already been booted with a site — otherwise pasting this file into the console
# would run argparse against IPython's argv and frappe.destroy() the live session.
if __name__ == "__main__" and not getattr(frappe.local, "site", None):
	_main()
