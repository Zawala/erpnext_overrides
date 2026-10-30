# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Three-way match before a supplier is paid (patch three_way_2026_10).

A supplier's bill line that comes from a Purchase Order must agree with what was
received against that order line (Purchase Receipt), and with the order's price:
- billed quantity, this bill plus earlier ones, no more than received;
- rate no higher than the order's, plus Accounts Settings → Over Billing Allowance.

Bills with no order lines (power, phone, rent) are "no PO" and pay as before. A payment
to a supplier that settles a bill that isn't matched is refused on submit, unless an
Accounts Manager ticks "Approved unmatched payment" on it (permission level 1); that
override is noted on the payment.
"""
import frappe
from frappe import _
from frappe.utils import flt

LABELS = {
	"matched": _("Matched"),
	"not_received": _("Not received"),
	"qty_over": _("Over-billed"),
	"rate_diff": _("Price differs"),
	"no_po": _("No PO"),
}
OK = ("matched", "no_po")
# worst first: the bill shows the worst of its lines
ORDER = ("not_received", "qty_over", "rate_diff", "matched")
OVERRIDE_FIELD = "custom_approved_unmatched"


def match_status(invoice):
	"""{status, label, message, lines} for a Purchase Invoice (a doc or its name)."""
	doc = frappe.get_doc("Purchase Invoice", invoice) if isinstance(invoice, str) else invoice
	if doc.get("is_return"):
		return _result("no_po", [])
	per_line = {}
	for r in doc.items:
		if r.get("po_detail"):
			line = per_line.setdefault(r.po_detail, dict(item_code=r.item_code, purchase_order=r.purchase_order,
			                                             qty=0.0, rate=0.0))
			line["qty"] += flt(r.stock_qty) or flt(r.qty) * flt(r.conversion_factor or 1)
			line["rate"] = max(line["rate"], flt(r.rate) / flt(r.conversion_factor or 1))
	if not per_line:
		return _result("no_po", [])

	allowance = flt(frappe.db.get_single_value("Accounts Settings", "over_billing_allowance"))
	lines = []
	for po_detail, line in per_line.items():
		po = frappe.db.get_value("Purchase Order Item", po_detail,
		                         ["received_qty", "conversion_factor", "rate", "uom", "stock_uom"], as_dict=True)
		if not po:
			continue
		factor = flt(po.conversion_factor or 1)
		received = flt(po.received_qty) * factor
		before = flt(frappe.db.sql(
			"""select sum(stock_qty) from `tabPurchase Invoice Item`
			   where po_detail = %s and docstatus = 1 and parent != %s""", (po_detail, doc.name or ""))[0][0])
		billed = before + line["qty"]
		ordered_rate = flt(po.rate) / factor
		if received <= 0:
			status = "not_received"
		elif billed > received + 1e-6:
			status = "qty_over"
		elif line["rate"] > ordered_rate * (1 + allowance / 100) + 0.005:
			status = "rate_diff"
		else:
			status = "matched"
		lines.append(dict(line, po_detail=po_detail, status=status, received=received, billed=billed,
		                  ordered_rate=ordered_rate, uom=po.stock_uom))
	if not lines:
		return _result("no_po", [])
	return _result(min((l["status"] for l in lines), key=ORDER.index), lines)


def _result(status, lines):
	return dict(status=status, label=LABELS[status], message=_message(status, lines), lines=lines)


def _message(status, lines):
	bad = [l for l in lines if l["status"] == status]
	if status == "no_po":
		return _("Not from a purchase order")
	if status == "matched":
		return _("Billed, received and ordered agree")
	l = bad[0]
	if status == "not_received":
		return _("{0}: nothing received yet on {1}").format(l["item_code"], l["purchase_order"])
	if status == "qty_over":
		return _("{0}: {1} billed, {2} received on {3}").format(
			l["item_code"], _num(l["billed"]), _num(l["received"]), l["purchase_order"])
	return _("{0}: billed at {1}, ordered at {2} on {3}").format(
		l["item_code"], _num(l["rate"]), _num(l["ordered_rate"]), l["purchase_order"])


def _num(v):
	return f"{flt(v, 2):g}"


def statuses(names):
	"""{invoice name: match_status} for several bills (the Accounts app's lists)."""
	return {n: match_status(n) for n in dict.fromkeys(names) if n}


def payment_before_submit(doc, method=None):
	"""A payment to a supplier may only settle matched bills (or bills with no PO)."""
	if doc.payment_type != "Pay" or doc.party_type != "Supplier":
		return
	bills = [r.reference_name for r in doc.references
	         if r.reference_doctype == "Purchase Invoice" and flt(r.allocated_amount) > 0]
	unmatched = [(n, s) for n, s in statuses(bills).items() if s["status"] not in OK]
	if not unmatched:
		return
	listed = "<br>".join(f"{n}: {s['label']} — {s['message']}" for n, s in unmatched)
	if doc.get(OVERRIDE_FIELD):
		doc.add_comment("Comment", _("Paid unmatched bills, approved by {0}:<br>{1}").format(
			frappe.utils.get_fullname(frappe.session.user), listed))
		return
	frappe.throw(
		_("These bills aren't matched to what was ordered and received, so they can't be paid yet:<br>{0}<br><br>"
		  "Receive the goods or service against the order, or correct the bill. An Accounts Manager can "
		  "tick <b>Approved unmatched payment</b> to pay anyway.").format(listed),
		title=_("Three-way match"),
	)
