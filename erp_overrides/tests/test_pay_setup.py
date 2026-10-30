# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, flt, get_first_day, nowdate

from erp_overrides.api import hr
from erp_overrides.api import pay_setup as ps
from erp_overrides.tests.test_hr_api import company, make_employee, payable_account

STRUCTURE, SLAB = "Staff 2026", "Income Tax USD 2026"
# $50 on a $1,000 gross: taxable goes from 960 (after the capped pension) to 1,010, so 40 is
# taxed at 25% and 10 at 30% (the 1,000 edge), plus the 3% levy on the tax
TRANSPORT_50_NET = 50 - (40 * 0.25 + 10 * 0.30) * 1.03


def rows_of(name):
	return next(s for s in ps.get_pay_setup()["structures"] if s["name"] == name)["rows"]


class TestPaySetup(IntegrationTestCase):
	"""Needs the demo payroll (erp_overrides.demo.seed): Staff 2026 and its tax slab."""

	def setUp(self):
		if not frappe.db.exists("Salary Structure", {"name": STRUCTURE, "docstatus": 1}) or \
				not frappe.db.exists("Income Tax Slab", {"name": SLAB, "docstatus": 1}):
			self.skipTest("run erp_overrides.demo.seed first")
		frappe.db.set_value("Company", company(), "default_payroll_payable_account", payable_account())
		frappe.clear_document_cache("Company", company())
		self.month = str(get_first_day(add_months(nowdate(), 1)))

	def test_plain_choices_round_trip(self):
		rows = {r["component"]: r for r in rows_of(STRUCTURE)}
		pension = rows["Pension (Capped)"]
		self.assertEqual((pension["method"], pension["rate"], pension["cap"]), ("capped", 5, 40))
		self.assertEqual((rows["Basic"]["method"], rows["Basic"]["rate"]), ("percent", 100))
		self.assertEqual(rows["Income Tax"]["method"], "tax")
		self.assertEqual((rows["Employer Levy"]["kind"], rows["Employer Levy"]["rate"]), ("employer", 1))
		for r in rows.values():  # each choice writes the formula it was read from
			self.assertEqual(ps.from_row(frappe._dict(ps.to_row(r)), "earnings" if r["kind"] == "earning" else "deductions")
			                 ["method"], r["method"])
		odd = ps.from_row(frappe._dict(salary_component="X", amount_based_on_formula=1, formula="B * 2 + 7"), "earnings")
		self.assertEqual(odd["method"], "formula")

	def test_preview_prices_a_draft_and_leaves_nothing(self):
		before = frappe.db.count("Salary Structure")
		now = ps.preview(structure_name=STRUCTURE, slab_name=SLAB, gross=1000, month=self.month)
		draft = rows_of(STRUCTURE) + [dict(kind="earning", component="Transport", method="fixed", amount=50,
		                                   is_tax_applicable=1)]
		after = ps.preview(structure=dict(rows=draft), slab_name=SLAB, gross=1000, month=self.month)
		self.assertNotIn("error", after, after)
		self.assertAlmostEqual(after["net"] - now["net"], TRANSPORT_50_NET, delta=0.01)
		self.assertEqual(frappe.db.count("Salary Structure"), before)
		bad = ps.preview(structure=dict(rows=draft + [dict(kind="deduction", component="Housing", method="fixed", amount=5)]),
		                 slab_name=SLAB, gross=1000)
		self.assertIn("Housing is an earning", bad["error"])

	def test_rules_are_explained(self):
		rows = rows_of(STRUCTURE)
		cases = [
			(rows + [dict(kind="deduction", component="Employer Levy", method="fixed", amount=5)], "twice"),
			(rows + [dict(kind="deduction", component="Employer Levy", method="tax")], "Only one line"),
			([r for r in rows if r["kind"] != "earning"], "at least one earning"),
			([dict(r, formula="B + Transport_allowance", method="formula") if r["component"] == "Basic" else r for r in rows],
			 "Transport_allowance"),
			([dict(r, of="gross_pay") if r["component"] == "Basic" else r for r in rows], "not of gross pay"),
			([dict(r, cap=0) if r["method"] == "capped" else r for r in rows], "the most it can be"),
		]
		for case, message in cases:
			with self.assertRaisesRegex(frappe.ValidationError, message):
				ps.validate_rows(case)

	def test_in_use_saves_a_version_and_people_move(self):
		emp = make_employee("PaySetup")
		hr.save_salaries(STRUCTURE, self.month, [{"employee": emp.name, "base": 1000, "agreed_net": 755.16}], SLAB)
		rows = rows_of(STRUCTURE) + [dict(kind="earning", component="Transport", method="fixed", amount=50,
		                                  is_tax_applicable=1)]
		saved = ps.save_structure(dict(name=STRUCTURE, original=STRUCTURE, rows=rows))
		self.assertEqual((saved["name"], saved["versioned_from"]), (f"{STRUCTURE} (v2)", STRUCTURE))
		self.assertEqual(frappe.db.get_value("Salary Structure", STRUCTURE, "docstatus"), 1)  # untouched

		later = str(add_months(self.month, 1))
		dry = ps.move_people("structure", STRUCTURE, saved["name"], later)
		me = next(r for r in dry["rows"] if r["employee"] == emp.name)
		self.assertAlmostEqual(me["net_new"] - me["net_now"], TRANSPORT_50_NET, delta=0.01)
		self.assertFalse(frappe.db.exists("Salary Structure Assignment", {"employee": emp.name, "from_date": later}))

		ps.move_people("structure", STRUCTURE, saved["name"], later, confirm=1)
		new = frappe.db.get_value("Salary Structure Assignment", {"employee": emp.name, "from_date": later, "docstatus": 1},
		                          ["salary_structure", "base", "agreed_net_pay", "income_tax_slab"], as_dict=True)
		self.assertEqual((new.salary_structure, flt(new.base), flt(new.agreed_net_pay), new.income_tax_slab),
		                 (saved["name"], 1000, 755.16, SLAB))

	def test_unused_structure_is_replaced_in_place(self):
		rows = [dict(kind="earning", component="Basic", method="percent", of="base", rate=100, depends_on_payment_days=1,
		             is_tax_applicable=1)]
		ps.save_structure(dict(name="PaySetup Test", rows=rows))
		ps.save_structure(dict(name="PaySetup Test", original="PaySetup Test",
		                       rows=rows + [dict(kind="earning", component="Housing", method="percent", rate=10,
		                                         is_tax_applicable=1)]))
		doc = frappe.get_doc("Salary Structure", "PaySetup Test")
		self.assertEqual((doc.docstatus, [e.formula for e in doc.earnings]), (1, ["base", "base * 0.1"]))
		self.assertFalse(frappe.db.exists("Salary Structure", "PaySetup Test (v2)"))

	def test_tax_bands_new_version_taxes_the_same(self):
		slab = next(s for s in ps.get_pay_setup()["slabs"] if s["name"] == SLAB)
		self.assertEqual(slab["bands"][1], dict(from_amount=100, to_amount=300, percent=20))  # as the tax authority publishes it
		emp = make_employee("PaySetupSlab")
		hr.save_salaries(STRUCTURE, self.month, [{"employee": emp.name, "base": 1000}], SLAB)
		saved = ps.save_slab(dict(slab, original=SLAB))
		self.assertEqual(saved["name"], f"{SLAB} (v2)")
		self.assertEqual(frappe.db.get_value("Taxable Salary Slab", {"parent": saved["name"], "percent_deduction": 20},
		                                     "from_amount"), 101)
		same = ps.preview(structure_name=STRUCTURE, slab_name=saved["name"], gross=1000, month=self.month)
		self.assertAlmostEqual(same["net"], ps.preview(structure_name=STRUCTURE, slab_name=SLAB, gross=1000,
		                                               month=self.month)["net"], places=2)
		dearer = dict(slab, bands=[dict(b, percent=b["percent"] + 1 if b["percent"] else 0) for b in slab["bands"]])
		self.assertLess(ps.preview(structure_name=STRUCTURE, slab=dearer, gross=1000, month=self.month)["net"], same["net"])
		with self.assertRaisesRegex(frappe.ValidationError, "should start where"):
			ps._slab_doc(dict(slab, bands=[slab["bands"][0], dict(slab["bands"][2])]), "x")

	def test_hr_user_reads_but_cannot_change(self):
		user = "paysetup.hruser@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(dict(doctype="User", email=user, first_name="PaySetup", send_welcome_email=0,
			                    roles=[dict(role="HR User")])).insert(ignore_permissions=True)
		frappe.set_user(user)
		self.addCleanup(frappe.set_user, "Administrator")
		self.assertFalse(ps.get_pay_setup()["can_edit"])
		with self.assertRaises(frappe.PermissionError):
			ps.save_structure(dict(name="Nope", rows=[]))
