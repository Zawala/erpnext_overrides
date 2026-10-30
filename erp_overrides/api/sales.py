# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Backend for the /sales PWA (Lead → Purchase Order).

Every "create next document" goes through `make_next`, which only dispatches to
ERPNext's own mappers, so the PWA carries exactly what desk's Create button does.
Approval enforcement stays in the "Credit and Discount Approval" server script;
`get_approval_status` only mirrors it so the UI can warn before submit.
"""
import re

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_first_day, getdate, now_datetime, nowdate

APPROVER_ROLES = ("Sales Manager", "Sales Master Manager", "System Manager")

# (source, target) -> ERPNext mapper. Nothing outside this map can be called.
NEXT_STEPS = {
	("Lead", "Opportunity"): "erpnext.crm.doctype.lead.lead.make_opportunity",
	("Lead", "Quotation"): "erpnext.crm.doctype.lead.lead.make_quotation",
	("Opportunity", "Quotation"): "erpnext.crm.doctype.opportunity.opportunity.make_quotation",
	("Quotation", "Sales Order"): "erpnext.selling.doctype.quotation.quotation.make_sales_order",
	("Sales Order", "Delivery Note"): "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
	("Sales Order", "Sales Invoice"): "erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice",
	("Delivery Note", "Sales Invoice"): "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice",
	# buy for the order straight away; Material Requests stay in desk (erp_overrides.stock_light)
	("Sales Order", "Purchase Order"): "erp_overrides.api.sales.make_purchase_order_from_sales_order",
	# goods or service delivered: the receipt half of the three-way match (erp_overrides.three_way)
	("Purchase Order", "Purchase Receipt"): "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
}

# Lead and Opportunity are not submittable; everything else must be submitted first.
SUBMITTABLE_SOURCES = ("Quotation", "Sales Order", "Delivery Note", "Purchase Order")

CHAIN_DOCTYPES = (
	"Lead", "Opportunity", "Quotation", "Sales Order", "Delivery Note", "Sales Invoice",
	"Purchase Order", "Purchase Receipt",
)
CHAIN_LIMIT = 60


@frappe.whitelist()
def make_next(source_doctype: str, source_name: str, target_doctype: str):
	"""Map `source` to an unsaved `target_doctype` doc, as desk's Create button would."""
	method = NEXT_STEPS.get((source_doctype, target_doctype))
	if not method:
		frappe.throw(_("Cannot create {0} from {1}").format(_(target_doctype), _(source_doctype)))

	source = frappe.get_doc(source_doctype, source_name)
	source.check_permission("read")

	if source_doctype in SUBMITTABLE_SOURCES and source.docstatus != 1:
		frappe.throw(
			_("{0} {1} is still a draft. Submit it first — drafts produce nothing downstream.").format(
				_(source_doctype), source_name
			),
			title=_("Submit First"),
		)

	if source_doctype == "Quotation" and source.valid_till and getdate(source.valid_till) < getdate(nowdate()):
		frappe.throw(
			_("Quotation {0} expired on {1}. Re-open it or raise a fresh quotation.").format(
				source_name, frappe.format(source.valid_till, "Date")
			),
			title=_("Quotation Expired"),
		)

	target = frappe.get_attr(method)(source_name)

	if not target.get("items") and source_doctype in SUBMITTABLE_SOURCES:
		covered = {"Delivery Note": _("delivered"), "Sales Invoice": _("billed"),
		           "Purchase Order": _("ordered from a supplier"), "Purchase Receipt": _("received")}.get(target_doctype, _("covered"))
		frappe.throw(
			_("Nothing left to carry across — every line on {0} is already {1}.").format(source_name, covered),
			title=_("Nothing to Create"),
		)

	return target.as_dict()


