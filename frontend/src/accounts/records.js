/**
 * The accounts documents editable in the app: invoices, payments, journals, dunning and the
 * templates behind them. Same shape as the sales registry (src/doctypes/index.js), plus:
 *
 * tables:  [{ field, doctype, label, help, readonly, columns, defaults(doc), onChange(row, fieldname, doc), fetch }]
 *          columns as in components/ChildTable.vue; fetch: { label, run(doc) } fills the table from the server
 * onChange: { fieldname: async (doc) => {} } — after a header field changes (taxes from a template, party accounts)
 * summary(doc): [{ label, value, warn }] for the right rail
 * actions(doc): [{ label, icon, run(doc) → { slug, doc } }] — make a related document (payment, dunning)
 * noNew: the document is only ever made from another one (a dunning from an overdue invoice)
 */
import { call } from "frappe-ui"
import { boot } from "@/boot"
import { today } from "@/utils/format"
import { cur } from "./api"

const company = () => boot.company
const STATUS = (d) => (d.docstatus === 2 ? "Cancelled" : d.docstatus === 0 ? "Draft" : d.status || "Submitted")
const ENABLED = (d) => (d.disabled ? "Disabled" : "Enabled")
const leafAccount = (_row, doc) => ({ company: doc.company || company(), is_group: 0, disabled: 0 })
const accountName = (account) => String(account || "").replace(/ - [^-]+$/, "")

// ── Taxes ───────────────────────────────────────────────────────────────────

const CHARGE_TYPES = ["On Net Total", "Actual", "On Previous Row Amount", "On Previous Row Total", "On Item Quantity"]

function taxColumns(buying) {
	return [
		...(buying ? [
			{ fieldname: "add_deduct_tax", label: "Add or deduct", type: "Select", options: ["Add", "Deduct"], reqd: true, width: "w-32" },
			{ fieldname: "category", label: "Consider for", type: "Select", options: ["Total", "Valuation", "Valuation and Total"], reqd: true, width: "w-40" },
		] : []),
		{ fieldname: "charge_type", label: "Type", type: "Select", options: CHARGE_TYPES, reqd: true, width: "w-44" },
		{ fieldname: "account_head", label: "Account", type: "Link", options: "Account", reqd: true, filters: leafAccount, width: "min-w-[220px]" },
		{ fieldname: "rate", label: "Rate %", type: "Float", width: "w-24" },
		{ fieldname: "tax_amount", label: "Amount", type: "Currency", width: "w-32" },
		{ fieldname: "description", label: "Description", type: "Data", reqd: true },
		{ fieldname: "included_in_print_rate", label: "In price", type: "Check", width: "w-20" },
	]
}

const taxTable = (doctype, buying, help) => ({
	field: "taxes",
	doctype,
	label: "Taxes and charges",
	help,
	columns: taxColumns(buying),
	defaults: () => ({ charge_type: "On Net Total", ...(buying ? { add_deduct_tax: "Add", category: "Total" } : {}) }),
	// description is mandatory; the account's name is what desk would suggest
	onChange: (row, fieldname) => {
		if (fieldname === "account_head" && !row.description) row.description = accountName(row.account_head)
	},
})

/** Picking a template on an invoice replaces its tax rows with the template's, as desk does. */
const fillTaxes = (templateDoctype, rowDoctype) => async (doc) => {
	if (!doc.taxes_and_charges) return
	const rows = await call("erpnext.controllers.accounts_controller.get_taxes_and_charges", {
		master_doctype: templateDoctype, master_name: doc.taxes_and_charges,
	})
	doc.taxes = (rows || []).map((r) => ({ ...r, doctype: rowDoctype, _key: Math.random().toString(36).slice(2) }))
}

