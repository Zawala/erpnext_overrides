# Copyright (c) 2026, Kelvin Zawala and contributors
# See license.txt
import base64
import csv
import io

import frappe
from frappe.tests import IntegrationTestCase

from erp_overrides.api import app_settings, sysadmin

LIST = "SATEST Selling"
ITEM = "SATEST-ITEM"


def user(email, roles=(), profiles=()):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True)
	doc = frappe.get_doc(dict(doctype="User", email=email, first_name=email.split("@")[0], send_welcome_email=0,
	                          user_type="System User"))
	doc.append_roles(*roles)
	for p in profiles:
		doc.append("role_profiles", {"role_profile": p})
	doc.insert(ignore_permissions=True)
	return doc


def price_list(name=LIST, enabled=1):
	if not frappe.db.exists("Price List", name):
		frappe.get_doc(dict(doctype="Price List", price_list_name=name, currency="USD", selling=1, enabled=enabled)).insert()
	else:
		frappe.db.set_value("Price List", name, "enabled", enabled)
	return name


def item(code=ITEM):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(dict(doctype="Item", item_code=code, item_name=code, item_group=frappe.db.get_value("Item Group", {"is_group": 0}),
		                    stock_uom="Nos", is_stock_item=0)).insert()
	return code


def b64_csv(rows):
	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow(sysadmin.PRICE_COLUMNS)
	w.writerows(rows)
	return base64.b64encode(buf.getvalue().encode()).decode()


class Base(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")


class TestAccess(Base):
	def test_only_system_managers(self):
		user("satest-clerk@example.com", roles=("Sales User",))
		frappe.set_user("satest-clerk@example.com")
		for call in (lambda: sysadmin.get_users(), lambda: sysadmin.get_user("Administrator"),
		             lambda: sysadmin.inspect("Administrator", doctype="Item"), lambda: sysadmin.get_price_lists(),
		             lambda: sysadmin.set_price(ITEM, LIST, 1), lambda: sysadmin.preview_import("x.csv", b64_csv([])),
		             lambda: sysadmin.get_home(), lambda: sysadmin.get_data_types(), lambda: sysadmin.get_recent_imports(),
		             lambda: sysadmin.create_import("Customer", "Insert New Records", "x.csv", "")):
			self.assertRaises(frappe.PermissionError, call)


class TestRoles(Base):
	def test_add_and_remove(self):
		u = user("satest-roles@example.com", roles=("Sales User",))
		out = sysadmin.save_roles(u.name, add=["Accounts User"], remove=["Sales User"])
		self.assertIn("Accounts User", out["roles"])
		self.assertNotIn("Sales User", out["roles"])

	def test_profiles_set_the_roles(self):
		profile = frappe.get_all("Role Profile", pluck="name", limit=1)
		if not profile:
			self.skipTest("no role profiles")
		u = user("satest-profile@example.com", roles=("Sales User",))
		diff = sysadmin.preview_role_profiles(u.name, profile)
		out = sysadmin.set_role_profiles(u.name, profile)
		self.assertEqual(out["role_profiles"], profile)
		# HRMS drops Employee from a user with no Employee record, so the saved roles can be fewer than previewed
		self.assertTrue(set(out["roles"]) <= set(diff["add"]) | set(diff["keep"]))
		self.assertTrue(diff["add"])
		# roles come from the profile now: adding one by hand is refused, not silently undone
		self.assertRaises(frappe.ValidationError, sysadmin.save_roles, u.name, add=["Stock User"])

	def test_guards(self):
		self.assertRaises(frappe.ValidationError, sysadmin.set_enabled, "Administrator", 0)
		me = user("satest-admin@example.com", roles=("System Manager",))
		frappe.set_user(me.name)
		self.assertRaises(frappe.ValidationError, sysadmin.set_enabled, me.name, 0)
		self.assertRaises(frappe.ValidationError, sysadmin.save_roles, me.name, remove=["System Manager"])

	def test_create_user(self):
		email = "satest-new@example.com"
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True)
		out = sysadmin.create_user(email, "Satest", roles=["Stock User"], send_welcome_email=0)
		self.assertEqual(out["roles"], ["Stock User"])
		self.assertRaises(frappe.ValidationError, sysadmin.create_user, email, "Again")


