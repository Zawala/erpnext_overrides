# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Three-way match before a supplier is paid (erp_overrides.three_way)."""
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from erp_overrides.api import sales
from erp_overrides.stock_light import default_warehouse
from erp_overrides.tests.test_stock_light import COMPANY, HARDWARE_GROUP, make_item, mapped, party
from erp_overrides.three_way import OVERRIDE_FIELD, match_status


class TestThreeWay(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Item Group", HARDWARE_GROUP) or not default_warehouse(COMPANY):
			self.skipTest("run erp_overrides.demo.seed first")
		if not frappe.get_meta("Payment Entry").has_field(OVERRIDE_FIELD):
			self.skipTest("run the three_way_2026_10 patch first")
		self.supplier = party("Supplier")
		self.bank = frappe.db.get_value("Account", {"company": COMPANY, "account_type": "Bank", "is_group": 0,
		                                           "account_currency": "USD"}, "name")
		if not self.supplier or not self.bank:
			self.skipTest("needs a supplier and a USD bank account")

	def order(self, item_code, qty=2, rate=50):
		po = frappe.get_doc(dict(doctype="Purchase Order", company=COMPANY, supplier=self.supplier, currency="USD",
		                         transaction_date=nowdate(), schedule_date=add_days(nowdate(), 7),
		                         items=[dict(item_code=item_code, qty=qty, rate=rate)])).insert(ignore_permissions=True)
		po.submit()
		return po

	def receive(self, po, qty=None):
		pr = mapped(sales.make_next("Purchase Order", po.name, "Purchase Receipt"))
		if qty is not None:
			pr.items[0].qty = qty
			pr.save()
		pr.submit()
		return pr

	def bill(self, po, qty=None, rate=None, submit=True):
		from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice

		pi = make_purchase_invoice(po.name)
		pi.bill_no = f"TWTEST-{frappe.generate_hash(length=6)}"
		if qty is not None:
			pi.items[0].qty = qty
		if rate is not None:
			pi.items[0].rate = rate
		pi.insert(ignore_permissions=True)
		if submit:
			pi.submit()
		return pi

	def pay(self, pi, override=False):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Purchase Invoice", pi.name, bank_account=self.bank)
		pe.reference_no = pi.name
		pe.reference_date = nowdate()
		pe.set(OVERRIDE_FIELD, 1 if override else 0)
		pe.insert(ignore_permissions=True)
		pe.submit()
		return pe

	def test_received_bill_pays(self):
		po = self.order(make_item("TWTEST-LAPTOP-A", HARDWARE_GROUP).name)
		self.receive(po)
		pi = self.bill(po)
		self.assertEqual(match_status(pi.name)["status"], "matched")
		self.assertEqual(self.pay(pi).docstatus, 1)

	def test_service_received_pays(self):
		po = self.order(make_item("TWTEST-COURSE-A", "Products").name, qty=1, rate=200)
		self.receive(po)
		self.assertEqual(match_status(self.bill(po).name)["status"], "matched")

	def test_not_received_is_refused(self):
		po = self.order(make_item("TWTEST-LAPTOP-B", HARDWARE_GROUP).name)
		pi = self.bill(po)
		self.assertEqual(match_status(pi.name)["status"], "not_received")
		with self.assertRaisesRegex(frappe.ValidationError, "aren't matched"):
			self.pay(pi)

	def test_billing_more_than_received_is_refused(self):
		po = self.order(make_item("TWTEST-LAPTOP-C", HARDWARE_GROUP).name, qty=3)
		self.receive(po, qty=2)
		pi = self.bill(po, qty=3)
		s = match_status(pi.name)
		self.assertEqual(s["status"], "qty_over")
		self.assertIn("3 billed, 2 received", s["message"])
		with self.assertRaisesRegex(frappe.ValidationError, "Over-billed"):
			self.pay(pi)

	def test_price_above_the_order_is_refused(self):
		po = self.order(make_item("TWTEST-LAPTOP-D", HARDWARE_GROUP).name, rate=50)
		self.receive(po)
		with self.change_settings("Buying Settings", maintain_same_rate=0):
			pi = self.bill(po, qty=1, rate=55)  # within the order total, above its price
		self.assertEqual(match_status(pi.name)["status"], "rate_diff")
		with self.assertRaisesRegex(frappe.ValidationError, "Price differs"):
			self.pay(pi)

	def test_overhead_bill_with_no_order_pays(self):
		expense = frappe.get_cached_value("Company", COMPANY, "default_expense_account")
		pi = frappe.get_doc(dict(doctype="Purchase Invoice", company=COMPANY, supplier=self.supplier, currency="USD",
		                         bill_no=f"TWTEST-{frappe.generate_hash(length=6)}",
		                         items=[dict(item_name="Electricity", qty=1, rate=30, uom="Nos", conversion_factor=1,
		                                     expense_account=expense)])).insert(ignore_permissions=True)
		pi.submit()
		self.assertEqual(match_status(pi.name)["status"], "no_po")
		self.assertEqual(self.pay(pi).docstatus, 1)

	def test_manager_override_pays_and_is_noted(self):
		po = self.order(make_item("TWTEST-LAPTOP-E", HARDWARE_GROUP).name)
		pi = self.bill(po)
		pe = self.pay(pi, override=True)
		self.assertEqual(pe.docstatus, 1)
		self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": "Payment Entry", "reference_name": pe.name,
		                                             "content": ["like", "%Paid unmatched bills%"]}))

	def test_orders_to_bill_and_bill_this_order(self):
		from erp_overrides.api import accounts

		po = self.order(make_item("TWTEST-LAPTOP-F", HARDWARE_GROUP).name, qty=3, rate=40)
		self.assertNotIn(po.name, [r.name for r in accounts.get_orders_to_bill()["rows"]])
		with self.assertRaisesRegex(frappe.ValidationError, "Receive it first"):
			accounts.bill_order(po.name)
		self.receive(po, qty=2)
		row = next(r for r in accounts.get_orders_to_bill()["rows"] if r.name == po.name)
		self.assertAlmostEqual(row.to_bill, 80, places=2)
		pi = frappe.get_doc("Purchase Invoice", accounts.bill_order(po.name))
		self.assertEqual((pi.docstatus, pi.items[0].qty), (0, 2))  # what was received, not what was ordered
		self.assertEqual(accounts.get_match(pi.name)["status"], "matched")