def make_purchase_order_from_sales_order(source_name, target_doc=None):
	"""A Purchase Order for what the order still needs (ERPNext's own Sales Order → Purchase
	Order mapping, linked back row by row so the order's ordered quantity updates). Unlike
	ERPNext's, the supplier is picked on the form rather than per item first; lines start at
	the last price paid."""
	from erpnext.accounts.party import CROSS_PARTY_FIELD_NO_MAP
	from erpnext.selling.doctype.sales_order.sales_order import is_product_bundle
	from frappe.model.mapper import get_mapped_doc

	today = getdate(nowdate())

	def update_item(source, target, source_parent):
		target.schedule_date = max(getdate(source.delivery_date or today), today)
		target.qty = flt(source.qty) - (flt(source.ordered_qty) / flt(source.conversion_factor or 1))
		target.stock_qty = flt(source.stock_qty) - flt(source.ordered_qty)
		target.project = source_parent.project
		target.rate = flt(frappe.db.get_value("Item", source.item_code, "last_purchase_rate"))

	def finish(source, target):
		# the customer's side stays behind, as in ERPNext's own mapper
		target.customer = target.customer_name = ""
		target.inter_company_order_reference = target.shipping_rule = target.tc_name = target.terms = ""
		target.apply_discount_on = ""
		target.additional_discount_percentage = target.discount_amount = 0
		target.payment_schedule = []
		target.schedule_date = min((r.schedule_date for r in target.items), default=today)
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	return get_mapped_doc("Sales Order", source_name, {
		"Sales Order": {"doctype": "Purchase Order", "field_no_map": [*CROSS_PARTY_FIELD_NO_MAP],
		                "validation": {"docstatus": ["=", 1]}},
		"Sales Order Item": {
			"doctype": "Purchase Order Item",
			"field_map": [["name", "sales_order_item"], ["parent", "sales_order"], ["stock_uom", "stock_uom"],
			              ["uom", "uom"], ["conversion_factor", "conversion_factor"]],
			# the selling side's prices stay behind: a line starts at what we last paid
			"field_no_map": ["rate", "price_list_rate", "base_rate", "base_price_list_rate", "net_rate", "base_net_rate",
			                 "amount", "base_amount", "net_amount", "base_net_amount", "item_tax_template",
			                 "discount_percentage", "discount_amount", "pricing_rules", "margin_type",
			                 "margin_rate_or_amount", "rate_with_margin", "base_rate_with_margin", "warehouse"],
			"postprocess": update_item,
			"condition": lambda d: flt(d.ordered_qty) < flt(d.stock_qty) and not is_product_bundle(d.item_code),
		},
	}, target_doc, finish)


@frappe.whitelist()
def get_item_details(doc: str | dict, item_code: str):
	"""Rate, UOM and description for a new line, priced from the parent's price list."""
	doc = frappe.parse_json(doc)
	from erpnext.stock.get_item_details import get_item_details as _get_item_details

	is_buying = doc.get("doctype") in ("Purchase Order", "Purchase Invoice")
	ctx = {
		"item_code": item_code,
		"doctype": doc.get("doctype"),
		"company": doc.get("company") or frappe.defaults.get_user_default("Company"),
		"currency": doc.get("currency"),
		"conversion_rate": doc.get("conversion_rate") or 1,
		"price_list": doc.get("buying_price_list" if is_buying else "selling_price_list"),
		"price_list_currency": doc.get("price_list_currency"),
		"plc_conversion_rate": doc.get("plc_conversion_rate") or 1,
		"transaction_date": doc.get("transaction_date") or doc.get("posting_date") or nowdate(),
		"customer": doc.get("customer") or (doc.get("party_name") if doc.get("quotation_to") == "Customer" else None),
		"supplier": doc.get("supplier"),
		"qty": 1,
		"ignore_pricing_rule": 0,
	}
	if is_buying:
		ctx["buying_price_list"] = ctx["price_list"]
	else:
		ctx["selling_price_list"] = ctx["price_list"]

	details = _get_item_details(ctx)
	keep = (
		"item_name", "description", "uom", "stock_uom", "conversion_factor", "price_list_rate",
		"rate", "discount_percentage", "item_group", "brand", "is_stock_item", "warehouse",
	)
	return {k: details.get(k) for k in keep if k in details}


# ── Approval ─────────────────────────────────────────────────────────────────


def get_limits():
	settings = "Custom Selling Settings"
	if not frappe.db.exists("DocType", settings):
		return frappe._dict(sales_order_limit=0, discount_limit=0)
	return frappe._dict(
		sales_order_limit=flt(frappe.db.get_single_value(settings, "sales_order_limit")),
		discount_limit=flt(frappe.db.get_single_value(settings, "discount_limit")),
	)


def is_approver(user=None):
	return bool(set(APPROVER_ROLES) & set(frappe.get_roles(user)))


def approval_status(doc, limits=None):
	"""Mirror of the "Credit and Discount Approval" server script. Exactly-at-limit passes."""
	limits = limits or get_limits()
	max_discount = max((flt(i.discount_percentage) for i in doc.get("items") or []), default=0)
	total = flt(doc.get("base_grand_total"))

	discount_breached = bool(limits.discount_limit and max_discount > limits.discount_limit)
	credit_breached = bool(limits.sales_order_limit and total > limits.sales_order_limit)
	discount_ok = not discount_breached or cint(doc.get("custom_discount_approved"))
	credit_ok = not credit_breached or cint(doc.get("custom_credit_approval"))

	return frappe._dict(
		limits=limits,
		total=total,
		max_discount=max_discount,
		discount_breached=discount_breached,
		credit_breached=credit_breached,
		discount_approved=cint(doc.get("custom_discount_approved")),
		credit_approved=cint(doc.get("custom_credit_approval")),
		needs_approval=not (discount_ok and credit_ok),
		can_approve=is_approver(),
	)


