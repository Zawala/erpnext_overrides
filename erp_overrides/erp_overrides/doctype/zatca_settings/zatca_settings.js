// Copyright (c) 2026, Kelvin Zawala and contributors
// For license information, please see license.txt
frappe.ui.form.on("ZATCA Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Onboard"), () =>
			frappe.confirm(
				__("Get a new key and CSIDs from ZATCA ({0})? This starts a new invoice chain.", [frm.doc.environment]),
				() => frappe.call({
					method: "erp_overrides.zatca.onboarding.run",
					freeze: true,
					freeze_message: __("Onboarding with ZATCA…"),
				}).then(() => frm.reload_doc()),
			),
		);
	},
});
