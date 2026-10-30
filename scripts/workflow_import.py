# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Recreate a Workflow exported by workflow_export.py on another site.

HOW TO RUN — pick one:

1. bench console on the TARGET site (use %run -i, not a raw paste):

	$ bench --site <target-site> console
	>>> %run -i apps/erp_overrides/scripts/workflow_import.py
	>>> import_workflow("workflow-<name>.json", dry_run=True)   # check first
	>>> import_workflow("workflow-<name>.json")

2. straight from the bench directory:

	$ ./env/bin/python apps/erp_overrides/scripts/workflow_import.py \
		--site <target-site> --file workflow-<name>.json --dry-run
	$ ./env/bin/python apps/erp_overrides/scripts/workflow_import.py \
		--site <target-site> --file workflow-<name>.json

Idempotent: run it twice and the second run just updates the Workflow. Nothing
is written until every dependency check has passed, and nothing is committed
until the whole import succeeds.
"""
import json
import os

import frappe

CHILD_TABLES = ("states", "transitions")


def load(payload):
	"""Accept a path, a JSON string or an already-parsed dict."""
	if isinstance(payload, dict):
		return payload

	if isinstance(payload, str) and payload.strip().startswith("{"):
		return json.loads(payload)

	with open(os.path.expanduser(payload)) as f:
		return json.load(f)


def check(payload, document_type=None):
	"""Report anything that would break the import or the workflow itself.

	Returns (blockers, warnings) — both lists of strings.
	"""
	workflow = payload["workflow"]
	doctype = document_type or workflow.get("document_type")
	state_field = workflow.get("workflow_state_field") or "workflow_state"
	blockers, warnings = [], []

	if not frappe.db.exists("DocType", doctype):
		blockers.append(f'DocType "{doctype}" does not exist here — install the app that owns it first.')

	for role in payload.get("roles") or []:
		if not frappe.db.exists("Role", role):
			blockers.append(f'Role "{role}" does not exist here.')

	states = {row.get("state") for row in workflow.get("states") or []}
	for row in workflow.get("transitions") or []:
		for key in ("state", "next_state"):
			if row.get(key) not in states:
				blockers.append(
					f'Transition "{row.get("action")}" points at state "{row.get(key)}", '
					"which the payload does not define."
				)

	# a state whose update_field is the workflow's own state field overwrites the
	# state Frappe just set — apply_workflow() sets the state field first, then
	# applies update_field/update_value
	for row in workflow.get("states") or []:
		if row.get("update_field") == state_field and row.get("update_value") != row.get("state"):
			warnings.append(
				f'State "{row.get("state")}" writes "{row.get("update_value")}" back into '
				f"{state_field} — any transition into it drops the document out of the workflow."
			)

	if frappe.db.exists("DocType", doctype):
		meta = frappe.get_meta(doctype)
		for row in workflow.get("states") or []:
			field = row.get("update_field")
			if field and field != state_field and not meta.has_field(field):
				blockers.append(f'State "{row.get("state")}" updates "{field}", which {doctype} does not have.')

	clashes = frappe.get_all(
		"Workflow",
		filters={"document_type": doctype, "is_active": 1, "name": ("!=", workflow.get("name"))},
		pluck="name",
	)
	if clashes and workflow.get("is_active"):
		warnings.append(
			f"{', '.join(clashes)} is already active on {doctype} — Frappe allows one, "
			"so saving this one deactivates it."
		)

	return blockers, warnings


def import_workflow(
	payload,
	overwrite=True,
	activate=None,
	create_missing_roles=False,
	document_type=None,
	dry_run=False,
	commit=True,
):
	"""Create or update the Workflow described by `payload`.

	payload              path to the exported JSON, a JSON string, or a dict
	overwrite            update the Workflow if one of that name already exists
	activate             True/False to force is_active, None keeps what was exported
	create_missing_roles create Roles the payload needs instead of refusing to run
	document_type        retarget to another doctype, None keeps what was exported
	dry_run              run every check, write nothing
	commit               commit at the end (needed in bench console)
	"""
	payload = load(payload)
	workflow = json.loads(json.dumps(payload["workflow"]))  # local copy

	if document_type:
		workflow["document_type"] = document_type
	if activate is not None:
		workflow["is_active"] = 1 if activate else 0

	name = workflow.get("name") or workflow.get("workflow_name")
	blockers, warnings = check(payload, document_type)

	missing_roles = [role for role in payload.get("roles") or [] if not frappe.db.exists("Role", role)]
	if create_missing_roles:
		blockers = [b for b in blockers if not b.startswith("Role ")]

	for line in warnings:
		print(f"  warning: {line}")
	for line in blockers:
		print(f"  BLOCKER: {line}")

	if blockers:
		print("\nNothing written. Fix the blockers above (or pass create_missing_roles=True).")
		return None

	if dry_run:
		print(f'\nDry run OK — "{name}" would be '
			f'{"updated" if frappe.db.exists("Workflow", name) else "created"}.')
		return {"blockers": blockers, "warnings": warnings}

	log = []

	# ---- masters --------------------------------------------------------------
	for role in missing_roles:
		frappe.get_doc({"doctype": "Role", "role_name": role}).insert()
		log.append(f'created Role "{role}"')

	for state in payload.get("state_masters") or []:
		if frappe.db.exists("Workflow State", state["name"]):
			continue
		frappe.get_doc({
			"doctype": "Workflow State",
			"workflow_state_name": state["name"],
			"icon": state.get("icon"),
			"style": state.get("style"),
		}).insert()
		log.append(f'created Workflow State "{state["name"]}"')

	for action in payload.get("action_masters") or []:
		if frappe.db.exists("Workflow Action Master", action["name"]):
			continue
		frappe.get_doc({
			"doctype": "Workflow Action Master",
			"workflow_action_name": action["name"],
		}).insert()
		log.append(f'created Workflow Action Master "{action["name"]}"')

	# ---- the workflow ---------------------------------------------------------
	fields = {k: v for k, v in workflow.items() if k not in CHILD_TABLES + ("name",)}
	exists = frappe.db.exists("Workflow", name)

	if exists and not overwrite:
		print(f'\nWorkflow "{name}" already exists and overwrite=False. Nothing written.')
		return None

	if exists:
		doc = frappe.get_doc("Workflow", name)
		doc.update(fields)
		for table in CHILD_TABLES:
			doc.set(table, [])
			for row in workflow.get(table) or []:
				doc.append(table, row)
		doc.save()
		log.append(f'updated Workflow "{doc.name}"')
	else:
		doc = frappe.get_doc(dict(doctype="Workflow", **fields))
		for table in CHILD_TABLES:
			for row in workflow.get(table) or []:
				doc.append(table, row)
		doc.insert()
		log.append(f'created Workflow "{doc.name}"')

	# ---- the state field ------------------------------------------------------
	# Frappe creates the state Custom Field itself when the Workflow saves; only
	# push the exported one if this site somehow still lacks it
	for field in payload.get("custom_fields") or []:
		dt = document_type or field.get("dt")
		fieldname = f"{dt}-{field.get('fieldname')}"
		if frappe.db.exists("Custom Field", fieldname):
			continue
		values = {k: v for k, v in field.items() if k != "name"}
		values.update({"doctype": "Custom Field", "dt": dt})
		frappe.get_doc(values).insert()
		log.append(f'created Custom Field "{fieldname}"')

	if commit:
		frappe.db.commit()

	print()
	for line in log:
		print(f"  {line}")
	print("\nDone. Reload the desk (Ctrl+Shift+R) and open a document to see the workflow.")

	return {"workflow": doc.name, "log": log, "warnings": warnings}


def _main():
	import argparse

	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--site", required=True, help="site to write the workflow to")
	parser.add_argument("--file", required=True, help="JSON written by workflow_export.py")
	parser.add_argument("--document-type", help="retarget the workflow to another doctype")
	parser.add_argument("--activate", dest="activate", action="store_true", default=None)
	parser.add_argument("--no-activate", dest="activate", action="store_false")
	parser.add_argument("--create-missing-roles", action="store_true")
	parser.add_argument("--no-overwrite", dest="overwrite", action="store_false", default=True)
	parser.add_argument("--dry-run", action="store_true")
	args = parser.parse_args()

	frappe.init(site=args.site)
	frappe.connect()
	try:
		import_workflow(
			args.file,
			overwrite=args.overwrite,
			activate=args.activate,
			create_missing_roles=args.create_missing_roles,
			document_type=args.document_type,
			dry_run=args.dry_run,
		)
	finally:
		frappe.destroy()


# `__name__` is "__main__" in bench console too, so also check that frappe has not
# already been booted with a site — otherwise running this file in the console
# would run argparse against IPython's argv and frappe.destroy() the live session.
if __name__ == "__main__" and not getattr(frappe.local, "site", None):
	_main()
