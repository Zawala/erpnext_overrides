/**
 * One entry per document in the chain. Forms show only the curated fields here —
 * everything else is left to ERPNext's defaults and validation.
 *
 * field: { fieldname, label, type, options, reqd, span, help, hidden(doc), filters(doc), quickCreate }
 *   type: Data | Link | DynamicLink | Date | Select | Currency | Percent | Text
 *   DynamicLink takes its doctype from doc[options]
 * propagate: header field → same field on every item (ERPNext recalculates the
 *   header from the items, so a header-only edit would be silently undone)
 * onChange: { fieldname: async (doc) => … } runs after the field is set
 */
import { call } from "frappe-ui"
import { boot } from "@/boot"
import { today, addDays } from "@/utils/format"

const company = () => boot.company

// VAT and other charges: picking a Sales Taxes and Charges Template fills the tax rows, as
// desk does (ERPNext applies none by itself unless a template is marked Default)
const taxField = {
	fieldname: "taxes_and_charges", label: "Tax template", type: "Link", options: "Sales Taxes and Charges Template",
	filters: (d) => ({ company: d.company, disabled: 0 }), help: "VAT: pick it for a VAT-registered sale; leave empty if exempt",
}
async function fillTaxes(doc) {
	const rows = doc.taxes_and_charges ? await call("erpnext.controllers.accounts_controller.get_taxes_and_charges", {
		master_doctype: "Sales Taxes and Charges Template", master_name: doc.taxes_and_charges,
	}) : []
	doc.taxes = (rows || []).map((r) => ({ ...r, doctype: "Sales Taxes and Charges" }))
}
const taxChange = { taxes_and_charges: fillTaxes }

