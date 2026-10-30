# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Backend for the /accounts PWA: the accounts team's Xero-like front door.

Bank reconciliation follows Xero's four tabs (Match, Create, Transfer, Discuss) plus
bank rules, and is built on ERPNext's own reconciliation functions — the ones the
/banking app calls — so a reconciled line is the same document either way. Where
those functions assume one currency (they post a ZWG line as if it were USD), the
entry is built here with the day's RBZ rate and then reconciled with ERPNext's
`reconcile_vouchers`.

Accounts Manager / Accounts User can post. Managers without an accounts role get
read-only Home and Dashboards.
"""
import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_first_day, get_last_day, getdate, nowdate

POST_ROLES = ("Accounts Manager", "Accounts User", "System Manager")
VIEW_ROLES = POST_ROLES + ("Sales Manager", "Purchase Manager", "HR Manager", "Auditor", "Finance Manager")

FINANCE_DOCTYPES = (
	"Bank Transaction", "Bank Transaction Rule", "Payment Entry", "Journal Entry", "Sales Invoice",
	"Purchase Invoice", "Purchase Order", "Bank Account", "Currency Exchange", "Budget",
	"Dunning", "Payment Terms Template", "Sales Taxes and Charges Template", "Purchase Taxes and Charges Template",
)
ACC_SETTINGS = "App Accounts Settings"
BRT = "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool"


# ── Who is asking ────────────────────────────────────────────────────────────

def can_post(user=None):
	return bool(set(frappe.get_roles(user)) & set(POST_ROLES))


def can_view(user=None):
	return bool(set(frappe.get_roles(user)) & set(VIEW_ROLES))


def _require_post():
	if not can_post():
		frappe.throw(_("Only the accounts team can post or reconcile."), frappe.PermissionError)


def _require_access():
	if not can_view():
		frappe.throw(_("The accounts app is for the accounts team and managers."), frappe.PermissionError)


def _company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")


def _company_currency(company=None):
	return frappe.get_cached_value("Company", company or _company(), "default_currency")


def _rate(from_currency, to_currency, date=None):
	"""Currency Exchange for the day (RBZ for USD/ZWG), falling back to the latest before it."""
	if not from_currency or from_currency == to_currency:
		return 1.0
	from erpnext.setup.utils import get_exchange_rate

	return flt(get_exchange_rate(from_currency, to_currency, date or nowdate())) or 0.0


def _setting(field, default=None):
	"""A value from App Accounts Settings (edited on the accounts Settings page)."""
	if not frappe.db.exists("DocType", ACC_SETTINGS):
		return default
	value = frappe.db.get_single_value(ACC_SETTINGS, field)
	return default if value in (None, "", 0) else value


def _attach(file_url, doctype, name):
	"""Attach a file the page uploaded (upload_file leaves it unattached), so the
	document doesn't end up with a copy beside an orphan."""
	uploaded = frappe.db.get_value("File", {"file_url": file_url, "attached_to_name": ["is", "not set"],
	                                        "owner": frappe.session.user}, "name", order_by="creation desc")
	if uploaded:
		frappe.db.set_value("File", uploaded, {"attached_to_doctype": doctype, "attached_to_name": name})
	else:
		frappe.get_doc(dict(doctype="File", file_url=file_url, attached_to_doctype=doctype, attached_to_name=name,
		                    is_private=1)).insert(ignore_permissions=True)


def _parse(value):
	return frappe.parse_json(value) if isinstance(value, str) else value


# ── Banks and statement lines ────────────────────────────────────────────────

def _bank_accounts(company=None):
	rows = frappe.get_all(
		"Bank Account",
		filters={"is_company_account": 1, "disabled": 0, "account": ["is", "set"], "company": company or _company()},
		fields=["name", "account_name", "bank", "account", "bank_account_no"], order_by="name asc")
	for r in rows:
		r.currency = frappe.get_cached_value("Account", r.account, "account_currency")
	return rows


@frappe.whitelist()
def get_banks():
	"""Each company bank account: balance per books and per statement, and what's left to reconcile."""
	_require_access()
	from erpnext.accounts.utils import get_balance_on

	today = nowdate()
	out = []
	for b in _bank_accounts():
		stats = frappe.db.sql(
			"""select count(*) n, sum(unallocated_amount * if(deposit > 0, 1, -1)) amount,
			          sum(if(matched_transaction_rule is not null and matched_transaction_rule != '', 1, 0)) rule_hits,
			          min(date) oldest
			   from `tabBank Transaction` where bank_account=%s and docstatus=1 and unallocated_amount > 0""",
			b.name, as_dict=True)[0]
		last = frappe.db.sql("select max(date) from `tabBank Transaction` where bank_account=%s and docstatus=1", b.name)[0][0]
		statement = frappe.db.get_value("Bank Account Balance", {"bank_account": b.name}, ["balance", "date"],
		                                order_by="date desc", as_dict=True)
		b.update(
			balance=flt(get_balance_on(b.account, today, in_account_currency=True, ignore_account_permission=True)),
			to_reconcile=cint(stats.n), to_reconcile_amount=flt(stats.amount), rule_hits=cint(stats.rule_hits),
			oldest=stats.oldest, last_statement_date=last,
			statement_balance=statement and flt(statement.balance), statement_date=statement and statement.date,
			reconciled=frappe.db.count("Bank Transaction", {"bank_account": b.name, "docstatus": 1, "status": "Reconciled"}),
			opening=_opening_journal(b.account),
		)
		out.append(b)
	return out


def _line_fields():
	return ["name", "date", "deposit", "withdrawal", "currency", "description", "reference_number", "bank_account",
	        "company", "party_type", "party", "allocated_amount", "unallocated_amount", "status",
	        "matched_transaction_rule", "_assign", "_comments"]


def _line_filters(bank_account, view="to_reconcile", search=None, rule_only=0, direction=None):
	filters = {"bank_account": bank_account, "docstatus": 1}
	if view == "reconciled":
		filters["status"] = "Reconciled"
	else:
		filters["unallocated_amount"] = [">", 0]
	if cint(rule_only):
		filters["matched_transaction_rule"] = ["is", "set"]
	if direction == "in":
		filters["deposit"] = [">", 0]
	elif direction == "out":
		filters["withdrawal"] = [">", 0]
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {"description": ["like", like], "reference_number": ["like", like], "party": ["like", like]}
		try:
			amount = flt(search.replace(",", ""))
			if amount:
				or_filters.update(deposit=amount, withdrawal=amount)
		except ValueError:
			pass
	return filters, or_filters


@frappe.whitelist()
def get_lines(bank_account: str, view: str = "to_reconcile", search: str | None = None, rule_only: int = 0,
              direction: str | None = None, start: int = 0, page_length: int = 50):
	"""Statement lines, newest first. view: to_reconcile | reconciled."""
	_require_access()
	filters, or_filters = _line_filters(bank_account, view, search, rule_only, direction)
	rows = frappe.get_list("Bank Transaction", filters=filters, or_filters=or_filters, fields=_line_fields(),
	                       order_by="date desc, creation desc", start=cint(start), page_length=cint(page_length))
	total = len(frappe.get_list("Bank Transaction", filters=filters, or_filters=or_filters, pluck="name", limit=10000))
	rules = {r.name: r for r in frappe.get_all("Bank Transaction Rule", fields=["name", "classify_as", "account", "party_type", "party"])}
	for r in rows:
		# Frappe leaves _comments / _assign out when the table doesn't have the column yet
		# (it is added on the first comment or assignment on any Bank Transaction)
		r.comments = len(json.loads(r.pop("_comments", None) or "[]"))
		r.assigned = json.loads(r.pop("_assign", None) or "[]")
		r.rule = rules.get(r.matched_transaction_rule)
	return dict(rows=rows, total=total)


@frappe.whitelist()
def get_rule_line_names(bank_account: str, search: str | None = None, direction: str | None = None):
	"""Every rule-matched line still to reconcile under the list's filters, oldest first,
	so OK can post them all and not just the page that is loaded."""
	_require_access()
	filters, or_filters = _line_filters(bank_account, "to_reconcile", search, 1, direction)
	return frappe.get_list("Bank Transaction", filters=filters, or_filters=or_filters, pluck="name",
	                       order_by="date asc, creation asc", limit=10000)


@frappe.whitelist()
def get_line(name: str):
	"""One statement line with everything the four tabs need."""
	_require_access()
	line = frappe.get_doc("Bank Transaction", name)
	line.check_permission("read")
	gl_account = frappe.get_cached_value("Bank Account", line.bank_account, "account")
	out = frappe._dict({f: line.get(f) for f in _line_fields() if not f.startswith("_")})
	out.gl_account = gl_account
	out.account_currency = frappe.get_cached_value("Account", gl_account, "account_currency")
	out.company_currency = _company_currency(line.company)
	out.rate = _rate(out.account_currency, out.company_currency, line.date)
	out.amount = flt(line.deposit or line.withdrawal)
	out.direction = "in" if flt(line.deposit) else "out"
	out.vouchers = [dict(doctype=p.payment_document, name=p.payment_entry, amount=flt(p.allocated_amount))
	                for p in line.payment_entries]
	out.rule = line.matched_transaction_rule and _rule_dict(frappe.get_doc("Bank Transaction Rule", line.matched_transaction_rule))
	out.suggestions = _suggestions(line) if flt(line.unallocated_amount) > 0 else []
	out.invoices = _invoice_suggestions(line, out) if flt(line.unallocated_amount) > 0 else []
	out.transfer_candidates = _transfer_candidates(line) if flt(line.unallocated_amount) > 0 else []
	# what one unit of this account's currency buys in each of our banks' currencies that day (for transfers)
	out.rates = {c: _rate(out.account_currency, c, line.date)
	             for c in {b.currency for b in _bank_accounts(line.company)} if c != out.account_currency}
	out.comments = frappe.get_all("Comment", filters={"reference_doctype": "Bank Transaction", "reference_name": name,
	                                                  "comment_type": "Comment"},
	                              fields=["name", "content", "owner", "creation"], order_by="creation asc")
	for c in out.comments:
		c.by = frappe.utils.get_fullname(c.owner)
	return out


def _suggestions(line):
	"""ERPNext's own matcher: payments and journals not yet cleared, ranked by
	reference, amount and party agreeing (rank 4 = all three)."""
	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import get_linked_payments

	try:
		rows = get_linked_payments(line.name, ["payment_entry", "journal_entry"],
		                           from_date=add_days(line.date, -60), to_date=add_days(line.date, 30))
	except Exception:
		frappe.clear_messages()
		return []
	out = []
	for r in rows[:20]:
		amount = flt(r.get("paid_amount"))
		out.append(dict(
			doctype=r.get("doctype"), name=r.get("name"), amount=amount, date=r.get("posting_date") or r.get("reference_date"),
			reference=r.get("reference_no"), party=r.get("party"), party_type=r.get("party_type"),
			currency=r.get("currency"), rank=cint(r.get("rank")),
			exact=abs(amount - flt(line.unallocated_amount)) < 0.005,
		))
	return out


def _invoice_suggestions(line, info):
	"""Open invoices of the same amount (Xero's "match to invoice"): a deposit pays a
	Sales Invoice, a withdrawal a Purchase Invoice. Paying it creates the Payment Entry."""
	doctype = "Sales Invoice" if info.direction == "in" else "Purchase Invoice"
	party_field = "customer" if doctype == "Sales Invoice" else "supplier"
	amount = flt(line.unallocated_amount)
	rows = frappe.get_list(
		doctype, filters={"docstatus": 1, "outstanding_amount": [">", 0], "company": line.company},
		fields=["name", party_field + " as party", "posting_date", "due_date", "grand_total", "outstanding_amount", "currency"],
		order_by="posting_date desc", limit=200)
	for r in rows:
		r.doctype = doctype
		r.exact = abs(flt(r.outstanding_amount) - amount) < 0.005 and r.currency == info.account_currency
		r.party_match = bool(line.party and line.party == r.party)
	rows.sort(key=lambda r: (not r.exact, not r.party_match, -(getdate(r.posting_date).toordinal())))
	return rows[:15]