@frappe.whitelist()
def get_approval_status(sales_order: str):
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")
	return approval_status(doc)


@frappe.whitelist()
def get_approvals():
	"""Draft Sales Orders blocked by a limit and not yet approved."""
	limits = get_limits()
	drafts = frappe.get_list(
		"Sales Order",
		filters={"docstatus": 0},
		fields=["name"],
		order_by="modified desc",
		limit_page_length=200,
	)
	out = []
	for row in drafts:
		doc = frappe.get_doc("Sales Order", row.name)
		status = approval_status(doc, limits)
		if status.needs_approval:
			out.append(
				dict(
					name=doc.name,
					customer=doc.customer,
					customer_name=doc.customer_name,
					grand_total=doc.grand_total,
					currency=doc.currency,
					owner=doc.owner,
					modified=doc.modified,
					**{k: status[k] for k in ("max_discount", "discount_breached", "credit_breached",
					                          "discount_approved", "credit_approved")},
				)
			)
	return out


@frappe.whitelist()
def get_approvers():
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", APPROVER_ROLES[:2]], "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	return frappe.get_all(
		"User",
		filters={"name": ["in", users or [""]], "enabled": 1, "user_type": "System User"},
		fields=["name", "full_name"],
		order_by="full_name asc",
	)


@frappe.whitelist()
def request_approval(sales_order: str, approver: str, note: str | None = None):
	"""The manual's step 2: assign the blocked order to a manager."""
	from frappe.desk.form.assign_to import add

	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("write")
	if approver not in [u.name for u in get_approvers()]:
		frappe.throw(_("{0} cannot approve Sales Orders").format(approver))

	add(
		{
			"doctype": "Sales Order",
			"name": sales_order,
			"assign_to": [approver],
			"description": note or _("Please approve credit/discount on {0}").format(sales_order),
		}
	)
	return True


# ── Chain ────────────────────────────────────────────────────────────────────


def _parents_of(child_doctype, parent_doctype, fieldname, value):
	return frappe.get_list(
		parent_doctype,
		filters=[[child_doctype, fieldname, "=", value], [parent_doctype, "docstatus", "<", 2]],
		pluck="name",
		distinct=True,
	)


def _child_values(child_doctype, parent, fieldname):
	return [
		v
		for v in frappe.get_all(child_doctype, filters={"parent": parent}, pluck=fieldname, distinct=True)
		if v
	]


def _neighbours(doctype, name):
	"""Linked documents one hop up and down the chain."""
	out = []
	if doctype == "Lead":
		out += [("Opportunity", n) for n in frappe.get_list(
			"Opportunity", filters={"opportunity_from": "Lead", "party_name": name}, pluck="name")]
		out += [("Quotation", n) for n in frappe.get_list(
			"Quotation", filters={"quotation_to": "Lead", "party_name": name, "docstatus": ["<", 2]}, pluck="name")]
	elif doctype == "Opportunity":
		opp = frappe.db.get_value("Opportunity", name, ["opportunity_from", "party_name"], as_dict=True)
		if opp and opp.opportunity_from == "Lead":
			out.append(("Lead", opp.party_name))
		out += [("Quotation", n) for n in frappe.get_list(
			"Quotation", filters={"opportunity": name, "docstatus": ["<", 2]}, pluck="name")]
	elif doctype == "Quotation":
		q = frappe.db.get_value("Quotation", name, ["opportunity", "quotation_to", "party_name"], as_dict=True)
		if q and q.opportunity:
			out.append(("Opportunity", q.opportunity))
		if q and q.quotation_to == "Lead":
			out.append(("Lead", q.party_name))
		out += [("Sales Order", n) for n in _parents_of("Sales Order Item", "Sales Order", "prevdoc_docname", name)]
	elif doctype == "Sales Order":
		out += [("Quotation", n) for n in _child_values("Sales Order Item", name, "prevdoc_docname")]
		out += [("Delivery Note", n) for n in _parents_of("Delivery Note Item", "Delivery Note", "against_sales_order", name)]
		out += [("Sales Invoice", n) for n in _parents_of("Sales Invoice Item", "Sales Invoice", "sales_order", name)]
		out += [("Purchase Order", n) for n in _parents_of("Purchase Order Item", "Purchase Order", "sales_order", name)]
	elif doctype == "Delivery Note":
		out += [("Sales Order", n) for n in _child_values("Delivery Note Item", name, "against_sales_order")]
		out += [("Sales Invoice", n) for n in _parents_of("Sales Invoice Item", "Sales Invoice", "delivery_note", name)]
	elif doctype == "Sales Invoice":
		out += [("Sales Order", n) for n in _child_values("Sales Invoice Item", name, "sales_order")]
		out += [("Delivery Note", n) for n in _child_values("Sales Invoice Item", name, "delivery_note")]
	elif doctype == "Purchase Order":
		out += [("Sales Order", n) for n in _child_values("Purchase Order Item", name, "sales_order")]
		out += [("Purchase Receipt", n) for n in _parents_of("Purchase Receipt Item", "Purchase Receipt", "purchase_order", name)]
	elif doctype == "Purchase Receipt":
		out += [("Purchase Order", n) for n in _child_values("Purchase Receipt Item", name, "purchase_order")]
	return out