export const doctypes = {
	Lead: {
		slug: "leads",
		label: "Leads",
		icon: "user-plus",
		submittable: false,
		listFields: ["name", "lead_name", "company_name", "status", "email_id", "mobile_no", "modified"],
		search: ["lead_name", "company_name", "email_id"],
		title: (d) => d.company_name || d.lead_name || d.name,
		subtitle: (d) => (d.company_name && d.lead_name ? d.lead_name : d.email_id || d.mobile_no),
		columns: [
			{ key: "lead_name", label: "Contact" },
			{ key: "email_id", label: "Email" },
			{ key: "mobile_no", label: "Mobile" },
		],
		filters: [
			{ label: "Open", filters: { status: ["in", ["Lead", "Open", "Replied", "Interested"]] } },
			{ label: "Converted", filters: { status: ["in", ["Opportunity", "Quotation", "Converted"]] } },
			{ label: "Lost", filters: { status: ["in", ["Lost Quotation", "Do Not Contact"]] } },
			{ label: "All", filters: {} },
		],
		sections: [
			{
				label: "Who",
				fields: [
					{ fieldname: "first_name", label: "First name", type: "Data", reqd: (d) => !d.company_name },
					{ fieldname: "last_name", label: "Last name", type: "Data" },
					{ fieldname: "company_name", label: "Organisation", type: "Data", reqd: (d) => !d.first_name },
					{ fieldname: "job_title", label: "Job title", type: "Data" },
					{ fieldname: "email_id", label: "Email", type: "Data", inputType: "email" },
					{ fieldname: "mobile_no", label: "Mobile", type: "Data", inputType: "tel" },
				],
			},
			{
				label: "Qualify",
				fields: [
					{ fieldname: "status", label: "Status", type: "Select", reqd: true,
						options: ["Lead", "Open", "Replied", "Interested", "Lost Quotation", "Do Not Contact"] },
					{ fieldname: "utm_source", label: "Source", type: "Link", options: "UTM Source" },
					{ fieldname: "territory", label: "Territory", type: "Link", options: "Territory" },
					{ fieldname: "industry", label: "Industry", type: "Link", options: "Industry Type" },
					{ fieldname: "lead_owner", label: "Owner", type: "Link", options: "User" },
				],
			},
		],
		defaults: () => ({ status: "Lead", lead_owner: boot.user, company: company() }),
	},

	Opportunity: {
		slug: "opportunities",
		label: "Opportunities",
		icon: "target",
		submittable: false,
		listFields: ["name", "title", "customer_name", "party_name", "status", "opportunity_amount", "currency",
			"expected_closing", "modified"],
		search: ["title", "customer_name", "party_name"],
		title: (d) => d.title || d.customer_name || d.party_name,
		subtitle: (d) => (d.expected_closing ? `Closing ${d.expected_closing}` : d.name),
		amount: (d) => d.opportunity_amount,
		columns: [
			{ key: "expected_closing", label: "Expected close", format: "date" },
			{ key: "opportunity_amount", label: "Value", format: "money", align: "right" },
		],
		filters: [
			{ label: "Open", filters: { status: ["in", ["Open", "Replied"]] } },
			{ label: "Quoted", filters: { status: "Quotation" } },
			{ label: "Converted", filters: { status: "Converted" } },
			{ label: "Lost", filters: { status: ["in", ["Lost", "Closed"]] } },
			{ label: "All", filters: {} },
		],
		sections: [
			{
				label: "Who",
				fields: [
					{ fieldname: "opportunity_from", label: "From", type: "Select", reqd: true,
						options: ["Lead", "Customer", "Prospect"] },
					{ fieldname: "party_name", label: "Party", type: "DynamicLink", options: "opportunity_from", reqd: true,
						quickCreate: (d) => (d.opportunity_from === "Customer" ? "Customer" : null) },
					{ fieldname: "opportunity_owner", label: "Owner", type: "Link", options: "User" },
				],
			},
			{
				label: "Deal",
				fields: [
					{ fieldname: "opportunity_type", label: "Type", type: "Link", options: "Opportunity Type" },
					{ fieldname: "sales_stage", label: "Sales stage", type: "Link", options: "Sales Stage" },
					{ fieldname: "status", label: "Status", type: "Select", reqd: true,
						options: ["Open", "Replied", "Quotation", "Lost", "Closed"] },
					{ fieldname: "transaction_date", label: "Date", type: "Date", reqd: true },
					{ fieldname: "expected_closing", label: "Expected close", type: "Date" },
					{ fieldname: "probability", label: "Probability %", type: "Percent" },
					{ fieldname: "opportunity_amount", label: "Value", type: "Currency" },
				],
			},
		],
		items: { mode: "selling", discount: false },
		defaults: () => ({
			opportunity_from: "Lead",
			status: "Open",
			transaction_date: today(),
			opportunity_owner: boot.user,
			company: company(),
			currency: boot.currency,
			items: [],
		}),
	},

	Quotation: {
		slug: "quotations",
		onChange: taxChange,
		label: "Quotations",
		icon: "file-text",
		submittable: true,
		printable: true,
		listFields: ["name", "customer_name", "party_name", "status", "docstatus", "grand_total", "currency",
			"transaction_date", "valid_till", "modified"],
		search: ["customer_name", "party_name"],
		title: (d) => d.customer_name || d.party_name,
		subtitle: (d) => d.name,
		amount: (d) => d.grand_total,
		columns: [
			{ key: "transaction_date", label: "Date", format: "date" },
			{ key: "valid_till", label: "Valid till", format: "date" },
			{ key: "grand_total", label: "Total", format: "money", align: "right" },
		],
		filters: [
			{ label: "Open", filters: { docstatus: 1, status: ["in", ["Open", "Replied", "Partially Ordered"]] } },
			{ label: "Draft", filters: { docstatus: 0 } },
			{ label: "Ordered", filters: { status: "Ordered" } },
			{ label: "Expired", filters: { status: "Expired" } },
			{ label: "Lost", filters: { status: "Lost" } },
			{ label: "All", filters: { docstatus: ["<", 2] } },
		],
		sections: [
			{
				label: "Customer",
				fields: [
					{ fieldname: "quotation_to", label: "Quote to", type: "Select", reqd: true, options: ["Customer", "Lead"] },
					{ fieldname: "party_name", label: "Customer", type: "DynamicLink", options: "quotation_to", reqd: true,
						quickCreate: (d) => (d.quotation_to === "Customer" ? "Customer" : null) },
					{ fieldname: "transaction_date", label: "Date", type: "Date", reqd: true },
					{ fieldname: "valid_till", label: "Valid till", type: "Date" },
				],
			},
			{
				label: "Pricing",
				fields: [
					{ fieldname: "selling_price_list", label: "Price list", type: "Link", options: "Price List", reqd: true,
						filters: () => ({ selling: 1 }) },
					{ fieldname: "currency", label: "Currency", type: "Link", options: "Currency", reqd: true },
					taxField,
				],
			},
		],
		items: { mode: "selling", discount: true },
		defaults: () => ({
			quotation_to: "Customer",
			order_type: "Sales",
			transaction_date: today(),
			valid_till: addDays(today(), 30),
			company: company(),
			currency: boot.currency,
			selling_price_list: boot.selling_price_list,
			items: [],
		}),
	},

	"Sales Order": {
		slug: "sales-orders",
		onChange: taxChange,
		label: "Sales Orders",
		icon: "shopping-bag",
		submittable: true,
		approval: true,
		margin: true,
		listFields: ["name", "customer_name", "customer", "status", "docstatus", "grand_total", "currency",
			"delivery_date", "po_no", "modified"],
		search: ["customer_name", "po_no"],
		title: (d) => d.customer_name || d.customer,
		subtitle: (d) => (d.po_no ? `${d.name} · PO ${d.po_no}` : d.name),
		amount: (d) => d.grand_total,
		columns: [
			{ key: "po_no", label: "Customer PO" },
			{ key: "delivery_date", label: "Delivery", format: "date" },
			{ key: "grand_total", label: "Total", format: "money", align: "right" },
		],
		filters: [
			{ label: "To deliver & bill", filters: { docstatus: 1, status: ["in", ["To Deliver and Bill", "To Deliver", "To Bill"]] } },
			{ label: "Draft", filters: { docstatus: 0 } },
			{ label: "Completed", filters: { status: "Completed" } },
			{ label: "All", filters: { docstatus: ["<", 2] } },
		],
		sections: [
			{
				label: "Customer",
				fields: [
					{ fieldname: "customer", label: "Customer", type: "Link", options: "Customer", reqd: true, quickCreate: () => "Customer",
						help: "Carried from the quotation — if it is wrong, the quotation was wrong" },
					{ fieldname: "po_no", label: "Customer's PO number", type: "Data",
						help: "Their reference, on our document. It is the proof the revenue is real." },
					{ fieldname: "po_date", label: "Customer's PO date", type: "Date" },
				],
			},
			{
				label: "Dates & pricing",
				fields: [
					{ fieldname: "transaction_date", label: "Date", type: "Date", reqd: true },
					{ fieldname: "delivery_date", label: "Delivery date", type: "Date", reqd: true,
						help: "What we promised. Drives Required By on everything downstream." },
					{ fieldname: "selling_price_list", label: "Price list", type: "Link", options: "Price List", reqd: true,
						filters: () => ({ selling: 1 }) },
					{ fieldname: "currency", label: "Currency", type: "Link", options: "Currency", reqd: true },
					taxField,
				],
			},
		],
		propagate: { delivery_date: "delivery_date" },
		items: { mode: "selling", discount: true },
		defaults: () => ({
			order_type: "Sales",
			transaction_date: today(),
			company: company(),
			currency: boot.currency,
			selling_price_list: boot.selling_price_list,
			items: [],
		}),
	},

	"Delivery Note": {
		slug: "delivery-notes",
		label: "Delivery Notes",
		icon: "package",
		submittable: true,
		printable: true,
		listFields: ["name", "customer_name", "customer", "status", "docstatus", "grand_total", "currency",
			"posting_date", "po_no", "modified"],
		search: ["customer_name", "po_no"],
		title: (d) => d.customer_name || d.customer,
		subtitle: (d) => d.name,
		amount: (d) => d.grand_total,
		columns: [
			{ key: "posting_date", label: "Delivered", format: "date" },
			{ key: "po_no", label: "Customer PO" },
			{ key: "grand_total", label: "Total", format: "money", align: "right" },
		],
		filters: [
			{ label: "To bill", filters: { docstatus: 1, status: ["in", ["To Bill", "Partially Billed"]] } },
			{ label: "Draft", filters: { docstatus: 0 } },
			{ label: "Completed", filters: { status: "Completed" } },
			{ label: "All", filters: { docstatus: ["<", 2] } },
		],
		sections: [
			{
				label: "Delivery",
				fields: [
					{ fieldname: "customer", label: "Customer", type: "Link", options: "Customer", reqd: true },
					{ fieldname: "posting_date", label: "Delivery date", type: "Date", reqd: true,
						help: "The day it actually went out, not the day you are keying it in" },
				],
			},
		],
		// optional proof of hand-over; the server picks the warehouse (erp_overrides.stock_light)
		items: { mode: "selling", discount: true, qtyHint: "Change the quantity to what actually went out — the order stays open for the rest." },
		defaults: () => ({
			posting_date: today(),
			set_posting_time: 1,
			company: company(),
			currency: boot.currency,
			selling_price_list: boot.selling_price_list,
			items: [],
		}),
	},

	"Sales Invoice": {
		slug: "sales-invoices",
		onChange: taxChange,
		label: "Sales Invoices",
		icon: "file",
		submittable: true,
		printable: true,
		listFields: ["name", "customer_name", "customer", "status", "docstatus", "grand_total", "outstanding_amount",
			"currency", "posting_date", "due_date", "modified"],
		search: ["customer_name", "po_no"],
		title: (d) => d.customer_name || d.customer,
		subtitle: (d) => (d.due_date ? `${d.name} · due ${d.due_date}` : d.name),
		amount: (d) => d.grand_total,
		columns: [
			{ key: "posting_date", label: "Date", format: "date" },
			{ key: "due_date", label: "Due", format: "date" },
			{ key: "grand_total", label: "Total", format: "money", align: "right" },
			{ key: "outstanding_amount", label: "Outstanding", format: "money", align: "right" },
		],
		filters: [
			{ label: "Unpaid", filters: { docstatus: 1, outstanding_amount: [">", 0] } },
			{ label: "Overdue", filters: { docstatus: 1, status: ["like", "Overdue%"] } },
			{ label: "Draft", filters: { docstatus: 0 } },
			{ label: "Paid", filters: { status: "Paid" } },
			{ label: "All", filters: { docstatus: ["<", 2] } },
		],
		sections: [
			{
				label: "Invoice",
				fields: [
					{ fieldname: "customer", label: "Customer", type: "Link", options: "Customer", reqd: true },
					{ fieldname: "po_no", label: "Customer's PO number", type: "Data",
						help: "Most customers will not pay an invoice that doesn't quote their PO" },
					{ fieldname: "posting_date", label: "Invoice date", type: "Date", reqd: true },
					{ fieldname: "due_date", label: "Due date", type: "Date",
						help: "Comes from the customer's payment terms — change it only if agreed otherwise" },
					taxField,
				],
			},
		],
		items: { mode: "selling", discount: true },
		defaults: () => ({
			posting_date: today(),
			set_posting_time: 1,
			company: company(),
			currency: boot.currency,
			selling_price_list: boot.selling_price_list,
			items: [],
		}),
	},

	"Purchase Order": {
		slug: "purchase-orders",
		label: "Purchase Orders",
		icon: "truck",
		submittable: true,
		margin: true,
		listFields: ["name", "supplier_name", "supplier", "status", "docstatus", "grand_total", "currency",
			"schedule_date", "modified"],
		search: ["supplier_name"],
		title: (d) => d.supplier_name || d.supplier,
		subtitle: (d) => d.name,
		amount: (d) => d.grand_total,
		columns: [
			{ key: "schedule_date", label: "Required by", format: "date" },
			{ key: "grand_total", label: "Total", format: "money", align: "right" },
		],
		filters: [
			{ label: "To receive & bill", filters: { docstatus: 1, status: ["in", ["To Receive and Bill", "To Receive", "To Bill"]] } },
			{ label: "Draft", filters: { docstatus: 0 } },
			{ label: "Completed", filters: { status: "Completed" } },
			{ label: "All", filters: { docstatus: ["<", 2] } },
		],
		sections: [
			{
				label: "Supplier",
				fields: [
					{ fieldname: "supplier", label: "Supplier", type: "Link", options: "Supplier", reqd: true, quickCreate: () => "Supplier",
						help: "Must already exist — add it properly, with payment terms and billing currency" },
					{ fieldname: "transaction_date", label: "Date", type: "Date", reqd: true },
					{ fieldname: "schedule_date", label: "Required by", type: "Date", reqd: true,
						help: "When the supplier must deliver — before the customer's delivery date" },
				],
			},
			{
				label: "Pricing",
				fields: [
					{ fieldname: "buying_price_list", label: "Price list", type: "Link", options: "Price List",
						filters: () => ({ buying: 1 }) },
					{ fieldname: "currency", label: "Currency", type: "Link", options: "Currency", reqd: true },
				],
			},
		],
		propagate: { schedule_date: "schedule_date" },
		items: { mode: "buying", discount: false, rateLabel: "Our cost" },
		defaults: () => ({
			transaction_date: today(),
			schedule_date: addDays(today(), 7),
			company: company(),
			currency: boot.currency,
			buying_price_list: boot.buying_price_list,
			items: [],
		}),
	},
	// the receipt half of the three-way match: goods arrived, or the service was delivered
	"Purchase Receipt": {
		slug: "receipts",
		label: "Receipts",
		icon: "inbox",
		submittable: true,
		listFields: ["name", "supplier_name", "supplier", "status", "docstatus", "grand_total", "currency",
			"posting_date", "supplier_delivery_note", "modified"],
		search: ["supplier_name", "supplier_delivery_note"],
		title: (d) => d.supplier_name || d.supplier,
		subtitle: (d) => d.name,
		amount: (d) => d.grand_total,
		columns: [
			{ key: "posting_date", label: "Received", format: "date" },
			{ key: "supplier_delivery_note", label: "Supplier's note" },
			{ key: "grand_total", label: "Total", format: "money", align: "right" },
		],
		filters: [
			{ label: "To bill", filters: { docstatus: 1, status: ["in", ["To Bill", "Partly Billed"]] } },
			{ label: "Draft", filters: { docstatus: 0 } },
			{ label: "Completed", filters: { status: "Completed" } },
			{ label: "All", filters: { docstatus: ["<", 2] } },
		],
		sections: [
			{
				label: "Receipt",
				fields: [
					{ fieldname: "supplier", label: "Supplier", type: "Link", options: "Supplier", reqd: true },
					{ fieldname: "posting_date", label: "Received on", type: "Date", reqd: true,
						help: "The day it arrived or the work was done, not the day you are keying it in" },
					{ fieldname: "supplier_delivery_note", label: "Supplier's delivery note",
						help: "Their delivery note or job card number, if there is one" },
				],
			},
		],
		// the server picks the warehouse for hardware (erp_overrides.stock_light)
		items: { mode: "buying", discount: false, rateLabel: "Our cost",
			qtyHint: "Change the quantity to what actually arrived — the order stays open for the rest." },
		defaults: () => ({
			posting_date: today(),
			set_posting_time: 1,
			company: company(),
			currency: boot.currency,
			items: [],
		}),
	},
}