class TestInspector(Base):
	def test_missing_role_and_fix(self):
		u = user("satest-inspect@example.com", roles=("Sales User",))
		res = sysadmin.inspect(u.name, doctype="Bank Transaction")["results"][0]
		read = next(p for p in res["perms"] if p["ptype"] == "read")
		self.assertFalse(read["allowed"])
		fix = next(f for f in read["fixes"] if f["kind"] == "role")
		sysadmin.save_roles(u.name, add=[fix["role"]])
		frappe.clear_cache(user=u.name)
		frappe.local.role_permissions = {}
		res = sysadmin.inspect(u.name, doctype="Bank Transaction")["results"][0]
		self.assertTrue(next(p for p in res["perms"] if p["ptype"] == "read")["allowed"])

	def test_user_permission_is_reported(self):
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		u = user("satest-restricted@example.com", roles=("Accounts User",))
		frappe.get_doc(dict(doctype="User Permission", user=u.name, allow="Company", for_value=company, apply_to_all_doctypes=1)).insert()
		res = sysadmin.inspect(u.name, doctype="Payment Entry")["results"][0]
		self.assertEqual([r.for_value for r in res["restrictions"]], [company])

	def test_app_check_and_who_lacks(self):
		u = user("satest-app@example.com", roles=("Accounts User",))
		res = sysadmin.inspect(u.name, app="accounts")
		self.assertEqual({r["doctype"] for r in res["results"]} - set(sysadmin.FINANCE_DOCTYPES), set())
		lacking = [x["name"] for x in sysadmin.users_lacking("Bank Transaction")]
		self.assertNotIn(u.name, lacking)


class TestPrices(Base):
	def setUp(self):
		super().setUp()
		price_list()
		item()
		frappe.db.delete("Item Price", {"item_code": ITEM})

	def test_create_then_update(self):
		out = sysadmin.set_price(ITEM, LIST, 100)
		self.assertEqual(out["rate"], 100)
		self.assertRaises(frappe.ValidationError, sysadmin.set_price, ITEM, LIST, 5)  # already has one: edit it
		out = sysadmin.set_price(ITEM, LIST, 120, item_price=out["name"], expected=100)
		self.assertEqual(frappe.db.get_value("Item Price", out["name"], "price_list_rate"), 120)

	def test_someone_else_changed_it(self):
		out = sysadmin.set_price(ITEM, LIST, 100)
		frappe.db.set_value("Item Price", out["name"], "price_list_rate", 110)
		self.assertRaises(frappe.ValidationError, sysadmin.set_price, ITEM, LIST, 120, item_price=out["name"], expected=100)

	def test_several_prices_are_not_inline(self):
		sysadmin.set_price(ITEM, LIST, 100)
		customer = frappe.db.get_value("Customer", {"disabled": 0})
		if not customer:
			self.skipTest("needs a customer")
		frappe.get_doc(dict(doctype="Item Price", item_code=ITEM, price_list=LIST, customer=customer, price_list_rate=90)).insert()
		cell = sysadmin.get_items([LIST], search=ITEM)["items"][0]["prices"][LIST]
		self.assertEqual((cell["count"], cell["editable"]), (2, False))