def _transfer_candidates(line):
	"""Lines in the company's other bank accounts that look like the other side: the
	opposite direction, within five days, same amount when the currency is the same."""
	other = [b for b in _bank_accounts(line.company) if b.name != line.bank_account]
	if not other:
		return []
	my_currency = frappe.get_cached_value("Account", frappe.get_cached_value("Bank Account", line.bank_account, "account"),
	                                      "account_currency")
	field = "deposit" if flt(line.withdrawal) else "withdrawal"
	amount = flt(line.withdrawal or line.deposit)
	rows = frappe.get_all(
		"Bank Transaction",
		filters={"bank_account": ["in", [b.name for b in other]], "docstatus": 1, "unallocated_amount": [">", 0],
		         field: [">", 0], "date": ["between", [add_days(line.date, -5), add_days(line.date, 5)]]},
		fields=["name", "bank_account", "date", "deposit", "withdrawal", "description", "currency"], limit=50)
	out = []
	for r in rows:
		r.amount = flt(r[field])
		if r.currency == my_currency:
			r.exact = abs(r.amount - amount) <= 0.005
		else:
			# a USD↔ZWG transfer: the other side should be worth the same at the day's rate, give or take
			# the tolerance in App Accounts Settings (3%)
			expected = amount * _rate(my_currency, r.currency, line.date)
			r.exact = False
			if not expected or abs(r.amount - expected) > flt(_setting("transfer_tolerance", 3)) / 100 * expected:
				continue
		if r.currency == my_currency and not r.exact:
			continue
		out.append(r)
	return out[:10]


# ── The four tabs ────────────────────────────────────────────────────────────

def _reconcile(line_name, doctype, name, amount):
	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import reconcile_vouchers

	return reconcile_vouchers(line_name, json.dumps([{"payment_doctype": doctype, "payment_name": name, "amount": flt(amount)}]),
	                          is_new_voucher=True)


@frappe.whitelist(methods=["POST"])
def match(name: str, vouchers: list | str):
	"""Match: clear existing payments/journals against the line (ERPNext's reconcile_vouchers)."""
	_require_post()
	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import reconcile_vouchers

	vouchers = _parse(vouchers)
	reconcile_vouchers(name, json.dumps([
		{"payment_doctype": v["doctype"], "payment_name": v["name"], "amount": flt(v["amount"])} for v in vouchers]))
	return _status(name)


def _status(name):
	return frappe.db.get_value("Bank Transaction", name, ["name", "status", "unallocated_amount", "allocated_amount"], as_dict=True)


@frappe.whitelist(methods=["POST"])
def pay_invoice(name: str, doctype: str, invoice: str):
	"""Match to an open invoice: a Payment Entry against it for the line's amount, then reconcile."""
	_require_post()
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	if doctype not in ("Sales Invoice", "Purchase Invoice"):
		frappe.throw(_("Only invoices can be paid from a bank line."))
	line = frappe.get_doc("Bank Transaction", name)
	gl_account = frappe.get_cached_value("Bank Account", line.bank_account, "account")
	amount = flt(line.unallocated_amount)
	pe = get_payment_entry(doctype, invoice, bank_account=gl_account, reference_date=line.date)
	pe.bank_account = line.bank_account
	pe.posting_date = line.date
	pe.reference_date = line.date
	pe.reference_no = (line.reference_number or line.description or line.name)[:140]
	_set_payment_amount(pe, amount)
	pe.insert()
	pe.submit()
	_reconcile(name, "Payment Entry", pe.name, amount)
	return dict(payment_entry=pe.name, **_status(name))


def _set_payment_amount(pe, bank_amount):
	"""Set the amount the bank actually moved, in the bank account's currency, and
	allocate it to the invoice (or less, for a part-payment)."""
	if pe.payment_type == "Receive":
		pe.received_amount = bank_amount
		pe.paid_amount = flt(bank_amount * flt(pe.target_exchange_rate) / flt(pe.source_exchange_rate or 1), 2) \
			if pe.paid_from_account_currency != pe.paid_to_account_currency else bank_amount
		party_amount = pe.paid_amount
	else:
		pe.paid_amount = bank_amount
		pe.received_amount = flt(bank_amount * flt(pe.source_exchange_rate) / flt(pe.target_exchange_rate or 1), 2) \
			if pe.paid_from_account_currency != pe.paid_to_account_currency else bank_amount
		party_amount = pe.received_amount
	for ref in pe.references:
		ref.allocated_amount = min(flt(ref.outstanding_amount), party_amount)
		party_amount -= ref.allocated_amount
	pe.set_amounts()


@frappe.whitelist(methods=["POST"])
def create(name: str, account: str | None = None, party_type: str | None = None, party: str | None = None,
           remark: str | None = None, vat_template: str | None = None):
	"""Create (Xero's who / what / why). With a party: a Payment Entry on account for
	them. Without: a bank Journal Entry to `account`, optionally split out VAT.
	Built here so a ZWG line is converted at the day's rate, then reconciled."""
	_require_post()
	line = frappe.get_doc("Bank Transaction", name)
	if flt(line.unallocated_amount) <= 0:
		frappe.throw(_("This line is already reconciled."))
	if party:
		doc = _payment_for_party(line, party_type or ("Customer" if flt(line.deposit) else "Supplier"), party, remark)
	else:
		if not account:
			frappe.throw(_("Pick the account this goes to (What)."))
		doc = _bank_journal(line, [dict(account=account, amount=flt(line.unallocated_amount), remark=remark)], remark, vat_template)
	_reconcile(name, doc.doctype, doc.name, line.unallocated_amount)
	return dict(voucher_type=doc.doctype, voucher=doc.name, **_status(name))


def _bank_journal(line, splits, remark=None, vat_template=None, submit=True):
	"""A Bank Entry for the line: the bank row in the bank account's currency, the
	other rows in theirs, both valued at the day's rate. A petty cash pseudo-line
	carries its cash `account` and `voucher_type` "Cash Entry" instead."""
	company = line.company
	company_currency = _company_currency(company)
	gl_account = line.get("account") or frappe.get_cached_value("Bank Account", line.bank_account, "account")
	bank_currency = frappe.get_cached_value("Account", gl_account, "account_currency")
	bank_rate = _rate(bank_currency, company_currency, line.date)
	if not bank_rate:
		frappe.throw(_("No {0} to {1} rate for {2}. Fetch the RBZ rate first (Rates).").format(
			bank_currency, company_currency, line.date))
	is_out = flt(line.withdrawal) > 0
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	total = sum(flt(s["amount"]) for s in splits)
	je = frappe.new_doc("Journal Entry")
	je.update(dict(voucher_type=line.get("voucher_type") or "Bank Entry", company=company, posting_date=line.date,
	               cheque_date=line.date, cheque_no=(line.reference_number or line.description or line.name)[:140],
	               user_remark=remark or line.description, pay_to_recd_from=line.get("pay_to"), multi_currency=1))
	je.flags.ignore_permissions = bool(line.get("ignore_permissions"))
	je.append("accounts", {
		"account": gl_account, "bank_account": line.get("bank_account"), "exchange_rate": bank_rate,
		("credit_in_account_currency" if is_out else "debit_in_account_currency"): total,
	})

	vat_rows = []
	if vat_template:
		# the amount is VAT-inclusive: split out the tax at the template's rates
		taxes = frappe.get_all("Purchase Taxes and Charges" if is_out else "Sales Taxes and Charges",
		                       filters={"parent": vat_template}, fields=["account_head", "rate"])
		rate_total = sum(flt(t.rate) for t in taxes)
		if rate_total:
			for s in splits:
				net = flt(flt(s["amount"]) / (1 + rate_total / 100), 2)
				for t in taxes:
					vat_rows.append(dict(account=t.account_head, amount=flt(net * flt(t.rate) / 100, 2), remark="VAT"))
				s["amount"] = flt(s["amount"]) - sum(v["amount"] for v in vat_rows[-len(taxes):])

	rows = splits + vat_rows
	bases = [flt(flt(s["amount"]) * bank_rate, 2) for s in rows]
	# rounding each row on its own can leave the entry 0.01 off the bank row; the first row
	# in the company currency takes the difference
	diff = flt(flt(total * bank_rate, 2) - sum(bases), 2)
	if diff:
		for i, s in enumerate(rows):
			if frappe.get_cached_value("Account", s["account"], "account_currency") == company_currency:
				bases[i] = flt(bases[i] + diff, 2)
				break
	for s, base in zip(rows, bases):
		acc_currency = frappe.get_cached_value("Account", s["account"], "account_currency")
		acc_rate = _rate(acc_currency, company_currency, line.date) if acc_currency != company_currency else 1
		if not acc_rate:
			frappe.throw(_("No {0} to {1} rate for {2}. Fetch the RBZ rate first (Rates).").format(
				acc_currency, company_currency, line.date))
		amount = flt(base / acc_rate, 2) if acc_currency != company_currency else base
		row = {"account": s["account"], "exchange_rate": acc_rate, "user_remark": s.get("remark"),
		       ("debit_in_account_currency" if is_out else "credit_in_account_currency"): amount}
		if frappe.get_cached_value("Account", s["account"], "report_type") == "Profit and Loss":
			row["cost_center"] = cost_center
		if s.get("party"):
			row.update(party_type=s["party_type"], party=s["party"])
		je.append("accounts", row)
	je.insert()
	if submit:
		je.submit()
	return je


def _payment_for_party(line, party_type, party, remark=None, invoices=None):
	"""A Payment Entry for the party, from or to this bank: allocated to `invoices`
	(oldest first) when given, the rest on account."""
	from erpnext.accounts.party import get_party_account

	company = line.company
	company_currency = _company_currency(company)
	gl_account = frappe.get_cached_value("Bank Account", line.bank_account, "account")
	bank_currency = frappe.get_cached_value("Account", gl_account, "account_currency")
	party_account = get_party_account(party_type, party, company)
	party_currency = frappe.get_cached_value("Account", party_account, "account_currency")
	is_out = flt(line.withdrawal) > 0
	amount = flt(line.unallocated_amount)
	bank_rate = _rate(bank_currency, company_currency, line.date)
	party_rate = _rate(party_currency, company_currency, line.date)
	if not bank_rate or not party_rate:
		frappe.throw(_("No exchange rate for {0}. Fetch the RBZ rate first (Rates).").format(line.date))
	party_amount = flt(amount * bank_rate / party_rate, 2) if bank_currency != party_currency else amount
	pe = frappe.new_doc("Payment Entry")
	pe.update(dict(
		payment_type="Pay" if is_out else "Receive", company=company, posting_date=line.date, reference_date=line.date,
		reference_no=(line.reference_number or line.description or line.name)[:140], bank_account=line.bank_account,
		party_type=party_type, party=party,
		paid_from=gl_account if is_out else party_account, paid_to=party_account if is_out else gl_account,
		paid_from_account_currency=bank_currency if is_out else party_currency,
		paid_to_account_currency=party_currency if is_out else bank_currency,
		paid_amount=amount if is_out else party_amount, received_amount=party_amount if is_out else amount,
		source_exchange_rate=bank_rate if is_out else party_rate, target_exchange_rate=party_rate if is_out else bank_rate,
		remarks=remark or line.description,
	))
	inv_doctype = "Purchase Invoice" if party_type == "Supplier" else "Sales Invoice"
	party_field = "supplier" if party_type == "Supplier" else "customer"
	left = party_amount
	for inv in sorted(invoices or [], key=lambda n: frappe.db.get_value(inv_doctype, n, "due_date") or getdate()):
		row = frappe.db.get_value(inv_doctype, inv, ["docstatus", party_field, "outstanding_amount"], as_dict=True)
		if not row or row.docstatus != 1 or row[party_field] != party:
			frappe.throw(_("{0} is not an open bill of {1}.").format(inv, party))
		allocated = min(flt(row.outstanding_amount), left)
		if allocated <= 0:
			continue
		pe.append("references", dict(reference_doctype=inv_doctype, reference_name=inv, allocated_amount=allocated))
		left -= allocated
	pe.setup_party_account_field()
	pe.set_missing_values()
	pe.set_amounts()
	pe.insert()
	pe.submit()
	return pe