const templateRecord = (doctype, slug, label, rowDoctype, buying) => ({
	doctype, slug, label,
	icon: buying ? "percent" : "tag",
	submittable: false,
	listFields: ["name", "title", "company", "is_default", "disabled", "tax_category", "modified"],
	search: ["title"],
	title: (d) => d.title || d.name || `New ${label.toLowerCase().replace(/s$/, "")}`,
	subtitle: (d) => [d.is_default ? "Default" : "", d.tax_category].filter(Boolean).join(" · ") || d.company,
	status: ENABLED,
	columns: [
		{ key: "tax_category", label: "Tax category" },
		{ key: "is_default", label: "Default", format: "check" },
	],
	filters: [
		{ label: "Enabled", filters: { disabled: 0 } },
		{ label: "Disabled", filters: { disabled: 1 } },
		{ label: "All", filters: {} },
	],
	sections: [{
		label: "Template",
		fields: [
			{ fieldname: "title", label: "Title", type: "Data", reqd: true, help: "What people pick on an invoice, e.g. “VAT 15.5%”" },
			{ fieldname: "company", label: "Company", type: "Link", options: "Company", reqd: true },
			{ fieldname: "tax_category", label: "Tax category", type: "Link", options: "Tax Category" },
			{ fieldname: "is_default", label: "Default", type: "Check", checkLabel: "Use on new invoices" },
			{ fieldname: "disabled", label: "Disabled", type: "Check", checkLabel: "Hide from invoices" },
		],
	}],
	tables: [taxTable(rowDoctype, buying, buying
		? "“Deduct” is for withholding tax; “Valuation” adds a charge to stock cost instead of the bill"
		: "“On Net Total” takes the rate on the lines; “Actual” is a fixed amount")],
	defaults: () => ({ company: company(), taxes: [] }),
})

// ── Invoices ────────────────────────────────────────────────────────────────

const invoiceFilters = [
	{ label: "Unpaid", filters: { docstatus: 1, outstanding_amount: [">", 0] } },
	{ label: "Overdue", filters: { docstatus: 1, status: ["like", "Overdue%"] } },
	{ label: "Draft", filters: { docstatus: 0 } },
	{ label: "Paid", filters: { status: "Paid" } },
	{ label: "Returns", filters: { is_return: 1 } },
	{ label: "All", filters: { docstatus: ["<", 2] } },
]

const invoiceSummary = (d) => [
	{ label: "Net total", value: cur(d.net_total, d.currency) },
	{ label: "Taxes", value: cur(d.total_taxes_and_charges, d.currency) },
	{ label: "Grand total", value: cur(d.grand_total, d.currency), strong: true },
	...(d.docstatus === 1 ? [{ label: "Outstanding", value: cur(d.outstanding_amount, d.currency), warn: d.outstanding_amount > 0, strong: true }] : []),
]

/** ERPNext's own "Payment" button on an invoice: a Payment Entry against it, allocated in full. */
// three-way match badges (erp_overrides.three_way)
export const MATCH_THEME = { matched: "bg-green-50 text-green-800", no_po: "bg-gray-100 text-gray-600",
	not_received: "bg-amber-50 text-amber-900", qty_over: "bg-red-50 text-red-800", rate_diff: "bg-red-50 text-red-800" }

const payAction = (doctype, label) => ({
	label, icon: "send",
	show: (d) => d.docstatus === 1 && d.outstanding_amount > 0,
	run: async (d) => ({
		slug: "payment-entries",
		doc: await call("erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry", { dt: doctype, dn: d.name }),
	}),
})

