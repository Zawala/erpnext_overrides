# Copyright (c) 2026, Kelvin Zawala and contributors
# See license.txt
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from erp_overrides.api import sales


def so(total, discounts=(), credit=0, discount=0):
	return frappe._dict(
		base_grand_total=total,
		custom_credit_approval=credit,
		custom_discount_approved=discount,
		items=[frappe._dict(discount_percentage=d) for d in discounts],
	)


LIMITS = frappe._dict(sales_order_limit=650, discount_limit=10)


class TestApprovalStatus(IntegrationTestCase):
	def test_exactly_at_limits_passes(self):
		status = sales.approval_status(so(650, [10]), LIMITS)
		self.assertFalse(status.credit_breached)
		self.assertFalse(status.discount_breached)
		self.assertFalse(status.needs_approval)

	def test_over_limits_needs_approval(self):
		status = sales.approval_status(so(650.01, [0, 10.5]), LIMITS)
		self.assertTrue(status.credit_breached)
		self.assertTrue(status.discount_breached)
		self.assertEqual(status.max_discount, 10.5)
		self.assertTrue(status.needs_approval)

	def test_both_approvals_clear_it(self):
		self.assertTrue(sales.approval_status(so(3720, [15], credit=1), LIMITS).needs_approval)
		self.assertFalse(sales.approval_status(so(3720, [15], credit=1, discount=1), LIMITS).needs_approval)

	def test_zero_limit_disables_check(self):
		status = sales.approval_status(so(99999, [90]), frappe._dict(sales_order_limit=0, discount_limit=0))
		self.assertFalse(status.needs_approval)


class TestMakeNext(IntegrationTestCase):
	def test_unknown_pair_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			sales.make_next("Quotation", "anything", "Purchase Invoice")

	def test_every_next_step_resolves(self):
		for method in sales.NEXT_STEPS.values():
			self.assertTrue(callable(frappe.get_attr(method)), method)

	def test_order_maps_to_delivery_and_invoice(self):
		order = frappe.db.get_value("Sales Order", {"docstatus": 1, "per_billed": ["<", 100], "per_delivered": ["<", 100],
		                                            "status": ["not in", ["Closed", "On Hold"]]}, "name")
		if not order:
			self.skipTest("no open submitted sales order on this site")
		for target, link in (("Delivery Note", "against_sales_order"), ("Sales Invoice", "sales_order")):
			doc = sales.make_next("Sales Order", order, target)
			self.assertEqual(doc["doctype"], target)
			self.assertTrue(doc["items"])
			self.assertTrue(all(i[link] == order for i in doc["items"]))

	def test_draft_source_is_rejected(self):
		draft = frappe.db.get_value("Quotation", {"docstatus": 0}, "name")
		if not draft:
			self.skipTest("no draft quotation on this site")
		with self.assertRaisesRegex(frappe.ValidationError, "Submit it first"):
			sales.make_next("Quotation", draft, "Sales Order")

class TestChain(IntegrationTestCase):
	def test_chain_links_quotation_to_order(self):
		row = frappe.db.sql(
			"""select soi.parent, soi.prevdoc_docname from `tabSales Order Item` soi
			join `tabSales Order` so on so.name = soi.parent
			where so.docstatus = 1 and ifnull(soi.prevdoc_docname, '') != '' limit 1""",
			as_dict=True,
		)
		if not row:
			self.skipTest("no sales order made from a quotation on this site")
		chain = sales.get_chain("Sales Order", row[0].parent)
		self.assertIn(row[0].prevdoc_docname, [r.name for r in chain["Quotation"]])
		self.assertTrue(any(r.current for r in chain["Sales Order"]))

		back = sales.get_chain("Quotation", row[0].prevdoc_docname)
		self.assertIn(row[0].parent, [r.name for r in back["Sales Order"]])

	def test_chain_has_fulfilment_stages(self):
		order = frappe.db.get_value("Sales Order", {"docstatus": 1}, "name")
		if not order:
			self.skipTest("no submitted sales order on this site")
		chain = sales.get_chain("Sales Order", order)
		self.assertIn("Delivery Note", chain)
		self.assertIn("Sales Invoice", chain)

	def test_rejects_doctypes_outside_chain(self):
		with self.assertRaises(frappe.ValidationError):
			sales.get_chain("User", "Administrator")