class TestOpeningBalance(IntegrationTestCase):
	def test_bank_opening_against_temporary_opening(self):
		from erp_overrides.api import accounts

		temp = accounts.temporary_opening_account("USD", COMPANY)
		if not temp:
			self.skipTest("no Temporary Opening account for USD")
		bank = frappe.db.get_value("Bank Account", {"is_company_account": 1, "disabled": 0, "company": COMPANY,
		                                            "account": ["is", "set"]}, ["name", "account"], as_dict=True)
		if not bank:
			self.skipTest("needs a company bank account")
		existing = accounts._opening_journal(bank.account)
		if existing:
			with self.assertRaisesRegex(frappe.ValidationError, "already has an opening balance"):
				accounts.set_opening_balance(bank.name, "2026-01-01", 100)
			return
		currency = frappe.get_cached_value("Account", bank.account, "account_currency")
		je = frappe.get_doc("Journal Entry", accounts.set_opening_balance(bank.name, "2026-01-01", 1234.5))
		self.assertEqual((je.docstatus, je.is_opening), (1, "Yes"))
		lines = {a.account: a.debit_in_account_currency - a.credit_in_account_currency for a in je.accounts}
		self.assertEqual(lines[bank.account], 1234.5)
		self.assertEqual(lines[accounts.temporary_opening_account(currency, COMPANY)], -1234.5)
