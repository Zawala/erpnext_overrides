# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Hardware stock that looks after itself (erp_overrides.stock_light)."""
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from erp_overrides.api import sales
from erp_overrides.stock_light import default_warehouse

COMPANY = "Demo Trading Ltd"  # the demo company (erp_overrides.demo)
HARDWARE_GROUP = "Laptops & Desktops"


def make_item(code, group):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(dict(doctype="Item", item_code=code, item_name=code, item_group=group, stock_uom="Nos",
		                    is_sales_item=1, is_purchase_item=1)).insert(ignore_permissions=True)
	return frappe.get_doc("Item", code)


def party(doctype):
	return frappe.db.get_value(doctype, {"disabled": 0, "default_currency": ["in", ["USD", "", None]]}, "name") \
		or frappe.db.get_value(doctype, {"disabled": 0}, "name")


def bin_qty(item_code):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": default_warehouse(COMPANY)}, "actual_qty"))


def cost_of_sales(invoice, account_number):
	return flt(frappe.db.sql(
		"""select sum(g.debit) - sum(g.credit) from `tabGL Entry` g join tabAccount a on a.name = g.account
		   where g.voucher_no = %s and g.is_cancelled = 0 and a.account_number = %s""", (invoice, account_number))[0][0])


def mapped(target_dict):
	doc = frappe.get_doc(target_dict)
	doc.insert(ignore_permissions=True)
	return doc


class TestStockLight(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Item Group", HARDWARE_GROUP) or not default_warehouse(COMPANY):
			self.skipTest("run erp_overrides.demo.seed first")
		self.customer, self.supplier = party("Customer"), party("Supplier")
		if not self.customer or not self.supplier:
			self.skipTest("needs a customer and a supplier")

	def order(self, item_code, qty=1, rate=100):
		so = frappe.get_doc(dict(doctype="Sales Order", company=COMPANY, customer=self.customer, currency="USD",
		                         transaction_date=nowdate(), delivery_date=add_days(nowdate(), 7),
		                         items=[dict(item_code=item_code, qty=qty, rate=rate)])).insert(ignore_permissions=True)
		so.submit()
		return so

	def buy(self, so, rate):
		po = mapped(sales.make_next("Sales Order", so.name, "Purchase Order") | {"supplier": self.supplier})
		for r in po.items:
			r.rate = rate
		po.save()
		po.submit()
		return po

	def receive(self, po):
		pr = mapped(sales.make_next("Purchase Order", po.name, "Purchase Receipt"))
		pr.submit()
		return pr

	def supplier_invoice(self, po):
		from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice

		pi = make_purchase_invoice(po.name)
		pi.bill_no = f"HRTEST-{po.name}"
		pi.insert(ignore_permissions=True)
		pi.submit()
		return pi

	def customer_invoice(self, source_doctype, source_name):
		si = mapped(sales.make_next(source_doctype, source_name, "Sales Invoice"))
		si.submit()
		return si

	def test_only_hardware_keeps_stock(self):
		laptop = make_item("HRTEST-LAPTOP-A", HARDWARE_GROUP)
		self.assertEqual((laptop.is_stock_item, laptop.allow_negative_stock), (1, 1))
		course = make_item("HRTEST-COURSE-A", "Products")
		self.assertEqual(course.is_stock_item, 0)
		course.item_group = HARDWARE_GROUP  # moved into hardware before it's used: now it keeps stock
		course.save()
		self.assertEqual(course.is_stock_item, 1)

	def test_order_buy_receive_invoice_with_no_delivery(self):
		item = make_item("HRTEST-LAPTOP-B", HARDWARE_GROUP).name
		so = self.order(item, qty=2, rate=100)
		po = self.buy(so, rate=60)
		self.assertTrue(all(r.sales_order == so.name and r.warehouse for r in po.items))
		self.assertEqual(flt(frappe.db.get_value("Sales Order Item", {"parent": so.name}, "ordered_qty")), 2)
		with self.assertRaisesRegex(frappe.ValidationError, "ordered from a supplier"):
			sales.make_next("Sales Order", so.name, "Purchase Order")

		self.receive(po)
		self.assertEqual(bin_qty(item), 2)
		pi = self.supplier_invoice(po)
		self.assertEqual(pi.update_stock, 0)  # the receipt brought it in
		self.assertEqual(bin_qty(item), 2)

		si = self.customer_invoice("Sales Order", so.name)
		self.assertEqual(si.update_stock, 1)
		self.assertEqual(bin_qty(item), 0)
		self.assertAlmostEqual(cost_of_sales(si.name, "5110"), 120, places=2)
		self.assertFalse(frappe.db.exists("Delivery Note Item", {"item_code": item}))

	def test_sold_before_it_is_received(self):
		item = make_item("HRTEST-LAPTOP-C", HARDWARE_GROUP).name
		so = self.order(item, rate=100)
		po = self.buy(so, rate=70)
		si = self.customer_invoice("Sales Order", so.name)  # not received yet
		self.assertEqual(bin_qty(item), -1)
		self.assertAlmostEqual(cost_of_sales(si.name, "5110"), 70, places=2)  # at the order's price
		self.receive(po)
		self.assertEqual(bin_qty(item), 0)

	def test_services_move_no_stock(self):
		course = make_item("HRTEST-COURSE-B", "Products").name
		si = self.customer_invoice("Sales Order", self.order(course).name)
		self.assertEqual(si.update_stock, 0)

	def test_optional_delivery_note_moves_stock_once(self):
		item = make_item("HRTEST-LAPTOP-D", HARDWARE_GROUP).name
		so = self.order(item, rate=100)
		self.buy(so, rate=50)
		dn = mapped(sales.make_next("Sales Order", so.name, "Delivery Note"))
		dn.submit()
		self.assertEqual(bin_qty(item), -1)
		si = self.customer_invoice("Delivery Note", dn.name)
		self.assertEqual(si.update_stock, 0)
		self.assertEqual(bin_qty(item), -1)
