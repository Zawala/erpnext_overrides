# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Supplier upload for the sales app (/sales/suppliers): Excel or CSV,
previewed row by row, then applied. A row whose supplier name already exists updates
that supplier; any other row creates one. Billing currency and payment terms are
required, so every supplier can be ordered from and billed.

Needs Supplier create and write permission. Changes are saved through the documents,
so the Version log shows who changed what.
"""
import frappe
from frappe import _
from frappe.utils import cstr

from erp_overrides.api.sysadmin import _read_file, _safe

COLUMNS = ("supplier_name", "supplier_group", "country", "billing_currency", "payment_terms", "tax_id",
           "email_id", "mobile_no", "address_line1", "city")
REQUIRED = ("supplier_name", "billing_currency", "payment_terms")
ALIASES = {"supplier": "supplier_name", "name": "supplier_name", "group": "supplier_group", "currency": "billing_currency",
           "default_currency": "billing_currency", "terms": "payment_terms", "payment_terms_template": "payment_terms",
           "email": "email_id", "phone": "mobile_no", "mobile": "mobile_no", "address": "address_line1", "tin": "tax_id",
           "bp_number": "tax_id", "vat_number": "tax_id"}
# file column → Supplier field, for comparing and saving
FIELDS = {"supplier_group": "supplier_group", "country": "country", "billing_currency": "default_currency",
          "payment_terms": "payment_terms", "tax_id": "tax_id", "email_id": "email_id", "mobile_no": "mobile_no"}
PREVIEW_TTL = 30 * 60


def can_import(user=None):
	return bool(frappe.has_permission("Supplier", "create", user=user) and frappe.has_permission("Supplier", "write", user=user))


def _require():
	if not can_import():
		frappe.throw(_("You need permission to create and edit suppliers."), frappe.PermissionError)


@frappe.whitelist()
def template():
	"""An empty file with the columns, and one example row."""
	_require()
	from frappe.utils.csvutils import build_csv_response

	example = ["Example Supplier (Pvt) Ltd", "Hardware", "Zimbabwe", "USD", _first_terms(), "", "accounts@example.co.zw",
	           "+263 77 000 0000", "1 Example Road", "Harare"]
	build_csv_response([list(COLUMNS), [_safe(v) for v in example]], "suppliers-template")


def _first_terms():
	return frappe.db.get_value("Payment Terms Template", {}, "name") or ""


def _lookups():
	return dict(
		groups={g.lower(): g for g in frappe.get_all("Supplier Group", pluck="name")},
		countries={c.lower(): c for c in frappe.get_all("Country", pluck="name")},
		currencies={c.lower(): c for c in frappe.get_all("Currency", filters={"enabled": 1}, pluck="name")},
		terms={t.lower(): t for t in frappe.get_all("Payment Terms Template", pluck="name")},
		suppliers={s.supplier_name.strip().lower(): s.name for s in frappe.get_all("Supplier", fields=["name", "supplier_name"])
		           if s.supplier_name},
	)


def _check(values, look):
	"""The row's values with names put right (case), and its errors."""
	errors, out = [], {}
	for col in COLUMNS:
		out[col] = cstr(values.get(col)).strip()
	if not out["supplier_name"]:
		errors.append(_("Supplier name is empty"))
	for col, key, label in (("supplier_group", "groups", _("Supplier group")), ("country", "countries", _("Country")),
	                        ("billing_currency", "currencies", _("Billing currency")),
	                        ("payment_terms", "terms", _("Payment terms"))):
		v = out[col]
		if not v:
			if col in REQUIRED:
				errors.append(_("{0} is required").format(label))
			continue
		found = look[key].get(v.lower())
		if not found:
			errors.append(_("{0} \"{1}\" doesn't exist").format(label, v) if col != "billing_currency"
			              else _("Billing currency \"{0}\" isn't an enabled currency").format(v))
		out[col] = found or v
	if out["address_line1"] and not (out["city"] and out["country"]):
		errors.append(_("An address needs a city and a country"))
	return out, errors


