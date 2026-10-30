# Copyright (c) 2026, Kelvin Zawala and contributors
# See license.txt
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from erp_overrides.api import accounts

USD_BANK, ZWG_BANK = "Main Bank USD - Main Bank", "Main Bank ZWG - Main Bank"
DATE = "2026-07-20"


def company():
	return frappe.db.get_single_value("Global Defaults", "default_company")


def account(number):
	return frappe.db.get_value("Account", {"company": company(), "account_number": number}, "name")


def other_usd_bank():
	return frappe.db.get_value("Bank Account", {"is_company_account": 1, "account": ["is", "set"], "name": ["!=", USD_BANK],
	                                            "account": ["like", "%USD%"]}, "name")


def line(bank=USD_BANK, deposit=0, withdrawal=0, description="HRTEST LINE", date=DATE, reference=None):
	doc = frappe.get_doc(dict(doctype="Bank Transaction", date=date, bank_account=bank, deposit=deposit, withdrawal=withdrawal,
	                          description=description, reference_number=reference, company=company(),
	                          currency=frappe.get_cached_value("Account", frappe.get_cached_value("Bank Account", bank, "account"),
	                                                           "account_currency")))
	doc.insert()
	doc.submit()
	return doc


def status(name):
	return frappe.db.get_value("Bank Transaction", name, ["status", "unallocated_amount"], as_dict=True)