export const records = {
	"sales-invoices": {
		doctype: "Sales Invoice", label: "Sales invoices", icon: "file-text",
		submittable: true, printable: true,
		listFields: ["name", "customer_name", "customer", "status", "docstatus", "grand_total", "outstanding_amount",
			"currency", "posting_date", "due_date", "modified"],
		search: ["customer_name", "po_no"],
		title: (d) => d.customer_name || d.customer || "New sales invoice",
		subtitle: (d) => (d.due_date ? `${d.name} · due ${d.due_date}` : d.name),
		amount: (d) => d.grand_total,
		status: STATUS,
		columns: [
			{ key: "posting_date", label: "Date", format: "date" },
			{ key: "due_date", label: "Due", format: "date" },
			{ key: "grand_total", label: "Total", format: "money", align: "right" },
			{ key: "outstanding_amount", label: "Outstanding", format: "money", align: "right" },
		],
		filters: invoiceFilters,
		sections: [{
			label: "Invoice",
			fields: [
				{ fieldname: "customer", label: "Customer", type: "Link", options: "Customer", reqd: true },
				{ fieldname: "po_no", label: "Customer's PO number", type: "Data" },
				{ fieldname: "posting_date", label: "Invoice date", type: "Date", reqd: true },
				{ fieldname: "due_date", label: "Due date", type: "Date", help: "Leave empty to take it from the payment terms" },
				{ fieldname: "payment_terms_template", label: "Payment terms", type: "Link", options: "Payment Terms Template", placeholder: "Pick payment terms" },
				{ fieldname: "taxes_and_charges", label: "Tax template", type: "Link", options: "Sales Taxes and Charges Template", placeholder: "Pick a tax template",
					filters: (d) => ({ company: d.company, disabled: 0 }), help: "Fills the taxes below" },
			],
		}],
		items: { mode: "selling", discount: true },
		tables: [taxTable("Sales Taxes and Charges", false)],
		onChange: { taxes_and_charges: fillTaxes("Sales Taxes and Charges Template", "Sales Taxes and Charges") },
		summary: invoiceSummary,
		actions: (d) => [
			payAction("Sales Invoice", "Receive payment"),
			{
				label: "Create dunning", icon: "alert-triangle",
				show: (x) => x.docstatus === 1 && x.outstanding_amount > 0 && String(x.status).startsWith("Overdue"),
				run: async (x) => ({
					slug: "dunnings",
					doc: await call("erpnext.accounts.doctype.sales_invoice.sales_invoice.create_dunning", { source_name: x.name }),
				}),
			},
		].filter((a) => a.show(d)),
		defaults: () => ({
			posting_date: today(), set_posting_time: 1, company: company(), currency: boot.currency,
			selling_price_list: boot.selling_price_list, items: [], taxes: [],
		}),
	},

	"purchase-invoices": {
		doctype: "Purchase Invoice", label: "Purchase invoices", icon: "file-minus",
		submittable: true, printable: true,
		listFields: ["name", "supplier_name", "supplier", "bill_no", "status", "docstatus", "grand_total", "outstanding_amount",
			"currency", "posting_date", "due_date", "modified"],
		search: ["supplier_name", "bill_no"],
		title: (d) => d.supplier_name || d.supplier || "New purchase invoice",
		subtitle: (d) => [d.bill_no || d.name, d.due_date ? `due ${d.due_date}` : ""].filter(Boolean).join(" · "),
		amount: (d) => d.grand_total,
		status: STATUS,
		columns: [
			{ key: "bill_no", label: "Supplier's invoice no." },
			{ key: "posting_date", label: "Date", format: "date" },
			{ key: "due_date", label: "Due", format: "date" },
			{ key: "grand_total", label: "Total", format: "money", align: "right" },
			{ key: "outstanding_amount", label: "Outstanding", format: "money", align: "right" },
		],
		filters: invoiceFilters,
		sections: [{
			label: "Bill",
			fields: [
				{ fieldname: "supplier", label: "Supplier", type: "Link", options: "Supplier", reqd: true },
				{ fieldname: "bill_no", label: "Supplier's invoice no.", type: "Data" },
				{ fieldname: "bill_date", label: "Supplier's invoice date", type: "Date" },
				{ fieldname: "posting_date", label: "Posting date", type: "Date", reqd: true },
				{ fieldname: "due_date", label: "Due date", type: "Date", help: "Leave empty to take it from the payment terms" },
				{ fieldname: "taxes_and_charges", label: "Tax template", type: "Link", options: "Purchase Taxes and Charges Template", placeholder: "Pick a tax template",
					filters: (d) => ({ company: d.company, disabled: 0 }), help: "Fills the taxes below" },
			],
		}],
		items: { mode: "buying", discount: false },
		tables: [taxTable("Purchase Taxes and Charges", true)],
		onChange: { taxes_and_charges: fillTaxes("Purchase Taxes and Charges Template", "Purchase Taxes and Charges") },
		summary: invoiceSummary,
		actions: (d) => [payAction("Purchase Invoice", "Pay this bill")].filter((a) => a.show(d)),
		defaults: () => ({
			posting_date: today(), set_posting_time: 1, company: company(), currency: boot.currency,
			buying_price_list: boot.buying_price_list, items: [], taxes: [],
		}),
	},

	// ── Payments ──────────────────────────────────────────────────────────────
	"payment-entries": {
		doctype: "Payment Entry", label: "Payment entries", icon: "repeat",
		submittable: true, printable: true,
		listFields: ["name", "payment_type", "party_type", "party", "party_name", "paid_amount", "paid_from_account_currency",
			"paid_to_account_currency", "status", "docstatus", "posting_date", "reference_no", "modified"],
		search: ["party_name", "party", "reference_no"],
		title: (d) => d.party_name || d.party || (d.payment_type === "Internal Transfer" ? "Internal transfer" : "New payment"),
		subtitle: (d) => [d.payment_type, d.reference_no || d.name].filter(Boolean).join(" · "),
		amount: (d) => d.paid_amount,
		currency: (d) => (d.payment_type === "Receive" ? d.paid_to_account_currency : d.paid_from_account_currency),
		status: STATUS,
		columns: [
			{ key: "payment_type", label: "Type" },
			{ key: "posting_date", label: "Date", format: "date" },
			{ key: "reference_no", label: "Reference" },
			{ key: "paid_amount", label: "Amount", format: "money", align: "right" },
		],
		filters: [
			{ label: "Received", filters: { docstatus: 1, payment_type: "Receive" } },
			{ label: "Paid", filters: { docstatus: 1, payment_type: "Pay" } },
			{ label: "Transfers", filters: { docstatus: 1, payment_type: "Internal Transfer" } },
			{ label: "Draft", filters: { docstatus: 0 } },
			{ label: "All", filters: { docstatus: ["<", 2] } },
		],
		sections: [
			{
				label: "Payment",
				fields: [
					{ fieldname: "payment_type", label: "Type", type: "Select", options: ["Receive", "Pay", "Internal Transfer"], reqd: true },
					{ fieldname: "posting_date", label: "Date", type: "Date", reqd: true },
					{ fieldname: "mode_of_payment", label: "Mode of payment", type: "Link", options: "Mode of Payment" },
					{ fieldname: "party_type", label: "Party type", type: "Select", options: ["Customer", "Supplier", "Employee"],
						reqd: true, hidden: (d) => d.payment_type === "Internal Transfer" },
					{ fieldname: "party", label: "Party", type: "DynamicLink", options: "party_type", reqd: true,
						hidden: (d) => d.payment_type === "Internal Transfer" },
				],
			},
			{
				label: "Money",
				fields: [
					{ fieldname: "paid_from", label: "Paid from", type: "Link", options: "Account", reqd: true,
						filters: (d) => ({ company: d.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] }),
						hidden: (d) => d.payment_type === "Receive", help: "Our bank or cash account" },
					{ fieldname: "paid_to", label: "Received into", type: "Link", options: "Account", reqd: true,
						filters: (d) => ({ company: d.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] }),
						hidden: (d) => d.payment_type === "Pay", help: "Our bank or cash account" },
					{ fieldname: "paid_amount", label: "Amount", type: "Currency", reqd: true },
					{ fieldname: "received_amount", label: "Amount received", type: "Currency",
						hidden: (d) => d.payment_type !== "Internal Transfer", help: "Differs from the amount when the two accounts are in different currencies" },
					{ fieldname: "reference_no", label: "Bank reference", type: "Data", help: "Needed for a bank account: cheque or transfer number" },
					{ fieldname: "reference_date", label: "Reference date", type: "Date", reqd: (d) => !!d.reference_no },
					{ fieldname: "remarks", label: "Remarks", type: "Text", span: 3 },
				],
			},
		],
		tables: [{
			field: "references",
			doctype: "Payment Entry Reference",
			label: "Invoices this pays",
			help: "Leave empty for an advance; the server checks each amount against what's outstanding",
			columns: [
				{ fieldname: "reference_doctype", label: "Type", type: "Select", reqd: true, width: "w-36",
					options: ["Sales Invoice", "Purchase Invoice", "Journal Entry", "Sales Order", "Purchase Order", "Dunning"] },
				{ fieldname: "reference_name", label: "Document", type: "DynamicLink", options: "reference_doctype", reqd: true },
				{ fieldname: "due_date", label: "Due", type: "Date", readonly: true, width: "w-28" },
				{ fieldname: "outstanding_amount", label: "Outstanding", type: "Currency", readonly: true, width: "w-28" },
				{ fieldname: "allocated_amount", label: "Allocated", type: "Currency", total: true, width: "w-28" },
			],
			defaults: (d) => ({ reference_doctype: d.party_type === "Supplier" ? "Purchase Invoice" : "Sales Invoice" }),
			fetch: {
				label: "Get outstanding invoices",
				show: (d) => d.payment_type !== "Internal Transfer" && d.party,
				run: fetchOutstanding,
			},
		}],
		onChange: {
			payment_type: (d) => {
				if (d.payment_type === "Internal Transfer") Object.assign(d, { party: "", references: [] })
				else d.party_type = d.payment_type === "Pay" ? "Supplier" : "Customer"
			},
			party_type: (d) => Object.assign(d, { party: "", references: [] }),
			party: (d) => (d.references = []),
			// ERPNext wants a received amount before it works one out; a receipt or payment is in one currency here
			paid_amount: (d) => {
				if (d.payment_type !== "Internal Transfer" || !d.received_amount) d.received_amount = d.paid_amount
			},
		},
		summary: (d) => [
			{ label: "Amount", value: cur(d.paid_amount, d.paid_from_account_currency) },
			{ label: "Allocated to invoices", value: cur(d.total_allocated_amount ?? sum(d.references, "allocated_amount"), d.paid_from_account_currency) },
			...(d.unallocated_amount ? [{ label: "Unallocated (advance)", value: cur(d.unallocated_amount, d.paid_from_account_currency), warn: true }] : []),
			...(d.difference_amount ? [{ label: "Difference", value: cur(d.difference_amount), warn: true, strong: true }] : []),
		],
		defaults: () => ({ payment_type: "Receive", party_type: "Customer", posting_date: today(), company: company(), references: [] }),
	},

	"journal-entries": {
		doctype: "Journal Entry", label: "Journal entries", icon: "book-open",
		submittable: true, printable: true,
		// a journal entry has no status field; docstatus says it all
		listFields: ["name", "title", "voucher_type", "total_debit", "docstatus", "posting_date", "cheque_no", "modified"],
		search: ["title", "cheque_no", "user_remark"],
		title: (d) => d.title || d.name || "New journal entry",
		subtitle: (d) => [d.voucher_type, d.cheque_no || d.name].filter(Boolean).join(" · "),
		amount: (d) => d.total_debit,
		status: STATUS,
		columns: [
			{ key: "voucher_type", label: "Type" },
			{ key: "posting_date", label: "Date", format: "date" },
			{ key: "cheque_no", label: "Reference" },
			{ key: "total_debit", label: "Total", format: "money", align: "right" },
		],
		filters: [
			{ label: "Submitted", filters: { docstatus: 1 } },
			{ label: "Draft", filters: { docstatus: 0 } },
			{ label: "All", filters: { docstatus: ["<", 2] } },
		],
		sections: [{
			label: "Entry",
			fields: [
				{ fieldname: "voucher_type", label: "Type", type: "Select", reqd: true,
					options: ["Journal Entry", "Bank Entry", "Cash Entry", "Credit Note", "Debit Note", "Contra Entry", "Write Off Entry", "Opening Entry"] },
				{ fieldname: "posting_date", label: "Date", type: "Date", reqd: true },
				{ fieldname: "cheque_no", label: "Reference", type: "Data", reqd: (d) => ["Bank Entry"].includes(d.voucher_type) },
				{ fieldname: "cheque_date", label: "Reference date", type: "Date", reqd: (d) => !!d.cheque_no },
				{ fieldname: "user_remark", label: "Remark", type: "Text", span: 3 },
			],
		}],
		tables: [{
			field: "accounts",
			doctype: "Journal Entry Account",
			label: "Accounts",
			help: "Debits must equal credits. A receivable or payable account needs the customer or supplier.",
			columns: [
				{ fieldname: "account", label: "Account", type: "Link", options: "Account", reqd: true, filters: leafAccount, width: "min-w-[220px]" },
				{ fieldname: "party_type", label: "Party type", type: "Select", options: ["", "Customer", "Supplier", "Employee"], width: "w-32" },
				{ fieldname: "party", label: "Party", type: "DynamicLink", options: "party_type" },
				{ fieldname: "debit_in_account_currency", label: "Debit", type: "Currency", total: true, width: "w-36" },
				{ fieldname: "credit_in_account_currency", label: "Credit", type: "Currency", total: true, width: "w-36" },
				{ fieldname: "user_remark", label: "Remark", type: "Data" },
			],
			onChange: (row, fieldname) => {
				if (fieldname === "party_type") row.party = ""
			},
		}],
		summary: (d) => {
			const debit = sum(d.accounts, "debit_in_account_currency")
			const credit = sum(d.accounts, "credit_in_account_currency")
			return [
				{ label: "Debit", value: cur(debit) },
				{ label: "Credit", value: cur(credit) },
				{ label: "Difference", value: cur(debit - credit), warn: Math.abs(debit - credit) >= 0.005, strong: true },
			]
		},
		defaults: () => ({ voucher_type: "Journal Entry", posting_date: today(), company: company(), accounts: [] }),
	},

	dunnings: {
		doctype: "Dunning", label: "Dunning", icon: "alert-triangle",
		submittable: true, printable: true,
		noNew: "Start a dunning from an overdue sales invoice (Create dunning).",
		listFields: ["name", "customer_name", "customer", "dunning_type", "grand_total", "currency", "status", "docstatus", "posting_date", "modified"],
		search: ["customer_name", "customer"],
		title: (d) => d.customer_name || d.customer || "New dunning",
		subtitle: (d) => [d.dunning_type, d.name].filter(Boolean).join(" · "),
		amount: (d) => d.grand_total,
		status: STATUS,
		columns: [
			{ key: "dunning_type", label: "Level" },
			{ key: "posting_date", label: "Date", format: "date" },
			{ key: "grand_total", label: "Total", format: "money", align: "right" },
		],
		filters: [
			{ label: "Unresolved", filters: { docstatus: 1, status: "Unresolved" } },
			{ label: "Draft", filters: { docstatus: 0 } },
			{ label: "Resolved", filters: { status: "Resolved" } },
			{ label: "All", filters: { docstatus: ["<", 2] } },
		],
		sections: [{
			label: "Dunning",
			fields: [
				{ fieldname: "customer", label: "Customer", type: "Link", options: "Customer", reqd: true },
				{ fieldname: "posting_date", label: "Date", type: "Date", reqd: true },
				{ fieldname: "dunning_type", label: "Dunning type", type: "Link", options: "Dunning Type",
					filters: (d) => ({ company: d.company }), help: "Sets the fee, interest and letter text" },
				{ fieldname: "rate_of_interest", label: "Interest % a year", type: "Float" },
				{ fieldname: "dunning_fee", label: "Fee", type: "Currency" },
			],
		}],
		tables: [{
			field: "overdue_payments",
			doctype: "Overdue Payment",
			label: "Overdue payments",
			readonly: true,
			columns: [
				{ fieldname: "sales_invoice", label: "Invoice", type: "Link", options: "Sales Invoice" },
				{ fieldname: "due_date", label: "Due", type: "Date" },
				{ fieldname: "overdue_days", label: "Days overdue", type: "Data" },
				{ fieldname: "outstanding", label: "Outstanding", type: "Currency", total: true },
				{ fieldname: "interest", label: "Interest", type: "Currency", total: true },
			],
		}],
		summary: (d) => [
			{ label: "Outstanding", value: cur(d.total_outstanding, d.currency) },
			{ label: "Interest", value: cur(d.total_interest, d.currency) },
			{ label: "Fee", value: cur(d.dunning_fee, d.currency) },
			{ label: "Grand total", value: cur(d.grand_total, d.currency), strong: true },
		],
		actions: (d) => [{
			label: "Receive payment", icon: "send",
			show: (x) => x.docstatus === 1 && x.status === "Unresolved",
			run: async (x) => ({
				slug: "payment-entries",
				doc: await call("erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry", { dt: "Dunning", dn: x.name }),
			}),
		}].filter((a) => a.show(d)),
		defaults: () => ({ posting_date: today(), company: company(), overdue_payments: [] }),
	},

	// ── Templates ─────────────────────────────────────────────────────────────
	"payment-terms": {
		doctype: "Payment Terms Template", label: "Payment terms", icon: "calendar",
		submittable: false,
		listFields: ["name", "template_name", "modified"],
		search: ["template_name"],
		title: (d) => d.template_name || d.name || "New payment terms",
		subtitle: (d) => d.name,
		status: () => "",
		columns: [],
		filters: [{ label: "All", filters: {} }],
		sections: [{
			label: "Terms",
			fields: [
				{ fieldname: "template_name", label: "Name", type: "Data", reqd: true, help: "e.g. “30 days”, “50% upfront, 50% on delivery”" },
				{ fieldname: "allocate_payment_based_on_payment_terms", label: "Allocate payments per term", type: "Check",
					checkLabel: "Match payments to each term in turn" },
			],
		}],
		tables: [{
			field: "terms",
			doctype: "Payment Terms Template Detail",
			label: "Instalments",
			help: "Portions must add up to 100",
			columns: [
				{ fieldname: "payment_term", label: "Payment term", type: "Link", options: "Payment Term" },
				{ fieldname: "invoice_portion", label: "Portion %", type: "Float", reqd: true, total: true, width: "w-28" },
				{ fieldname: "due_date_based_on", label: "Due", type: "Select", reqd: true,
					options: ["Day(s) after invoice date", "Day(s) after the end of the invoice month", "Month(s) after the end of the invoice month"] },
				{ fieldname: "credit_days", label: "Days", type: "Int", width: "w-24" },
				{ fieldname: "credit_months", label: "Months", type: "Int", width: "w-24" },
				{ fieldname: "mode_of_payment", label: "Mode", type: "Link", options: "Mode of Payment" },
			],
			defaults: (d) => ({ due_date_based_on: "Day(s) after invoice date", invoice_portion: Math.max(0, 100 - sum(d.terms, "invoice_portion")) }),
		}],
		defaults: () => ({ terms: [] }),
	},

	"sales-tax-templates": templateRecord("Sales Taxes and Charges Template", "sales-tax-templates", "Sales tax templates",
		"Sales Taxes and Charges", false),
	"purchase-tax-templates": templateRecord("Purchase Taxes and Charges Template", "purchase-tax-templates", "Purchase tax templates",
		"Purchase Taxes and Charges", true),
}