@frappe.whitelist(methods=["POST"])
def transfer(name: str, other_bank_account: str, other_line: str | None = None, other_amount: float | None = None):
	"""Transfer between two of our bank accounts: an Internal Transfer Payment Entry.
	The other side's statement line, when given, is reconciled with the same entry."""
	_require_post()
	line = frappe.get_doc("Bank Transaction", name)
	company = line.company
	company_currency = _company_currency(company)
	mine = frappe.get_cached_value("Bank Account", line.bank_account, "account")
	theirs = frappe.get_cached_value("Bank Account", other_bank_account, "account")
	my_currency = frappe.get_cached_value("Account", mine, "account_currency")
	their_currency = frappe.get_cached_value("Account", theirs, "account_currency")
	amount = flt(line.unallocated_amount)
	if other_line:
		other = frappe.get_doc("Bank Transaction", other_line)
		other_amount = flt(other.unallocated_amount)
	if my_currency == their_currency:
		other_amount = amount
	elif not flt(other_amount):
		other_amount = flt(amount * _rate(my_currency, their_currency, line.date), 2)
	if not flt(other_amount):
		# no rate for the day: without this the exchange rate below divides by zero (a bare 500)
		frappe.throw(_("No {0} to {1} rate for {2}. Fetch the RBZ rate first (Rates), or pick the other bank's statement line.").format(
			my_currency, their_currency, line.date))
	is_out = flt(line.withdrawal) > 0
	pe = frappe.new_doc("Payment Entry")
	pe.update(dict(
		payment_type="Internal Transfer", company=company, posting_date=line.date, reference_date=line.date,
		reference_no=(line.reference_number or line.description or line.name)[:140],
		paid_from=mine if is_out else theirs, paid_to=theirs if is_out else mine,
		paid_amount=amount if is_out else flt(other_amount), received_amount=flt(other_amount) if is_out else amount,
	))
	from_currency = my_currency if is_out else their_currency
	to_currency = their_currency if is_out else my_currency
	pe.source_exchange_rate = _rate(from_currency, company_currency, line.date)
	if not pe.source_exchange_rate:
		frappe.throw(_("No {0} to {1} rate for {2}. Fetch the RBZ rate first (Rates).").format(
			from_currency, company_currency, line.date))
	pe.target_exchange_rate = flt(pe.paid_amount * pe.source_exchange_rate / pe.received_amount, 9) \
		if from_currency != to_currency else pe.source_exchange_rate
	pe.set_missing_values()
	pe.set_amounts()
	pe.insert()
	pe.submit()
	_reconcile(name, "Payment Entry", pe.name, amount)
	if other_line:
		_reconcile(other_line, "Payment Entry", pe.name, other_amount)
	return dict(payment_entry=pe.name, **_status(name))


@frappe.whitelist(methods=["POST"])
def discuss(name: str, text: str, assign_to: str | None = None):
	"""Discuss: a comment on the line, optionally handed to a colleague (a ToDo)."""
	_require_post()
	doc = frappe.get_doc("Bank Transaction", name)
	doc.add_comment("Comment", frappe.utils.escape_html(text))
	if assign_to:
		from frappe.desk.form.assign_to import add

		add({"assign_to": [assign_to], "doctype": "Bank Transaction", "name": name, "description": text})
	return get_line(name).comments


@frappe.whitelist(methods=["POST"])
def unreconcile(name: str):
	"""Undo: the line goes back to the list; entries created for it are cancelled."""
	_require_post()
	from erpnext.accounts.doctype.bank_transaction.bank_transaction import unreconcile_transaction

	unreconcile_transaction(name)
	return _status(name)


# ── Bank rules ───────────────────────────────────────────────────────────────

def _rule_dict(rule):
	return dict(
		name=rule.name, rule_name=rule.rule_name, transaction_type=rule.transaction_type, min_amount=rule.min_amount,
		max_amount=rule.max_amount, classify_as=rule.classify_as, account=rule.account, party_type=rule.party_type,
		party=rule.party, priority=rule.priority, description=rule.rule_description, bank_entry_type=rule.bank_entry_type,
		conditions=[dict(check=d.check, value=d.value) for d in rule.description_rules],
	)


@frappe.whitelist()
def get_rules():
	_require_access()
	hits = dict(frappe.db.sql(
		"""select matched_transaction_rule, count(*) from `tabBank Transaction`
		   where docstatus=1 and unallocated_amount > 0 and matched_transaction_rule is not null group by matched_transaction_rule"""))
	rules = [_rule_dict(frappe.get_doc("Bank Transaction Rule", n))
	         for n in frappe.get_all("Bank Transaction Rule", order_by="priority asc, rule_name asc", pluck="name")]
	for r in rules:
		r["hits"] = hits.get(r["name"], 0)
	return rules


def _rule_doc(rule):
	rule = _parse(rule)
	doc = frappe.get_doc("Bank Transaction Rule", rule["name"]) if rule.get("name") else frappe.new_doc("Bank Transaction Rule")
	doc.update({k: rule.get(k) for k in ("rule_name", "transaction_type", "min_amount", "max_amount", "classify_as",
	                                     "account", "party_type", "party", "priority") if k in rule})
	doc.company = doc.company or _company()
	doc.bank_entry_type = "Single Account"
	doc.rule_description = rule.get("description")
	doc.set("description_rules", [dict(check=c.get("check") or "Contains", value=c.get("value"))
	                              for c in rule.get("conditions") or [] if c.get("value")])
	return doc


@frappe.whitelist(methods=["POST"])
def preview_rule(rule: dict | str):
	"""How many lines still to reconcile this rule would catch, and a few of them."""
	_require_access()
	doc = _rule_doc(rule)
	lines = frappe.get_all("Bank Transaction", filters={"docstatus": 1, "unallocated_amount": [">", 0], "company": doc.company},
	                       fields=["name", "bank_account", "company", "date", "withdrawal", "deposit", "description",
	                               "reference_number", "currency"], limit=5000)
	caught = [line for line in lines if doc.evaluate_rule(line)]
	return dict(count=len(caught), sample=caught[:8])


@frappe.whitelist(methods=["POST"])
def save_rule(rule: dict | str):
	_require_post()
	doc = _rule_doc(rule)
	if not doc.description_rules and not (doc.min_amount or doc.max_amount):
		frappe.throw(_("Give the rule at least one description condition or an amount range."))
	doc.save()
	run_rules()
	return _rule_dict(doc)


@frappe.whitelist(methods=["POST"])
def delete_rule(name: str):
	_require_post()
	frappe.db.set_value("Bank Transaction", {"matched_transaction_rule": name, "unallocated_amount": [">", 0]},
	                    "matched_transaction_rule", None)
	frappe.delete_doc("Bank Transaction Rule", name)
	return get_rules()


@frappe.whitelist(methods=["POST"])
def run_rules():
	"""Re-tag every line still to reconcile with the first rule (by priority) it matches."""
	_require_post()
	from erpnext.accounts.doctype.bank_transaction_rule.bank_transaction_rule import _run_rule_evaluation

	frappe.db.sql("""update `tabBank Transaction` set matched_transaction_rule=null
	                 where docstatus=1 and unallocated_amount > 0""")
	_run_rule_evaluation(force_evaluate=True)
	return frappe.db.count("Bank Transaction", {"docstatus": 1, "unallocated_amount": [">", 0],
	                                            "matched_transaction_rule": ["is", "set"]})


@frappe.whitelist(methods=["POST"])
def apply_rule(names: list | str):
	"""OK on rule matches: each line gets the entry its rule describes, then is reconciled.
	One failure doesn't stop the rest; its reason comes back."""
	_require_post()
	names = _parse(names)
	if isinstance(names, str):
		names = [names]
	done, failed = [], []
	for name in names:
		frappe.db.savepoint("apply_rule")
		try:
			line = frappe.get_doc("Bank Transaction", name)
			if not line.matched_transaction_rule:
				frappe.throw(_("No rule matches this line."))
			rule = frappe.get_doc("Bank Transaction Rule", line.matched_transaction_rule)
			if rule.classify_as == "Payment Entry":
				doc = _payment_for_party(line, rule.party_type, rule.party, rule.rule_name)
			elif rule.classify_as == "Transfer":
				bank = frappe.db.get_value("Bank Account", {"account": rule.account, "is_company_account": 1}, "name")
				if not bank:
					frappe.throw(_("Rule {0}: {1} is not one of our bank accounts.").format(rule.rule_name, rule.account))
				done.append(dict(name=name, voucher=transfer(name, bank)["payment_entry"]))
				continue
			else:
				if rule.bank_entry_type == "Multiple Accounts" or not rule.account:
					frappe.throw(_("Rule {0} splits across several accounts; use Create.").format(rule.rule_name))
				doc = _bank_journal(line, [dict(account=rule.account, amount=flt(line.unallocated_amount),
				                                party_type=rule.party_type if rule.party else None, party=rule.party,
				                                remark=rule.rule_name)], line.description)
			_reconcile(name, doc.doctype, doc.name, line.unallocated_amount)
			done.append(dict(name=name, voucher=doc.name))
		except Exception as e:
			frappe.db.rollback(save_point="apply_rule")
			frappe.clear_messages()
			failed.append(dict(name=name, error=str(e)))
	return dict(done=done, failed=failed)


# ── Statement upload ─────────────────────────────────────────────────────────

MAPPABLE = ("Do not import", "Date", "Withdrawal", "Deposit", "Amount", "Description", "Reference", "Transaction Type",
            "Debit/Credit", "Balance")


def _line_key(date, deposit, withdrawal, description):
	"""Same day, same amounts, same words. The reference is left out: CSV exports
	often drop the column that a PDF or the bank's own feed carried."""
	desc = re.sub(r"\s+", " ", (description or "")).strip().upper()[:140]
	return (str(getdate(date)), round(flt(deposit), 2), round(flt(withdrawal), 2), desc)


def _preview(log_name):
	from erpnext.accounts.doctype.bank_statement_import_log.bank_statement_import_log import get_statement_details

	details = get_statement_details(log_name)
	doc = details["doc"]
	final = details["final_transactions"]
	existing = {
		_line_key(t.date, t.deposit, t.withdrawal, t.description)
		for t in frappe.get_all("Bank Transaction", filters={
			"bank_account": doc.bank_account, "docstatus": 1,
			"date": ["between", [doc.start_date or "1900-01-01", doc.end_date or "2999-12-31"]]},
			fields=["date", "deposit", "withdrawal", "description", "reference_number"])
	}
	rows = []
	for t in final:
		key = _line_key(t.get("date"), t.get("deposit"), t.get("withdrawal"), t.get("description"))
		rows.append(dict(date=t.get("date"), deposit=flt(t.get("deposit")), withdrawal=flt(t.get("withdrawal")),
		                 description=t.get("description"), reference=t.get("reference"), duplicate=key in existing))
	return dict(
		name=doc.name, bank_account=doc.bank_account, currency=doc.currency, status=doc.status, is_pdf=doc.is_pdf(),
		start_date=doc.start_date, end_date=doc.end_date, closing_balance=doc.closing_balance,
		date_format=details["date_format"], header_index=doc.detected_header_index,
		columns=[dict(index=c.index, header=c.header_text, maps_to=c.maps_to) for c in doc.column_mapping],
		raw=(details.get("raw_data") or [])[:12], options=MAPPABLE,
		rows=rows, new=sum(1 for r in rows if not r["duplicate"]), duplicates=sum(1 for r in rows if r["duplicate"]),
	)


@frappe.whitelist(methods=["POST"])
def start_import(bank_account: str, file_url: str):
	"""Read an uploaded statement (CSV, XLS, XLSX or PDF): ERPNext detects the header
	row and columns; the preview marks lines already imported."""
	_require_post()
	log = frappe.get_doc(dict(doctype="Bank Statement Import Log", bank_account=bank_account, file=file_url))
	log.insert()
	return _preview(log.name)


@frappe.whitelist(methods=["POST"])
def map_columns(name: str, columns: list | str):
	_require_post()
	from erpnext.accounts.doctype.bank_statement_import_log.bank_statement_import_log import update_column_mapping

	columns = _parse(columns)
	update_column_mapping(name, [dict(index=c["index"], header_text=c.get("header"), maps_to=c["maps_to"]) for c in columns])
	return _preview(name)


@frappe.whitelist(methods=["POST"])
def set_header_row(name: str, header_index: int):
	_require_post()
	from erpnext.accounts.doctype.bank_statement_import_log.bank_statement_import_log import set_header_index

	set_header_index(name, cint(header_index))
	return _preview(name)