def _summary(doctype, name):
	fields = ["name", "docstatus", "modified"]
	meta = frappe.get_meta(doctype)
	for f in ("status", "grand_total", "outstanding_amount", "currency", "title", "lead_name", "company_name",
	          "customer_name", "supplier_name", "party_name"):
		if meta.has_field(f):
			fields.append(f)
	row = frappe.db.get_value(doctype, name, fields, as_dict=True)
	if row:
		row.doctype = doctype
		row.label = (row.get("customer_name") or row.get("supplier_name") or row.get("title")
		             or row.get("lead_name") or row.get("company_name") or row.get("party_name") or name)
	return row


@frappe.whitelist()
def get_chain(doctype: str, name: str):
	"""Every document in this deal, grouped by chain stage."""
	if doctype not in CHAIN_DOCTYPES:
		frappe.throw(_("{0} is not part of the sales chain").format(doctype))
	frappe.get_doc(doctype, name).check_permission("read")

	seen = {(doctype, name)}
	queue = [(doctype, name)]
	while queue and len(seen) < CHAIN_LIMIT:
		node = queue.pop(0)
		for nxt in _neighbours(*node):
			if nxt not in seen and frappe.has_permission(nxt[0], "read", nxt[1]):
				seen.add(nxt)
				queue.append(nxt)

	chain = {dt: [] for dt in CHAIN_DOCTYPES}
	for dt, dn in seen:
		row = _summary(dt, dn)
		if row:
			row.current = dt == doctype and dn == name
			chain[dt].append(row)
	for rows in chain.values():
		rows.sort(key=lambda r: r.name)
	return chain


@frappe.whitelist()
def get_margin(doctype: str, name: str):
	"""Sell (Sales Orders) vs cost (Purchase Orders) for the deal this doc belongs to."""
	chain = get_chain(doctype, name)
	sell = sum(flt(r.grand_total) for r in chain["Sales Order"] if r.docstatus == 1)
	cost = sum(flt(r.grand_total) for r in chain["Purchase Order"] if r.docstatus < 2)
	currency = next((r.currency for r in chain["Sales Order"] + chain["Purchase Order"] if r.get("currency")), None)
	return dict(
		sell=sell,
		cost=cost,
		margin=sell - cost,
		margin_pct=round((sell - cost) / sell * 100, 1) if sell else None,
		currency=currency,
		sales_orders=[r.name for r in chain["Sales Order"]],
		purchase_orders=[r.name for r in chain["Purchase Order"]],
	)


# ── Home ─────────────────────────────────────────────────────────────────────


def _stage(key, label, doctype, filters, total_field="base_grand_total", hint=None):
	fields = [{"COUNT": "*", "as": "count"}]
	if total_field:
		fields.append({"SUM": total_field, "as": "total"})
	if not frappe.has_permission(doctype, "read"):
		return None
	row = (frappe.get_list(doctype, filters=filters, fields=fields) or [{}])[0]
	return dict(
		key=key,
		label=label,
		doctype=doctype,
		filters=filters,
		count=cint(row.get("count")),
		total=flt(row.get("total")) if total_field else None,
		hint=hint,
	)