// sidebar order and grouping
export const recordGroups = [
	{ label: "Documents", slugs: ["sales-invoices", "purchase-invoices", "payment-entries", "journal-entries", "dunnings"] },
	{ label: "Templates", slugs: ["sales-tax-templates", "purchase-tax-templates", "payment-terms"] },
]

for (const [slug, r] of Object.entries(records)) r.slug = slug

export const canRead = (r) => !!boot.permissions?.[r.doctype]?.read
/** The in-app page for a document, or null when it isn't one of these (or the role can't read it): open desk instead. */
export const recordRoute = (doctype, name) => {
	const r = Object.values(records).find((x) => x.doctype === doctype)
	return r && canRead(r) ? `/records/${r.slug}${name ? `/${encodeURIComponent(name)}` : ""}` : null
}
export const canCreate = (r) => !!boot.permissions?.[r.doctype]?.create && !r.noNew

// a document made by an action, waiting for the New page to pick it up
export const pendingRecords = new Map()

function sum(rows, field) {
	return (rows || []).reduce((s, r) => s + Number(r[field] || 0), 0)
}

/** The party's open invoices into references, allocating the amount oldest first (as desk does). */
async function fetchOutstanding(doc) {
	const party = await call("erpnext.accounts.doctype.payment_entry.payment_entry.get_party_details", {
		company: doc.company, party_type: doc.party_type, party: doc.party, date: doc.posting_date,
	})
	const open = await call("erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_reference_documents", {
		args: {
			company: doc.company, party_type: doc.party_type, party: doc.party, party_account: party.party_account,
			posting_date: doc.posting_date, get_outstanding_invoices: true,
		},
	})
	// no amount yet: pay everything open; otherwise spread the amount over the oldest first
	const full = !Number(doc.paid_amount)
	let left = Number(doc.paid_amount || 0)
	doc.references = (open || []).map((r) => {
		const out = Number(r.outstanding_amount || 0)
		const allocated = full ? out : Math.max(0, Math.min(left, out))
		left -= allocated
		return {
			_key: Math.random().toString(36).slice(2), doctype: "Payment Entry Reference",
			reference_doctype: r.voucher_type, reference_name: r.voucher_no, due_date: r.due_date, bill_no: r.bill_no,
			payment_term: r.payment_term, total_amount: r.invoice_amount, outstanding_amount: out,
			exchange_rate: r.exchange_rate, allocated_amount: allocated,
		}
	})
	if (!doc.references.length) return "No open invoices for this party."
	if (full) doc.paid_amount = sum(doc.references, "allocated_amount")
	return `${doc.references.length} open document${doc.references.length === 1 ? "" : "s"} added.`
}
