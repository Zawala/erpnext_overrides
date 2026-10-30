// Copyright (c) 2025, Kelvin Zawala and contributors
// For license information, please see license.txt

frappe.ui.form.on("Egp Settings", {
	onload_post_render: function(frm){

        frm.add_custom_button(__('Execute Now'), function(frm){
        if (cur_frm.is_dirty()) {
            frappe.show_alert('Save Egp Doctype First')
        }
        frappe.call({
            method: "erp_overrides.scrapers.get_tenders",
            freeze: true,
            callback: function(r) {
                frappe.msgprint('Data Fetched')
                    }
                });
            	
    });;
    },
});