@frappe.whitelist()
def get_pipeline():
	today = nowdate()
	in_week = add_days(today, 7)
	stages = [
		_stage("leads", _("Open leads"), "Lead",
		       {"status": ["in", ["Lead", "Open", "Replied", "Interested"]]}, None),
		_stage("opportunities", _("Open opportunities"), "Opportunity",
		       {"status": ["in", ["Open", "Replied"]]}, "opportunity_amount"),
		_stage("quotations", _("Open quotations"), "Quotation",
		       {"docstatus": 1, "status": ["in", ["Open", "Replied", "Partially Ordered"]]},
		       hint=_("Anything the customer said yes to should become a Sales Order")),
		_stage("expiring", _("Quotes expiring this week"), "Quotation",
		       {"docstatus": 1, "status": ["in", ["Open", "Replied"]], "valid_till": ["between", [today, in_week]]}),
		_stage("draft_quotes", _("Draft quotations"), "Quotation", {"docstatus": 0}),
		_stage("draft_orders", _("Draft sales orders"), "Sales Order", {"docstatus": 0},
		       hint=_("Need approval or a submit")),
		_stage("to_deliver", _("Orders to deliver"), "Sales Order",
		       {"docstatus": 1, "status": ["in", ["To Deliver and Bill", "To Deliver"]]}),
		_stage("to_bill", _("Orders to bill"), "Sales Order",
		       {"docstatus": 1, "status": ["in", ["To Deliver and Bill", "To Bill"]]},
		       hint=_("Service orders can be invoiced straight from the order")),
		_stage("dn_to_bill", _("Deliveries to bill"), "Delivery Note",
		       {"docstatus": 1, "status": ["in", ["To Bill", "Partially Billed"]]}),
		_stage("unpaid", _("Unpaid invoices"), "Sales Invoice",
		       {"docstatus": 1, "outstanding_amount": [">", 0]}, "outstanding_amount"),
		_stage("overdue", _("Overdue invoices"), "Sales Invoice",
		       {"docstatus": 1, "status": ["like", "Overdue%"]}, "outstanding_amount"),
		_stage("purchase_orders", _("Purchase orders to receive"), "Purchase Order",
		       {"docstatus": 1, "status": ["in", ["To Receive and Bill", "To Receive", "To Bill"]]}),
	]
	return dict(stages=[s for s in stages if s], approvals=len(get_approvals()) if is_approver() else 0)


# ── My sales (reporting on Home) ─────────────────────────────────────────────
# Nobody here is set up as a Sales Person, so a seller's figures are the documents they created.

TEAM_ROLES = ("Sales Manager", "System Manager")
WON = ("Ordered", "Partially Ordered")
OPEN_QUOTE = ("Open", "Replied")

# The curated sales reports, in the order a seller looks for them; every other Selling and CRM
# report follows under "Other sales reports" (see api/reports.py)
SALES_REPORTS = {
	"Pipeline": [
		("Lead Details", "Every lead with source, status and owner"),
		("Sales Pipeline Analytics", "Open opportunities by stage, owner or month"),
		("Opportunity Summary by Sales Stage", "How much is sitting at each stage"),
		("Lost Opportunity", "Opportunities lost, with reasons and competitors"),
		("Prospects Engaged But Not Converted", "Leads talked to but never quoted"),
		("Lead Conversion Time", "Days from lead to first order"),
		("Lead Owner Efficiency", "Leads, opportunities and quotes per owner"),
		("Campaign Efficiency", "Leads, quotes and orders per campaign"),
	],
	"Quotes and orders": [
		("Quotation Trends", "Quotations by month, item or customer"),
		("Lost Quotations", "Quotations lost, with reasons"),
		("Sales Order Analysis", "Each order: delivered, billed and still to come"),
		("Sales Order Trends", "Orders by month, item or customer"),
		("Pending SO Items For Purchase Request", "Order lines nobody has asked to buy yet"),
		("Payment Terms Status for Sales Order", "What each order's payment terms say is due and paid"),
	],
	"Sales": [
		("Sales Analytics", "Sales by customer, item or territory, per period"),
		("Territory-wise Sales", "Opportunities, quotes, orders and invoices per territory"),
		("Sales Person-wise Transaction Summary", "What each sales person sold"),
		("Item-wise Sales History", "Every item sold, to whom and at what price"),
		("Customer-wise Item Price", "The price each customer pays for an item"),
		("Customer Acquisition and Loyalty", "New against repeat customers, per month"),
		("Inactive Customers", "Customers who haven't bought for a while"),
		("Customers Without Any Sales Transactions", "Customers set up but never sold to"),
	],
	"Billing and money": [
		("Sales Invoice Trends", "Invoices by month, item or customer"),
		("Sales Register", "Every sales invoice, with tax and totals"),
		("Item-wise Sales Register", "Every invoice line, with tax"),
		("Delivered Items To Be Billed", "Delivered and not yet invoiced"),
		("Gross Profit", "Margin per invoice, item or customer"),
		("Accounts Receivable", "Every open customer invoice, aged"),
		("Accounts Receivable Summary", "What each customer owes, aged"),
		("Customer Credit Balance", "Each customer's credit limit and what's used"),
		("Sales Payment Summary", "Payments received per day and mode"),
	],
	"Delivery": [
		("Delivery Note Trends", "Deliveries by month, item or customer"),
	],
	"Buying for orders": [
		("Purchase Order Analysis", "Each purchase order: received, billed and still to come"),
		("Purchase Order Trends", "Purchase orders by month, item or supplier"),
		("Procurement Tracker", "Material request to purchase order to receipt, line by line"),
	],
}
SALES_REPORT_MODULES = ("Selling", "CRM")
# the few My sales on Home links to
MY_SALES_REPORTS = ("Sales Analytics", "Quotation Trends", "Sales Order Analysis", "Sales Register", "Gross Profit")


def is_sales_manager(user=None):
	return bool(set(TEAM_ROLES) & set(frappe.get_roles(user)))