for (const [doctype, cfg] of Object.entries(doctypes)) cfg.doctype = doctype

export const chainOrder = Object.keys(doctypes)
export const chainLanes = [
	{ label: "Sell", doctypes: ["Lead", "Opportunity", "Quotation", "Sales Order", "Delivery Note", "Sales Invoice"] },
	{ label: "Buy", doctypes: ["Purchase Order", "Purchase Receipt"] },
]
// shown in a chain only when it has one: Delivery Notes are optional proof of hand-over
export const optionalStages = ["Delivery Note"]

// From www/sales.py boot; absent (older boot) means allowed — the server still checks
export const can = (doctype, ptype = "read") => boot.permissions?.[doctype]?.[ptype] ?? true
export const bySlug = Object.fromEntries(Object.values(doctypes).map((c) => [c.slug, c]))
export const docRoute = (doctype, name) => `/${doctypes[doctype].slug}/${encodeURIComponent(name)}`

// Next documents in the chain. `when(doc)` returns true, or a reason string why not.
export const nextSteps = {
	Lead: [
		{ target: "Opportunity", hint: "Qualify the deal" },
		{ target: "Quotation", hint: "Straight to a price" },
	],
	Opportunity: [
		{ target: "Quotation", hint: "Price it up",
			when: (d) => !["Lost", "Closed"].includes(d.status) || `Opportunity is ${d.status}` },
	],
	Quotation: [
		{ target: "Sales Order", hint: "The customer said yes",
			when: (d) =>
				(d.status === "Expired" && "Expired — re-open it or raise a fresh quotation") ||
				(d.status === "Lost" && "Quotation was lost") ||
				(d.status === "Ordered" && "Already fully ordered") ||
				true },
	],
	"Sales Order": [
		{ target: "Sales Invoice", hint: "Bill the customer — any hardware goes out with the invoice",
			when: (d) =>
				(["Closed", "On Hold"].includes(d.status) && `Order is ${d.status}`) ||
				(d.per_billed >= 100 && "Everything has been billed") ||
				true },
		{ target: "Purchase Order", label: "Order from supplier", hint: "Buy what this order needs",
			when: (d) =>
				(["Closed", "Completed", "On Hold"].includes(d.status) && `Order is ${d.status}`) ||
				((d.items || []).length && d.items.every((i) => (i.ordered_qty || 0) >= (i.stock_qty || i.qty)) && "Everything has been ordered") ||
				true },
		{ target: "Delivery Note", optional: true, hint: "Optional: signed proof of hand-over",
			when: (d) =>
				(["Closed", "On Hold"].includes(d.status) && `Order is ${d.status}`) ||
				(d.per_delivered >= 100 && "Everything has been delivered") ||
				true },
	],
	"Delivery Note": [
		{ target: "Sales Invoice", hint: "Bill what went out",
			when: (d) => ["To Bill", "Partially Billed"].includes(d.status) || `Delivery is ${d.status}` },
	],
	"Sales Invoice": [],
	"Purchase Order": [
		{ target: "Purchase Receipt", label: "Receive", hint: "The goods arrived, or the service was delivered — Accounts can only pay what was received",
			when: (d) =>
				(["Closed", "Completed", "On Hold", "Delivered"].includes(d.status) && `Order is ${d.status}`) ||
				(d.per_received >= 100 && "Everything has been received") ||
				true },
	],
	"Purchase Receipt": [],
}

// Hand-off from "Create next" to the new-document form
export const pendingDocs = new Map()
