# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""ZATCA POC demo data. All of it is fictional; the VAT numbers only have the right shape.

	bench --site <site> execute erp_overrides.zatca.demo.seed        # company, VAT, customers, settings
	bench --site <site> execute erp_overrides.zatca.onboarding.run   # or the Onboard button
	bench --site <site> execute erp_overrides.zatca.demo.invoices    # B2B, B2C and a credit note, sent now

Separate from erp_overrides.demo (the Zimbabwe demo), which it doesn't touch.
"""

import frappe
from frappe.utils import nowdate

COMPANY = "Demo Saudi Trading Co"
ABBR = "DSTC"
PRICE_LIST = "KSA Selling"
ITEM = "ZATCA Demo Service"
VAT_ACCOUNT = f"VAT 15% - {ABBR}"
TAX_TEMPLATE = f"KSA VAT 15% - {ABBR}"
B2B = "Fictional Buyer LLC"
B2C = "Walk-in Customer KSA"

SELLER = dict(
	vat_number="399999999900003", crn="1010010000", street="King Fahd Rd", building_number="1234",
	district="Al Olaya", city="Riyadh", postal_code="12345",
)


def _leaf(doctype):
	"""Any non-group record of a tree doctype (Customer Group, Territory, Item Group)."""
	return frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="creation")


def _insert(doc):
	return frappe.get_doc(doc).insert(ignore_permissions=True)


def seed():
	frappe.db.set_value("Currency", "SAR", "enabled", 1)
	if not frappe.db.exists("Company", COMPANY):
		_insert(dict(
			doctype="Company", company_name=COMPANY, abbr=ABBR, country="Saudi Arabia", default_currency="SAR",
			create_chart_of_accounts_based_on="Standard Template", chart_of_accounts="Standard",
		))
	if not frappe.db.exists("Account", VAT_ACCOUNT):
		parent = frappe.db.get_value("Account", {"company": COMPANY, "account_name": "Duties and Taxes", "is_group": 1})
		_insert(dict(doctype="Account", company=COMPANY, account_name="VAT 15%", parent_account=parent,
		             account_type="Tax", tax_rate=15, account_currency="SAR"))
	if not frappe.db.exists("Sales Taxes and Charges Template", TAX_TEMPLATE):
		_insert(dict(doctype="Sales Taxes and Charges Template", title="KSA VAT 15%", company=COMPANY,
		             taxes=[dict(charge_type="On Net Total", account_head=VAT_ACCOUNT, rate=15, description="VAT 15%")]))
	if not frappe.db.exists("Price List", PRICE_LIST):
		_insert(dict(doctype="Price List", price_list_name=PRICE_LIST, currency="SAR", selling=1, enabled=1))
	if not frappe.db.exists("Item", ITEM):
		_insert(dict(doctype="Item", item_code=ITEM, item_name=ITEM, item_group=_leaf("Item Group"),
		             stock_uom="Nos", is_stock_item=0))

	if not frappe.db.exists("Customer", B2B):
		_insert(dict(doctype="Customer", customer_name=B2B, customer_type="Company", tax_id="399999999800003",
		             customer_group=_leaf("Customer Group"), territory=_leaf("Territory")))
		_insert(dict(
			doctype="Address", address_title=B2B, address_type="Billing", address_line1="Prince Sultan St",
			city="Jeddah", pincode="23456", country="Saudi Arabia", zatca_building_number="5678",
			zatca_district="Al Rawdah", is_primary_address=1, links=[dict(link_doctype="Customer", link_name=B2B)],
		))
	if not frappe.db.exists("Customer", B2C):
		_insert(dict(doctype="Customer", customer_name=B2C, customer_type="Individual",
		             customer_group=_leaf("Customer Group"), territory=_leaf("Territory")))

	# The main demo (erp_overrides.demo) limits its users to the Zimbabwe company with User Permissions;
	# let its accounts users see the Saudi company too, so the ZATCA flow can be shown as an accountant.
	for user in ("daniel@example.com", "lindiwe@example.com", "grace@example.com"):
		if frappe.db.exists("User", user) and frappe.db.exists("User Permission", {"user": user, "allow": "Company"}) \
				and not frappe.db.exists("User Permission", {"user": user, "allow": "Company", "for_value": COMPANY}):
			_insert(dict(doctype="User Permission", user=user, allow="Company", for_value=COMPANY))

	s = frappe.get_doc("ZATCA Settings")
	s.update(dict(company=COMPANY, environment="developer-portal", otp="123345", business_category="Trading", **SELLER))
	s.enabled = 1
	s.save(ignore_permissions=True)
	frappe.db.commit()
	print(f"{COMPANY} ready. Next: Onboard in ZATCA Settings (or bench execute erp_overrides.zatca.onboarding.run).")


def invoice(customer, items, submit=True):
	"""A SAR Sales Invoice for the demo company, with KSA VAT 15%."""
	doc = frappe.get_doc(dict(
		doctype="Sales Invoice", company=COMPANY, customer=customer, currency="SAR", conversion_rate=1,
		selling_price_list=PRICE_LIST, posting_date=nowdate(), due_date=nowdate(),
		taxes_and_charges=TAX_TEMPLATE,
		items=[dict(item_code=ITEM, item_name=name, qty=qty, rate=rate) for name, qty, rate in items],
		taxes=[dict(charge_type="On Net Total", account_head=VAT_ACCOUNT, rate=15, description="VAT 15%")],
	))
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def credit_note(against, qty=1):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

	doc = make_sales_return(against)
	for row in doc.items:
		row.qty = -abs(qty)
	doc.remarks = "Goods returned"
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def invoices():
	"""Submit a B2B invoice, a B2C invoice and a credit note, and send each one to ZATCA straight away
	(the background job would do the same once a worker picks it up)."""
	from erp_overrides.zatca.submit import send

	b2b = invoice(B2B, [("Network installation", 2, 1500), ("Support (hours)", 3, 199.99)])
	b2c = invoice(B2C, [("Router", 1, 349)])
	frappe.db.commit()
	cn = credit_note(b2c.name)
	frappe.db.commit()
	for doc in (b2b, b2c, cn):
		status = send(doc.zatca_submission)
		print(f"{doc.name:28} {doc.customer:22} {doc.grand_total:>10} SAR  → {status}")
	return [d.name for d in (b2b, b2c, cn)]