def _sales_report_groups():
	from erp_overrides.api.reports import report_groups

	return report_groups(SALES_REPORTS, SALES_REPORT_MODULES, _("Other sales reports"))


@frappe.whitelist()
def get_reports():
	"""Every sales report the user may open, grouped (the Reports page)."""
	return _sales_report_groups()


def _sales_reports():
	return [r for g in _sales_report_groups() for r in g["reports"] if r["name"] in MY_SALES_REPORTS]


@frappe.whitelist()
def get_my_report(scope: str = "me", months: int = 12):
	"""Quoted, won and invoiced per month, quote outcomes, biggest customers and most-quoted items,
	for the user's own documents ("me") or, for a sales manager, everyone's ("team").
	Amounts are net of tax in the company currency."""
	from erpnext.accounts.utils import get_fiscal_year

	user = frappe.session.user
	team = scope == "team" and is_sales_manager(user)
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	today = getdate()
	months = min(cint(months) or 12, 24)
	start = get_first_day(add_months(today, -(months - 1)))
	month_start = get_first_day(today)
	fy_start = get_fiscal_year(today, company=company)[1]
	can = {dt: frappe.has_permission(dt, "read") for dt in ("Quotation", "Sales Order", "Sales Invoice")}

	who = "" if team else "and d.owner = %(user)s"
	args = dict(company=company, user=user, start=start, month_start=month_start, fy_start=fy_start, today=today,
	            won=WON, open=OPEN_QUOTE)

	def sql(query, **extra):
		return frappe.db.sql(query.replace("{who}", who), {**args, **extra}, as_dict=True)

	def per_month(doctype, date_field):
		return {r.month: flt(r.total) for r in sql(
			f"""select date_format(d.{date_field}, '%%Y-%%m') month, sum(d.base_net_total) total from `tab{doctype}` d
			    where d.docstatus=1 and d.company=%(company)s and d.{date_field} >= %(start)s {{who}} group by month""")}

	def totals(doctype, date_field, a):
		r = sql(f"""select sum(d.base_net_total) total, count(*) n from `tab{doctype}` d
		            where d.docstatus=1 and d.company=%(company)s and d.{date_field} between %(a)s and %(today)s {{who}}""", a=a)[0]
		return dict(total=flt(r.total), count=cint(r.n))

	SOURCES = (("quoted", "Quotation", "transaction_date"), ("ordered", "Sales Order", "transaction_date"),
	           ("invoiced", "Sales Invoice", "posting_date"))
	by_month = {key: per_month(dt, f) if can[dt] else {} for key, dt, f in SOURCES}
	series = []
	for i in range(months):
		m = add_months(start, i).strftime("%Y-%m")
		series.append(dict(month=m, **{key: by_month[key].get(m, 0) for key, _dt, _f in SOURCES}))

	out = dict(
		scope="team" if team else "me",
		can_team=is_sales_manager(user),
		currency=frappe.get_cached_value("Company", company, "default_currency"),
		can=can,
		months=series,
		this_month={key: totals(dt, f, month_start) for key, dt, f in SOURCES if can[dt]},
		year_to_date={key: totals(dt, f, fy_start) for key, dt, f in SOURCES if can[dt]},
		reports=_sales_reports(),
	)

	if can["Quotation"]:
		rows = sql("""select d.status, count(*) n, sum(d.base_net_total) total from `tabQuotation` d
		              where d.docstatus=1 and d.company=%(company)s and d.transaction_date >= %(start)s {who}
		              group by d.status""")
		by = {r.status: r for r in rows}
		pick = lambda *st: dict(count=sum(cint(by[s].n) for s in st if s in by),  # noqa: E731
		                        total=sum(flt(by[s].total) for s in st if s in by))
		won, lost, expired = pick(*WON), pick("Lost"), pick("Expired")
		decided = won["count"] + lost["count"] + expired["count"]
		decided_value = won["total"] + lost["total"] + expired["total"]
		submitted = pick(*OPEN_QUOTE, *WON, "Lost", "Expired")
		out["quotes"] = dict(
			open=pick(*OPEN_QUOTE), won=won, lost=lost, expired=expired, decided=decided,
			win_rate=round(won["count"] / decided * 100, 1) if decided else None,
			win_rate_value=round(won["total"] / decided_value * 100, 1) if decided_value else None,
			average=submitted["total"] / submitted["count"] if submitted["count"] else 0,
		)
		out["top_customers"] = sql(
			"""select d.party_name party, max(d.customer_name) name, d.quotation_to, count(*) quotes,
			          sum(d.base_net_total) quoted, sum(if(d.status in %(won)s, d.base_net_total, 0)) won
			   from `tabQuotation` d where d.docstatus=1 and d.company=%(company)s
			   and d.transaction_date between %(fy_start)s and %(today)s {who}
			   group by d.quotation_to, d.party_name order by quoted desc limit 8""")
		out["top_items"] = sql(
			"""select i.item_code, max(i.item_name) item_name, sum(i.stock_qty) qty, max(i.stock_uom) uom,
			          sum(i.base_net_amount) amount, count(distinct d.name) quotes
			   from `tabQuotation Item` i join `tabQuotation` d on d.name = i.parent
			   where d.docstatus=1 and d.company=%(company)s and d.transaction_date between %(fy_start)s and %(today)s {who}
			   group by i.item_code order by amount desc limit 8""")
		out["lost_reasons"] = sql(
			"""select r.lost_reason reason, count(distinct d.name) n from `tabQuotation Lost Reason Detail` r
			   join `tabQuotation` d on d.name = r.parent
			   where d.status='Lost' and d.company=%(company)s and d.transaction_date between %(fy_start)s and %(today)s {who}
			   group by r.lost_reason order by n desc limit 6""")

	if team:
		sellers = {}

		def add(doctype, date_field, fields):
			if not can[doctype]:
				return
			for r in sql(f"""select d.owner, {fields} from `tab{doctype}` d where d.docstatus=1 and d.company=%(company)s
			                 and d.{date_field} >= %(start)s group by d.owner"""):
				sellers.setdefault(r.pop("owner"), {}).update(r)

		add("Quotation", "transaction_date",
		    """count(*) quotes, sum(d.base_net_total) quoted, sum(if(d.status in %(won)s, 1, 0)) won_n,
		       sum(if(d.status in %(won)s, d.base_net_total, 0)) won,
		       sum(if(d.status in %(won)s or d.status in ('Lost', 'Expired'), 1, 0)) decided""")
		add("Sales Order", "transaction_date", "sum(d.base_net_total) ordered")
		add("Sales Invoice", "posting_date", "sum(d.base_net_total) invoiced")
		out["by_seller"] = sorted(
			(dict(user=u, name=frappe.utils.get_fullname(u), quotes=cint(r.get("quotes")), quoted=flt(r.get("quoted")),
			      won=flt(r.get("won")), ordered=flt(r.get("ordered")), invoiced=flt(r.get("invoiced")),
			      win_rate=round(cint(r.get("won_n")) / cint(r.get("decided")) * 100, 1) if cint(r.get("decided")) else None)
			 for u, r in sellers.items()),
			key=lambda r: -r["quoted"])
	return out


