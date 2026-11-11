// Copyright (c) 2026, Kelvin Zawala and contributors
// For license information, please see license.txt
frappe.ui.form.on("ZATCA Settings", {
	refresh(frm) {
		if (frm.doc.enabled) {
			frappe.call("erp_overrides.zatca.submit.backlog").then(({ message: b }) => {
				if (!b) return;
				const waiting = b.pending + b.failed + b.rejected;
				const text = waiting
					? __("Outbox: {0} pending, {1} failed ({2} given up), {3} rejected. {4} simplified invoice(s) near the 24-hour limit.",
						[b.pending, b.failed, b.gave_up, b.rejected, b.overdue])
					: __("Outbox: everything has been sent to ZATCA.");
				frm.set_intro(text, waiting ? (b.overdue || b.gave_up ? "red" : "orange") : "green");
			});
		}
		const call =(method, message) =>
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