def seller(email, roles):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True)
	doc = frappe.get_doc(dict(doctype="User", email=email, first_name=email.split("@")[0], send_welcome_email=0,
	                          user_type="System User"))
	doc.append_roles(*roles)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestMyReport(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
		self.currency = frappe.get_cached_value("Company", self.company, "default_currency")
		self.customer = frappe.db.get_value("Customer", {"disabled": 0}, "name")
		self.item = "SALESTEST-REPORT-ITEM"
		if not frappe.db.exists("Item", self.item):
			frappe.get_doc(dict(doctype="Item", item_code=self.item, item_name="Sales report test item", item_group="All Item Groups",
			                    stock_uom="Nos", is_stock_item=0, is_sales_item=1)).insert()
		self.a = seller("report-a@example.com", ["Sales User"])
		self.b = seller("report-b@example.com", ["Sales User"])
		self.boss = seller("report-boss@example.com", ["Sales Manager"])
		self.clear()

	def tearDown(self):
		frappe.set_user("Administrator")
		self.clear()

	def clear(self):
		# owners are set with db_set, so these quotes outlive their users unless removed here
		names = frappe.get_all("Quotation", filters={"owner": ["in", [self.a, self.b, self.boss]]}, pluck="name")
		if names:
			frappe.db.delete("Quotation Item", {"parent": ["in", names]})
			frappe.db.delete("Quotation", {"name": ["in", names]})

	def quote(self, owner, rate, status=None):
		q = frappe.get_doc(dict(doctype="Quotation", company=self.company, quotation_to="Customer", party_name=self.customer,
		                        currency=self.currency, conversion_rate=1, transaction_date=nowdate(),
		                        valid_till=add_days(nowdate(), 30), selling_price_list=frappe.db.get_single_value("Selling Settings", "selling_price_list"),
		                        items=[dict(item_code=self.item, qty=1, rate=rate, uom="Nos", conversion_factor=1)]))
		q.insert()
		q.submit()
		q.db_set("owner", owner)
		if status:
			q.db_set("status", status)
		return q

	def report(self, user, scope="me"):
		frappe.set_user(user)
		try:
			return sales.get_my_report(scope)
		finally:
			frappe.set_user("Administrator")

	def test_me_counts_only_my_quotations(self):
		self.quote(self.a, 100, "Ordered")
		self.quote(self.a, 200, "Lost")
		self.quote(self.a, 300)
		self.quote(self.b, 999)
		r = self.report(self.a)
		self.assertEqual(r["scope"], "me")
		self.assertEqual(r["this_month"]["quoted"], {"total": 600, "count": 3})
		self.assertEqual(r["months"][-1]["quoted"], 600)
		self.assertEqual(r["quotes"]["won"], {"count": 1, "total": 100})
		self.assertEqual(r["quotes"]["open"]["count"], 1)
		self.assertEqual(r["quotes"]["win_rate"], 50.0)  # 1 won of 2 decided; the open one doesn't count
		self.assertEqual(r["top_items"][0]["item_code"], self.item)
		self.assertEqual(r["top_customers"][0]["won"], 100)
		self.assertNotIn("by_seller", r)

	def test_a_seller_cannot_see_the_team(self):
		self.quote(self.b, 999)
		r = self.report(self.a, "team")
		self.assertEqual(r["scope"], "me")
		self.assertFalse(r["can_team"])
		self.assertNotIn("by_seller", r)
		self.assertEqual(r["this_month"]["quoted"]["count"], 0)

	def test_a_manager_sees_each_seller(self):
		self.quote(self.a, 100, "Ordered")
		self.quote(self.b, 250)
		r = self.report(self.boss, "team")
		self.assertEqual(r["scope"], "team")
		rows = {s["user"]: s for s in r["by_seller"]}
		self.assertEqual(rows[self.a]["won"], 100)
		self.assertEqual(rows[self.a]["win_rate"], 100.0)
		self.assertEqual(rows[self.b]["quoted"], 250)
		self.assertIsNone(rows[self.b]["win_rate"])
		self.assertTrue(all(rep["url"].startswith("/desk/query-report/") for rep in r["reports"]))


class TestProforma(IntegrationTestCase):
	SO, QUOTE = "Proforma Invoice", "Proforma Invoice (Quotation)"

	def setUp(self):
		if not frappe.db.exists("Print Format", self.SO):
			self.skipTest("no Proforma Invoice print formats on this site")

	def test_both_formats_offered(self):
		self.assertEqual(sales.proforma_formats(), {"Sales Order": self.SO, "Quotation": self.QUOTE})

	def test_disabled_format_is_left_out(self):
		frappe.db.set_value("Print Format", self.QUOTE, "disabled", 1)
		self.addCleanup(frappe.db.set_value, "Print Format", self.QUOTE, "disabled", 0)
		self.assertEqual(sales.proforma_formats(), {"Sales Order": self.SO})

	def test_format_must_match_the_doctype(self):
		self.assertEqual(sales._print_format("Sales Order", self.SO), self.SO)
		self.assertRaises(frappe.ValidationError, sales._print_format, "Sales Order", self.QUOTE)

	def test_submitted_order_renders_as_proforma(self):
		name = frappe.db.get_value("Sales Order", {"docstatus": 1})
		if not name:
			self.skipTest("no submitted sales order")
		html = sales.get_print_preview("Sales Order", name, print_format=self.SO)["html"]
		self.assertIn("Proforma", html)