# ── Tenders ──────────────────────────────────────────────────────────────────
# Filled by the feeds in erp_overrides.scrapers: Zimbabwe e-GP → Egp Tender, Zambia ZPPA → Eprocure Tender.
# Both are System-Manager-only on desk, so the board reads them here for anyone who sells.

TENDER_CLOSED_DAYS = 30
TENDER_LIMIT = 2000


def can_view_tenders(user=None):
	return any(frappe.has_permission(dt, "read", user=user) for dt in ("Lead", "Opportunity"))


def _split_categories(value):
	# e-GP joins categories with a bare comma; commas inside a category name are followed by a space
	return [c.strip() for c in re.split(r",(?=\S)", value or "") if c.strip()]


@frappe.whitelist()
def get_tenders(closed: int = 0):
	"""Open tenders from both countries, or those that closed in the last TENDER_CLOSED_DAYS."""
	if not can_view_tenders():
		frappe.throw(_("Not permitted to view tenders"), frappe.PermissionError)

	now = now_datetime()
	if cint(closed):
		window = lambda f: {f: ["between", [add_days(now, -TENDER_CLOSED_DAYS), now]]}  # noqa: E731
		order = "desc"
	else:
		window = lambda f: {f: [">", now]}  # noqa: E731
		order = "asc"

	zw = frappe.get_all(
		"Egp Tender",
		filters=window("closing_date"),
		fields=["name", "id", "title", "entity", "link", "method", "categories", "publish_date",
		        "closing_date", "status", "is_limited", "creation"],
		order_by=f"closing_date {order}",
		limit=TENDER_LIMIT,
	)
	zm = frappe.get_all(
		"Eprocure Tender",
		filters=window("submission_deadline"),
		fields=["name", "reference_id", "title", "procuring_entity", "tender_link", "notice_pdf",
		        "procedure", "category", "status", "value_amount", "currency", "submission_deadline",
		        "creation"],
		order_by=f"submission_deadline {order}",
		limit=TENDER_LIMIT,
	)

	tenders = [
		dict(country="Zimbabwe", key=f"zw:{t.name}", ref=t.id, title=t.title, entity=t.entity,
		     method=t.method, categories=_split_categories(t.categories), published=t.publish_date,
		     closing=t.closing_date, status=t.status, limited=cint(t.is_limited), link=t.link,
		     created=t.creation)
		for t in zw
	] + [
		dict(country="Zambia", key=f"zm:{t.name}", ref=t.reference_id, title=t.title,
		     entity=t.procuring_entity, method=t.procedure,
		     categories=[t.category.strip()] if (t.category or "").strip() else [],
		     closing=t.submission_deadline, status=t.status, link=t.tender_link, pdf=t.notice_pdf,
		     value=flt(t.value_amount) or None, currency=t.currency, created=t.creation)
		for t in zm
	]
	tenders.sort(key=lambda t: t["closing"], reverse=bool(cint(closed)))

	return dict(
		tenders=tenders,
		now=now,
		closed_days=TENDER_CLOSED_DAYS,
		last_scraped={
			"Zimbabwe": frappe.db.sql("select max(creation) from `tabEgp Tender`")[0][0],
			"Zambia": frappe.db.sql("select max(creation) from `tabEprocure Tender`")[0][0],
		},
	)


