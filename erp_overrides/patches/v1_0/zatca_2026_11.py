# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""ZATCA Phase 2 POC (erp_overrides.zatca): status, UUID and QR on Sales Invoice, and the two
Saudi address parts ERPNext's Address has no field for (both required on standard invoices)."""
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Sales Invoice": [
		dict(fieldname="zatca_section", label="ZATCA", fieldtype="Section Break", insert_after="amended_from",
		     collapsible=1, depends_on="eval:doc.zatca_submission"),
		dict(fieldname="zatca_status", label="ZATCA status", fieldtype="Data", read_only=1, allow_on_submit=1,
		     no_copy=1, in_standard_filter=1, insert_after="zatca_section"),
		dict(fieldname="zatca_submission", label="ZATCA submission", fieldtype="Link", options="ZATCA Submission",
		     read_only=1, allow_on_submit=1, no_copy=1, insert_after="zatca_status"),
		dict(fieldname="zatca_column", fieldtype="Column Break", insert_after="zatca_submission"),
		dict(fieldname="zatca_uuid", label="ZATCA UUID", fieldtype="Data", read_only=1, allow_on_submit=1,
		     no_copy=1, insert_after="zatca_column"),
		dict(fieldname="zatca_qr", label="ZATCA QR", fieldtype="Small Text", read_only=1, allow_on_submit=1,
		     no_copy=1, hidden=1, insert_after="zatca_uuid"),
	],
	"Address": [
		dict(fieldname="zatca_building_number", label="Building number (KSA)", fieldtype="Data",
		     insert_after="address_line2", description="4 digits. Needed on Saudi B2B e-invoices."),
		dict(fieldname="zatca_district", label="District (KSA)", fieldtype="Data",
		     insert_after="zatca_building_number"),
	],
}


def execute():
	create_custom_fields(FIELDS, update=True)