class TestSkip(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Bank Account", USD_BANK) or not account("6510"):
			self.skipTest("needs a numbered chart of accounts and a bank account")


class TestCreate(TestSkip):
	def test_bank_charge_to_an_account(self):
		ln = line(withdrawal=12.34, description="HRTEST SERVICE CHARGE")
		out = accounts.create(ln.name, account=account("6510"), remark="Bank charge")
		self.assertEqual(out["voucher_type"], "Journal Entry")
		self.assertEqual(status(ln.name).status, "Reconciled")
		je = frappe.get_doc("Journal Entry", out["voucher"])
		self.assertEqual(je.docstatus, 1)
		self.assertAlmostEqual(sum(a.credit for a in je.accounts), 12.34)

	def test_zwg_line_is_converted_at_the_days_rate(self):
		rate = accounts._rate("ZWG", "USD", DATE)
		if not rate:
			self.skipTest("no ZWG rate for the test date")
		ln = line(bank=ZWG_BANK, withdrawal=1000, description="HRTEST ZWG CHARGE")
		out = accounts.create(ln.name, account=account("6510"))
		je = frappe.get_doc("Journal Entry", out["voucher"])
		bank_row = next(a for a in je.accounts if a.account == frappe.get_cached_value("Bank Account", ZWG_BANK, "account"))
		self.assertAlmostEqual(bank_row.credit_in_account_currency, 1000)
		self.assertAlmostEqual(bank_row.credit, flt(1000 * rate, 2), delta=0.01)  # in USD, not 1000
		expense = next(a for a in je.accounts if a.account == account("6510"))
		self.assertAlmostEqual(expense.debit, bank_row.credit, delta=0.01)
		self.assertEqual(status(ln.name).status, "Reconciled")

	def test_with_a_party_makes_a_payment(self):
		supplier = frappe.db.get_value("Supplier", {"disabled": 0}, "name")
		ln = line(withdrawal=75, description="HRTEST SUPPLIER PAYMENT")
		out = accounts.create(ln.name, party_type="Supplier", party=supplier)
		pe = frappe.get_doc("Payment Entry", out["voucher"])
		self.assertEqual((pe.payment_type, pe.party, pe.paid_amount, pe.docstatus), ("Pay", supplier, 75, 1))
		self.assertEqual(status(ln.name).status, "Reconciled")

	def test_already_reconciled_is_refused(self):
		ln = line(withdrawal=5, description="HRTEST TWICE")
		accounts.create(ln.name, account=account("6510"))
		with self.assertRaises(frappe.ValidationError):
			accounts.create(ln.name, account=account("6510"))


class TestMatch(TestSkip):
	def test_existing_payment_is_suggested_and_matched(self):
		supplier = frappe.db.get_value("Supplier", {"disabled": 0}, "name")
		bank_gl = frappe.get_cached_value("Bank Account", USD_BANK, "account")
		from erpnext.accounts.party import get_party_account

		pe = frappe.get_doc(dict(
			doctype="Payment Entry", payment_type="Pay", company=company(), posting_date=DATE, party_type="Supplier",
			party=supplier, paid_from=bank_gl, paid_to=get_party_account("Supplier", supplier, company()),
			paid_amount=43.21, received_amount=43.21, reference_no="HRTEST-REF-1", reference_date=DATE,
			source_exchange_rate=1, target_exchange_rate=1, bank_account=USD_BANK))
		pe.insert()
		pe.submit()
		ln = line(withdrawal=43.21, description="HRTEST MATCH", reference="HRTEST-REF-1")
		found = next((s for s in accounts.get_line(ln.name).suggestions if s["name"] == pe.name), None)
		self.assertTrue(found and found["exact"], accounts.get_line(ln.name).suggestions)
		accounts.match(ln.name, [{"doctype": "Payment Entry", "name": pe.name, "amount": 43.21}])
		self.assertEqual(status(ln.name).status, "Reconciled")

	def test_deposit_pays_an_open_invoice(self):
		inv = frappe.db.get_value("Sales Invoice", {"docstatus": 1, "outstanding_amount": [">", 0], "currency": "USD"},
		                          ["name", "outstanding_amount"], as_dict=True)
		if not inv:
			self.skipTest("no open USD sales invoice")
		ln = line(deposit=inv.outstanding_amount, description="HRTEST CUSTOMER PAYS")
		self.assertIn(inv.name, [i.name for i in accounts.get_line(ln.name).invoices if i.exact])
		out = accounts.pay_invoice(ln.name, "Sales Invoice", inv.name)
		self.assertEqual(status(ln.name).status, "Reconciled")
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", inv.name, "outstanding_amount")), 0)
		self.assertEqual(frappe.db.get_value("Payment Entry", out["payment_entry"], "docstatus"), 1)


class TestTransfer(TestSkip):
	def test_same_currency_both_sides_reconciled(self):
		other = other_usd_bank()
		if not other:
			self.skipTest("needs a second USD bank account")
		out_line = line(withdrawal=100, description="HRTEST TRANSFER OUT")
		in_line = line(bank=other, deposit=100, description="HRTEST TRANSFER IN")
		self.assertIn(in_line.name, [c.name for c in accounts.get_line(out_line.name).transfer_candidates])
		out = accounts.transfer(out_line.name, other, other_line=in_line.name)
		pe = frappe.get_doc("Payment Entry", out["payment_entry"])
		self.assertEqual((pe.payment_type, pe.paid_amount, pe.received_amount), ("Internal Transfer", 100, 100))
		self.assertEqual(status(out_line.name).status, "Reconciled")
		self.assertEqual(status(in_line.name).status, "Reconciled")

	def test_usd_to_zwg_uses_both_amounts(self):
		out_line = line(withdrawal=100, description="HRTEST FX OUT")
		in_line = line(bank=ZWG_BANK, deposit=2650, description="HRTEST FX IN")
		out = accounts.transfer(out_line.name, ZWG_BANK, other_line=in_line.name)
		pe = frappe.get_doc("Payment Entry", out["payment_entry"])
		self.assertEqual((pe.paid_amount, pe.received_amount), (100, 2650))
		self.assertEqual(status(in_line.name).status, "Reconciled")


	def test_no_rate_for_the_day_says_so(self):
		# a USD -> ZWG transfer with no RBZ rate used to divide by zero: a bare 500 on the bank page
		from unittest.mock import patch

		out_line = line(withdrawal=100, description="HRTEST FX NO RATE")
		with patch.object(accounts, "_rate", lambda f, t, d=None: 1.0 if f == t else 0.0):
			with self.assertRaisesRegex(frappe.ValidationError, "Fetch the RBZ rate"):
				accounts.transfer(out_line.name, ZWG_BANK)
		self.assertEqual(status(out_line.name).unallocated_amount, 100)


class TestVatSplit(TestSkip):
	def test_zwg_lines_with_vat_balance(self):
		# each row rounded on its own used to leave the entry 0.01 out ("Total Debit must be equal to Total Credit")
		vat = frappe.db.get_value("Purchase Taxes and Charges Template", {"company": company()}, "name")
		if not vat or not accounts._rate("ZWG", "USD", DATE):
			self.skipTest("needs a purchase tax template and a ZWG rate for the test date")
		for cents in range(0, 1200, 97):
			amount = flt(1234 + cents / 100, 2)
			ln = line(bank=ZWG_BANK, withdrawal=amount, description=f"HRTEST VAT {amount}")
			out = accounts.create(ln.name, account=account("6510"), vat_template=vat)
			je = frappe.get_doc("Journal Entry", out["voucher"])
			self.assertEqual(je.docstatus, 1, amount)
			self.assertAlmostEqual(je.total_debit, je.total_credit, places=2)


class TestRules(TestSkip):
	def test_rule_tags_and_ok_reconciles(self):
		rule = accounts.save_rule(dict(rule_name="HRTest charges", transaction_type="Withdrawal", classify_as="Bank Entry",
		                               account=account("6510"), priority=1,
		                               conditions=[{"check": "Regex", "value": "HRTEST (SMS|LEDGER) FEE"}]))
		a, b = line(withdrawal=1.5, description="HRTEST SMS FEE"), line(withdrawal=2.5, description="HRTEST LEDGER FEE")
		accounts.run_rules()
		self.assertEqual(frappe.db.get_value("Bank Transaction", a.name, "matched_transaction_rule"), rule["name"])
		self.assertEqual(accounts.preview_rule(rule)["count"], 2)
		out = accounts.apply_rule([a.name, b.name])
		self.assertEqual((len(out["done"]), out["failed"]), (2, []))
		self.assertEqual(status(b.name).status, "Reconciled")

	def test_ok_takes_every_match_not_just_the_page(self):
		rule = accounts.save_rule(dict(rule_name="HRTest bulk fees", transaction_type="Withdrawal", classify_as="Bank Entry",
		                               account=account("6510"), priority=1,
		                               conditions=[{"check": "Contains", "value": "HRTEST BULK FEE"}]))
		made = [line(withdrawal=1 + i, description=f"HRTEST BULK FEE {i}").name for i in range(4)]
		other = line(withdrawal=7, description="HRTEST UNMATCHED").name
		accounts.run_rules()
		page = accounts.get_lines(USD_BANK, search="HRTEST BULK FEE", rule_only=1, page_length=2)
		self.assertEqual((len(page["rows"]), page["total"]), (2, 4))
		names = accounts.get_rule_line_names(USD_BANK, search="HRTEST BULK FEE")
		self.assertEqual(sorted(names), sorted(made))
		self.assertNotIn(other, accounts.get_rule_line_names(USD_BANK, search="HRTEST"))
		self.assertEqual(accounts.get_rule_line_names(USD_BANK, search="HRTEST BULK FEE", direction="in"), [])
		self.assertEqual(frappe.db.get_value("Bank Transaction", made[0], "matched_transaction_rule"), rule["name"])

	def test_rule_needs_a_condition(self):
		with self.assertRaises(frappe.ValidationError):
			accounts.save_rule(dict(rule_name="HRTest empty", classify_as="Bank Entry", account=account("6510")))


class TestDiscussAndUndo(TestSkip):
	def test_comment_and_assign(self):
		ln = line(withdrawal=9, description="HRTEST WHAT IS THIS")
		comments = accounts.discuss(ln.name, "Who paid this?", assign_to="Administrator")
		self.assertEqual(comments[-1].content, "Who paid this?")
		self.assertTrue(frappe.db.exists("ToDo", {"reference_name": ln.name, "allocated_to": "Administrator", "status": "Open"}))

	def test_lines_load_before_anyone_has_commented(self):
		# a site where no Bank Transaction was ever commented on or assigned has no _comments / _assign
		# column, and Frappe then leaves those fields out of get_list
		from unittest.mock import patch

		ln = line(withdrawal=4, description="HRTEST NO COMMENT COLUMN")
		get_list = frappe.get_list

		def without_optional_columns(*args, **kwargs):
			rows = get_list(*args, **kwargs)
			for r in rows:
				if isinstance(r, dict):
					r.pop("_comments", None)
					r.pop("_assign", None)
			return rows

		with patch.object(frappe, "get_list", without_optional_columns):
			rows = accounts.get_lines(USD_BANK, search="HRTEST NO COMMENT COLUMN")["rows"]
		row = next(r for r in rows if r.name == ln.name)
		self.assertEqual((row.comments, row.assigned), (0, []))

	def test_undo_cancels_the_entry(self):
		ln = line(withdrawal=3, description="HRTEST UNDO")
		je = accounts.create(ln.name, account=account("6510"))["voucher"]
		accounts.unreconcile(ln.name)
		self.assertEqual(status(ln.name).status, "Unreconciled")
		self.assertEqual(frappe.db.get_value("Journal Entry", je, "docstatus"), 2)


class TestImport(TestSkip):
	def test_duplicates_are_skipped(self):
		# the bank feed gave this line a reference; the CSV export has no reference column
		existing = line(withdrawal=11.11, description="HRTEST DUP LINE", date="2026-07-21", reference="055NPAR-HRTEST")
		csv = ("Date,Description,Debit,Credit,Balance\n"
		       "21/07/2026,HRTEST DUP LINE,11.11,,100.00\n"
		       "22/07/2026,HRTEST NEW ONE,22.22,,77.78\n"
		       "23/07/2026,HRTEST NEW TWO,,50.00,127.78\n")
		f = frappe.get_doc(dict(doctype="File", file_name="hrtest-statement.csv", content=csv, is_private=1)).insert()
		preview = accounts.start_import(USD_BANK, f.file_url)
		self.assertEqual((preview["new"], preview["duplicates"]), (2, 1), preview)
		out = accounts.import_statement(preview["name"])
		self.assertEqual((out["created"], out["skipped"]), (2, 1))
		self.assertTrue(frappe.db.exists("Bank Transaction", {"description": "HRTEST NEW TWO", "deposit": 50}))
		self.assertTrue(existing.name)


class TestAccess(TestSkip):
	def test_manager_reads_but_cannot_post(self):
		user = frappe.get_doc(dict(doctype="User", email="hrtest.manager@example.com", first_name="Manager",
		                           send_welcome_email=0)).insert(ignore_permissions=True)
		user.add_roles("Sales Manager")
		ln = line(withdrawal=4, description="HRTEST MANAGER")
		frappe.set_user(user.name)
		try:
			self.assertIn("cash", accounts.get_dashboard())
			with self.assertRaises(frappe.PermissionError):
				accounts.create(ln.name, account=account("6510"))
			with self.assertRaises(frappe.PermissionError):
				accounts.save_rule(dict(rule_name="x", conditions=[{"value": "x"}]))
		finally:
			frappe.set_user("Administrator")

	def test_employee_without_roles_is_kept_out(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				accounts.get_dashboard()
		finally:
			frappe.set_user("Administrator")


class TestOwed(TestSkip):
	def test_supplier_bill_is_a_draft_with_the_document(self):
		supplier = frappe.db.get_value("Supplier", {"disabled": 0}, "name")
		f = frappe.get_doc(dict(doctype="File", file_name="hrtest-bill.txt", content="bill", is_private=1)).insert()
		name = accounts.new_supplier_bill(supplier, "2026-07-20", [{"description": "Internet July", "account": account("6280"), "amount": 120}],
		                                  bill_no="HRTEST-INV-9", file_url=f.file_url)
		pi = frappe.get_doc("Purchase Invoice", name)
		self.assertEqual((pi.docstatus, pi.supplier, pi.bill_no, flt(pi.net_total)), (0, supplier, "HRTEST-INV-9", 120))
		self.assertEqual(pi.items[0].expense_account, account("6280"))
		self.assertTrue(frappe.db.exists("File", {"attached_to_doctype": "Purchase Invoice", "attached_to_name": name}))

	def test_receive_against_an_invoice(self):
		inv = frappe.db.get_value("Sales Invoice", {"docstatus": 1, "outstanding_amount": [">", 0], "currency": "USD"},
		                          ["name", "outstanding_amount", "customer"], as_dict=True)
		if not inv:
			self.skipTest("no open USD sales invoice")
		self.assertIn(inv.customer, [r["party"] for r in accounts.get_ageing("Customer")["rows"]])
		pe = accounts.record_payment("Sales Invoice", inv.name, USD_BANK, 100, "2026-07-20", "HRTEST-RCPT")
		self.assertEqual(frappe.db.get_value("Payment Entry", pe, "docstatus"), 1)
		self.assertAlmostEqual(flt(frappe.db.get_value("Sales Invoice", inv.name, "outstanding_amount")), flt(inv.outstanding_amount) - 100)


class TestMakePayment(TestSkip):
	def test_spend_to_an_expense_account(self):
		out = accounts.make_payment(USD_BANK, 40, DATE, account=account("6510"), reference_no="HRTEST-SPEND", remark="Courier")
		je = frappe.get_doc("Journal Entry", out["voucher"])
		self.assertEqual((je.docstatus, je.cheque_no), (1, "HRTEST-SPEND"))
		bank_gl = frappe.get_cached_value("Bank Account", USD_BANK, "account")
		self.assertAlmostEqual(next(a for a in je.accounts if a.account == bank_gl).credit, 40)
		# when the line arrives, Bank offers it
		ln = line(withdrawal=40, description="HRTEST COURIER", reference="HRTEST-SPEND")
		self.assertIn(je.name, [s["name"] for s in accounts.get_line(ln.name).suggestions])

	def test_pays_the_ticked_bill_rest_on_account(self):
		supplier = frappe.db.get_value("Supplier", {"disabled": 0, "default_currency": ["in", ["USD", "", None]]}, "name") \
			or frappe.db.get_value("Supplier", {"disabled": 0}, "name")
		pi = frappe.get_doc("Purchase Invoice", accounts.new_supplier_bill(
			supplier, DATE, [{"description": "HRTEST bill", "account": account("6510"), "amount": 60}], currency="USD"))
		pi.submit()
		out = accounts.make_payment(USD_BANK, 100, DATE, supplier=supplier, invoices=[pi.name], reference_no="HRTEST-PAY")
		pe = frappe.get_doc("Payment Entry", out["voucher"])
		self.assertEqual((pe.docstatus, pe.payment_type, pe.paid_amount), (1, "Pay", 100))
		self.assertEqual([(r.reference_name, r.allocated_amount) for r in pe.references], [(pi.name, 60)])
		self.assertAlmostEqual(pe.unallocated_amount, 40)
		self.assertEqual(flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount")), 0)

	def test_another_suppliers_bill_is_refused(self):
		suppliers = frappe.get_all("Supplier", filters={"disabled": 0}, pluck="name", limit=2)
		if len(suppliers) < 2:
			self.skipTest("needs two suppliers")
		pi = frappe.get_doc("Purchase Invoice", accounts.new_supplier_bill(
			suppliers[0], DATE, [{"description": "HRTEST bill", "account": account("6510"), "amount": 10}], currency="USD"))
		pi.submit()
		with self.assertRaises(frappe.ValidationError):
			accounts.make_payment(USD_BANK, 10, DATE, supplier=suppliers[1], invoices=[pi.name])

	def test_no_accounts_role_cannot_pay(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				accounts.make_payment(USD_BANK, 10, DATE, account=account("6510"))
		finally:
			frappe.set_user("Administrator")


class TestPayments(TestSkip):
	def test_waiting_then_cleared_then_listed(self):
		out = accounts.make_payment(USD_BANK, 33.33, DATE, account=account("6510"), reference_no="HRTEST-TRACK")
		found = accounts.get_payments(search="HRTEST-TRACK", direction="out")
		self.assertEqual([(r.name, r.status, r.amount) for r in found["rows"]], [(out["voucher"], "waiting", 33.33)])
		self.assertEqual(found["totals"]["USD"]["waiting"], 1)
		self.assertTrue(accounts.get_payment("Journal Entry", out["voucher"])["can_cancel"])
		ln = line(withdrawal=33.33, description="HRTEST TRACKED", reference="HRTEST-TRACK")
		accounts.match(ln.name, [{"doctype": "Journal Entry", "name": out["voucher"], "amount": 33.33}])
		row = accounts.get_payments(search="HRTEST-TRACK", status="cleared")["rows"][0]
		self.assertEqual((row.status, row.bank_line["name"]), ("cleared", ln.name))
		with self.assertRaises(frappe.ValidationError):
			accounts.cancel_payment("Journal Entry", out["voucher"])

	def test_supplier_payment_shows_the_bills_and_cancels(self):
		supplier = frappe.db.get_value("Supplier", {"disabled": 0}, "name")
		pi = frappe.get_doc("Purchase Invoice", accounts.new_supplier_bill(
			supplier, DATE, [{"description": "HRTEST bill", "account": account("6510"), "amount": 20}], currency="USD"))
		pi.submit()
		out = accounts.make_payment(USD_BANK, 20, DATE, supplier=supplier, invoices=[pi.name], reference_no="HRTEST-PAYBILL")
		detail = accounts.get_payment("Payment Entry", out["voucher"])
		self.assertEqual([(p["name"], p["amount"]) for p in detail["paid"]], [(pi.name, 20)])
		accounts.cancel_payment("Payment Entry", out["voucher"])
		self.assertEqual(accounts.get_payments(search="HRTEST-PAYBILL")["rows"], [])
		self.assertEqual(accounts.get_payments(search="HRTEST-PAYBILL", status="cancelled")["rows"][0].status, "cancelled")
		self.assertEqual(flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount")), 20)


PETTY, ZWG_CASH = "1200", "1190"


def custodian():
	email = "hrtest-custodian@example.com"
	if not frappe.db.exists("User", email):
		frappe.get_doc(dict(doctype="User", email=email, first_name="HRTEST Custodian", send_welcome_email=0,
		                    roles=[{"role": "Employee"}])).insert(ignore_permissions=True)
	return email


class TestPettyCash(TestSkip):
	def setUp(self):
		super().setUp()
		if not frappe.db.exists("DocType", "App Accounts Settings") or not account(PETTY) or not account("6545"):
			self.skipTest("run erp_overrides.demo.seed first")
		s = frappe.get_single("App Accounts Settings")
		s.petty_cash_boxes = []
		s.append("petty_cash_boxes", dict(account=account(PETTY), custodian=custodian(), float_amount=200, approval_limit=50))
		if account(ZWG_CASH):
			s.append("petty_cash_boxes", dict(account=account(ZWG_CASH), float_amount=5000))
		s.cash_over_short_account = account("6545")
		s.save()

	def tearDown(self):
		frappe.set_user("Administrator")

	def top_up(self, amount=200):
		return accounts.top_up(account(PETTY), USD_BANK, DATE, amount)

	def test_voucher_under_the_limit_posts_with_its_receipt(self):
		self.top_up()
		f = frappe.get_doc(dict(doctype="File", file_name="hrtest-receipt.txt", content="receipt", is_private=1)).insert()
		out = accounts.new_voucher(account(PETTY), DATE, 12.5, account("6510"), paid_to="HRTEST Courier", file_url=f.file_url)
		self.assertEqual(out["status"], "posted")
		je = frappe.get_doc("Journal Entry", out["name"])
		self.assertEqual((je.docstatus, je.voucher_type, je.pay_to_recd_from), (1, "Cash Entry", "HRTEST Courier"))
		row = accounts.get_vouchers(account(PETTY), "posted")[0]
		self.assertEqual((row.name, row.kind, row.amount), (je.name, "voucher", 12.5))
		self.assertTrue(row.receipt)

	def test_over_the_limit_waits_then_approve_or_decline(self):
		self.top_up()
		a = accounts.new_voucher(account(PETTY), DATE, 80, account("6510"), paid_to="HRTEST Big")
		self.assertEqual((a["status"], frappe.db.get_value("Journal Entry", a["name"], "docstatus")), ("awaiting", 0))
		self.assertEqual(next(b for b in accounts.get_petty_cash()["boxes"] if b["account"] == account(PETTY))["awaiting"], 1)
		accounts.approve_voucher(a["name"])
		self.assertEqual(frappe.db.get_value("Journal Entry", a["name"], "docstatus"), 1)
		b = accounts.new_voucher(account(PETTY), DATE, 90, account("6510"), paid_to="HRTEST Bigger")
		with self.assertRaises(frappe.ValidationError):
			accounts.decline_voucher(b["name"], "")
		accounts.decline_voucher(b["name"], "No receipt")
		self.assertFalse(frappe.db.exists("Journal Entry", b["name"]))
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": account(PETTY), "content": ["like", "%No receipt%"]}))

	def test_custodian_records_for_their_own_box_only(self):
		self.top_up()
		frappe.set_user(custodian())
		boxes = accounts.get_petty_cash()["boxes"]
		self.assertEqual([b["account"] for b in boxes], [account(PETTY)])
		out = accounts.new_voucher(account(PETTY), DATE, 10, account("6510"), paid_to="HRTEST Milk")
		self.assertEqual(frappe.db.get_value("Journal Entry", out["name"], "owner"), custodian())
		self.assertTrue(accounts.petty_search("Account", "Bank"))
		if account(ZWG_CASH):
			with self.assertRaises(frappe.PermissionError):
				accounts.new_voucher(account(ZWG_CASH), DATE, 10, account("6510"))
		for call in (lambda: self.top_up(), lambda: accounts.count_cash(account(PETTY), 1, DATE),
		             lambda: accounts.approve_voucher(out["name"]), lambda: accounts.get_dashboard()):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_top_up_defaults_to_the_float_and_is_a_transfer(self):
		from erpnext.accounts.utils import get_balance_on

		before = get_balance_on(account(PETTY), DATE, in_account_currency=True)
		s = frappe.get_single("App Accounts Settings")
		s.petty_cash_boxes[0].float_amount = before + 150  # other tests may have topped it up already
		s.save()
		out = accounts.top_up(account(PETTY), USD_BANK, DATE)
		self.assertAlmostEqual(out["amount"], 150)
		self.assertAlmostEqual(get_balance_on(account(PETTY), DATE, in_account_currency=True), before + 150)
		with self.assertRaises(frappe.ValidationError):
			accounts.top_up(account(PETTY), USD_BANK, DATE)  # already at the float
		rows = [r for r in accounts.get_payments(direction="")["rows"] if r.name == out["name"]]
		self.assertEqual([(r.direction, r.status) for r in rows], [("transfer", "waiting")])

	def test_cash_count_posts_the_difference(self):
		from erpnext.accounts.utils import get_balance_on

		self.top_up()
		books = get_balance_on(account(PETTY), DATE, in_account_currency=True)
		self.assertIsNone(accounts.count_cash(account(PETTY), books, DATE)["journal_entry"])
		out = accounts.count_cash(account(PETTY), books - 7.5, DATE)
		self.assertAlmostEqual(out["difference"], -7.5)
		je = frappe.get_doc("Journal Entry", out["journal_entry"])
		self.assertAlmostEqual(next(a for a in je.accounts if a.account == account("6545")).debit, 7.5)
		self.assertAlmostEqual(get_balance_on(account(PETTY), DATE, in_account_currency=True), books - 7.5)
		box = next(b for b in accounts.get_petty_cash()["boxes"] if b["account"] == account(PETTY))
		self.assertIn("difference -7.50", box["last_count"]["content"])

	def test_zwg_box_is_valued_at_the_days_rate(self):
		rate = accounts._rate("ZWG", "USD", DATE)
		if not account(ZWG_CASH) or not rate:
			self.skipTest("needs CASH ZWG and a rate")
		out = accounts.new_voucher(account(ZWG_CASH), DATE, 1000, account("6510"), paid_to="HRTEST ZWG")
		je = frappe.get_doc("Journal Entry", out["name"])
		cash = next(a for a in je.accounts if a.account == account(ZWG_CASH))
		self.assertAlmostEqual(cash.credit_in_account_currency, 1000)
		self.assertAlmostEqual(cash.credit, flt(1000 * rate, 2), delta=0.01)

	def test_cash_payments_are_not_waiting_for_a_statement(self):
		self.top_up()
		out = accounts.new_voucher(account(PETTY), DATE, 9.99, account("6510"), paid_to="HRTEST Cash row")
		row = next(r for r in accounts.get_payments(search="HRTEST Cash row")["rows"] if r.name == out["name"])
		self.assertEqual(row.status, "cash")
		self.assertIn(out["name"], [r.name for r in accounts.get_payments(status="cash", search="HRTEST")["rows"]])
		self.assertNotIn(out["name"], [r.name for r in accounts.get_payments(status="waiting", search="HRTEST")["rows"]])


class TestPurchases(TestSkip):
	def order(self, rate, qty=2, days_ago=0, due_in=7):
		from frappe.utils import add_days, nowdate

		item = "HRTEST-PO-ITEM"
		if not frappe.db.exists("Item", item):
			frappe.get_doc(dict(doctype="Item", item_code=item, item_name="HRTEST PO item", item_group="All Item Groups",
			                    stock_uom="Nos", is_stock_item=0, is_purchase_item=1)).insert()
		supplier = frappe.db.get_value("Supplier", {"disabled": 0, "default_currency": ["in", ["USD", "", None]]}, "name") \
			or frappe.db.get_value("Supplier", {"disabled": 0}, "name")
		po = frappe.get_doc(dict(doctype="Purchase Order", company=company(), supplier=supplier, currency="USD",
		                         transaction_date=add_days(nowdate(), -days_ago), schedule_date=add_days(nowdate(), due_in),
		                         items=[dict(item_code=item, qty=qty, rate=rate, uom="Nos", conversion_factor=1)]))
		po.insert()
		po.submit()
		return po

	def test_open_orders_and_invoices_are_counted(self):
		from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice
		from frappe.utils import nowdate

		before = accounts.get_purchases()
		late = self.order(50, days_ago=10, due_in=-3)
		billed = self.order(100)
		pi = make_purchase_invoice(billed.name)
		pi.items[0].qty = 1  # half of it billed
		pi.posting_date, pi.set_posting_time, pi.bill_no = nowdate(), 1, "HRTEST-PO-BILL"
		pi.insert()
		pi.submit()

		after = accounts.get_purchases()
		o, o0 = after["orders"], before["orders"]
		self.assertEqual(o["open"] - o0["open"], 2)
		self.assertGreaterEqual(o["late"] - o0["late"], 1)
		per_billed = flt(frappe.db.get_value("Purchase Order", billed.name, "per_billed"))
		self.assertEqual(per_billed, 50)
		unbilled = flt(late.base_grand_total) + flt(billed.base_grand_total) / 2
		self.assertAlmostEqual(o["to_bill"] - o0["to_bill"], unbilled, places=2)
		self.assertTrue({late.name, billed.name} <= {r.name for r in after["recent_orders"]})
		month = nowdate()[:7]
		m, m0 = (next(x for x in r["months"] if x["month"] == month) for r in (after, before))
		self.assertAlmostEqual(m["invoiced"] - m0["invoiced"], flt(pi.base_net_total), places=2)
		ordered = sum(flt(p.base_net_total) for p in (late, billed) if str(p.transaction_date)[:7] == month)
		self.assertAlmostEqual(m["ordered"] - m0["ordered"], ordered, places=2)
		self.assertAlmostEqual(after["this_month"]["total"] - before["this_month"]["total"], flt(pi.base_net_total), places=2)
		self.assertIn(pi.supplier, [s.supplier for s in after["top_suppliers"]])
		self.assertEqual(accounts.get_dashboard()["purchases"], o)

	def test_a_manager_without_purchase_rights_sees_no_orders(self):
		email = "hrtest.nopo@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(dict(doctype="User", email=email, first_name="NoPO", send_welcome_email=0)).insert(ignore_permissions=True)
		frappe.get_doc("User", email).add_roles("HR Manager")
		frappe.set_user(email)
		try:
			if frappe.has_permission("Purchase Order", "read"):
				self.skipTest("HR Manager reads purchase orders on this site")
			out = accounts.get_purchases()
			self.assertFalse(out["can_orders"])
			self.assertNotIn("recent_orders", out)
			self.assertIsNone(accounts.get_dashboard()["purchases"])
		finally:
			frappe.set_user("Administrator")


class TestHealthStock(TestSkip):
	def test_hardware_stock_is_not_flagged_as_a_service(self):
		from erp_overrides.tests.test_stock_light import make_item

		if not frappe.db.exists("Item Group", "Laptops & Desktops"):
			self.skipTest("run erp_overrides.demo.seed first")
		laptop = make_item("HRTEST-HEALTH-LAPTOP", "Laptops & Desktops")
		self.assertEqual(laptop.is_stock_item, 1)
		flagged = " ".join(i["message"] for i in accounts.get_health()["issues"] if i["check"].startswith("stock_services"))
		self.assertNotIn(laptop.name, flagged)
