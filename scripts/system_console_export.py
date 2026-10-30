# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt
#
# Export a Workflow from the DESK: /app/system-console, Type = Python.
# Paste this whole file into the Console field and hit Execute.
#
# The System Console runs under RestrictedPython (safe_exec), which is why this
# file looks different from scripts/workflow_export.py — in there you get no
# imports, no file access, and no name may start with an underscore. So the
# payload is PRINTED into the Output box; copy it from there.
#
# Leave WORKFLOW empty on the first run to list the workflows on the site.
# The "Commit" checkbox is irrelevant here: this script only reads.

WORKFLOW = ""
DOCUMENT_TYPE = ""

# keys starting with "_" (_user_tags, _comments, _assign, _liked_by) are dropped
# separately: safe_exec's _getitem refuses to subscript them at all
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
)


def to_dict(row):
	# older safe_exec hands back a real Document, newer one a dict-like SafeDoc
	if isinstance(row, dict):
		return row
	return row.as_dict()


def clean(row, drop_name=False):
	row = to_dict(row)
	out = {}
	for key in row:
		if key.startswith("_"):
			continue
		if key in VOLATILE_FIELDS:
			continue
		if drop_name and key == "name":
			continue
		value = row.get(key)   # not row[key]: _getitem guards subscripting
		if value is None or value == "":
			continue
		out[key] = value
	return out


def show_workflows(document_type):
	filters = {"document_type": document_type} if document_type else None
	rows = frappe.get_all(
		"Workflow",
		filters=filters,
		fields=["name", "document_type", "workflow_state_field", "is_active"],
		order_by="document_type asc, name asc",
	)
	print("Workflows on this site:")
	for row in rows:
		print("  " + row["name"] + "  |  " + row["document_type"] + "  |  active=" + str(row["is_active"]))
	return rows


def summarize(workflow, state_field):
	print("")
	print("Workflow: " + str(workflow.get("name")) + "  (" + str(workflow.get("document_type"))
		+ ", active=" + str(workflow.get("is_active")) + ")")
	print("State field: " + state_field)
	print("")
	print("States:")
	for row in workflow["states"]:
		print("  " + str(row.get("state")) + "  docstatus=" + str(row.get("doc_status"))
			+ "  edit=" + str(row.get("allow_edit") or "-")
			+ "  update=" + str(row.get("update_field") or "-") + ":" + str(row.get("update_value") or "-"))
	print("")
	print("Transitions:")
	for row in workflow["transitions"]:
		line = ("  " + str(row.get("state")) + " --" + str(row.get("action")) + "--> "
			+ str(row.get("next_state")) + "  by " + str(row.get("allowed")))
		if row.get("condition"):
			line = line + "  [" + str(row.get("condition")) + "]"
		print(line)


def export(workflow_name, document_type):
	rows = frappe.get_all(
		"Workflow",
		filters={"document_type": document_type} if document_type else None,
		fields=["name"],
	)
	names = [row["name"] for row in rows]

	if not workflow_name:
		show_workflows(document_type)
		print("")
		print("Set WORKFLOW at the top of the script to one of the names above.")
		return None

	if workflow_name not in names and not frappe.db.exists("Workflow", workflow_name):
		show_workflows(document_type)
		print("")
		print('Workflow "' + workflow_name + '" not found on this site.')
		return None

	# read through get_all only: frappe.get_doc returns a Document on some
	# safe_exec versions and a dict on others, and a Document is not iterable
	parent_rows = frappe.get_all("Workflow", filters={"name": workflow_name}, fields=["*"])
	state_rows = frappe.get_all(
		"Workflow Document State",
		filters={"parent": workflow_name, "parenttype": "Workflow"},
		fields=["*"],
		order_by="idx asc",
	)
	transition_rows = frappe.get_all(
		"Workflow Transition",
		filters={"parent": workflow_name, "parenttype": "Workflow"},
		fields=["*"],
		order_by="idx asc",
	)

	workflow = clean(parent_rows[0])
	workflow["states"] = [clean(row, True) for row in state_rows]
	workflow["transitions"] = [clean(row, True) for row in transition_rows]

	state_names = sorted({row.get("state") for row in workflow["states"] if row.get("state")})
	action_names = sorted({row.get("action") for row in workflow["transitions"] if row.get("action")})
	roles = sorted(
		{row.get("allow_edit") for row in workflow["states"] if row.get("allow_edit")}
		| {row.get("allowed") for row in workflow["transitions"] if row.get("allowed")}
	)

	state_masters = []
	if state_names:
		state_masters = [
			clean(row)
			for row in frappe.get_all(
				"Workflow State",
				filters={"name": ("in", state_names)},
				fields=["name", "icon", "style"],
			)
		]

	action_masters = []
	if action_names:
		action_masters = [
			clean(row)
			for row in frappe.get_all(
				"Workflow Action Master",
				filters={"name": ("in", action_names)},
				fields=["name"],
			)
		]

	state_field = workflow.get("workflow_state_field") or "workflow_state"
	custom_fields = [
		clean(row)
		for row in frappe.get_all(
			"Custom Field",
			filters={"dt": workflow.get("document_type"), "fieldname": state_field},
			fields=["name", "dt", "fieldname", "label", "fieldtype", "options", "insert_after",
				"hidden", "read_only", "allow_on_submit", "no_copy", "print_hide"],
		)
	]

	summarize(workflow, state_field)

	# a state whose update_field is the workflow's own state field overwrites the
	# state Frappe just set — apply_workflow() sets the state field, then applies
	# update_field/update_value
	for row in workflow["states"]:
		if row.get("update_field") == state_field and row.get("update_value") != row.get("state"):
			print("")
			print('WARNING: state "' + str(row.get("state")) + '" writes "'
				+ str(row.get("update_value")) + '" back into ' + state_field
				+ " — any transition into it drops the document out of the workflow.")

	print("")
	print("Roles needed on the target site: " + (", ".join(roles) or "-"))

	return {
		"exported_at": frappe.utils.now(),
		"workflow": workflow,
		"state_masters": state_masters,
		"action_masters": action_masters,
		"roles": roles,
		"custom_fields": custom_fields,
	}


payload = export(WORKFLOW, DOCUMENT_TYPE)

if payload:
	print("")
	print("---------- copy everything below into a .json file ----------")
	print(as_json(payload))
