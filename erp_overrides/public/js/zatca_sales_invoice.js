// ZATCA Phase 2 POC (erp_overrides.zatca): status, QR and retry on a submitted Sales Invoice.
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		const status = frm.doc.zatca_status;
		if (!status || frm.doc.docstatus !== 1) return;
		const colour = { Cleared: "green", Reported: "green", "Accepted with warnings": "orange",
			Pending: "blue", Failed: "red", Rejected: "red" }[status] || "gray";
		frm.dashboard.add_indicator(__("ZATCA: {0}", [__(status)]), colour);

		if (["Pending", "Failed", "Rejected"].includes(status)) {
			frm.add_custom_button(__("Send to ZATCA again"), () =>
				frappe.call({
					method: "erp_overrides.zatca.submit.retry",
					args: { invoice: frm.doc.name },
					freeze: true,
					freeze_message: __("Sending to ZATCA…"),
				}).then(() => frm.reload_doc()),
			);
		}
		if (frm.doc.zatca_submission) {
			frm.add_custom_button(__("ZATCA response"), () =>
				frappe.set_route("Form", "ZATCA Submission", frm.doc.zatca_submission), __("View"));
		}
		if (frm.doc.zatca_qr) {
			frappe.call("erp_overrides.zatca.submit.qr_svg", { invoice: frm.doc.name }).then((r) => {
				if (r.message) frm.dashboard.set_headline(`<div style="display:flex;gap:12px;align-items:center">
					${r.message}<span>${__("ZATCA QR code")}</span></div>`);
			});
		}
	},
});
