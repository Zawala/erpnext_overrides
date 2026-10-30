# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.workflow import get_workflow_name
from frappe.utils import cstr

# States a Quotation must reach before it may be printed. Override per site with
# "quotation_print_approved_states": ["Approved", "Accepted"] in site_config.json.
DEFAULT_APPROVED_STATES = ("Approved",)


def get_approved_states():
	states = frappe.conf.get("quotation_print_approved_states") or DEFAULT_APPROVED_STATES
	if isinstance(states, str):
		states = [states]
	return [cstr(state).strip().lower() for state in states]


def get_workflow_state(doc):
	"""Current workflow state of `doc`, or None if the doctype has no active workflow."""
	workflow = get_workflow_name(doc.doctype)
	if not workflow:
		return None

	state_field = frappe.get_cached_value("Workflow", workflow, "workflow_state_field")
	return doc.get(state_field or "workflow_state")


def is_approved(doc):
	state = get_workflow_state(doc)
	if state is None:
		# no workflow configured — fall back to "submitted"
		return doc.docstatus == 1

	return cstr(state).strip().lower() in get_approved_states()


def block_unapproved(doc):
	state = get_workflow_state(doc)
	frappe.throw(
		_("Quotation {0} is in state {1} and cannot be printed until it is approved.").format(
			frappe.bold(doc.name), frappe.bold(_(cstr(state) or "Draft"))
		),
		frappe.PermissionError,
		title=_("Approval Required"),
	)


def before_print(doc, method=None, print_settings=None, **kwargs):
	"""Block printing a Quotation until its workflow says it is approved.

	This is the gate that matters. `printview.get_rendered_template` is the single
	funnel for the print view, Download PDF and the PDF attached to an email, and
	it runs `before_print` *after* its permission checks — so this also closes the
	shared `?key=` link, which skips permissions entirely.
	"""
	if not is_approved(doc):
		block_unapproved(doc)


def has_permission(doc, ptype, user=None, debug=False):
	"""Second gate, for the print-format-builder (weasyprint) route.

	That route calls `doc.check_permission("print")` instead of going through
	printview, so it never reaches `before_print`.

	Note this hook alone is NOT enough: `printview.validate_print_permission`
	tests `read` *or* `print` and returns on the first that passes, so a user who
	can read a Quotation is never asked for print permission.

	Must return True to abstain, never None. Since v16 `has_controller_permissions`
	denies on any falsy return (`if not controller_permission: return bool(...)`),
	so the v15 "None means no opinion" convention now blocks every ptype.
	"""
	if ptype != "print" or not doc:
		return True

	if is_approved(doc):
		return True

	block_unapproved(doc)


@frappe.whitelist()
def can_print(name):
	"""Used by the form script to hide Print before the quotation is approved."""
	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("read")
	return is_approved(doc)