@frappe.whitelist(methods=["POST"])
def import_statement(name: str):
	"""Import the new lines only — a statement uploaded twice, or overlapping the last
	one, doesn't double up (ERPNext's own import would). Rules run afterwards."""
	_require_post()
	from erpnext.accounts.doctype.bank_account.bank_account import set_closing_balance_as_per_statement
	from erpnext.accounts.doctype.bank_transaction_rule.bank_transaction_rule import _run_rule_evaluation

	log = frappe.get_doc("Bank Statement Import Log", name)
	if log.status == "Completed":
		frappe.throw(_("This statement has already been imported."))
	preview = _preview(name)
	company, account = frappe.get_value("Bank Account", log.bank_account, ["company", "account"])
	currency = frappe.get_cached_value("Account", account, "account_currency")
	created = 0
	for r in preview["rows"]:
		if r["duplicate"]:
			continue
		frappe.get_doc(dict(
			doctype="Bank Transaction", date=r["date"], status="Unreconciled", bank_account=log.bank_account,
			withdrawal=r["withdrawal"], deposit=r["deposit"], description=r["description"],
			reference_number=r["reference"], currency=currency, company=company,
		)).insert().submit()
		created += 1
	if log.closing_balance is not None and log.end_date:
		set_closing_balance_as_per_statement(log.bank_account, getdate(log.end_date), log.closing_balance)
	_run_rule_evaluation()
	log.db_set("status", "Completed")
	return dict(created=created, skipped=preview["duplicates"])


@frappe.whitelist(methods=["POST"])
def set_statement_balance(bank_account: str, date: str, balance: float):
	_require_post()
	from erpnext.accounts.doctype.bank_account.bank_account import set_closing_balance_as_per_statement

	set_closing_balance_as_per_statement(bank_account, getdate(date), flt(balance))
	return get_banks()


TEMP_OPENING = "Temporary Opening"


def temporary_opening_account(currency, company=None):
	"""The company's "Temporary Opening…" account (type Temporary) in the bank's currency: the other
	side of a bank's opening balance, cleared once opening debtors and creditors are in."""
	return frappe.db.get_value("Account", {"company": company or _company(), "account_type": "Temporary", "is_group": 0,
	                                       "account_currency": currency, "account_name": ["like", f"{TEMP_OPENING}%"]}, "name")


def _opening_journal(account):
	r = frappe.db.sql(
		"""select je.name from `tabJournal Entry` je join `tabJournal Entry Account` a on a.parent = je.name
		   where je.docstatus = 1 and je.is_opening = 'Yes' and a.account = %s limit 1""", account)
	return r[0][0] if r else None


@frappe.whitelist(methods=["POST"])
def set_opening_balance(bank_account: str, date: str, amount: float):
	"""The bank's balance on the go-live date, as on the statement: an opening journal
	against Temporary Opening in the bank's currency."""
	_require_post()
	amount = flt(amount)
	if not amount:
		frappe.throw(_("Enter the balance on the statement."))
	bank = frappe.db.get_value("Bank Account", bank_account, ["account", "company"], as_dict=True)
	if not bank or not bank.account:
		frappe.throw(_("{0} has no ledger account.").format(bank_account))
	currency = frappe.get_cached_value("Account", bank.account, "account_currency")
	temp = temporary_opening_account(currency, bank.company)
	if not temp:
		frappe.throw(_("There is no Temporary Opening account in {0}. Add one to the chart of accounts (account type Temporary, currency {0}).").format(currency))
	existing = _opening_journal(bank.account)
	if existing:
		frappe.throw(_("{0} already has an opening balance ({1}). Cancel that journal first to change it.")
		             .format(bank_account, existing))
	company_currency = _company_currency(bank.company)
	rate = 1 if currency == company_currency else _rate(currency, company_currency, date)
	if not rate:
		frappe.throw(_("No exchange rate for {0}. Fetch the RBZ rate first (Rates).").format(date))
	debit, credit = (amount, 0) if amount > 0 else (0, -amount)
	je = frappe.new_doc("Journal Entry")
	je.update(dict(voucher_type="Opening Entry", is_opening="Yes", company=bank.company, posting_date=date,
	               multi_currency=1 if currency != company_currency else 0,
	               user_remark=_("Opening balance of {0} as on the statement").format(bank_account)))
	for account, dr, cr in ((bank.account, debit, credit), (temp, credit, debit)):
		je.append("accounts", dict(account=account, exchange_rate=rate,
		                           debit_in_account_currency=dr, credit_in_account_currency=cr))
	je.insert()
	je.submit()
	return je.name


# ── Receivables and payables ─────────────────────────────────────────────────

BUCKETS = ((0, "Not due"), (30, "1–30"), (60, "31–60"), (90, "61–90"), (10**6, "90+"))


def _bucket(due_date, today):
	days = (getdate(today) - getdate(due_date or today)).days
	if days <= 0:
		return "Not due"
	for limit, label in BUCKETS[1:]:
		if days <= limit:
			return label
	return "90+"


@frappe.whitelist()
def get_ageing(party_type: str = "Customer"):
	"""Who owes us (Customer) or whom we owe (Supplier): outstanding invoices per
	party in ageing buckets by due date, per currency."""
	_require_access()
	doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
	party_field = "customer" if party_type == "Customer" else "supplier"
	today = nowdate()
	invoices = frappe.get_list(
		doctype, filters={"docstatus": 1, "outstanding_amount": [">", 0], "company": _company()},
		fields=["name", party_field + " as party", party_field + "_name as party_name", "due_date", "posting_date",
		        "outstanding_amount", "currency", "conversion_rate"], limit_page_length=0)
	parties, totals = {}, {}
	for inv in invoices:
		b = _bucket(inv.due_date, today)
		key = (inv.party, inv.currency)
		p = parties.setdefault(key, dict(party=inv.party, party_name=inv.party_name or inv.party, currency=inv.currency,
		                                 total=0, invoices=0, oldest_due=inv.due_date, **{lbl: 0 for _, lbl in BUCKETS}))
		p[b] += flt(inv.outstanding_amount)
		p["total"] += flt(inv.outstanding_amount)
		p["invoices"] += 1
		p["oldest_due"] = min(getdate(p["oldest_due"]), getdate(inv.due_date or today))
		t = totals.setdefault(inv.currency, {lbl: 0 for _, lbl in BUCKETS} | {"total": 0})
		t[b] += flt(inv.outstanding_amount)
		t["total"] += flt(inv.outstanding_amount)
	rows = sorted(parties.values(), key=lambda p: -p["total"])
	return dict(rows=rows, totals=totals, buckets=[lbl for _, lbl in BUCKETS], doctype=doctype)


@frappe.whitelist()
def get_open_invoices(party_type: str, party: str):
	_require_access()
	doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
	party_field = "customer" if party_type == "Customer" else "supplier"
	rows = frappe.get_list(doctype, filters={"docstatus": 1, "outstanding_amount": [">", 0], party_field: party},
	                       fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount", "currency",
	                               "bill_no" if doctype == "Purchase Invoice" else "po_no"],
	                       order_by="due_date asc")
	for r in rows:
		r.bucket = _bucket(r.due_date, nowdate())
		r.doctype = doctype
		if doctype == "Purchase Invoice":
			r.match = _match(r.name)
	return rows


# ── Three-way match and bills from purchase orders ───────────────────────────

def _match(invoice):
	"""The badge for a supplier's bill: status, label, message, and whether it may be paid."""
	from erp_overrides.three_way import OK, match_status

	m = match_status(invoice)
	return dict(status=m["status"], label=m["label"], message=m["message"], payable=m["status"] in OK)


@frappe.whitelist()
def get_match(invoice: str):
	"""The three-way match of one bill, line by line, for its page."""
	_require_access()
	from erp_overrides.three_way import OK, match_status

	frappe.get_doc("Purchase Invoice", invoice).check_permission("read")
	m = match_status(invoice)
	return dict(m, payable=m["status"] in OK)


@frappe.whitelist()
def get_orders_to_bill():
	"""Open purchase orders with something received but not yet billed: what Accounts bills next."""
	_require_post()
	rows = frappe.db.sql(
		"""select po.name, po.supplier, po.supplier_name, po.transaction_date, po.currency, po.grand_total,
		          po.per_received, po.per_billed,
		          sum(greatest(i.received_qty * i.rate - i.billed_amt, 0)) to_bill
		   from `tabPurchase Order` po join `tabPurchase Order Item` i on i.parent = po.name
		   where po.docstatus = 1 and po.company = %s and po.status not in ('Completed', 'Closed', 'Cancelled', 'On Hold')
		   group by po.name having to_bill > 0.005
		   order by po.transaction_date asc""", _company(), as_dict=True)
	waiting = frappe.db.count("Purchase Order", {"docstatus": 1, "company": _company(), "per_received": 0,
	                                            "status": ["not in", ["Completed", "Closed", "Cancelled", "On Hold"]]})
	return dict(rows=rows, waiting=waiting)


@frappe.whitelist(methods=["POST"])
def bill_order(purchase_order: str):
	"""A draft Purchase Invoice for what has been received on the order and not yet billed.
	Accounts adds the supplier's invoice number, date and attachment, then submits."""
	_require_post()
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice

	frappe.get_doc("Purchase Order", purchase_order).check_permission("read")
	pi = make_purchase_invoice(purchase_order)
	keep = []
	for r in pi.items:
		po = frappe.db.get_value("Purchase Order Item", r.po_detail, ["received_qty", "qty"], as_dict=True)
		billed = flt(frappe.db.sql("""select sum(qty) from `tabPurchase Invoice Item`
		                              where po_detail = %s and docstatus = 1""", r.po_detail)[0][0])
		r.qty = flt(po.received_qty) - billed if po else 0
		if r.qty > 0:
			keep.append(r)
	if not keep:
		frappe.throw(_("Nothing received on {0} is waiting to be billed. Receive it first (Sales app → Purchase Order → Receive).")
		             .format(purchase_order))
	pi.set("items", keep)
	for i, r in enumerate(pi.items, 1):
		r.idx = i
	pi.run_method("calculate_taxes_and_totals")
	pi.insert()
	return pi.name


@frappe.whitelist(methods=["POST"])
def record_payment(doctype: str, invoice: str, bank_account: str, amount: float, posting_date: str,
                   reference_no: str | None = None):
	"""Receive (sales invoice) or Pay (purchase invoice) through a bank account."""
	_require_post()
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	if doctype not in ("Sales Invoice", "Purchase Invoice"):
		frappe.throw(_("Only invoices can be paid here."))
	gl_account = frappe.get_cached_value("Bank Account", bank_account, "account")
	pe = get_payment_entry(doctype, invoice, bank_account=gl_account, reference_date=posting_date)
	pe.bank_account = bank_account
	pe.posting_date = posting_date
	pe.reference_date = posting_date
	pe.reference_no = reference_no or invoice
	_set_payment_amount(pe, flt(amount))
	pe.insert()
	pe.submit()
	return pe.name


@frappe.whitelist(methods=["POST"])
def make_payment(bank_account: str, amount: float, posting_date: str, supplier: str | None = None,
                 invoices: list | str | None = None, account: str | None = None, vat_template: str | None = None,
                 reference_no: str | None = None, remark: str | None = None):
	"""Money out from Home / Dashboards, before it is on a statement: pay a supplier
	(the ticked bills first, any rest on account) or spend straight to an account
	(Xero's Spend money), optionally splitting out VAT. `amount` is in the bank's
	currency. When the line arrives, Bank suggests this entry as its match."""
	_require_post()
	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Enter the amount paid."))
	if bank_account not in {b.name for b in _bank_accounts()}:
		frappe.throw(_("Pay from one of the company's bank accounts."))
	# the bank side of the payment, shaped like a statement line for the builders above
	ref = (reference_no or "").strip() or _("Payment {0}").format(posting_date)
	out = frappe._dict(company=frappe.get_cached_value("Bank Account", bank_account, "company") or _company(),
	                   bank_account=bank_account, date=posting_date, withdrawal=amount, deposit=0,
	                   unallocated_amount=amount, reference_number=ref, description=remark or ref, name=ref)
	if supplier:
		doc = _payment_for_party(out, "Supplier", supplier, remark, invoices=_parse(invoices) or [])
	elif account:
		doc = _bank_journal(out, [dict(account=account, amount=amount, remark=remark)], remark, vat_template)
	else:
		frappe.throw(_("Pick a supplier or the account the money goes to."))
	return dict(voucher_type=doc.doctype, voucher=doc.name)