@frappe.whitelist(methods=["POST"])
def preview_import(filename: str, content: str):
	"""What each row would do: new, changed (with each change), unchanged or error.
	Nothing is written; apply_import takes the returned token within half an hour."""
	_require()
	raw = _read_file(filename, content, aliases=ALIASES, required=("supplier_name",))
	look = _lookups()
	rows, seen = [], set()
	for n, values in raw:
		v, errors = _check(values, look)
		key = v["supplier_name"].lower()
		if key and key in seen:
			errors.append(_("The same supplier is on an earlier row"))
		seen.add(key)
		existing = look["suppliers"].get(key)
		changes = []
		if existing and not errors:
			doc = frappe.db.get_value("Supplier", existing, list(FIELDS.values()), as_dict=True)
			changes = [(col, doc.get(field) or "", v[col]) for col, field in FIELDS.items()
			           if v[col] and cstr(doc.get(field)) != v[col]]
			if v["address_line1"] and not frappe.db.get_value("Supplier", existing, "supplier_primary_address"):
				changes.append(("address_line1", "", f"{v['address_line1']}, {v['city']}"))
		status = "error" if errors else "changed" if changes else "unchanged" if existing else "new"
		rows.append(dict(row=n, status=status, supplier=existing, values=v, changes=changes, errors=errors))
	token = frappe.generate_hash(length=16)
	frappe.cache.set_value(f"erp_overrides:supplier_import:{token}", dict(user=frappe.session.user, filename=filename, rows=rows),
	                       expires_in_sec=PREVIEW_TTL)
	totals = {s: sum(1 for r in rows if r["status"] == s) for s in ("new", "changed", "unchanged", "error")}
	return dict(token=token, filename=filename, rows=rows, totals=totals)


@frappe.whitelist(methods=["POST"])
def apply_import(token: str):
	"""Create the new suppliers and update the changed ones from a preview."""
	_require()
	data = frappe.cache.get_value(f"erp_overrides:supplier_import:{token}")
	if not data or data["user"] != frappe.session.user:
		frappe.throw(_("This preview has expired. Upload the file again."))
	created = updated = 0
	failed = []
	for row in data["rows"]:
		if row["status"] not in ("new", "changed"):
			continue
		v = row["values"]
		frappe.db.savepoint("supplier_row")
		try:
			if row["status"] == "new":
				doc = frappe.new_doc("Supplier")
				doc.supplier_name = v["supplier_name"]
				doc.supplier_group = v["supplier_group"] or frappe.db.get_single_value("Buying Settings", "supplier_group") \
					or "All Supplier Groups"
				doc.supplier_type = "Company"
			else:
				doc = frappe.get_doc("Supplier", row["supplier"])
			for col, field in FIELDS.items():
				if v[col]:
					doc.set(field, v[col])
			if v["address_line1"] and not doc.get("supplier_primary_address"):
				doc.update(dict(address_line1=v["address_line1"], city=v["city"], country=v["country"]))
				if not doc.is_new():
					_add_address(doc)
			doc.save()
			if row["status"] == "new":
				created += 1
			else:
				updated += 1
		except Exception as e:
			frappe.db.rollback(save_point="supplier_row")
			frappe.clear_last_message()
			failed.append(dict(row=row["row"], supplier_name=v["supplier_name"], reason=cstr(e) or e.__class__.__name__))
	frappe.cache.delete_value(f"erp_overrides:supplier_import:{token}")
	return dict(created=created, updated=updated, failed=len(failed), failed_rows=failed)


def _add_address(doc):
	"""ERPNext makes the primary address only for a new supplier; this does it for an existing one."""
	from erpnext.selling.doctype.customer.customer import make_address
	from frappe.contacts.doctype.address.address import get_address_display

	address = make_address(doc)
	doc.supplier_primary_address = address.name
	doc.primary_address = get_address_display(address.name)


@frappe.whitelist()
def get_supplier_gaps():
	"""How many suppliers can't yet be billed properly: no billing currency or no payment terms."""
	_require()
	rows = frappe.get_all("Supplier", filters={"disabled": 0}, fields=["name", "supplier_name", "default_currency", "payment_terms"])
	missing = [r for r in rows if not r.default_currency or not r.payment_terms]
	return dict(total=len(rows), missing=len(missing), examples=[r.supplier_name or r.name for r in missing[:8]])