# ── Print ────────────────────────────────────────────────────────────────────

PROFORMA = "Proforma Invoice"

PRINTABLE = ("Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "Purchase Order", "Salary Slip",
             "Payment Entry", "Journal Entry", "Purchase Invoice", "Dunning")


def proforma_formats():
	"""{doctype: print format} for the proforma invoices this site has ("Proforma Invoice" on Sales
	Order, "Proforma Invoice (Quotation)" on Quotation), so the app only offers the Proforma invoice
	button where the format exists and is enabled."""
	wanted = {"Sales Order": PROFORMA, "Quotation": f"{PROFORMA} (Quotation)"}
	found = {pf.name: pf.doc_type for pf in frappe.get_all(
		"Print Format", filters={"name": ["in", list(wanted.values())], "disabled": 0}, fields=["name", "doc_type"])}
	return {dt: name for dt, name in wanted.items() if found.get(name) == dt}


def _print_format(doctype, print_format=None):
	print_format = print_format or frappe.get_meta(doctype).default_print_format or "Standard"
	if print_format != "Standard":
		pf = frappe.db.get_value("Print Format", print_format, ["doc_type", "disabled"], as_dict=True)
		if not pf or pf.doc_type != doctype or pf.disabled:
			frappe.throw(_("Print Format {0} is not available for {1}").format(print_format, doctype))
	return print_format


def _check_printable(doctype):
	if doctype not in PRINTABLE:
		frappe.throw(_("{0} cannot be printed from this app").format(doctype))


@frappe.whitelist()
def get_print_options(doctype: str):
	"""Print formats and letter heads to offer in the preview, with desk's defaults."""
	_check_printable(doctype)
	formats = frappe.get_all(
		"Print Format",
		filters={"doc_type": doctype, "disabled": 0},
		fields=["name", "print_designer", "pdf_generator"],
		order_by="name asc",
	)
	formats.insert(0, frappe._dict(name="Standard", print_designer=0, pdf_generator=None))
	letter_heads = frappe.get_all("Letter Head", filters={"disabled": 0}, fields=["name", "is_default"], order_by="name asc")
	return dict(
		formats=formats,
		default_format=_print_format(doctype),
		letter_heads=letter_heads,
		default_letter_head=next((lh.name for lh in letter_heads if lh.is_default), None),
	)


@frappe.whitelist()
def get_print_preview(doctype: str, name: str, print_format: str | None = None,
                      letterhead: str | None = None, no_letterhead: int = 0):
	"""HTML preview exactly as desk's print view renders it."""
	from frappe.utils.jinja_globals import bundled_asset
	from frappe.www.printview import get_html_and_style

	_check_printable(doctype)
	print_format = _print_format(doctype, print_format)
	out = get_html_and_style(doctype, name, print_format=print_format,
	                         no_letterhead=cint(no_letterhead), letterhead=letterhead or None)
	out["css"] = [bundled_asset("print.bundle.css")]
	return out


@frappe.whitelist()
def download_pdf(doctype: str, name: str, print_format: str | None = None,
                 letterhead: str | None = None, no_letterhead: int = 0):
	"""PDF with the same generator desk would use for the chosen print format.

	frappe's `download_pdf` falls back to wkhtmltopdf when no generator is passed,
	whereas desk takes it from the print format, then Print Settings.
	"""
	from frappe.utils.print_format import download_pdf as _download_pdf

	_check_printable(doctype)
	print_format = _print_format(doctype, print_format)
	generator = None
	if print_format != "Standard":
		generator = frappe.db.get_value("Print Format", print_format, "pdf_generator")
	generator = generator or frappe.db.get_single_value("Print Settings", "pdf_generator") or "wkhtmltopdf"

	return _download_pdf(doctype, name, format=print_format, letterhead=letterhead or None,
	                     no_letterhead=cint(no_letterhead), pdf_generator=generator)