@frappe.whitelist(methods=["POST"])
def new_supplier_bill(supplier: str, posting_date: str, lines: list | str, bill_no: str | None = None,
                      due_date: str | None = None, tax_template: str | None = None, file_url: str | None = None,
                      currency: str | None = None):
	"""A draft Purchase Invoice from a supplier's bill, with the bill attached, for
	review and submit. Lines are services/expenses: description, amount, account."""
	_require_post()
	lines = _parse(lines)
	company = _company()
	pi = frappe.new_doc("Purchase Invoice")
	pi.update(dict(company=company, supplier=supplier, posting_date=posting_date, set_posting_time=1,
	               bill_no=bill_no, bill_date=posting_date, due_date=due_date or None))
	if currency:
		pi.currency = currency
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	for ln in lines:
		pi.append("items", dict(item_name=(ln.get("description") or "Expense")[:140], description=ln.get("description"),
		                        qty=1, rate=flt(ln.get("amount")), uom="Nos", conversion_factor=1,
		                        expense_account=ln.get("account"), cost_center=cost_center))
	if tax_template:
		pi.taxes_and_charges = tax_template
		pi.set_taxes()
	pi.set_missing_values()
	pi.insert()
	if file_url:
		_attach(file_url, "Purchase Invoice", pi.name)
	return pi.name


# ── Petty cash ───────────────────────────────────────────────────────────────
# A float system: each box (a Cash account in App Accounts Settings) has a
# custodian and a float. Vouchers spend from it, a top-up from the bank brings it
# back to the float, and a cash count posts any difference to over / short.

CASH_COUNT = "Cash count"


def is_accounts_manager(user=None):
	return bool({"Accounts Manager", "System Manager"} & set(frappe.get_roles(user)))


def _boxes():
	if not frappe.db.exists("DocType", ACC_SETTINGS):
		return []
	return [b for b in frappe.get_single(ACC_SETTINGS).petty_cash_boxes if b.account]


def custodian_boxes(user=None):
	"""The boxes this user keeps (custodians may have no accounts role at all)."""
	user = user or frappe.session.user
	return [b.account for b in _boxes() if b.custodian == user]


def _require_box(account, manage=False):
	"""Recording a voucher: an accounts role or the box's custodian. Top-ups and
	counts (`manage`): an accounts role."""
	box = next((b for b in _boxes() if b.account == account), None)
	if not box:
		frappe.throw(_("{0} is not a petty cash box. Add it under Settings → Petty cash.").format(account))
	if not can_post() and (manage or box.custodian != frappe.session.user):
		frappe.throw(_("Only the accounts team or this box's custodian can do that."), frappe.PermissionError)
	return box


def _box_line(box, date, amount=0, deposit=0, **extra):
	"""A pseudo statement line for `_bank_journal`, on the box's cash account."""
	line = frappe._dict(company=frappe.get_cached_value("Account", box.account, "company"), account=box.account,
	                    bank_account=None, date=date, withdrawal=amount, deposit=deposit,
	                    unallocated_amount=amount or deposit, reference_number=None, name="",
	                    voucher_type="Cash Entry", ignore_permissions=True)
	line.update(extra)
	return line


def _box_entries(account, docstatus=(0, 1, 2), start=0, page_length=50):
	"""The box's journal rows, newest first: vouchers (money out), top-ups (money in
	from a bank) and cash counts."""
	rows = frappe.db.sql(
		"""select je.name, je.posting_date, je.docstatus, je.cheque_no, je.pay_to_recd_from paid_to, je.user_remark remark,
		          je.owner, je.creation, jea.debit_in_account_currency money_in, jea.credit_in_account_currency money_out,
		          (select group_concat(distinct o.account separator ', ') from `tabJournal Entry Account` o
		           where o.parent=je.name and o.account != jea.account) other
		   from `tabJournal Entry` je join `tabJournal Entry Account` jea on jea.parent=je.name and jea.account=%(account)s
		   where je.docstatus in %(docstatus)s
		   order by je.posting_date desc, je.creation desc limit %(start)s, %(page_length)s""",
		dict(account=account, docstatus=tuple(docstatus), start=cint(start), page_length=cint(page_length)), as_dict=True)
	for r in rows:
		r.kind = "count" if r.cheque_no == CASH_COUNT else "top_up" if flt(r.money_in) else "voucher"
		r.amount = flt(r.money_in or r.money_out)
		r.status = {0: "awaiting", 1: "posted", 2: "cancelled"}[r.docstatus]
	return rows


def _attach_receipts(rows):
	names = [r.name for r in rows]
	files = {}
	if names:
		for f in frappe.get_all("File", filters={"attached_to_doctype": "Journal Entry", "attached_to_name": ["in", names]},
		                        fields=["attached_to_name", "file_url", "file_name"]):
			files.setdefault(f.attached_to_name, f)
	users = {}
	for r in rows:
		r.receipt = files.get(r.name)
		r.by = users.setdefault(r.owner, frappe.utils.get_fullname(r.owner))
	return rows


@frappe.whitelist()
def get_petty_cash():
	"""The boxes this user may see: all of them for the accounts team, their own for a custodian."""
	from erpnext.accounts.utils import get_balance_on

	if not can_post() and not custodian_boxes():
		frappe.throw(_("Petty cash is for the accounts team and box custodians."), frappe.PermissionError)
	today = nowdate()
	out = []
	for b in _boxes():
		if not can_post() and b.custodian != frappe.session.user:
			continue
		currency = frappe.get_cached_value("Account", b.account, "account_currency")
		entries = _box_entries(b.account, docstatus=(0, 1), page_length=500)
		last_top_up = next((e.posting_date for e in entries if e.kind == "top_up" and e.docstatus == 1), None)
		count = frappe.get_all("Comment", filters={"reference_doctype": "Account", "reference_name": b.account,
		                                           "content": ["like", f"{CASH_COUNT}%"]},
		                       fields=["content", "creation", "owner"], order_by="creation desc", limit=1)
		out.append(dict(
			account=b.account, name=frappe.get_cached_value("Account", b.account, "account_name"), currency=currency,
			custodian=b.custodian, custodian_name=b.custodian and frappe.utils.get_fullname(b.custodian),
			float_amount=flt(b.float_amount), approval_limit=flt(b.approval_limit),
			balance=flt(get_balance_on(b.account, today, in_account_currency=True, ignore_account_permission=True)),
			spent_since_top_up=sum(e.amount for e in entries if e.kind == "voucher" and e.docstatus == 1
			                       and (not last_top_up or getdate(e.posting_date) >= getdate(last_top_up))),
			last_top_up=last_top_up, awaiting=sum(1 for e in entries if e.docstatus == 0),
			last_count=count[0] if count else None,
			mine=b.custodian == frappe.session.user,
		))
	return dict(boxes=out, can_manage=can_post(), can_approve=is_accounts_manager())


@frappe.whitelist()
def get_vouchers(account: str, status: str | None = None, start: int = 0):
	_require_box(account)
	docstatus = {"posted": (1,), "awaiting": (0,), "cancelled": (2,)}.get(status, (0, 1, 2))
	return _attach_receipts(_box_entries(account, docstatus=docstatus, start=start))


@frappe.whitelist()
def petty_search(doctype: str, txt: str = "", filters: dict | str | None = None, page_length: int = 20):
	"""Link search for the voucher form. Custodians may have no read access to
	Account or tax templates, so this lists only what a voucher can use."""
	if not can_post() and not custodian_boxes():
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	like = f"%{txt or ''}%"
	if doctype == "Account":
		rows = frappe.get_all("Account", filters={"company": _company(), "is_group": 0, "disabled": 0, "root_type": "Expense"},
		                      or_filters={"name": ["like", like], "account_name": ["like", like]},
		                      fields=["name as value", "account_name as label"], order_by="lft", limit=cint(page_length))
	elif doctype == "Purchase Taxes and Charges Template":
		rows = frappe.get_all(doctype, filters={"company": _company(), "disabled": 0, "name": ["like", like]},
		                      fields=["name as value"], limit=cint(page_length))
	else:
		frappe.throw(_("Not searchable here."))
	return rows


@frappe.whitelist(methods=["POST"])
def new_voucher(account: str, posting_date: str, amount: float, expense_account: str, paid_to: str | None = None,
                remark: str | None = None, vat_template: str | None = None, file_url: str | None = None):
	"""Cash paid out of a box. Over the box's approval limit it waits as a draft for
	an Accounts Manager; otherwise it posts straight away."""
	box = _require_box(account)
	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Enter the amount paid."))
	if frappe.db.get_value("Account", expense_account, "root_type") != "Expense":
		frappe.throw(_("Pick an expense account for what the cash was spent on."))
	needs_approval = bool(flt(box.approval_limit) and amount > flt(box.approval_limit))
	what = remark or paid_to or _("Petty cash")
	je = _bank_journal(_box_line(box, posting_date, amount, description=what, pay_to=paid_to),
	                   [dict(account=expense_account, amount=amount, remark=remark)], what, vat_template,
	                   submit=not needs_approval)
	if file_url:
		_attach(file_url, "Journal Entry", je.name)
	return dict(name=je.name, status="awaiting" if needs_approval else "posted")


def _petty_draft(name):
	if not is_accounts_manager():
		frappe.throw(_("Only an Accounts Manager can approve petty cash."), frappe.PermissionError)
	je = frappe.get_doc("Journal Entry", name)
	if je.docstatus != 0:
		frappe.throw(_("{0} isn't waiting for approval.").format(name))
	boxes = {b.account for b in _boxes()}
	box_row = next((a for a in je.accounts if a.account in boxes), None)
	if not box_row:
		frappe.throw(_("{0} isn't a petty cash voucher.").format(name))
	return je, box_row


@frappe.whitelist(methods=["POST"])
def approve_voucher(name: str):
	je, _row = _petty_draft(name)
	je.flags.ignore_permissions = True
	je.submit()
	return dict(name=name, status="posted")


@frappe.whitelist(methods=["POST"])
def decline_voucher(name: str, reason: str):
	"""Delete the draft; the decline stays as a comment on the box's account."""
	if not (reason or "").strip():
		frappe.throw(_("Say why it's declined, so the custodian knows."))
	je, row = _petty_draft(name)
	currency = row.account_currency
	frappe.get_doc(dict(doctype="Comment", comment_type="Comment", reference_doctype="Account", reference_name=row.account,
	                    content=_("Declined petty cash voucher {0} by {1}: {2} {3} to {4} — {5}").format(
	                        name, frappe.utils.get_fullname(je.owner), currency, flt(row.credit_in_account_currency),
	                        je.pay_to_recd_from or je.user_remark or "—", reason.strip()))).insert(ignore_permissions=True)
	frappe.delete_doc("Journal Entry", name, ignore_permissions=True)
	return dict(name=name, status="declined")


@frappe.whitelist(methods=["POST"])
def top_up(account: str, bank_account: str, posting_date: str, amount: float | None = None,
           reference_no: str | None = None):
	"""Bring the box back to its float from a bank account. `amount` is in the bank's
	currency; left empty, it is the float less the balance."""
	from erpnext.accounts.utils import get_balance_on

	box = _require_box(account, manage=True)
	if bank_account not in {b.name for b in _bank_accounts()}:
		frappe.throw(_("Top up from one of the company's bank accounts."))
	bank_currency = frappe.get_cached_value("Account", frappe.get_cached_value("Bank Account", bank_account, "account"),
	                                       "account_currency")
	box_currency = frappe.get_cached_value("Account", box.account, "account_currency")
	if not flt(amount):
		short = flt(box.float_amount) - flt(get_balance_on(box.account, posting_date, in_account_currency=True,
		                                                    ignore_account_permission=True))
		if short <= 0:
			frappe.throw(_("The box is already at its float."))
		amount = flt(short * _rate(box_currency, bank_currency, posting_date), 2)
	ref = (reference_no or "").strip() or _("Petty cash top-up {0}").format(posting_date)
	line = frappe._dict(company=frappe.get_cached_value("Bank Account", bank_account, "company") or _company(),
	                    bank_account=bank_account, date=posting_date, withdrawal=flt(amount), deposit=0,
	                    unallocated_amount=flt(amount), reference_number=ref, description=ref, name=ref)
	je = _bank_journal(line, [dict(account=box.account, amount=flt(amount), remark=_("Petty cash top-up"))],
	                   _("Petty cash top-up"))
	return dict(name=je.name, amount=flt(amount), currency=bank_currency)