class TestImport(Base):
	def setUp(self):
		super().setUp()
		price_list()
		item()
		frappe.db.delete("Item Price", {"item_code": ITEM})
		self.existing = sysadmin.set_price(ITEM, LIST, 100)["name"]

	def test_preview_statuses_and_apply(self):
		other = item("SATEST-ITEM-2")
		frappe.db.delete("Item Price", {"item_code": other})
		rows = [
			[self.existing, ITEM, "", LIST, "", "", 150, "", "", "", ""],   # changed
			["", other, "", LIST, "", "", 80, "", "", "", ""],               # new
			["", "SATEST-NOPE", "", LIST, "", "", 5, "", "", "", ""],         # unknown item
			["", other, "", LIST, "", "", "abc", "", "", "", ""],             # not a number
			[self.existing, ITEM, "", LIST, "", "", 160, "", "", "", ""],    # duplicate of row 2
		]
		p = sysadmin.preview_import("prices.csv", b64_csv(rows))
		self.assertEqual([r["status"] for r in p["rows"]], ["changed", "new", "error", "error", "error"])
		self.assertEqual(p["rows"][0]["changes"], [["price_list_rate", 100.0, 150.0]])
		self.assertEqual(frappe.db.get_value("Item Price", self.existing, "price_list_rate"), 100)  # preview writes nothing
		out = sysadmin.apply_import(p["token"])
		self.assertEqual((out["updated"], out["created"], out["skipped"], out["failed"]), (1, 1, 0, 0))
		self.assertEqual(frappe.db.get_value("Item Price", self.existing, "price_list_rate"), 150)
		self.assertTrue(frappe.db.exists("Item Price", {"item_code": other, "price_list": LIST, "price_list_rate": 80}))
		self.assertRaises(frappe.ValidationError, sysadmin.apply_import, p["token"])  # used up

	def test_row_without_id_or_date_updates_the_price(self):
		# a hand-made file: no item_price_id, no valid_from (ERPNext set one when the price was made)
		p = sysadmin.preview_import("prices.csv", b64_csv([["", ITEM, "", LIST, "", "", 175, "", "", "", ""]]))
		row = p["rows"][0]
		self.assertEqual((row["status"], row["item_price"], row["changes"]), ("changed", self.existing, [["price_list_rate", 100.0, 175.0]]))

	def test_changed_after_preview_is_skipped(self):
		p = sysadmin.preview_import("prices.csv", b64_csv([[self.existing, ITEM, "", LIST, "", "", 150, "", "", "", ""]]))
		frappe.db.set_value("Item Price", self.existing, "price_list_rate", 130)
		out = sysadmin.apply_import(p["token"])
		self.assertEqual((out["updated"], out["skipped"]), (0, 1))
		self.assertEqual(frappe.db.get_value("Item Price", self.existing, "price_list_rate"), 130)

	def test_export_round_trip_is_unchanged(self):
		rows = sysadmin._export_rows([LIST])
		p = sysadmin.preview_import("export.csv", b64_csv(rows))
		self.assertEqual({r["status"] for r in p["rows"]}, {"unchanged"})


def b64(text):
	return base64.b64encode(text.encode()).decode()


