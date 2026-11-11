# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Sales Invoice → the plain dict `ubl.build` takes.

Standard (B2B, cleared) or simplified (B2C, reported): a Company customer with a VAT number
(`tax_id`) gets a standard invoice; everyone else a simplified one.
"""

import json

import frappe
from frappe import _
from frappe.utils import cstr, flt, get_time

from erp_overrides.zatca import ubl


def kind(doc) -> str:
	customer_type, tax_id = frappe.get_cached_value("Customer", doc.customer, ["customer_type", "tax_id"])
	return "standard" if customer_type == "Company" and (doc.tax_id or tax_id) else "simplified"


def doc_type(doc) -> str:
	if doc.is_return:
		return "credit"
	if doc.get("is_debit_note"):
		return "debit"
	return "invoice"


def seller(settings) -> dict:
	return dict(
		name=frappe.get_cached_value("Company", settings.company, "company_name"),
		vat=settings.vat_number,
		crn=settings.crn,
		street=settings.street,
		building=settings.building_number,
		district=settings.district,
		city=settings.city,
		postal_code=settings.postal_code,
	)


def buyer(doc) -> dict | None:
	name = doc.customer_name or doc.customer
	tax_id = doc.tax_id or frappe.get_cached_value("Customer", doc.customer, "tax_id")
	address = frappe.db.get_value(
		"Address",
		doc.customer_address,
		["address_line1", "address_line2", "city", "pincode", "zatca_building_number", "zatca_district"],
		as_dict=True,
	) if doc.customer_address else None
	party = dict(name=name, vat=tax_id)
	if address:
		party.update(
			street=address.address_line1,
			building=address.zatca_building_number,
			district=address.zatca_district or address.address_line2,
			city=address.city,
			postal_code=address.pincode,
		)
	return party


def _vat_percent(doc, row) -> float:
	"""The row's VAT rate: its item tax template if it has one, else the invoice's On Net Total taxes."""
	if row.get("item_tax_rate"):
		rates = json.loads(row.item_tax_rate or "{}")
		if rates:
			return sum(flt(r) for r in rates.values())
	return sum(flt(t.rate) for t in doc.get("taxes") or [] if t.charge_type == "On Net Total")


def lines(doc, settings) -> list[dict]:
	out = []
	for row in doc.items:
		pct = _vat_percent(doc, row)
		line = dict(
			name=row.item_name or row.item_code,
			qty=abs(flt(row.qty)),
			# net_rate: after item and document discounts, before tax
			rate=abs(flt(row.net_rate or row.rate, 2)),
			tax_percent=pct,
			tax_category="S" if pct else "Z",
		)
		if not pct:
			line.update(exemption_code=settings.zero_rate_code, exemption_reason=settings.zero_rate_reason)
		out.append(line)
	return out


def to_dict(doc, settings, *, icv: int, pih: str, uuid: str) -> dict:
	k, t = kind(doc), doc_type(doc)
	return dict(
		kind=k,
		type=t,
		id=doc.name,
		uuid=uuid,
		issue_date=str(doc.posting_date),
		issue_time=get_time(doc.posting_time).strftime("%H:%M:%S"),
		supply_date=str(doc.posting_date),
		currency=doc.currency,
		icv=icv,
		pih=pih,
		billing_reference=doc.return_against,
		reason=cstr(doc.get("remarks")).strip()[:1000] or ("Goods returned" if t == "credit" else "Price adjustment"),
		payment_means="10" if doc.is_pos else "30",
		seller=seller(settings),
		buyer=buyer(doc) if k == "standard" else None,
		lines=lines(doc, settings),
	)


def check(doc, settings) -> list[str]:
	"""What would make ZATCA reject this invoice, in words a user can act on. Empty = good to go."""
	problems = []
	if doc.currency != "SAR":
		problems.append(_("ZATCA invoices must be in SAR in this proof of concept (this one is {0}).").format(doc.currency))
	if doc_type(doc) != "invoice" and not doc.return_against:
		problems.append(_("A credit or debit note must point at the original invoice (Return Against)."))
	if kind(doc) == "standard":
		b = buyer(doc) or {}
		missing = [label for key, label in (
			("street", _("street")), ("building", _("building number")), ("district", _("district")),
			("city", _("city")), ("postal_code", _("postal code")),
		) if not b.get(key)]
		if missing:
			problems.append(
				_("Customer {0} has a VAT number, so this is a standard (B2B) invoice and their address needs: {1}.")
				.format(doc.customer, ", ".join(missing))
			)
	t = ubl.totals(lines(doc, settings))
	if abs(float(t["total"]) - abs(flt(doc.grand_total))) > 0.05:
		problems.append(
			_("The ZATCA total ({0}) doesn't match the invoice's grand total ({1}). Check the VAT template.")
			.format(t["total"], abs(flt(doc.grand_total)))
		)
	return problems
