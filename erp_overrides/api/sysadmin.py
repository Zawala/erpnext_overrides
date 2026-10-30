# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Backend for the admin app (/sys-admin): users and roles, a permission inspector
with suggested fixes, item prices (inline edits, export, preview-then-apply import),
and guided data import / export over Frappe's own Data Import.

System Managers only. Every change is saved through the documents themselves, so
Frappe's Version log records who changed what, as it does for edits made in desk.
"""
import base64
import csv
import io
import json

import frappe
from frappe import _
from frappe.model import no_value_fields
from frappe.permissions import _pop_debug_log, get_role_permissions
from frappe.utils import cint, cstr, flt, getdate, nowdate

from erp_overrides.api.accounts import FINANCE_DOCTYPES, POST_ROLES
from erp_overrides.api.hr import HR_DOCTYPES
from erp_overrides.api.sales import CHAIN_DOCTYPES

SYSTEM = "System Manager"
STANDARD_USERS = ("Administrator", "Guest")
AUTOMATIC_ROLES = ("All", "Guest", "Administrator", "Desk User")
PTYPES = ("read", "write", "create", "submit", "cancel", "delete", "export", "import")

# The roles that open each app and the doctypes that app reads; used by the "app access" check
APPS = (
	dict(key="sales", label="Sales", roles=("Sales User", "Sales Manager"), doctypes=CHAIN_DOCTYPES),
	dict(key="hr", label="HR admin", roles=("HR User", "HR Manager"), doctypes=HR_DOCTYPES),
	dict(key="approvals", label="HR approvals", roles=("Leave Approver", "Expense Approver"),
	     doctypes=("Leave Application", "Expense Claim")),
	dict(key="accounts", label="Accounts", roles=tuple(r for r in POST_ROLES if r != SYSTEM), doctypes=FINANCE_DOCTYPES),
	dict(key="stock", label="Items and prices", roles=("Item Manager", "Stock Manager", "Stock User"),
	     doctypes=("Item", "Item Price", "Price List")),
)
APP_ROLES = sorted({r for a in APPS for r in a["roles"]} | {SYSTEM})

PRICE_COLUMNS = ("item_price_id", "item_code", "item_name", "price_list", "currency", "uom", "price_list_rate",
                 "valid_from", "valid_upto", "customer", "supplier")
IMPORT_FIELDS = ("uom", "price_list_rate", "valid_from", "valid_upto", "customer", "supplier")
KEEP_IF_BLANK = ("uom", "valid_from")  # ERPNext fills these in on every price
PREVIEW_TTL = 30 * 60
LAST_IMPORT = "erp_overrides_last_price_import"


# ── Who is asking ────────────────────────────────────────────────────────────

def is_system_manager(user=None):
	return SYSTEM in frappe.get_roles(user)


def _require():
	if not is_system_manager():
		frappe.throw(_("The admin app is for System Managers."), frappe.PermissionError)


def _cached(key, compute, ttl=600):
	value = frappe.cache.get_value(key)
	if value is None:
		value = compute()
		frappe.cache.set_value(key, value, expires_in_sec=ttl)
	return value


def _system_users():
	return frappe.get_all("User", filters={"enabled": 1, "user_type": "System User", "name": ["not in", STANDARD_USERS]},
	                      pluck="name")


# ── Users ────────────────────────────────────────────────────────────────────

def _app_access(user, roles=None):
	"""For each app the user has a role for: the doctypes they can't read."""
	roles = set(roles if roles is not None else frappe.get_roles(user))
	out = []
	for app in APPS:
		if not roles & set(app["roles"]):
			continue
		missing = [dt for dt in app["doctypes"] if frappe.db.exists("DocType", dt)
		           and not get_role_permissions(frappe.get_meta(dt), user=user).get("read")]
		out.append(dict(key=app["key"], label=app["label"], missing=missing))
	return out