class TestDataImport(Base):
	"""The guided import runs Frappe's Data Import inline here (tests run it without the scheduler)."""

	def setUp(self):
		super().setUp()
		self.group = frappe.db.get_value("Customer Group", {"is_group": 0})
		self.territory = frappe.db.get_value("Territory", {"is_group": 0})

	def customers(self, *names):
		for n in names:
			gone = lambda n=n: [frappe.delete_doc("Customer", c, force=True)
			                    for c in frappe.get_all("Customer", {"customer_name": n}, pluck="name")]
			gone()
			self.addCleanup(lambda gone=gone: (gone(), frappe.db.commit()))  # nosemgrep  the importer commits each row

	def start(self, text, mode="Insert New Records"):
		check = sysadmin.create_import("Customer", mode, "customers.csv", b64(text))
		# a failed row rolls the whole transaction back, as it does after a real upload request has committed
		frappe.db.commit()  # nosemgrep
		self.addCleanup(lambda: (frappe.delete_doc("Data Import", check["name"], force=True), frappe.db.commit()))  # nosemgrep
		return check

	def test_types_and_other_search(self):
		types = {t["doctype"]: t for t in sysadmin.get_data_types()}
		self.assertIn("Customer", types)
		self.assertTrue(types["Journal Entry"]["submittable"])
		others = [d["doctype"] for d in sysadmin.search_doctypes("")]
		self.assertNotIn("Customer", others)  # already a card
		self.assertNotIn("DocType", others)  # blocked by Frappe
		self.assertRaises(frappe.ValidationError, sysadmin.get_data_type, "Sales Invoice Item")  # a child table

	def test_template_has_the_required_columns(self):
		sysadmin.export_data("Customer", template=1, fmt="CSV")
		header = next(csv.reader(io.StringIO(frappe.response.result)))
		self.assertIn("Customer Name", header)
		self.assertIn("Customer Group", header)

	def test_check_then_import(self):
		self.customers("SATEST Co A", "SATEST Co B")
		check = self.start(f"Customer Name,Customer Group,Territory,Notes\nSATEST Co A,{self.group},{self.territory},x\n"
		                   f"SATEST Co B,SATEST No Group,{self.territory},y\n")
		self.assertEqual(check["records"], 2)
		self.assertEqual(next(c for c in check["columns"] if c["header"] == "Notes")["state"], "unmatched")
		value = next(v for v in check["values"] if v["source"] == "SATEST No Group")
		self.assertEqual(value["rows"], [3])
		self.assertFalse(check["ready"])  # the unknown group must be matched or its row left out
		self.assertRaises(frappe.ValidationError, sysadmin.run_import, check["name"])
		frappe.clear_messages()

		check = sysadmin.save_import_choices(check["name"], values={value["id"]: self.group}, columns={"3": sysadmin.DONT_IMPORT})
		self.assertTrue(check["ready"])
		self.assertEqual(next(c for c in check["columns"] if c["header"] == "Notes")["state"], "left_out")
		out = sysadmin.run_import(check["name"])
		self.assertEqual((out["status"], out["succeeded"], out["failed"]), ("Success", 2, []), out)
		self.assertEqual(frappe.db.get_value("Customer", {"customer_name": "SATEST Co B"}, "customer_group"), self.group)
		self.assertEqual(sysadmin.get_recent_imports()[0]["name"], check["name"])

	def test_missing_required_column(self):
		check = self.start(f"Customer Group\n{self.group}\n")
		self.assertFalse(check["ready"])
		self.assertTrue(any("Customer Name" in p["message"] for p in check["must_fix"]))

	def test_update_needs_the_id_and_changes_the_record(self):
		self.customers("SATEST Co C")
		c = frappe.get_doc(dict(doctype="Customer", customer_name="SATEST Co C", customer_group=self.group,
		                        territory=self.territory)).insert()
		check = self.start("Customer Name,Tax ID\nSATEST Co C,123\n", "Update Existing Records")
		self.assertTrue(any("ID" in p["message"] for p in check["must_fix"]))
		check = self.start(f"ID,Tax ID\n{c.name},SATEST-TAX\n", "Update Existing Records")
		self.assertTrue(check["ready"], check["must_fix"])
		out = sysadmin.run_import(check["name"])
		self.assertEqual(out["succeeded"], 1)
		self.assertEqual(frappe.db.get_value("Customer", c.name, "tax_id"), "SATEST-TAX")

	def test_failed_row_is_reported_with_its_row(self):
		self.customers("SATEST Co D")
		check = self.start(f"ID,Customer Name,Customer Group,Territory\nSATEST-NOPE,SATEST Co D,{self.group},{self.territory}\n",
		                   "Update Existing Records")
		out = sysadmin.run_import(check["name"])
		self.assertEqual(out["succeeded"], 0)
		self.assertEqual(out["failed"][0]["rows"], [2])
		self.assertTrue(out["failed"][0]["reason"])


class TestDefaultPriceList(Base):
	def test_change_and_disabled_refused(self):
		before = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		change = lambda v: app_settings.save_settings("sysadmin", [dict(doctype="Selling Settings", fieldname="selling_price_list", value=v)])
		change(price_list())
		self.assertEqual(frappe.db.get_single_value("Selling Settings", "selling_price_list"), LIST)
		facts = sysadmin.price_list_facts(LIST)
		self.assertEqual(facts.currency, "USD")
		price_list("SATEST Off", enabled=0)
		self.assertRaises(frappe.ValidationError, change, "SATEST Off")
		if before:
			change(before)
