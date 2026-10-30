# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Install the Quotation print guard's UI half as a Client Script.

The gate that actually enforces anything is server side and lives in the app:
erp_overrides.quotation.before_print (doc_events) plus
erp_overrides.quotation.has_permission. This script only installs the bit of UI
that hides the Print menu item, so users see why instead of hitting an error.

Deleting or disabling this Client Script does NOT let anyone print an unapproved
quotation — it only puts the button back.

HOW TO RUN — pick one:

1. bench console (use %run -i, not a raw paste):

	$ bench --site <site> console
	>>> %run -i apps/erp_overrides/scripts/install_print_guard.py
	>>> install_print_guard()
	>>> uninstall_print_guard()          # to remove it again

2. straight from the bench directory:

	$ ./env/bin/python apps/erp_overrides/scripts/install_print_guard.py --site <site>
	$ ./env/bin/python apps/erp_overrides/scripts/install_print_guard.py --site <site> --remove

Or skip both and paste CLIENT_SCRIPT by hand into a new Client Script
(DocType: Quotation, Apply To: Form) in the desk UI.
"""
import frappe

SCRIPT_NAME = "Quotation Print Guard"

CLIENT_SCRIPT = """
frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (frm.is_new()) return;

		frappe.xcall("erp_overrides.quotation.can_print", { name: frm.doc.name })
			.then((allowed) => {
				// server side is the real gate (erp_overrides.quotation.before_print);
				// this only keeps users from walking into the error
				const print_item = frm.page.menu
					.find(`[data-label="${encodeURIComponent(__("Print"))}"]`)
					.parent();
				print_item.toggleClass("hide", !allowed);

				frm.dashboard.clear_comment();
				if (!allowed) {
					frm.dashboard.add_comment(
						__("This Quotation cannot be printed until it is approved."),
						"orange",
						true
					);
				}
			});
	},
});
""".strip()


def install_print_guard(commit=True):
	"""Create or update the Client Script. Safe to run repeatedly."""
	if frappe.db.exists("Client Script", SCRIPT_NAME):
		doc = frappe.get_doc("Client Script", SCRIPT_NAME)
		doc.update({"dt": "Quotation", "view": "Form", "script": CLIENT_SCRIPT, "enabled": 1})
		doc.save()
		action = "updated"
	else:
		doc = frappe.get_doc({
			"doctype": "Client Script",
			"name": SCRIPT_NAME,
			"dt": "Quotation",
			"view": "Form",
			"enabled": 1,
			"script": CLIENT_SCRIPT,
		})
		doc.insert()
		action = "created"

	if commit:
		frappe.db.commit()

	print(f'{action} Client Script "{SCRIPT_NAME}" on Quotation (Form).')
	print("Reload the desk (Ctrl+Shift+R) to pick it up.")
	return doc.name


def uninstall_print_guard(commit=True):
	if not frappe.db.exists("Client Script", SCRIPT_NAME):
		print(f'No Client Script named "{SCRIPT_NAME}".')
		return

	frappe.delete_doc("Client Script", SCRIPT_NAME)
	if commit:
		frappe.db.commit()

	print(f'deleted Client Script "{SCRIPT_NAME}" — the server side gate is untouched.')


def _main():
	import argparse

	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--site", required=True)
	parser.add_argument("--remove", action="store_true", help="delete the Client Script instead")
	args = parser.parse_args()

	frappe.init(site=args.site)
	frappe.connect()
	try:
		uninstall_print_guard() if args.remove else install_print_guard()
	finally:
		frappe.destroy()


# `__name__` is "__main__" in bench console too, so also check that frappe has not
# already been booted with a site — otherwise running this file in the console
# would run argparse against IPython's argv and frappe.destroy() the live session.
if __name__ == "__main__" and not getattr(frappe.local, "site", None):
	_main()
