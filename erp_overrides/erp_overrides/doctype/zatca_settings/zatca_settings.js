// Copyright (c) 2026, Kelvin Zawala and contributors
// For license information, please see license.txt
frappe.ui.form.on("ZATCA Settings", {
	refresh(frm) {
		const call = (method, message) =>
			frappe.call({ method, freeze: true, freeze_message: message }).then(() => frm.reload_doc());

		frm.add_custom_button(__("Onboard"), () =>
			frappe.confirm(
				__("Get a new key and CSIDs from ZATCA ({0})? This starts a new invoice chain.", [frm.doc.environment]),
				() => call("erp_overrides.zatca.onboarding.run", __("Onboarding with ZATCA…")),
			),
		);
		if (frm.doc.certificate_expiry) {
			frm.add_custom_button(__("Renew CSID"), () =>
				frappe.confirm(
					__("Renew the production CSID with a new key? Uses the OTP above; the invoice chain carries on."),
					() => call("erp_overrides.zatca.onboarding.renew", __("Renewing with ZATCA…")),
				),
			);
		}
	},
});
