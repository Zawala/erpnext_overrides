# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""Bi-weekly reviews, a starting point (erp_overrides.reviews):

1. Employee Feedback Criteria: Quality of work, Delivery on commitments, Collaboration, Initiative.
2. Review Form "Bi-weekly check-in": the employee's wins, blockers, priorities and support
   needed; the manager's rating per criterion, comments and agreed priorities.
3. Appraisal Template "Staff Appraisal": KRAs Role responsibilities (60%) and Customers and
   team (40%), and those four criteria at 25% each, so a review's ratings count in an
   appraisal as soon as HR starts an Appraisal Cycle with it. HR can change the KRAs.

No Review Schedule: HR decides who and when. Anything already there is left alone.
"""
import frappe

CRITERIA = ("Quality of work", "Delivery on commitments", "Collaboration", "Initiative")
FORM = "Bi-weekly check-in"
TEMPLATE = "Staff Appraisal"
KRAS = (("Role responsibilities", 60), ("Customers and team", 40))

QUESTIONS = [
	("What went well in the last two weeks?", "Text", "Employee", 1, None, None),
	("What got in your way?", "Text", "Employee", 0, "Blockers, delays, anything you needed and didn't have", None),
	("Your priorities for the next two weeks", "Text", "Employee", 1, None, None),
	("What support do you need?", "Text", "Employee", 0, None, None),
	("Quality of work", "Rating", "Manager", 1, "1 = well below what the role needs, 5 = outstanding", "Quality of work"),
	("Delivery on commitments", "Rating", "Manager", 1, "Did they do what they said they would, on time?", "Delivery on commitments"),
	("Collaboration", "Rating", "Manager", 1, "Working with the team, customers and other departments", "Collaboration"),
	("Initiative", "Rating", "Manager", 1, "Finding and fixing problems without being asked", "Initiative"),
	("Agreed priorities for the next two weeks", "Text", "Manager", 0, None, None),
]


def execute():
	for c in CRITERIA:
		if not frappe.db.exists("Employee Feedback Criteria", c):
			frappe.get_doc(dict(doctype="Employee Feedback Criteria", criteria=c)).insert(ignore_permissions=True)
	if not frappe.db.exists("Review Form", FORM):
		frappe.get_doc(dict(
			doctype="Review Form", title=FORM, active=1,
			intro="Ten minutes every two weeks: you say how it went, your manager adds ratings and comments.",
			questions=[dict(label=l, kind=k, answered_by=by, required=r, help=h, criteria=c) for l, k, by, r, h, c in QUESTIONS],
		)).insert(ignore_permissions=True)
		print(f"Review Form {FORM} created")
	for kra, _weight in KRAS:
		if not frappe.db.exists("KRA", kra):
			frappe.get_doc(dict(doctype="KRA", title=kra)).insert(ignore_permissions=True)
	if not frappe.db.exists("Appraisal Template", TEMPLATE):
		frappe.get_doc(dict(
			doctype="Appraisal Template", template_title=TEMPLATE,
			description="Rated from the bi-weekly reviews (Employee Performance Feedback) and the self-appraisal.",
			goals=[dict(key_result_area=k, per_weightage=w) for k, w in KRAS],
			rating_criteria=[dict(criteria=c, per_weightage=100 / len(CRITERIA)) for c in CRITERIA],
		)).insert(ignore_permissions=True)
		print(f"Appraisal Template {TEMPLATE} created")