@frappe.whitelist()
def get_users(search: str | None = None, enabled: str | None = None, role: str | None = None,
              start: int = 0, page_length: int = 50):
	_require()
	filters = [["name", "not in", STANDARD_USERS]]
	if enabled not in (None, ""):
		filters.append(["enabled", "=", cint(enabled)])
	if role:
		filters.append(["name", "in", frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent") or [""]])
	or_filters = [["full_name", "like", f"%{search}%"], ["name", "like", f"%{search}%"]] if search else None
	users = frappe.get_all("User", filters=filters, or_filters=or_filters,
	                       fields=["name", "full_name", "enabled", "user_type", "last_login", "user_image"],
	                       order_by="enabled desc, full_name asc", start=cint(start), page_length=cint(page_length))
	names = [u.name for u in users] or [""]
	roles, profiles = {}, {}
	for r in frappe.get_all("Has Role", filters={"parent": ["in", names], "parenttype": "User"}, fields=["parent", "role"]):
		roles.setdefault(r.parent, []).append(r.role)
	for p in frappe.get_all("User Role Profile", filters={"parent": ["in", names], "parenttype": "User"},
	                        fields=["parent", "role_profile"]):
		profiles.setdefault(p.parent, []).append(p.role_profile)
	for u in users:
		mine = roles.get(u.name, [])
		u.roles = len([r for r in mine if r not in AUTOMATIC_ROLES])
		u.role_profiles = profiles.get(u.name, [])
		u.apps = _app_access(u.name, mine) if u.enabled and u.user_type == "System User" else []
		u.gaps = sum(len(a["missing"]) for a in u.apps)
	total = len(frappe.get_all("User", filters=filters, or_filters=or_filters, pluck="name"))
	return dict(users=users, total=total)


def _assignable_roles():
	return frappe.get_all("Role", filters={"disabled": 0, "desk_access": 1, "name": ["not in", AUTOMATIC_ROLES]},
	                      pluck="name", order_by="name")


@frappe.whitelist()
def get_user(user: str):
	_require()
	doc = frappe.get_doc("User", user)
	mine = [r.role for r in doc.roles]
	profiles = [p.role_profile for p in doc.role_profiles]
	return dict(
		name=doc.name, full_name=doc.full_name, email=doc.email, enabled=doc.enabled, user_type=doc.user_type,
		last_login=doc.last_login, user_image=doc.user_image, is_self=doc.name == frappe.session.user,
		standard=doc.name in STANDARD_USERS,
		roles=[r for r in mine if r not in AUTOMATIC_ROLES],
		role_profiles=profiles,
		# roles that come from a profile can't be changed one by one: the profile puts them back on save
		roles_from_profiles=bool(profiles),
		all_roles=_assignable_roles(), app_roles=APP_ROLES,
		all_profiles=[dict(name=p, roles=_profile_roles(p)) for p in frappe.get_all("Role Profile", pluck="name", order_by="name")],
		user_permissions=frappe.get_all("User Permission", filters={"user": user},
		                                fields=["name", "allow", "for_value", "applicable_for", "apply_to_all_doctypes", "is_default"],
		                                order_by="allow, for_value"),
		apps=_app_access(user, mine),
		history=_user_history(user),
	)


def _profile_roles(profile):
	return [r.role for r in frappe.get_cached_doc("Role Profile", profile).roles]


def _user_history(user, limit=40):
	"""Changes to the user (roles, profiles, enabled) and their User Permissions, newest first."""
	ups = frappe.get_all("User Permission", filters={"user": user}, pluck="name")
	versions = frappe.get_all("Version", filters={"ref_doctype": "User", "docname": user},
	                          fields=["name", "owner", "creation", "data", "ref_doctype"], order_by="creation desc", limit=limit)
	if ups:
		versions += frappe.get_all("Version", filters={"ref_doctype": "User Permission", "docname": ["in", ups]},
		                           fields=["name", "owner", "creation", "data", "ref_doctype"], order_by="creation desc", limit=limit)
	out = []
	for v in sorted(versions, key=lambda v: v.creation, reverse=True)[:limit]:
		data = frappe.parse_json(v.data or "{}")
		lines = []
		for fieldname, old, new in data.get("changed") or []:
			if fieldname in ("enabled", "user_type", "full_name", "first_name", "last_name", "email"):
				lines.append(_("{0}: {1} → {2}").format(fieldname.replace("_", " "), cstr(old) or "—", cstr(new) or "—"))
		rows = {kind: [(f, r.get("role") or r.get("role_profile")) for f, r in data.get(kind) or [] if f in ("roles", "role_profiles")]
		        for kind in ("added", "removed")}
		# a profile re-sync removes and re-adds rows: only the net change is news
		same = set(rows["added"]) & set(rows["removed"])
		for kind, sign in (("added", "+"), ("removed", "−")):
			for fieldname, value in rows[kind]:
				if (fieldname, value) not in same:
					lines.append(f"{sign} {_('profile') + ' ' if fieldname == 'role_profiles' else ''}{value}")
		if v.ref_doctype == "User Permission":
			lines = lines or [_("User Permission changed")]
		if lines:
			out.append(dict(by=frappe.utils.get_fullname(v.owner), when=v.creation, lines=lines))
	return out


def _guard(doc, removing=(), disabling=False):
	if doc.name in STANDARD_USERS:
		frappe.throw(_("{0} is a built-in user and can't be changed here.").format(doc.name))
	if doc.name == frappe.session.user and (disabling or SYSTEM in removing):
		frappe.throw(_("You can't disable yourself or remove your own System Manager role."))
	if (disabling and SYSTEM in [r.role for r in doc.roles]) or SYSTEM in removing:
		others = frappe.get_all("Has Role", filters={"role": SYSTEM, "parenttype": "User", "parent": ["not in", (doc.name, *STANDARD_USERS)]},
		                        pluck="parent")
		if not frappe.get_all("User", filters={"name": ["in", others or [""]], "enabled": 1}, limit=1):
			frappe.throw(_("{0} is the last enabled System Manager.").format(doc.full_name))


@frappe.whitelist(methods=["POST"])
def save_roles(user: str, add: list | str | None = None, remove: list | str | None = None):
	"""Add and remove roles one by one. Refused while role profiles set the user's roles."""
	_require()
	add, remove = frappe.parse_json(add or "[]"), frappe.parse_json(remove or "[]")
	doc = frappe.get_doc("User", user)
	_guard(doc, removing=remove)
	if doc.role_profiles:
		frappe.throw(_("{0}'s roles come from the role profile(s) {1}. Change the profiles, or clear them to set roles by hand.")
		             .format(doc.full_name, ", ".join(p.role_profile for p in doc.role_profiles)))
	valid = set(_assignable_roles())
	for r in add:
		if r not in valid:
			frappe.throw(_("{0} isn't a role that can be given here.").format(r))
	doc.append_roles(*add)
	doc.set("roles", [r for r in doc.roles if r.role not in remove])
	doc.save()
	return get_user(user)


@frappe.whitelist()
def preview_role_profiles(user: str, profiles: list | str):
	"""What setting these profiles would do to the user's roles."""
	_require()
	profiles = frappe.parse_json(profiles or "[]")
	current = {r.role for r in frappe.get_doc("User", user).roles if r.role not in AUTOMATIC_ROLES}
	if not profiles:
		return dict(add=[], remove=[], keep=sorted(current))
	target = {r for p in profiles for r in _profile_roles(p) if r not in AUTOMATIC_ROLES}
	return dict(add=sorted(target - current), remove=sorted(current - target), keep=sorted(current & target))


@frappe.whitelist(methods=["POST"])
def set_role_profiles(user: str, profiles: list | str):
	_require()
	profiles = frappe.parse_json(profiles or "[]")
	doc = frappe.get_doc("User", user)
	diff = preview_role_profiles(user, profiles)
	_guard(doc, removing=diff["remove"])
	doc.set("role_profiles", [dict(role_profile=p) for p in profiles])
	doc.role_profile_name = None
	doc.save()
	return get_user(user)


@frappe.whitelist(methods=["POST"])
def set_enabled(user: str, enabled: int):
	_require()
	doc = frappe.get_doc("User", user)
	_guard(doc, disabling=not cint(enabled))
	doc.enabled = cint(enabled)
	doc.save()
	return get_user(user)


@frappe.whitelist(methods=["POST"])
def create_user(email: str, first_name: str, last_name: str | None = None, roles: list | str | None = None,
                profiles: list | str | None = None, send_welcome_email: int = 1):
	_require()
	email = (email or "").strip().lower()
	if frappe.db.exists("User", email):
		frappe.throw(_("{0} already has a user.").format(email))
	doc = frappe.new_doc("User")
	doc.update(dict(email=email, first_name=first_name, last_name=last_name, user_type="System User",
	                send_welcome_email=cint(send_welcome_email)))
	profiles = frappe.parse_json(profiles or "[]")
	if profiles:
		doc.set("role_profiles", [dict(role_profile=p) for p in profiles])
	else:
		valid = set(_assignable_roles())
		doc.append_roles(*[r for r in frappe.parse_json(roles or "[]") if r in valid])
	doc.insert()
	return get_user(doc.name)


@frappe.whitelist(methods=["POST"])
def remove_user_permission(name: str):
	_require()
	user = frappe.db.get_value("User Permission", name, "user")
	frappe.delete_doc("User Permission", name)
	return get_user(user)


# ── Permission inspector ─────────────────────────────────────────────────────

def _role_breadth():
	"""role → number of doctypes it can read; a role that opens fewer doctypes is the
	smaller fix. Custom DocPerm replaces DocPerm for a doctype that has any."""
	def compute():
		custom = set(frappe.get_all("Custom DocPerm", pluck="parent", distinct=True))
		rows = frappe.get_all("DocPerm", filters={"read": 1, "permlevel": 0}, fields=["role", "parent"])
		rows = [r for r in rows if r.parent not in custom]
		rows += frappe.get_all("Custom DocPerm", filters={"read": 1, "permlevel": 0}, fields=["role", "parent"])
		out = {}
		for r in rows:
			out.setdefault(r.role, set()).add(r.parent)
		return {role: len(dts) for role, dts in out.items()}
	return _cached("erp_overrides:role_breadth", compute)


def _ptypes(meta):
	return [p for p in PTYPES if (p not in ("submit", "cancel") or meta.is_submittable) and (p != "import" or meta.allow_import)]


def _fixes(user, doc_roles, profiles, meta, ptype):
	"""Roles that grant `ptype` on this doctype, smallest first; app roles break ties."""
	granting = sorted({p.role for p in meta.permissions if cint(p.permlevel) == 0 and p.get(ptype) and not p.get("if_owner")
	                   and p.role not in AUTOMATIC_ROLES})
	if not granting:
		return [dict(kind="no_rule", text=_("No role grants {0} on {1}. Add a rule in Role Permission Manager.").format(_(ptype), _(meta.name)),
		             link=f"/app/permission-manager/{meta.name}")]
	breadth = _role_breadth()
	granting.sort(key=lambda r: (r not in APP_ROLES, breadth.get(r, 0), r))
	if profiles:
		# roles come from profiles, so the fix is a profile that carries one of these roles
		out = []
		for name in frappe.get_all("Role Profile", pluck="name", order_by="name"):
			if name in profiles:
				continue
			hit = [r for r in _profile_roles(name) if r in granting]
			if hit:
				out.append(dict(kind="profile", profile=name, role=hit[0],
				                text=_("Add the role profile {0} (it has {1})").format(name, hit[0])))
		return out[:3] or [dict(kind="profiles_block", text=_("No role profile has a role that grants this. Clear the user's profiles to add {0} by hand.").format(granting[0]))]
	return [dict(kind="role", role=r, also=breadth.get(r, 0),
	             text=_("Add the role {0}").format(r)) for r in granting[:3]]


def _restrictions(user, meta):
	"""User Permissions that limit which records of this doctype the user sees."""
	links = {df.options for df in meta.get_link_fields()} | {meta.name}
	ups = frappe.get_all("User Permission", filters={"user": user, "allow": ["in", list(links)]},
	                     fields=["name", "allow", "for_value", "applicable_for", "apply_to_all_doctypes"])
	return [u for u in ups if u.apply_to_all_doctypes or u.applicable_for == meta.name]


def _inspect_doctype(user, doctype):
	meta = frappe.get_meta(doctype)
	user_doc = frappe.get_cached_doc("User", user)
	roles = frappe.get_roles(user)
	profiles = [p.role_profile for p in user_doc.role_profiles]
	perms = get_role_permissions(meta, user=user)
	rows = []
	for ptype in _ptypes(meta):
		allowed = bool(perms.get(ptype))
		# "if owner" rules: the user reaches only the documents they created
		only_own = ptype in (perms.get("if_owner") or {})
		row = dict(ptype=ptype, allowed=allowed or only_own, only_own=only_own)
		if not row["allowed"]:
			frappe.has_permission(doctype, ptype, user=user, debug=True)
			row["why"] = _pop_debug_log()
			row["fixes"] = _fixes(user, roles, profiles, meta, ptype)
		rows.append(row)
	return dict(doctype=doctype, perms=rows, restrictions=_restrictions(user, meta))


@frappe.whitelist()
def inspect(user: str, doctype: str | None = None, app: str | None = None):
	"""Each permission type the user has or lacks on a doctype (or on every doctype an
	app needs), why, and the smallest fixes."""
	_require()
	u = frappe.db.get_value("User", user, ["name", "full_name", "enabled", "user_type"], as_dict=True)
	if not u:
		frappe.throw(_("No user {0}.").format(user))
	notes = []
	if not u.enabled:
		notes.append(_("{0} is disabled, so they can't log in at all.").format(u.full_name))
	if u.user_type != "System User":
		notes.append(_("{0} is a {1}: only System Users can open desk documents. Change the user type to System User.")
		             .format(u.full_name, u.user_type))
	if app:
		conf = next((a for a in APPS if a["key"] == app), None)
		if not conf:
			frappe.throw(_("Unknown app {0}.").format(app))
		doctypes = [dt for dt in conf["doctypes"] if frappe.db.exists("DocType", dt)]
	else:
		if not doctype or not frappe.db.exists("DocType", doctype):
			frappe.throw(_("Pick a document type."))
		doctypes = [doctype]
	return dict(user=u, notes=notes, results=[_inspect_doctype(user, dt) for dt in doctypes],
	            apps=[dict(key=a["key"], label=a["label"]) for a in APPS])


@frappe.whitelist()
def users_lacking(doctype: str, ptype: str = "read"):
	"""Enabled System Users without `ptype` on a doctype."""
	_require()
	meta = frappe.get_meta(doctype)
	out = []
	for user in _system_users():
		if not get_role_permissions(meta, user=user).get(ptype):
			out.append(dict(name=user, full_name=frappe.utils.get_fullname(user)))
	return out


# ── Items and prices ─────────────────────────────────────────────────────────

def _is_general(p, stock_uom, today):
	"""One price that applies to everyone today, in the item's own unit."""
	return (not p.customer and not p.supplier and not p.get("batch_no")
	        and (not p.uom or p.uom == stock_uom)
	        and (not p.valid_from or getdate(p.valid_from) <= today)
	        and (not p.valid_upto or getdate(p.valid_upto) >= today))


@frappe.whitelist()
def get_price_lists():
	_require()
	lists = frappe.get_all("Price List", fields=["name", "currency", "enabled", "selling", "buying"], order_by="name")
	counts = dict(frappe.db.sql("select price_list, count(*) from `tabItem Price` group by price_list"))
	for pl in lists:
		pl.prices = counts.get(pl.name, 0)
	return dict(lists=lists, selling_default=frappe.db.get_single_value("Selling Settings", "selling_price_list"),
	            buying_default=frappe.db.get_single_value("Buying Settings", "buying_price_list"))


@frappe.whitelist()
def get_items(price_lists: list | str, search: str | None = None, item_group: str | None = None,
              disabled: int = 0, missing_in: str | None = None, start: int = 0, page_length: int = 50):
	"""Items with, per chosen price list, the price shown in the cell: one editable
	general price, nothing yet (a new one can be typed), or a count of several."""
	_require()
	price_lists = frappe.parse_json(price_lists) if isinstance(price_lists, str) else price_lists
	filters = [["disabled", "=", cint(disabled)]]
	if item_group:
		filters.append(["item_group", "descendants of (inclusive)", item_group])
	if missing_in:
		priced = frappe.get_all("Item Price", filters={"price_list": missing_in}, pluck="item_code", distinct=True)
		if priced:
			filters.append(["name", "not in", priced])
	or_filters = [["item_code", "like", f"%{search}%"], ["item_name", "like", f"%{search}%"]] if search else None
	items = frappe.get_all("Item", filters=filters, or_filters=or_filters,
	                       fields=["name as item_code", "item_name", "item_group", "stock_uom", "disabled", "is_sales_item", "is_purchase_item"],
	                       order_by="item_name asc", start=cint(start), page_length=cint(page_length))
	total = frappe.db.count("Item", filters=filters) if not or_filters else len(
		frappe.get_all("Item", filters=filters, or_filters=or_filters, pluck="name"))
	codes = [i.item_code for i in items] or [""]
	prices = frappe.get_all("Item Price", filters={"item_code": ["in", codes], "price_list": ["in", price_lists or [""]]},
	                        fields=["name", "item_code", "price_list", "price_list_rate", "currency", "uom", "customer",
	                                "supplier", "batch_no", "valid_from", "valid_upto", "modified"])
	by = {}
	for p in prices:
		by.setdefault((p.item_code, p.price_list), []).append(p)
	today = getdate(nowdate())
	for i in items:
		i.prices = {}
		for pl in price_lists or []:
			rows = by.get((i.item_code, pl), [])
			if not rows:
				i.prices[pl] = dict(count=0, editable=True)
			elif len(rows) == 1 and _is_general(rows[0], i.stock_uom, today):
				p = rows[0]
				i.prices[pl] = dict(count=1, editable=True, name=p.name, rate=p.price_list_rate, uom=p.uom or i.stock_uom,
				                    currency=p.currency, modified=p.modified)
			else:
				i.prices[pl] = dict(count=len(rows), editable=False)
	return dict(items=items, total=total)


@frappe.whitelist()
def get_item_prices(item_code: str, price_list: str):
	_require()
	return frappe.get_all("Item Price", filters={"item_code": item_code, "price_list": price_list},
	                      fields=["name", "price_list_rate", "currency", "uom", "customer", "supplier", "batch_no",
	                              "valid_from", "valid_upto", "modified", "modified_by"], order_by="valid_from desc, modified desc")


@frappe.whitelist(methods=["POST"])
def set_price(item_code: str, price_list: str, rate: float, item_price: str | None = None, expected: float | None = None):
	"""Change one Item Price, or create the item's first price in a list. `expected` is
	the rate the user saw: if someone changed it since, nothing is overwritten."""
	_require()
	rate = flt(rate)
	if rate < 0:
		frappe.throw(_("A price can't be negative."))
	if item_price:
		doc = frappe.get_doc("Item Price", item_price)
		if (doc.item_code, doc.price_list) != (item_code, price_list):
			frappe.throw(_("That price belongs to another item or list."))
		if expected is not None and flt(doc.price_list_rate, 6) != flt(expected, 6):
			frappe.throw(_("{0} was changed to {1} by {2} since you opened it; reload and try again.")
			             .format(item_code, doc.price_list_rate, frappe.utils.get_fullname(doc.modified_by)))
		doc.price_list_rate = rate
		doc.save()
	else:
		if frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
			frappe.throw(_("{0} already has a price in {1}; edit that one.").format(item_code, price_list))
		doc = frappe.get_doc(dict(doctype="Item Price", item_code=item_code, price_list=price_list,
		                          uom=frappe.db.get_value("Item", item_code, "stock_uom"), price_list_rate=rate))
		doc.insert()
	return dict(name=doc.name, rate=doc.price_list_rate, uom=doc.uom, currency=doc.currency, modified=doc.modified)


@frappe.whitelist()
def get_price_history(item_code: str, price_list: str):
	"""Who changed this item's prices in a list, newest first."""
	_require()
	names = frappe.get_all("Item Price", filters={"item_code": item_code, "price_list": price_list}, pluck="name")
	if not names:
		return []
	out = []
	for v in frappe.get_all("Version", filters={"ref_doctype": "Item Price", "docname": ["in", names]},
	                        fields=["owner", "creation", "data"], order_by="creation desc", limit=30):
		for fieldname, old, new in frappe.parse_json(v.data or "{}").get("changed") or []:
			if fieldname in IMPORT_FIELDS:
				out.append(dict(by=frappe.utils.get_fullname(v.owner), when=v.creation, field=fieldname, old=old, new=new))
	return out


# ── Export ───────────────────────────────────────────────────────────────────

def _export_rows(price_lists, item_group=None, include_missing=0):
	filters = {"price_list": ["in", price_lists]}
	if item_group:
		filters["item_code"] = ["in", frappe.get_all("Item", filters=[["item_group", "descendants of (inclusive)", item_group]],
		                                             pluck="name") or [""]]
	prices = frappe.get_all("Item Price", filters=filters,
	                        fields=["name", "item_code", "item_name", "price_list", "currency", "uom", "price_list_rate",
	                                "valid_from", "valid_upto", "customer", "supplier"], order_by="price_list, item_code")
	rows = [[p.name, p.item_code, p.item_name, p.price_list, p.currency, p.uom, p.price_list_rate,
	         cstr(p.valid_from or ""), cstr(p.valid_upto or ""), p.customer or "", p.supplier or ""] for p in prices]
	if cint(include_missing):
		item_filters = [["disabled", "=", 0]]
		if item_group:
			item_filters.append(["item_group", "descendants of (inclusive)", item_group])
		items = frappe.get_all("Item", filters=item_filters, fields=["name", "item_name", "stock_uom"], order_by="name")
		for pl in price_lists:
			have = {p.item_code for p in prices if p.price_list == pl}
			currency = frappe.get_cached_value("Price List", pl, "currency")
			rows += [["", i.name, i.item_name, pl, currency, i.stock_uom, "", "", "", "", ""] for i in items if i.name not in have]
	return rows


@frappe.whitelist()
def export_prices(price_lists: list | str, item_group: str | None = None, include_missing: int = 0, fmt: str = "csv",
                  template: int = 0):
	_require()
	price_lists = frappe.parse_json(price_lists) if isinstance(price_lists, str) else price_lists
	rows = [] if cint(template) else _export_rows(price_lists or [], item_group, include_missing)
	name = "item-prices-template" if cint(template) else f"item-prices-{nowdate()}"
	if fmt == "xlsx":
		from openpyxl import Workbook

		wb = Workbook()
		ws = wb.active
		ws.title = "Item Prices"
		ws.append(list(PRICE_COLUMNS))
		for r in rows:
			ws.append([v if i == 6 else _safe(v) for i, v in enumerate(r)])
		buf = io.BytesIO()
		wb.save(buf)
		frappe.response.filename = f"{name}.xlsx"
		frappe.response.filecontent = buf.getvalue()
		frappe.response.type = "binary"
	else:
		from frappe.utils.csvutils import build_csv_response

		build_csv_response([list(PRICE_COLUMNS), *rows], name)


def _safe(v):
	"""Stop a spreadsheet treating a cell as a formula."""
	return f"'{v}" if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


# ── Import: preview, then apply ──────────────────────────────────────────────

ALIASES = {"item_price": "item_price_id", "id": "item_price_id", "name": "item_price_id", "rate": "price_list_rate",
           "price": "price_list_rate", "item": "item_code", "list": "price_list"}


def _read_file(filename, content, aliases=None, required=("item_code", "price_list", "price_list_rate")):
	"""(row number, {column: value}) for each non-empty row of an uploaded .xlsx or .csv."""
	aliases = ALIASES if aliases is None else aliases
	data = base64.b64decode(content)
	if filename.lower().endswith((".xlsx", ".xlsm")):
		from openpyxl import load_workbook

		ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
		table = [list(r) for r in ws.iter_rows(values_only=True)]
	else:
		text = data.decode("utf-8-sig", errors="replace")
		table = list(csv.reader(io.StringIO(text)))
	if not table:
		frappe.throw(_("The file is empty."))
	header = [aliases.get(k, k) for k in (cstr(h).strip().lower().replace(" ", "_") for h in table[0])]
	missing = set(required) - set(header)
	if missing:
		frappe.throw(_("The file needs the columns {0}. Download the template to see the layout.").format(", ".join(sorted(missing))))
	rows = []
	for n, r in enumerate(table[1:], start=2):
		values = {k: ("" if v is None else v) for k, v in zip(header, r)}
		if not any(cstr(v).strip() for v in values.values()):
			continue
		rows.append((n, {k: (v.lstrip("'").strip() if isinstance(v, str) else v) for k, v in values.items()}))
	return rows


def _date(v):
	if v in ("", None):
		return None
	return cstr(getdate(v))


def _norm(field, v):
	if field == "price_list_rate":
		return flt(v, 6)
	if field in ("valid_from", "valid_upto"):
		return cstr(v) if v else None
	return cstr(v or "") or None


def _key(r, stock_uom):
	return (r["item_code"], r["price_list"], r.get("uom") or stock_uom, r.get("customer"), r.get("supplier"), r.get("valid_from"))


@frappe.whitelist(methods=["POST"])
def preview_import(filename: str, content: str):
	"""Read the file and say what each row would do. Nothing is written; the result is
	kept for half an hour under a token that apply_import takes."""
	_require()
	raw = _read_file(filename, content)
	codes = {cstr(r.get("item_code")) for _n, r in raw}
	items = {i.name: i for i in frappe.get_all("Item", filters={"name": ["in", list(codes) or [""]]},
	                                           fields=["name", "item_name", "stock_uom", "disabled"])}
	lists = {p.name: p for p in frappe.get_all("Price List", fields=["name", "currency", "enabled"])}
	existing = frappe.get_all("Item Price", filters={"item_code": ["in", list(items) or [""]]},
	                          fields=["name", "item_code", "price_list", *IMPORT_FIELDS])
	by_name = {p.name: p for p in existing}
	by_key = {}  # (item, list, unit, customer, supplier) → prices; valid_from tells them apart when given
	for p in existing:
		stock_uom = items[p.item_code].stock_uom
		by_key.setdefault((p.item_code, p.price_list, p.uom or stock_uom, p.customer, p.supplier), []).append(p)

	seen, out = {}, []
	for n, r in raw:
		row = dict(row=n, item_code=cstr(r.get("item_code")), price_list=cstr(r.get("price_list")), errors=[], warnings=[],
		           changes=[])
		item, pl = items.get(row["item_code"]), lists.get(row["price_list"])
		if not row["item_code"]:
			row["errors"].append(_("No item code"))
		elif not item:
			row["errors"].append(_("No item {0}").format(row["item_code"]))
		elif item.disabled:
			row["warnings"].append(_("Item is disabled"))
		if not row["price_list"]:
			row["errors"].append(_("No price list"))
		elif not pl:
			row["errors"].append(_("No price list {0}").format(row["price_list"]))
		rate = cstr(r.get("price_list_rate")).replace(",", "")
		try:
			rate = float(rate)
			if rate < 0:
				row["errors"].append(_("Negative price"))
		except ValueError:
			row["errors"].append(_("Price {0} isn't a number").format(r.get("price_list_rate") or "(blank)"))
			rate = None
		values = dict(price_list_rate=rate, uom=cstr(r.get("uom")) or None, customer=cstr(r.get("customer")) or None,
		              supplier=cstr(r.get("supplier")) or None)
		for f in ("valid_from", "valid_upto"):
			try:
				values[f] = _date(r.get(f))
			except Exception:
				row["errors"].append(_("{0} {1} isn't a date").format(f.replace("_", " "), r.get(f)))
				values[f] = None
		for f, dt in (("uom", "UOM"), ("customer", "Customer"), ("supplier", "Supplier")):
			if values[f] and not frappe.db.exists(dt, values[f]):
				row["errors"].append(_("No {0} {1}").format(_(dt), values[f]))
		row["item_name"] = item.item_name if item else ""
		row["currency"] = pl.currency if pl else ""
		row["uom"] = values["uom"] or (item.stock_uom if item else "")
		row["values"] = values

		target = None
		ip_id = cstr(r.get("item_price_id"))
		if ip_id:
			target = by_name.get(ip_id)
			if not target:
				row["errors"].append(_("No Item Price {0}").format(ip_id))
			elif (target.item_code, target.price_list) != (row["item_code"], row["price_list"]):
				row["errors"].append(_("Item Price {0} is for {1} in {2}").format(ip_id, target.item_code, target.price_list))
		elif item and pl:
			found = by_key.get(_key({**values, **row}, item.stock_uom)[:5], [])
			if values["valid_from"]:
				found = [p for p in found if _date(p.valid_from) == values["valid_from"]]
			if len(found) == 1:
				target = found[0]
			elif len(found) > 1:
				row["errors"].append(_("{0} prices match this row; add its item_price_id or valid_from").format(len(found)))
		dup = target.name if target else (item and pl and _key({**values, **row}, item.stock_uom))
		if dup and dup in seen:
			row["errors"].append(_("Same price as row {0}").format(seen[dup]))
		elif dup:
			seen[dup] = n

		if row["errors"]:
			row["status"] = "error"
		elif target:
			row["item_price"] = target.name
			for f in IMPORT_FIELDS:
				if f in KEEP_IF_BLANK and not values[f]:
					continue  # a blank unit or start date leaves the price's own
				new = values[f]
				old = _norm(f, target.get(f) if f not in ("valid_from", "valid_upto") else _date(target.get(f)))
				if _norm(f, new) != old:
					row["changes"].append([f, old, _norm(f, new)])
			row["status"] = "changed" if row["changes"] else "unchanged"
		else:
			row["status"] = "new"
		out.append(row)

	token = frappe.generate_hash(length=16)
	frappe.cache.set_value(f"erp_overrides:price_import:{token}", dict(user=frappe.session.user, filename=filename, rows=out),
	                       expires_in_sec=PREVIEW_TTL)
	totals = {s: sum(1 for r in out if r["status"] == s) for s in ("new", "changed", "unchanged", "error")}
	return dict(token=token, filename=filename, rows=out, totals=totals,
	            warnings=sum(1 for r in out if r["warnings"]))


@frappe.whitelist(methods=["POST"])
def apply_import(token: str):
	"""Write the new and changed rows of a preview. A price someone changed after the
	preview is skipped, not overwritten."""
	_require()
	data = frappe.cache.get_value(f"erp_overrides:price_import:{token}")
	if not data or data["user"] != frappe.session.user:
		frappe.throw(_("This preview has expired. Upload the file again."))
	created = updated = 0
	skipped, failed = [], []
	for row in data["rows"]:
		if row["status"] not in ("new", "changed"):
			continue
		frappe.db.savepoint("price_row")
		try:
			if row["status"] == "changed":
				doc = frappe.get_doc("Item Price", row["item_price"])
				moved = [f for f, old, _new in row["changes"]
				         if _norm(f, _date(doc.get(f)) if f in ("valid_from", "valid_upto") else doc.get(f)) != old]
				if moved:
					skipped.append(dict(row=row["row"], item_code=row["item_code"],
					                    reason=_("Changed by {0} after the preview").format(frappe.utils.get_fullname(doc.modified_by))))
					continue
				for f, _old, new in row["changes"]:
					doc.set(f, new)
				doc.save()
				updated += 1
			else:
				v = row["values"]
				doc = frappe.get_doc(dict(doctype="Item Price", item_code=row["item_code"], price_list=row["price_list"],
				                          uom=v["uom"] or frappe.db.get_value("Item", row["item_code"], "stock_uom"),
				                          price_list_rate=v["price_list_rate"], valid_from=v["valid_from"],
				                          valid_upto=v["valid_upto"], customer=v["customer"], supplier=v["supplier"]))
				doc.insert()
				created += 1
		except Exception as e:
			frappe.db.rollback(save_point="price_row")
			frappe.clear_last_message()
			failed.append(dict(row=row["row"], item_code=row["item_code"], reason=cstr(e) or e.__class__.__name__))
	frappe.cache.delete_value(f"erp_overrides:price_import:{token}")
	summary = dict(by=frappe.session.user, by_name=frappe.utils.get_fullname(frappe.session.user), when=frappe.utils.now(),
	               filename=data["filename"], created=created, updated=updated, skipped=len(skipped), failed=len(failed))
	frappe.db.set_default(LAST_IMPORT, json.dumps(summary))
	return dict(summary, skipped_rows=skipped, failed_rows=failed)


# ── Default price list ───────────────────────────────────────────────────────

@frappe.whitelist()
def price_list_facts(price_list: str):
	"""What a price list holds, so whoever makes it the default knows what they pick."""
	_require()
	pl = frappe.db.get_value("Price List", price_list, ["name", "currency", "enabled", "selling", "buying"], as_dict=True)
	if not pl:
		frappe.throw(_("No price list {0}.").format(price_list))
	pl.prices = frappe.db.count("Item Price", {"price_list": price_list})
	sales_items = frappe.db.count("Item", {"disabled": 0, "is_sales_item": 1})
	priced = frappe.db.sql("""select count(distinct ip.item_code) from `tabItem Price` ip join tabItem i on i.name = ip.item_code
	                          where ip.price_list = %s and i.disabled = 0 and i.is_sales_item = 1""", price_list)[0][0]
	pl.sales_items, pl.sales_items_without_price = sales_items, sales_items - priced
	pl.last_changed = frappe.db.sql("select max(modified) from `tabItem Price` where price_list = %s", price_list)[0][0]
	return pl


# ── Data import / export ─────────────────────────────────────────────────────
# A guided front for Frappe's own Data Import and exporter: the importing itself
# (child tables, links, insert or update, the background job and its log) is
# Frappe's, so an import started here also shows in desk under Data Import.

# The record types offered first. `common` are the columns the template carries
# beyond the required ones; "table.field" is a child-table column.
DATA_TYPES = (
	dict(doctype="Customer", label="Customers", icon="briefcase", group="Selling",
	     help="People and companies you sell to.",
	     common=("customer_name", "customer_type", "customer_group", "territory", "default_currency", "tax_id"),
	     rules=("Customer group and territory must already exist, spelt as they are in the system.",
	            "Customer type is Company or Individual.",
	            "Add emails and phone numbers by importing Contacts afterwards.")),
	dict(doctype="Supplier", label="Suppliers", icon="truck", group="Buying",
	     help="Companies you buy from.",
	     common=("supplier_name", "supplier_type", "supplier_group", "country", "default_currency", "tax_id"),
	     rules=("Supplier group and country must already exist.",
	            "Supplier type is Company or Individual.")),
	dict(doctype="Contact", label="Contacts", icon="user", group="Selling",
	     help="People at your customers and suppliers, with their emails and phone numbers.",
	     common=("first_name", "last_name", "company_name", "designation", "email_ids.email_id", "email_ids.is_primary",
	             "phone_nos.phone", "phone_nos.is_primary_mobile_no", "links.link_doctype", "links.link_name"),
	     rules=("To tie a contact to a customer, put Customer under Link Document Type and the customer's ID under Link Name.",
	            "A contact with two emails takes two rows: the second row leaves the person's columns blank and fills in only the email.")),
	dict(doctype="Address", label="Addresses", icon="map-pin", group="Selling",
	     help="Billing and shipping addresses of customers and suppliers.",
	     common=("address_title", "address_type", "address_line1", "address_line2", "city", "country", "phone", "email_id",
	             "is_primary_address", "is_shipping_address", "links.link_doctype", "links.link_name"),
	     rules=("Address type is Billing, Shipping, Office and so on.",
	            "Link it the same way as a contact: Link Document Type Customer (or Supplier) and Link Name the ID.")),
	dict(doctype="Lead", label="Leads", icon="target", group="Selling",
	     help="Prospects who may become customers.",
	     common=("first_name", "last_name", "company_name", "email_id", "mobile_no", "source", "status"),
	     rules=("Source must already exist under Lead Source.",)),
	dict(doctype="Item", label="Items", icon="package", group="Stock",
	     help="Products and services you buy, sell or keep in stock.",
	     common=("item_code", "item_name", "item_group", "stock_uom", "is_stock_item", "is_sales_item", "is_purchase_item",
	             "description"),
	     rules=("The item code is the item's ID: an update can't rename it.",
	            "Item group and unit of measure must already exist.",
	            "Tick-box columns take 1 for yes and 0 for no.",
	            "For prices use Import prices instead.")),
	dict(doctype="Employee", label="Employees", icon="users", group="HR",
	     help="Staff records used by HR and payroll.",
	     common=("first_name", "last_name", "gender", "date_of_birth", "date_of_joining", "company", "department",
	             "designation", "status", "cell_number", "personal_email"),
	     rules=("Write dates as YYYY-MM-DD, for example 1990-03-25.",
	            "Company, department and designation must already exist.")),
	dict(doctype="Journal Entry", label="Journal entries", icon="book-open", group="Accounts", advanced=True,
	     help="Opening balances and other journals. Each entry takes one row per account line.",
	     common=("voucher_type", "company", "posting_date", "user_remark", "accounts.account",
	             "accounts.debit_in_account_currency", "accounts.credit_in_account_currency", "accounts.party_type",
	             "accounts.party", "accounts.cost_center"),
	     rules=("Each entry's debits must equal its credits.",
	            "The first row of an entry carries the date and company; its other rows leave those blank and fill in only the account line.",
	            "Use voucher type Opening Entry for opening balances.")),
)
DONT_IMPORT = "Don't Import"
IMPORT_MODES = ("Insert New Records", "Update Existing Records")


def _data_type(doctype):
	"""The curated entry, or a plain one for any other importable doctype."""
	from frappe.core.doctype.data_import.data_import import BLOCKED_DOCTYPES

	meta = frappe.get_meta(doctype)
	if doctype in BLOCKED_DOCTYPES or meta.istable or not meta.allow_import:
		frappe.throw(_("{0} can't be imported or exported here.").format(_(doctype)))
	t = next((dict(d) for d in DATA_TYPES if d["doctype"] == doctype), None)
	return t or dict(doctype=doctype, label=_(doctype), icon="file", group="", help="", common=(), rules=())


def _id_field(meta):
	"""What the ID column holds: the name, or the field the name is made from."""
	if meta.autoname and meta.autoname.startswith("field:"):
		df = meta.get_field(meta.autoname[len("field:"):])
		if df:
			return df.fieldname, _(df.label)
	return "name", _("ID")


def _required(meta):
	"""Fields every new record needs and that nothing fills in by itself."""
	return [df for df in meta.fields if df.reqd and not df.default and df.fieldtype not in no_value_fields
	        and not (df.fieldtype == "Select" and df.options)]


def _card(t):
	dt = t["doctype"]
	return dict(doctype=dt, label=t["label"], icon=t["icon"], group=t["group"], help=t["help"], advanced=t.get("advanced", False),
	            count=frappe.db.count(dt), submittable=frappe.get_meta(dt).is_submittable,
	            can_import=bool(frappe.has_permission(dt, "import")), can_export=bool(frappe.has_permission(dt, "export")))


@frappe.whitelist()
def get_data_types():
	_require()
	return [_card(t) for t in DATA_TYPES if frappe.db.exists("DocType", t["doctype"])
	        and frappe.get_meta(t["doctype"]).allow_import]


@frappe.whitelist()
def search_doctypes(txt: str | None = None):
	"""Every other record type that can be imported."""
	_require()
	from frappe.core.doctype.data_import.data_import import BLOCKED_DOCTYPES

	filters = {"allow_import": 1, "istable": 0, "name": ["not in", [*BLOCKED_DOCTYPES, *(t["doctype"] for t in DATA_TYPES)]]}
	or_filters = {"name": ["like", f"%{txt}%"], "module": ["like", f"%{txt}%"]} if txt else None
	return [dict(doctype=d.name, module=d.module) for d in
	        frappe.get_all("DocType", filters=filters, or_filters=or_filters, fields=["name", "module"], order_by="name",
	                       limit=30)]


@frappe.whitelist()
def get_data_type(doctype: str):
	"""Everything the two wizards show about one record type: its rules, the ID, and
	its columns grouped into the record itself and each of its tables."""
	_require()
	t = _data_type(doctype)
	meta = frappe.get_meta(doctype)
	common = set(t["common"])
	required = {df.fieldname for df in _required(meta)}
	id_field, id_label = _id_field(meta)

	def columns(m, prefix=""):
		return [dict(key=f"{prefix}{df.fieldname}", label=_(df.label or df.fieldname), fieldtype=df.fieldtype,
		             options=df.options if df.fieldtype in ("Link", "Select") else None, read_only=bool(df.read_only),
		             required=not prefix and df.fieldname in required,
		             essential=f"{prefix}{df.fieldname}" in common or (not prefix and df.fieldname in required))
		        for df in m.fields if df.fieldtype not in no_value_fields and not df.hidden]

	tables = [dict(key=doctype, label=t["label"], columns=columns(meta))]
	for tf in meta.get_table_fields():
		if not tf.hidden:
			tables.append(dict(key=tf.fieldname, label=_(tf.label or tf.fieldname), columns=columns(frappe.get_meta(tf.options), f"{tf.fieldname}.")))
	card = _card(t)
	return dict(card, rules=t["rules"], tables=tables, id_field=id_field, id_label=id_label,
	            required=[_(df.label) for df in _required(meta)])


def _export_fields(doctype, columns, with_id):
	"""The wizard's "table.field" keys as the exporter's {table: [fields]}."""
	meta = frappe.get_meta(doctype)
	out = {doctype: []}
	for key in columns:
		table, _dot, field = key.rpartition(".")
		if table and meta.get_field(table):
			out.setdefault(table, ["name"] if with_id else []).append(field)
		elif not table:
			out[doctype].append(field)
	if with_id:
		out[doctype].insert(0, "name")
	return out


def _filters(doctype, filters):
	meta = frappe.get_meta(doctype)
	out = []
	for f in frappe.parse_json(filters) if isinstance(filters, str) else (filters or []):
		field, op, value = f
		if not (field == "name" or meta.get_field(field)) or op not in ("=", "!=", "like", ">", "<", ">=", "<=", "is"):
			frappe.throw(_("Can't filter on {0} {1}.").format(field, op))
		out.append([doctype, field, op, f"%{value}%" if op == "like" else value])
	return out


@frappe.whitelist()
def count_records(doctype: str, filters: list | str | None = None):
	_require()
	_data_type(doctype)
	return frappe.get_list(doctype, filters=_filters(doctype, filters), fields=[{"COUNT": "*", "as": "n"}])[0].n


@frappe.whitelist()
def export_data(doctype: str, columns: list | str | None = None, filters: list | str | None = None, fmt: str = "Excel",
                template: int = 0, with_id: int = 0):
	"""Download records (or a blank template) in the layout the importer reads back."""
	_require()
	from frappe.core.doctype.data_import.exporter import Exporter

	t = _data_type(doctype)
	columns = frappe.parse_json(columns) if isinstance(columns, str) else columns
	if not columns:  # the template: required columns plus the common ones
		meta = frappe.get_meta(doctype)
		columns = list(dict.fromkeys(c for c in [*(df.fieldname for df in _required(meta)), *t["common"]]
		                             if meta.get_field(c.split(".")[0])))
	Exporter(doctype, export_fields=_export_fields(doctype, columns, cint(with_id)), export_data=not cint(template),
	         export_filters=_filters(doctype, filters), file_type="CSV" if fmt == "CSV" else "Excel").build_response()
	name = f"{frappe.scrub(t['label']).replace('_', '-')}-{'template' if cint(template) else nowdate()}"
	if fmt == "CSV":
		frappe.response["doctype"] = name  # build_csv_response names the file after this
	else:
		frappe.response["filename"] = f"{name}.xlsx"


def _import_doc(name):
	di = frappe.get_doc("Data Import", name)
	di.check_permission("write")
	return di


def _attach(di, filename, content):
	if not filename.lower().endswith((".csv", ".xlsx")):
		frappe.throw(_("Upload a CSV or Excel (.xlsx) file."))
	f = frappe.get_doc(dict(doctype="File", file_name=filename, attached_to_doctype="Data Import", attached_to_name=di.name,
	                        is_private=1, content=base64.b64decode(content))).insert()
	di.import_file = f.file_url
	di.save()


@frappe.whitelist(methods=["POST"])
def create_import(doctype: str, import_type: str, filename: str, content: str, submit_after_import: int = 0):
	"""Save the uploaded file as a new Data Import and check it. Nothing is imported yet."""
	_require()
	_data_type(doctype)
	if import_type not in IMPORT_MODES:
		frappe.throw(_("Choose to add new records or update existing ones."))
	if not frappe.has_permission(doctype, "import"):
		frappe.throw(_("You can't import {0}: no role of yours has Import on it. The Permission inspector shows how to add it.")
		             .format(_(doctype)), frappe.PermissionError)
	di = frappe.get_doc(dict(doctype="Data Import", reference_doctype=doctype, import_type=import_type, mute_emails=1,
	                         submit_after_import=cint(submit_after_import) if frappe.get_meta(doctype).is_submittable else 0))
	di.insert()
	_attach(di, filename, content)
	return get_import_check(di.name)


@frappe.whitelist(methods=["POST"])
def replace_import_file(name: str, filename: str, content: str):
	"""A corrected file for the same import; column choices start over."""
	_require()
	di = _import_doc(name)
	_attach(di, filename, content)
	return get_import_check(di.name)


def _plain(message):
	from frappe.utils import strip_html

	return strip_html(cstr(message).replace("<br>", "\n")).strip()


def _column_key(col):
	df = col.get("df")
	if not df:
		return None
	table = col.get("child_table_df")
	return f"{table['fieldname']}.{df['fieldname']}" if table else df["fieldname"]


@frappe.whitelist()
def get_import_check(name: str):
	"""Frappe's import preview in plain terms: which column goes where, what must be
	fixed before importing, values that don't exist, and notes that don't block."""
	_require()
	di = _import_doc(name)
	meta = frappe.get_meta(di.reference_doctype)
	di.set_delimiters_flag()
	importer = di.get_importer()
	preview = importer.get_data_for_import_preview()
	cols = preview.columns[1:]  # the first is Frappe's row number

	columns = []
	for col in cols:
		left_out = col.get("map_to_field") == DONT_IMPORT
		key = None if left_out else _column_key(col)
		columns.append(dict(index=col.get("index"), header=cstr(col.get("header_title")), key=key,
		                    label=_(col["df"]["label"]) if key and col["df"].get("label") else None,
		                    state="left_out" if left_out else "matched" if key else "unmatched"))
	matched = {c["key"] for c in columns if c["key"]}

	must_fix, notes = [], []
	id_field, id_label = _id_field(meta)
	if di.import_type == "Update Existing Records":
		if not matched & {"name", id_field}:
			must_fix.append(dict(message=_("Updating needs the {0} column, so each row finds its record. Export the records first to get it.")
			                     .format(id_label)))
	else:
		for df in _required(meta):
			if df.fieldname not in matched:
				must_fix.append(dict(message=_("No column for {0}: every {1} needs one.").format(_(df.label), _(di.reference_doctype))))

	from frappe.core.doctype.data_import.value_mapping import get_blocking_warnings

	blocking = {id(w) for w in get_blocking_warnings(preview.warnings, importer.import_file, di)}
	skipped_rows = {cint(r.row_number) for r in di.skipped_rows}
	for w in preview.warnings:
		if w.get("type") == "value_mapping" or w.get("code") == "unknown_column" or (w.get("col") and "Skipping column" in cstr(w.get("message"))):
			continue  # the column list and the values to match show these
		entry = dict(message=_plain(w.get("message")), row=cint(w.get("row")) or None, col=w.get("col"))
		(must_fix if id(w) in blocking else notes).append(entry)

	unmatched = [dict(id=m.name, column=m.column_label, source=m.source_value, target=m.target_value or "",
	                  fieldtype=m.fieldtype, link_doctype=m.link_doctype,
	                  options=(m.select_options or "").split("\n") if m.fieldtype == "Select" else None,
	                  rows=frappe.parse_json(m.row_numbers or "[]"))
	             for m in di.value_mappings]
	open_values = [m for m in unmatched if not m["target"] and not set(m["rows"]) <= skipped_rows]

	return dict(name=di.name, doctype=di.reference_doctype, import_type=di.import_type, status=di.status,
	            filename=(di.import_file or "").rsplit("/", 1)[-1], records=di.payload_count, rows=preview.total_number_of_rows,
	            columns=columns, sample=[r[1:] for r in preview.data], skipped_rows=sorted(skipped_rows),
	            must_fix=must_fix, notes=notes, values=unmatched,
	            ready=not must_fix and not open_values and bool(di.payload_count))


@frappe.whitelist(methods=["POST"])
def save_import_choices(name: str, columns: dict | str | None = None, values: dict | str | None = None,
                        skip_rows: list | str | None = None):
	"""What the admin chose on the check step: where each column goes ({index: field
	key or "Don't Import"}), what each unknown value means ({mapping id: value}), and
	which rows to leave out."""
	_require()
	di = _import_doc(name)
	if di.status not in ("Pending", "Error"):
		frappe.throw(_("This import has already run."))
	if columns is not None:
		columns = frappe.parse_json(columns) if isinstance(columns, str) else columns
		options = frappe.parse_json(di.template_options or "{}")
		options.column_to_field_map = {str(k): v for k, v in columns.items()}
		di.template_options = frappe.as_json(options)
	if values is not None:
		values = frappe.parse_json(values) if isinstance(values, str) else values
		for m in di.value_mappings:
			if m.name in values:
				m.target_value = cstr(values[m.name]).strip()
	if skip_rows is not None:
		skip_rows = frappe.parse_json(skip_rows) if isinstance(skip_rows, str) else skip_rows
		di.set("skipped_rows", [dict(row_number=cint(r)) for r in sorted(set(skip_rows))])
	di.save()
	return get_import_check(di.name)


@frappe.whitelist(methods=["POST"])
def run_import(name: str):
	_require()
	di = _import_doc(name)
	check = get_import_check(name)
	if not check["ready"]:
		frappe.throw(_("Fix the problems on the check step first."))
	try:
		di.start_import()
	except frappe.ValidationError as e:
		if "Scheduler" in cstr(e):
			frappe.throw(_("Background jobs are switched off on this site, so imports can't run. Ask whoever looks after the server to enable the scheduler."))
		raise
	return get_import_result(name)


@frappe.whitelist()
def get_import_result(name: str):
	"""Progress while it runs, then what was added, updated and what failed and why."""
	_require()
	from frappe.core.doctype.data_import.data_import import get_import_logs, get_import_status

	di = _import_doc(name)
	status = get_import_status(name)
	failed = []
	for log in get_import_logs(name, "failed"):
		messages = frappe.parse_json(log.messages or "[]") or []
		text = "; ".join(_plain(m.get("message") or m.get("title") if isinstance(m, dict) else m) for m in messages)
		if not text and log.exception:
			text = cstr(log.exception).strip().splitlines()[-1]
		failed.append(dict(rows=frappe.parse_json(log.row_indexes or "[]"), reason=text or _("Could not be saved")))
	blocked = [_plain(w.get("message")) for w in frappe.parse_json(di.template_warnings or "[]")] if di.status == "Pending" else []
	return dict(name=di.name, doctype=di.reference_doctype, import_type=di.import_type, status=di.status,
	            total=status.get("total_records") or di.payload_count, done=status.get("processed_records", 0),
	            succeeded=status.get("success", 0), failed=failed, blocked=blocked,
	            list_url=f"/app/{frappe.scrub(di.reference_doctype).replace('_', '-')}")


@frappe.whitelist()
def get_recent_imports():
	_require()
	imports = frappe.get_all("Data Import", fields=["name", "reference_doctype", "import_type", "status", "owner", "creation",
	                                                "payload_count", "import_file"], order_by="creation desc", limit=20)
	counts = {(r.data_import, r.success): r.count for r in frappe.get_all(
		"Data Import Log", filters={"data_import": ["in", [i.name for i in imports] or [""]]},
		fields=["data_import", "success", {"COUNT": "*", "as": "count"}], group_by="data_import, success")}
	return [dict(name=i.name, doctype=i.reference_doctype, import_type=i.import_type, status=i.status,
	             by=frappe.utils.get_fullname(i.owner), when=i.creation, records=i.payload_count,
	             filename=(i.import_file or "").rsplit("/", 1)[-1],
	             succeeded=counts.get((i.name, 1), 0), failed=counts.get((i.name, 0), 0)) for i in imports]


# ── Home ─────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_home():
	_require()

	def gaps():
		out = []
		for user in _system_users():
			apps = [a for a in _app_access(user) if a["missing"]]
			if apps:
				out.append(dict(name=user, full_name=frappe.utils.get_fullname(user), apps=apps))
		return out

	selling = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	return dict(
		users=len(_system_users()),
		disabled=frappe.db.count("User", {"enabled": 0, "name": ["not in", STANDARD_USERS]}),
		gaps=_cached("erp_overrides:access_gaps", gaps),
		selling_price_list=selling,
		without_price=selling and price_list_facts(selling).sales_items_without_price,
		last_import=frappe.parse_json(frappe.db.get_default(LAST_IMPORT) or "null"),
	)
