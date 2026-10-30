# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Stock that looks after itself, for a business that mostly sells services and buys hardware only for an order:
- only items in the **Hardware** item group tree keep stock, each allowed to go
  negative (sold before it has been received); everything else is non-stock;
- a Purchase Receipt from the order brings hardware in (and, for services, records that
  the work was delivered): the receipt half of the three-way match (erp_overrides.three_way).
  The supplier's invoice then moves no stock;
- the customer's invoice takes hardware out (`update_stock`) of one default warehouse;
  a Delivery Note is optional proof of hand-over (an invoice made from one leaves the
  stock to it);
- a submitted Purchase Order sets the item's valuation rate, which ERPNext uses when
  hardware is invoiced before it has been received.
"""
import frappe
from frappe.utils import cint, flt

HARDWARE = "Hardware"
WAREHOUSE = "Stores"


def is_hardware_group(group):
	if not group or not frappe.db.exists("Item Group", HARDWARE):
		return False
	lft, rgt = frappe.get_cached_value("Item Group", HARDWARE, ["lft", "rgt"])
	g = frappe.get_cached_value("Item Group", group, ["lft", "rgt"])
	return bool(g) and lft <= g[0] and g[1] <= rgt


def default_warehouse(company):
	# newer ERPNext releases dropped Stock Settings → Default Warehouse (the test site's has none)
	wh = frappe.get_meta("Stock Settings").has_field("default_warehouse") and \
		frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if wh and frappe.db.get_value("Warehouse", wh, "company") == company:
		return wh
	abbr = frappe.get_cached_value("Company", company, "abbr")
	return frappe.db.exists("Warehouse", f"{WAREHOUSE} - {abbr}") and f"{WAREHOUSE} - {abbr}"


def item_before_validate(doc, method=None):
	"""Hardware keeps stock (and may go negative); nothing else does. Runs before ERPNext's
	own checks, and leaves alone an item ERPNext won't let change (on submitted documents)."""
	if cint(doc.is_fixed_asset) or not frappe.db.exists("Item Group", HARDWARE):
		return
	want = 1 if is_hardware_group(doc.item_group) else 0
	if cint(doc.is_stock_item) != want and not doc.is_new():
		before = cint(frappe.db.get_value("Item", doc.name, "is_stock_item"))
		if before != want and doc._get_linked_submitted_documents(["is_stock_item"]):
			return
	doc.is_stock_item = want
	if want:
		doc.allow_negative_stock = 1


def _is_stock(item_code):
	return item_code and cint(frappe.get_cached_value("Item", item_code, "is_stock_item"))


def invoice_before_validate(doc, method=None):
	"""A draft Sales Invoice with hardware takes it out of stock itself, unless a row comes
	from a Delivery Note (which already did). Supplier invoices don't: the receipt did."""
	if doc.docstatus != 0:
		return
	stock_rows = [r for r in doc.items if _is_stock(r.item_code)]
	if not stock_rows or any(r.get("dn_detail") or r.get("delivery_note") for r in doc.items):
		return
	doc.update_stock = 1
	wh = default_warehouse(doc.company)
	catch_all = frappe.get_cached_value("Company", doc.company, "default_expense_account")
	for r in stock_rows:
		r.warehouse = r.warehouse or wh
		if not r.expense_account or r.expense_account == catch_all:
			# an invoice mapped from an order arrives without one, and ERPNext then takes the
			# company's catch-all: cost of sales belongs on the item group's account (5110…)
			r.expense_account = _cost_of_sales_account(r.item_code, doc.company) or r.expense_account


def fill_warehouses(doc, method=None):
	"""Sales Orders, Delivery Notes, Purchase Orders and Purchase Receipts: ERPNext wants a warehouse on every
	stock row, and the forms no longer ask for one."""
	if doc.docstatus != 0:
		return
	rows = [r for r in doc.items if not r.get("warehouse") and _is_stock(r.item_code)]
	wh = rows and default_warehouse(doc.company)
	for r in rows:
		r.warehouse = wh


def receipt_before_validate(doc, method=None):
	"""Purchase Receipts: warehouses as above, and the received quantity follows the accepted
	one (the forms change only the quantity; ERPNext wants received = accepted + rejected)."""
	if doc.docstatus != 0:
		return
	fill_warehouses(doc)
	for r in doc.items:
		r.received_qty = flt(r.qty) + flt(r.rejected_qty)


def _cost_of_sales_account(item_code, company):
	from erpnext.setup.doctype.brand.brand import get_brand_defaults
	from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
	from erpnext.stock.doctype.item.item import get_item_defaults

	for defaults in (get_item_defaults(item_code, company), get_item_group_defaults(item_code, company),
	                 get_brand_defaults(item_code, company)):
		if defaults and defaults.get("expense_account"):
			return defaults["expense_account"]


def purchase_order_on_submit(doc, method=None):
	"""The latest price paid becomes the hardware's valuation rate: ERPNext's fallback when
	it's invoiced to the customer before it has been received."""
	for r in doc.items:
		if _is_stock(r.item_code) and flt(r.base_rate) > 0:
			frappe.db.set_value("Item", r.item_code, "valuation_rate", flt(r.base_rate) / flt(r.conversion_factor or 1),
			                    update_modified=False)