@frappe.whitelist(methods=["POST"])
def count_cash(account: str, counted: float, posting_date: str | None = None):
	"""Record a cash count. Any difference from the books goes to the over / short account."""
	from erpnext.accounts.utils import get_balance_on

	box = _require_box(account, manage=True)
	posting_date = posting_date or nowdate()
	books = flt(get_balance_on(box.account, posting_date, in_account_currency=True, ignore_account_permission=True))
	diff = flt(flt(counted) - books, 2)
	currency = frappe.get_cached_value("Account", box.account, "account_currency")
	je = None
	if abs(diff) >= 0.005:
		over_short = _setting("cash_over_short_account")
		if not over_short:
			frappe.throw(_("Set the cash over / short account under Settings → Petty cash first."))
		remark = _("{0}: counted {1:,.2f}, books {2:,.2f}").format(CASH_COUNT, flt(counted), books)
		je = _bank_journal(_box_line(box, posting_date, amount=-diff if diff < 0 else 0, deposit=diff if diff > 0 else 0,
		                             reference_number=CASH_COUNT, description=remark),
		                   [dict(account=over_short, amount=abs(diff), remark=remark)], remark)
	frappe.get_doc(dict(doctype="Comment", comment_type="Comment", reference_doctype="Account", reference_name=box.account,
	                    content=_("{0}: counted {1} {2:,.2f}, books {1} {3:,.2f}, difference {4:+,.2f}").format(
	                        CASH_COUNT, currency, flt(counted), books, diff))).insert(ignore_permissions=True)
	return dict(difference=diff, journal_entry=je and je.name)


# ── Payments made and received ───────────────────────────────────────────────

PAYMENT_STATUSES = ("waiting", "cleared", "cancelled")


def _payments_sql():
	"""Every Payment Entry and bank Journal Entry row that moves money through one of
	our bank or cash accounts, one row per payment, in the bank account's currency.
	A journal between our own bank / cash accounts (a petty cash top-up) is one
	transfer, listed on the side the money left."""
	only_money = """not exists (select 1 from `tabJournal Entry Account` o join `tabAccount` oa on oa.name=o.account
	                where o.parent=je.name and o.account != jea.account and coalesce(oa.account_type, '') not in ('Bank', 'Cash'))"""
	return f"""
		select 'Payment Entry' doctype, pe.name, pe.posting_date, pe.creation, pe.owner, pe.docstatus, pe.clearance_date,
		       case pe.payment_type when 'Receive' then 'in' when 'Pay' then 'out' else 'transfer' end direction,
		       coalesce(pe.party_name, pe.party, if(pe.payment_type='Internal Transfer', pe.paid_to, '')) counterparty,
		       if(pe.payment_type='Receive', pe.paid_to, pe.paid_from) account,
		       if(pe.payment_type='Receive', pe.received_amount, pe.paid_amount) amount,
		       if(pe.payment_type='Receive', pe.paid_to_account_currency, pe.paid_from_account_currency) currency,
		       pe.reference_no reference, pe.remarks remark
		from `tabPayment Entry` pe
		where pe.company=%(company)s and pe.docstatus in (1, 2)
		  and (pe.paid_from in %(banks)s or pe.paid_to in %(banks)s)
		union all
		select 'Journal Entry', je.name, je.posting_date, je.creation, je.owner, je.docstatus, je.clearance_date,
		       case when ({only_money}) then 'transfer' when jea.credit_in_account_currency > 0 then 'out' else 'in' end,
		       coalesce(nullif(je.pay_to_recd_from, ''),
		                (select group_concat(distinct coalesce(o.party, o.account) separator ', ') from `tabJournal Entry Account` o
		                 where o.parent=je.name and o.account != jea.account)),
		       jea.account, jea.credit_in_account_currency + jea.debit_in_account_currency, jea.account_currency,
		       je.cheque_no, je.user_remark
		from `tabJournal Entry` je join `tabJournal Entry Account` jea on jea.parent=je.name
		where je.company=%(company)s and je.docstatus in (1, 2) and jea.account in %(banks)s
		  and not (({only_money}) and jea.debit_in_account_currency > 0)"""


@frappe.whitelist()
def get_payments(direction: str = "out", status: str | None = None, account: str | None = None,
                 from_date: str | None = None, to_date: str | None = None, search: str | None = None,
                 mine: int = 0, start: int = 0, page_length: int = 50):
	"""Track payments: whether each is still waiting for the bank statement, cleared
	(matched to a statement line) or cancelled. Totals are per currency."""
	_require_post()
	company = _company()
	cash = _cash_accounts(company)
	if not cash:
		return dict(rows=[], total=0, totals={})
	params = dict(company=company, banks=tuple(a.name for a in cash),
	              cash=tuple(a.name for a in cash if a.account_type == "Cash") or ("",))
	where = []
	if direction in ("in", "out", "transfer"):
		where.append("p.direction=%(direction)s")
		params["direction"] = direction
	# cash moves never reach a bank statement, so they are "cash", not waiting
	if status == "waiting":
		where.append("p.docstatus=1 and p.clearance_date is null and p.account not in %(cash)s")
	elif status == "cleared":
		where.append("p.docstatus=1 and p.clearance_date is not null")
	elif status == "cash":
		where.append("p.docstatus=1 and p.account in %(cash)s")
	elif status == "cancelled":
		where.append("p.docstatus=2")
	else:
		where.append("p.docstatus=1")
	if account:
		where.append("p.account=%(account)s")
		params["account"] = account
	if from_date:
		where.append("p.posting_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		where.append("p.posting_date <= %(to_date)s")
		params["to_date"] = to_date
	if search:
		where.append("(p.name like %(search)s or p.counterparty like %(search)s or p.reference like %(search)s"
		             " or p.remark like %(search)s or cast(p.amount as char) like %(search)s)")
		params["search"] = f"%{search.strip()}%"
	if cint(mine):
		where.append("p.owner=%(user)s")
		params["user"] = frappe.session.user
	base = f"from ({_payments_sql()}) p where " + " and ".join(where)

	totals = {}
	for t in frappe.db.sql(f"""select currency, direction, sum(if(docstatus=1, amount, 0)) amount, count(*) n,
	                                  sum(if(docstatus=1 and clearance_date is null and account not in %(cash)s, 1, 0)) waiting,
	                                  sum(if(docstatus=1 and clearance_date is null and account not in %(cash)s, amount, 0)) waiting_amount
	                           {base} group by currency, direction""", params, as_dict=True):
		c = totals.setdefault(t.currency, {"out": 0, "in": 0, "transfer": 0, "count": 0, "waiting": 0, "waiting_amount": 0})
		c[t.direction] += flt(t.amount)
		c["count"] += cint(t.n)
		c["waiting"] += cint(t.waiting)
		c["waiting_amount"] += flt(t.waiting_amount)
	rows = frappe.db.sql(f"select p.* {base} order by p.posting_date desc, p.creation desc limit %(start)s, %(page_length)s",
	                     dict(params, start=cint(start), page_length=cint(page_length) or 50), as_dict=True)

	names = {(r.doctype, r.name) for r in rows}
	lines = {}
	if names:
		for b in frappe.db.sql("""select btp.payment_document, btp.payment_entry, bt.name, bt.date
		                          from `tabBank Transaction Payments` btp join `tabBank Transaction` bt on bt.name=btp.parent
		                          where bt.docstatus=1 and btp.payment_entry in %s""", (tuple(n for _, n in names),), as_dict=True):
			lines[(b.payment_document, b.payment_entry)] = dict(name=b.name, date=b.date)
	account_names = {a.name: a.account_name for a in cash}
	users = {}
	for r in rows:
		r.status = "cancelled" if r.docstatus == 2 else "cleared" if r.clearance_date else \
			"cash" if r.account in params["cash"] else "waiting"
		r.bank_line = lines.get((r.doctype, r.name))
		r.account_name = account_names.get(r.account, r.account)
		r.remark = (r.remark or "")[:200]
		r.by = users.setdefault(r.owner, frappe.utils.get_fullname(r.owner))
	total = frappe.db.sql(f"select count(*) {base}", params)[0][0]
	return dict(rows=rows, total=total, totals=totals)


@frappe.whitelist()
def get_payment(doctype: str, name: str):
	"""One payment: what it paid (bills or accounts), its statement line, and whether
	it can still be cancelled."""
	_require_post()
	if doctype not in ("Payment Entry", "Journal Entry"):
		frappe.throw(_("Not a payment."))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	line = frappe.db.sql("""select bt.name, bt.date, bt.description, bt.deposit, bt.withdrawal, bt.currency
	                        from `tabBank Transaction Payments` btp join `tabBank Transaction` bt on bt.name=btp.parent
	                        where bt.docstatus=1 and btp.payment_document=%s and btp.payment_entry=%s limit 1""",
	                     (doctype, name), as_dict=True)
	out = dict(doctype=doctype, name=name, docstatus=doc.docstatus, clearance_date=doc.clearance_date,
	           bank_line=line[0] if line else None, owner=frappe.utils.get_fullname(doc.owner), creation=doc.creation)
	if doctype == "Payment Entry":
		out.update(payment_type=doc.payment_type, party_type=doc.party_type, party=doc.party, party_name=doc.party_name,
		           unallocated=flt(doc.unallocated_amount), party_currency=doc.paid_to_account_currency
		           if doc.payment_type == "Pay" else doc.paid_from_account_currency,
		           paid=[dict(doctype=r.reference_doctype, name=r.reference_name, amount=flt(r.allocated_amount),
		                      bill_no=r.bill_no, due_date=r.due_date) for r in doc.references],
		           rows=[])
	else:
		out.update(paid=[], rows=[dict(account=a.account, party=a.party, currency=a.account_currency,
		                               debit=flt(a.debit_in_account_currency), credit=flt(a.credit_in_account_currency),
		                               remark=a.user_remark) for a in doc.accounts])
	out["can_cancel"] = doc.docstatus == 1 and not doc.clearance_date and not line
	return out


@frappe.whitelist(methods=["POST"])
def cancel_payment(doctype: str, name: str):
	"""Cancel a payment made by mistake. Only while it isn't matched to a statement
	line: a cleared one is undone from Bank (Reconciled → Undo)."""
	_require_post()
	detail = get_payment(doctype, name)
	if not detail["can_cancel"]:
		frappe.throw(_("{0} is matched to a bank statement line. Undo it from Bank first.").format(name)
		             if detail["docstatus"] == 1 else _("{0} is already cancelled.").format(name))
	frappe.get_doc(doctype, name).cancel()
	return dict(status="cancelled")


# ── Dashboards ───────────────────────────────────────────────────────────────

def _cash_accounts(company):
	return frappe.get_all("Account", filters={"company": company, "account_type": ["in", ["Bank", "Cash"]], "is_group": 0,
	                                          "disabled": 0}, fields=["name", "account_name", "account_currency", "account_type"],
	                      order_by="lft")


@frappe.whitelist()
def get_dashboard():
	_require_access()
	from erpnext.accounts.utils import get_balance_on

	company = _company()
	currency = _company_currency(company)
	today = nowdate()
	cash = []
	for a in _cash_accounts(company):
		bal = flt(get_balance_on(a.name, today, in_account_currency=True, ignore_account_permission=True))
		base = flt(get_balance_on(a.name, today, ignore_account_permission=True))
		if bal or base:
			cash.append(dict(account=a.name, name=a.account_name, currency=a.account_currency, balance=bal,
			                 base=base, today_value=flt(bal * _rate(a.account_currency, currency, today), 2)))
	month_start = get_first_day(today)
	io = frappe.db.sql(
		"""select sum(debit) money_in, sum(credit) money_out from `tabGL Entry` gle
		   join `tabAccount` a on a.name = gle.account
		   where gle.company=%s and a.account_type in ('Bank','Cash') and gle.is_cancelled=0
		     and gle.posting_date between %s and %s
		     and not (gle.voucher_type='Payment Entry' and exists (select 1 from `tabPayment Entry` pe
		              where pe.name=gle.voucher_no and pe.payment_type='Internal Transfer'))""",
		(company, month_start, today), as_dict=True)[0]
	owed = {}
	for dt, key in (("Sales Invoice", "receivable"), ("Purchase Invoice", "payable")):
		r = frappe.db.sql(f"""select sum(outstanding_amount * conversion_rate) total,
		                             sum(if(due_date < %s, outstanding_amount * conversion_rate, 0)) overdue, count(*) n
		                      from `tab{dt}` where docstatus=1 and outstanding_amount > 0 and company=%s""",
		                  (today, company), as_dict=True)[0]
		owed[key] = dict(total=flt(r.total), overdue=flt(r.overdue), invoices=cint(r.n))
	to_reconcile = frappe.db.count("Bank Transaction", {"docstatus": 1, "unallocated_amount": [">", 0], "company": company})
	assigned = frappe.get_all("ToDo", filters={"allocated_to": frappe.session.user, "status": "Open",
	                                           "reference_type": "Bank Transaction"},
	                          fields=["reference_name", "description", "assigned_by_full_name", "creation"], limit=20)
	# supplier bills to pay next, for the Pay buttons on Home
	bills_due = frappe.get_list(
		"Purchase Invoice", filters={"docstatus": 1, "outstanding_amount": [">", 0], "company": company},
		fields=["name", "supplier", "supplier_name", "bill_no", "due_date", "outstanding_amount", "currency"],
		order_by="due_date asc", limit_page_length=8) if can_post() else []
	for b in bills_due:
		b.match = _match(b.name)
	petty_awaiting = frappe.db.sql(
		"""select count(distinct je.name) from `tabJournal Entry` je join `tabJournal Entry Account` jea on jea.parent=je.name
		   where je.docstatus=0 and je.voucher_type='Cash Entry' and jea.account in %s""",
		(tuple(b.account for b in _boxes()) or ("",),))[0][0] if is_accounts_manager() else 0
	health = get_health()
	return dict(
		bills_due=bills_due, petty_awaiting=petty_awaiting, purchases=_open_orders(company, today),
		currency=currency, cash=cash, cash_total=sum(c["today_value"] for c in cash),
		money_in=flt(io.money_in), money_out=flt(io.money_out), month_start=month_start,
		**owed, to_reconcile=to_reconcile, assigned=assigned,
		rate=dict(pair="USD→ZWG", value=_rate("USD", "ZWG", today),
		          date=frappe.db.sql("""select max(date) from `tabCurrency Exchange`
		                                where from_currency='USD' and to_currency='ZWG'""")[0][0]),
		health=dict(count=len(health["issues"]), errors=sum(1 for i in health["issues"] if i["severity"] == "error")),
	)


@frappe.whitelist()
def get_cash_flow(months: int = 12):
	"""Money in and out of banks and cash per month, in the company currency
	(transfers between our own accounts left out)."""
	_require_access()
	company = _company()
	start = get_first_day(add_months(nowdate(), -(cint(months) - 1)))
	rows = frappe.db.sql(
		"""select date_format(gle.posting_date, '%%Y-%%m') month, sum(debit) money_in, sum(credit) money_out
		   from `tabGL Entry` gle join `tabAccount` a on a.name = gle.account
		   where gle.company=%s and a.account_type in ('Bank','Cash') and gle.is_cancelled=0 and gle.posting_date >= %s
		     and not (gle.voucher_type='Payment Entry' and exists (select 1 from `tabPayment Entry` pe
		              where pe.name=gle.voucher_no and pe.payment_type='Internal Transfer'))
		   group by month order by month""", (company, start), as_dict=True)
	by_month = {r.month: r for r in rows}
	out = []
	for i in range(cint(months)):
		m = add_months(start, i).strftime("%Y-%m")
		r = by_month.get(m) or {}
		out.append(dict(month=m, money_in=flt(r.get("money_in")), money_out=flt(r.get("money_out")),
		                net=flt(r.get("money_in")) - flt(r.get("money_out"))))
	return dict(currency=_company_currency(company), months=out)


def _pnl(company, start, end):
	r = frappe.db.sql(
		"""select sum(if(a.root_type='Income', credit - debit, 0)) income,
		          sum(if(a.root_type='Expense', debit - credit, 0)) expense
		   from `tabGL Entry` gle join `tabAccount` a on a.name = gle.account
		   where gle.company=%s and gle.is_cancelled=0 and gle.posting_date between %s and %s""",
		(company, start, end), as_dict=True)[0]
	income, expense = flt(r.income), flt(r.expense)
	return dict(income=income, expense=expense, profit=income - expense, start=start, end=end)


@frappe.whitelist()
def get_pnl():
	_require_access()
	from erpnext.accounts.utils import get_fiscal_year

	company = _company()
	today = getdate()
	last = add_months(today, -1)
	fy_start = get_fiscal_year(today, company=company)[1]
	return dict(
		currency=_company_currency(company),
		this_month=_pnl(company, get_first_day(today), today),
		last_month=_pnl(company, get_first_day(last), get_last_day(last)),
		year_to_date=_pnl(company, fy_start, today),
		top_expenses=frappe.db.sql(
			"""select a.account_name account, sum(debit - credit) amount from `tabGL Entry` gle
			   join `tabAccount` a on a.name = gle.account
			   where gle.company=%s and gle.is_cancelled=0 and a.root_type='Expense' and gle.posting_date between %s and %s
			   group by a.name having amount > 0 order by amount desc limit 8""",
			(company, fy_start, today), as_dict=True),
	)


@frappe.whitelist()
def get_budget():
	"""Budget against actual for the fiscal year, per account. Empty until budgets exist."""
	_require_access()
	from erpnext.accounts.utils import get_fiscal_year

	company = _company()
	fy, fy_start, fy_end = get_fiscal_year(getdate(), company=company)[:3]
	budgets = frappe.get_all("Budget", filters={"company": company, "fiscal_year": fy, "docstatus": 1},
	                         fields=["name", "budget_against", "cost_center", "project"])
	rows = []
	for b in budgets:
		for acc in frappe.get_all("Budget Account", filters={"parent": b.name}, fields=["account", "budget_amount"]):
			field = "cost_center" if b.budget_against == "Cost Center" else "project"
			actual = frappe.db.sql(
				f"""select sum(debit - credit) from `tabGL Entry` where company=%s and account=%s and {field}=%s
				    and is_cancelled=0 and posting_date between %s and %s""",
				(company, acc.account, b.get(field), fy_start, getdate()))[0][0]
			rows.append(dict(account=acc.account, against=b.get(field), budget=flt(acc.budget_amount), actual=flt(actual),
			                 variance=flt(acc.budget_amount) - flt(actual)))
	return dict(fiscal_year=fy, currency=_company_currency(company), rows=rows, budgets=len(budgets))


# ── Purchases ────────────────────────────────────────────────────────────────

# submitted and not finished; "On Hold" stays open, it still owes us goods or a bill
DONE_PO = ("Completed", "Closed", "Cancelled")
OPEN_PO = "docstatus=1 and company=%s and status not in ('Completed', 'Closed', 'Cancelled')"


def _open_orders(company, today):
	"""Open purchase orders: how many, what is still to come in and to be billed, and
	how many are late for delivery. None when the user can't read purchase orders."""
	if not frappe.has_permission("Purchase Order", "read"):
		return None
	r = frappe.db.sql(
		f"""select count(*) n, sum(base_grand_total) value,
		           sum(if(per_received < 100, 1, 0)) to_receive_n,
		           sum(base_grand_total * (100 - least(per_received, 100)) / 100) to_receive,
		           sum(if(per_billed < 100, 1, 0)) to_bill_n,
		           sum(base_grand_total * (100 - least(per_billed, 100)) / 100) to_bill,
		           sum(if(per_received < 100 and schedule_date < %s, 1, 0)) late
		    from `tabPurchase Order` where {OPEN_PO}""", (today, company), as_dict=True)[0]
	drafts = frappe.db.sql("""select count(*) n, sum(base_grand_total) value from `tabPurchase Order`
	                          where docstatus=0 and company=%s""", (company,), as_dict=True)[0]
	return dict(open=cint(r.n), value=flt(r.value), to_receive=flt(r.to_receive), to_receive_n=cint(r.to_receive_n),
	            to_bill=flt(r.to_bill), to_bill_n=cint(r.to_bill_n), late=cint(r.late),
	            drafts=cint(drafts.n), drafts_value=flt(drafts.value))


@frappe.whitelist()
def get_purchases(months: int = 12):
	"""Purchase orders and supplier invoices for the Dashboards page, in the company
	currency: per month, this month and this year, the biggest suppliers and the open orders."""
	_require_access()
	from erpnext.accounts.utils import get_fiscal_year

	company = _company()
	today = getdate()
	months = cint(months) or 12
	start = get_first_day(add_months(today, -(months - 1)))
	can_pi = frappe.has_permission("Purchase Invoice", "read")
	can_po = frappe.has_permission("Purchase Order", "read")

	def per_month(doctype, date_field, amount):
		return {r.month: flt(r.total) for r in frappe.db.sql(
			f"""select date_format({date_field}, '%%Y-%%m') month, sum({amount}) total from `tab{doctype}`
			    where docstatus=1 and company=%s and {date_field} >= %s group by month""", (company, start), as_dict=True)}

	invoiced = per_month("Purchase Invoice", "posting_date", "base_net_total") if can_pi else {}
	ordered = per_month("Purchase Order", "transaction_date", "base_net_total") if can_po else {}
	series = []
	for i in range(months):
		m = add_months(start, i).strftime("%Y-%m")
		series.append(dict(month=m, invoiced=invoiced.get(m, 0), ordered=ordered.get(m, 0)))

	fy_start = get_fiscal_year(today, company=company)[1]

	def invoiced_between(a, b):
		r = frappe.db.sql("""select sum(base_net_total) total, count(*) n from `tabPurchase Invoice`
		                     where docstatus=1 and company=%s and posting_date between %s and %s""",
		                  (company, a, b), as_dict=True)[0]
		return dict(total=flt(r.total), invoices=cint(r.n))

	out = dict(currency=_company_currency(company), months=series, can_invoices=can_pi, can_orders=can_po)
	if can_pi:
		out.update(
			this_month=invoiced_between(get_first_day(today), today),
			year_to_date=invoiced_between(fy_start, today),
			top_suppliers=frappe.db.sql(
				"""select supplier, max(supplier_name) supplier_name, sum(base_net_total) amount, count(*) invoices
				   from `tabPurchase Invoice` where docstatus=1 and company=%s and posting_date between %s and %s
				   group by supplier order by amount desc limit 8""", (company, fy_start, today), as_dict=True),
		)
	if can_po:
		out.update(
			orders=_open_orders(company, today),
			recent_orders=frappe.get_list(
				"Purchase Order",
				filters={"docstatus": 1, "company": company, "status": ["not in", DONE_PO]},
				fields=["name", "supplier", "supplier_name", "transaction_date", "schedule_date", "grand_total", "currency",
				        "base_grand_total", "per_received", "per_billed", "status"],
				order_by="transaction_date desc, creation desc", limit_page_length=10),
		)
	return out


# The curated accounts reports; every other Accounts and Regional report follows under
# "Other accounts reports" (see api/reports.py)
REPORTS = {
	"Financial statements": [
		("Profit and Loss Statement", "Income less expenses for a period"),
		("Balance Sheet", "What the company owns and owes on a date"),
		("Cash Flow", "Operating, investing and financing cash movements"),
		("Trial Balance", "Every account's opening, movement and closing"),
		("Gross and Net Profit Report", "Gross and net profit by period"),
		("Financial Ratios", "Liquidity, solvency and turnover ratios"),
		("Consolidated Financial Statement", "Statements across companies"),
		("Custom Financial Statement", "A statement laid out your way"),
	],
	"Ledgers": [
		("General Ledger", "Every posting to an account, with running balance"),
		("Payment Ledger", "Every invoice and the payments against it"),
		("Customer Ledger Summary", "Opening, invoiced, paid and closing per customer"),
		("Supplier Ledger Summary", "Opening, billed, paid and closing per supplier"),
		("Trial Balance for Party", "Opening, movement and closing per customer or supplier"),
		("Account Balance", "Balance of each account on a date"),
		("Voucher-wise Balance", "Debits and credits per voucher"),
	],
	"Money owed": [
		("Accounts Receivable", "Every open customer invoice, aged"),
		("Accounts Receivable Summary", "What each customer owes, aged"),
		("Accounts Payable", "Every open supplier invoice, aged"),
		("Accounts Payable Summary", "What we owe each supplier, aged"),
		("Payment Period Based On Invoice Date", "How long invoices took to be paid"),
		("Sales Payment Summary", "Payments received per day and mode"),
	],
	"Registers": [
		("Sales Register", "Every sales invoice, with tax and totals"),
		("Item-wise Sales Register", "Every sales invoice line, with tax"),
		("Purchase Register", "Every supplier invoice, with tax and totals"),
		("Item-wise Purchase Register", "Every supplier invoice line, with tax"),
		("Sales Invoice Trends", "Sales invoices by month, item or customer"),
		("Purchase Invoice Trends", "Supplier invoices by month, item or supplier"),
		("Gross Profit", "Margin per invoice, item or customer"),
		("Delivered Items To Be Billed", "Delivered to customers, not yet invoiced"),
		("Received Items To Be Billed", "Received from suppliers, not yet billed"),
	],
	"Banking": [
		("Bank Reconciliation Statement", "Book balance against the bank's"),
		("Bank Clearance Summary", "Payments and their clearance dates"),
		("Cheques and Deposits Incorrectly cleared", "Clearance dates before the posting date"),
	],
	"Tax": [
		("Tax Withholding Details", "Tax withheld per supplier and invoice"),
		("TDS Computation Summary", "Withholding tax per supplier and category"),
		("VAT Audit Report", "VAT on every sale and purchase"),
	],
	"Budget and analysis": [
		("Budget Variance Report", "Budget against actual, by account and period"),
		("Profitability Analysis", "Income and expense per cost centre or project"),
		("Dimension-wise Accounts Balance Report", "Balances split by cost centre or other dimension"),
		("Period-on-Period P&L Flux Variance", "What moved between two periods"),
		("Deferred Revenue and Expense", "Income and expense spread over time"),
	],
	"Purchases": [
		("Purchase Order Analysis", "Each order: received, billed and still to come"),
		("Purchase Analytics", "Purchases by supplier or item, per period"),
	],
}
REPORT_MODULES = ("Accounts", "Regional", "Erp Overrides")


@frappe.whitelist()
def get_reports():
	"""Every accounts report the user may open, grouped (the Reports page)."""
	_require_access()
	from erp_overrides.api.reports import report_groups

	return report_groups(REPORTS, REPORT_MODULES, _("Other accounts reports"))


# ── Exchange rates ───────────────────────────────────────────────────────────

@frappe.whitelist()
def get_rates(days: int = 60):
	_require_access()
	today = getdate()
	start = add_days(today, -cint(days))
	series = frappe.get_all("Currency Exchange", filters={"from_currency": "USD", "to_currency": "ZWG", "date": [">=", start]},
	                        fields=["date", "exchange_rate"], order_by="date asc")
	have = {str(r.date) for r in series}
	missing = [str(d) for d in (add_days(today, -i) for i in range(30)) if d.weekday() < 5 and str(d) not in have]
	pairs = frappe.db.sql(
		"""select from_currency, to_currency, max(date) last_date, count(*) n from `tabCurrency Exchange`
		   group by from_currency, to_currency order by from_currency, to_currency""", as_dict=True)
	for p in pairs:
		p.rate = frappe.db.get_value("Currency Exchange", {"from_currency": p.from_currency, "to_currency": p.to_currency,
		                                                   "date": p.last_date}, "exchange_rate")
		p.source = "RBZ" if {p.from_currency, p.to_currency} == {"USD", "ZWG"} else "ERPNext provider"
	provider = frappe.db.get_single_value("Currency Exchange Settings", "service_provider")
	latest = frappe.get_all("Currency Exchange", filters={"from_currency": "USD", "to_currency": "ZWG"},
	                        fields=["date", "exchange_rate"], order_by="date desc", limit=1)
	return dict(latest=latest[0] if latest else None, series=series, missing=missing, pairs=pairs, provider=provider)


@frappe.whitelist(methods=["POST"])
def sync_rbz(days: int = 14):
	"""Fetch RBZ's USD/ZWG mid-rates for the last few weeks (the same job the scheduler runs)."""
	_require_post()
	from erp_overrides.scrapers import sync_rates

	sync_rates(start=str(add_days(nowdate(), -cint(days))), end=nowdate(), verbose=False)
	return get_rates()


# ── Setup health ─────────────────────────────────────────────────────────────

def _issue(group, check, message, fix, severity="error"):
	return dict(group=group, check=check, message=message, fix=fix, severity=severity)


@frappe.whitelist()
def get_health():
	"""The setup gaps behind most "the numbers look wrong" questions, each with its fix."""
	_require_access()
	company = _company()
	issues = []
	today = getdate()

	# Exchange rates: a ZWG line can't be posted on a day with no rate
	have = set(str(d) for d in frappe.get_all("Currency Exchange", filters={
		"from_currency": "USD", "to_currency": "ZWG", "date": [">=", add_days(today, -30)]}, pluck="date"))
	missing = [d for d in (add_days(today, -i) for i in range(1, 30)) if d.weekday() < 5 and str(d) not in have]
	if missing:
		issues.append(_issue("rates", "missing_rates", _("{0} weekdays in the last month have no RBZ USD→ZWG rate (latest gap {1}).")
		                     .format(len(missing), missing[0].strftime("%d %b")), {"route": "/rates"}))

	# VAT label vs rate
	for tbl, tmpl in (("Sales Taxes and Charges", "Sales Taxes and Charges Template"),
	                  ("Purchase Taxes and Charges", "Purchase Taxes and Charges Template")):
		for row in frappe.get_all(tbl, filters={"parenttype": tmpl}, fields=["parent", "description", "rate"]):
			shown = re.search(r"(\d+(?:[.,]\d+)?)\s*%?", row.description or "")
			if shown and flt(row.rate) and abs(flt(shown.group(1).replace(",", ".")) - flt(row.rate)) > 0.001:
				issues.append(_issue("setup", "vat_label", _("{0} ({1}): says \"{2}\" but charges {3}%.").format(
					row.parent, "sales" if tbl.startswith("Sales") else "purchases", row.description, flt(row.rate)),
				                     {"desk_url": f"/app/{tmpl.lower().replace(' ', '-')}/{row.parent}"}))

	# Service items kept as stock (hardware is stock by design: erp_overrides.stock_light)
	from erp_overrides.stock_light import is_hardware_group

	stock_services = [r.name for r in frappe.db.sql(
		"""select i.name, i.item_group from tabItem i where i.is_stock_item=1 and i.disabled=0
		   and not exists (select 1 from `tabStock Ledger Entry` s where s.item_code=i.name and s.is_cancelled=0)""",
		as_dict=True) if not is_hardware_group(r.item_group)]
	# ERPNext won't untick Maintain Stock once an item is on a submitted document; those need a new item
	locked = []
	for name in stock_services:
		check = getattr(frappe.get_doc("Item", name), "_get_linked_submitted_documents", None)
		if check and check(["is_stock_item"]):
			locked.append(name)
	free = [n for n in stock_services if n not in locked]
	if free:
		issues.append(_issue("setup", "stock_services", _("{0} item(s) track stock but have never been stocked — services shouldn't: {1}.")
		                     .format(len(free), ", ".join(free[:5])), {"desk_url": "/app/item?is_stock_item=1"}))
	if locked:
		issues.append(_issue("setup", "stock_services_locked", _(
			"{0} item(s) track stock but are already on orders or invoices, so ERPNext won't change them: {1}. "
			"Make a non-stock replacement item and disable the old one.").format(len(locked), ", ".join(locked[:5])),
			{"desk_url": "/app/item?is_stock_item=1"}, "warning"))

	# Bank accounts
	for b in frappe.get_all("Bank Account", filters={"disabled": 0}, fields=["name", "account", "is_company_account"]):
		if not b.account:
			issues.append(_issue("bank", "bank_gl", _("Bank account {0} has no ledger account, so its lines can't be reconciled.").format(b.name),
			                     {"desk_url": f"/app/bank-account/{b.name}"}, "warning"))
	if not frappe.db.count("Bank Transaction Rule"):
		issues.append(_issue("bank", "no_rules", _("No bank rules — every bank charge and tax line is coded by hand."), {"route": "/bank/rules"}))
	stale = cint(_setting("stale_line_days", 60))
	old = frappe.db.count("Bank Transaction", {"docstatus": 1, "unallocated_amount": [">", 0], "date": ["<", add_days(today, -stale)]})
	if old:
		issues.append(_issue("bank", "old_lines", _("{0} bank lines older than {1} days are still to reconcile.").format(old, stale),
		                     {"route": "/bank"}, "warning"))

	# Temporary Opening should come back to zero once opening debtors and creditors are in
	for a in frappe.get_all("Account", filters={"company": company, "account_type": "Temporary", "is_group": 0,
	                                            "account_name": ["like", f"{TEMP_OPENING}%"]}, fields=["name", "account_currency"]):
		from erpnext.accounts.utils import get_balance_on

		left = flt(get_balance_on(a.name, nowdate(), in_account_currency=True, ignore_account_permission=True))
		if abs(left) > 0.005:
			issues.append(_issue("bank", "temporary_opening", _(
				"{0} holds {1} {2}. It clears to zero once opening debtors and creditors are posted; "
				"how to treat any remainder is still to be agreed with finance.").format(a.name, a.account_currency, f"{left:,.2f}"),
				{"desk_url": f"/app/general-ledger?account={a.name}"}, "warning"))

	# Petty cash
	for b in _boxes():
		name = frappe.get_cached_value("Account", b.account, "account_name")
		if not flt(b.float_amount) or not b.custodian:
			issues.append(_issue("petty", "box_setup", _("Petty cash box {0} has no {1}.").format(
				name, _("float or custodian") if not flt(b.float_amount) and not b.custodian else _("float") if not flt(b.float_amount)
				else _("custodian")), {"route": "/settings"}, "warning"))
			continue
		from erpnext.accounts.utils import get_balance_on

		balance = flt(get_balance_on(b.account, nowdate(), in_account_currency=True, ignore_account_permission=True))
		if balance < 0.2 * flt(b.float_amount):
			issues.append(_issue("petty", "box_low", _("Petty cash box {0} is down to {1} of its {2} float — top it up.").format(
				name, balance, flt(b.float_amount)), {"route": "/petty-cash"}, "warning"))
	stuck = frappe.db.sql(
		"""select count(distinct je.name) from `tabJournal Entry` je join `tabJournal Entry Account` jea on jea.parent=je.name
		   where je.docstatus=0 and je.voucher_type='Cash Entry' and jea.account in %s and je.creation < %s""",
		(tuple(b.account for b in _boxes()) or ("",), add_days(today, -3)))[0][0]
	if stuck:
		issues.append(_issue("petty", "awaiting", _("{0} petty cash voucher(s) have waited more than 3 days for approval.").format(stuck),
		                     {"route": "/petty-cash"}))

	# Money owed
	overdue = frappe.db.count("Sales Invoice", {"docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", add_days(today, -90)]})
	if overdue:
		issues.append(_issue("money", "overdue_90", _("{0} customer invoices are more than 90 days overdue.").format(overdue),
		                     {"route": "/receivables"}, "warning"))

	# Next year's fiscal year
	next_year = add_days(get_last_day(today.replace(month=12)), 1)
	if not frappe.db.exists("Fiscal Year", {"year_start_date": ["<=", next_year], "year_end_date": [">=", next_year]}):
		issues.append(_issue("setup", "fiscal_year", _("There is no fiscal year for {0} yet.").format(next_year.year),
		                     {"desk_url": "/app/fiscal-year/new"}, "warning"))

	counts = {}
	for i in issues:
		counts[i["group"]] = counts.get(i["group"], 0) + 1
	return dict(issues=issues, counts=counts)
