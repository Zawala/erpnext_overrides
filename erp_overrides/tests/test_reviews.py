# Copyright (c) 2026, Kelvin Zawala and contributors
# See license.txt
"""Bi-weekly reviews (erp_overrides.reviews, erp_overrides.api.reviews)."""
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from erp_overrides import reviews
from erp_overrides.api import reviews as api
from erp_overrides.tests.test_hr_api import company, make_employee

FORM = "Bi-weekly check-in"


def make_user(email):
	if not frappe.db.exists("User", email):
		doc = frappe.get_doc(dict(doctype="User", email=email, first_name="Rev", send_welcome_email=0))
		doc.append_roles("Employee")
		doc.insert(ignore_permissions=True)
	return email


def employee_for(email, first_name, **kw):
	name = frappe.db.get_value("Employee", {"user_id": email})
	return frappe.get_doc("Employee", name) if name else make_employee(first_name, user_id=make_user(email), **kw)


def as_user(user, fn, *args, **kw):
	frappe.set_user(user)
	try:
		return fn(*args, **kw)
	finally:
		frappe.set_user("Administrator")


class TestReviews(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Review Form", FORM):
			raise cls.skipTest(cls, "run the reviews_setup_2026_10 patch first")
		cls.mgr_user = "rev-manager@example.com"
		cls.manager = employee_for(cls.mgr_user, "Boss").name

	def setUp(self):
		# a fresh employee and schedule per test: the first period ended yesterday, so its review opens today
		self.emp_user = make_user(f"rev-emp-{frappe.generate_hash(length=6)}@example.com")
		self.employee = make_employee("Reviewed", user_id=self.emp_user, reports_to=self.manager).name
		self.lonely = make_employee("Lonely").name  # no manager at all
		self.schedule = frappe.get_doc(dict(
			doctype="Review Schedule", title=f"REVTEST {frappe.generate_hash(length=6)}", active=1, review_form=FORM,
			frequency="Every 2 weeks", first_period_start=add_days(nowdate(), -14), window_days=5, company=company(),
			employees=[dict(employee=self.employee), dict(employee=self.lonely)],
		)).insert(ignore_permissions=True)

	def open_one(self):
		reviews.open_reviews()
		return frappe.get_doc("Review", {"schedule": self.schedule.name, "employee": self.employee})

	def answers(self, review, side):
		return {a.name: ("4" if a.kind == "Rating" else "Done well") for a in review.answers
		        if a.answered_by in (side, "Both")}

	def test_opens_once_per_period_and_skips_people_with_no_manager(self):
		first = reviews.open_reviews()
		again = reviews.open_reviews()
		mine = frappe.get_all("Review", filters={"schedule": self.schedule.name}, fields=["employee", "period_start", "due_on"])
		self.assertEqual([r.employee for r in mine], [self.employee])
		self.assertEqual((getdate(mine[0].period_start), getdate(mine[0].due_on)),
		                 (getdate(add_days(nowdate(), -14)), getdate(add_days(nowdate(), 4))))
		self.assertTrue(set(first) - set(again))
		self.assertFalse([n for n in again if frappe.db.get_value("Review", n, "schedule") == self.schedule.name])
		self.assertIn("Lonely", frappe.db.get_value("Review Schedule", self.schedule.name, "skipped"))

	def test_opening_emails_and_notifies_both(self):
		review = self.open_one()
		for user in (self.emp_user, self.mgr_user):
			self.assertTrue(frappe.db.exists("Notification Log", {"for_user": user, "document_name": review.name}))
			self.assertTrue(frappe.db.sql("""select 1 from `tabEmail Queue` q join `tabEmail Queue Recipient` r on r.parent=q.name
			                                 where q.reference_name=%s and r.recipient=%s""", (review.name, user)))

	def test_reminder_goes_to_whoever_has_not_done_their_part(self):
		review = self.open_one()
		day = add_days(review.due_on, -reviews.REMIND_DAYS_BEFORE)
		self.assertIn((review.name, self.emp_user), reviews.remind(day))
		as_user(self.emp_user, api.save_review, review.name, self.answers(review, "Employee"), done=1)
		self.assertIn((review.name, self.mgr_user), reviews.remind(day))

	def test_overdue_after_the_due_date(self):
		review = self.open_one()
		self.assertNotIn(review.name, reviews.mark_overdue(review.due_on))
		self.assertIn(review.name, reviews.mark_overdue(add_days(review.due_on, 1)))
		self.assertTrue(reviews.weekly_overdue_summary())

	def test_who_may_fill_what(self):
		review = self.open_one()
		with self.assertRaises(frappe.PermissionError):
			as_user(make_user("rev-stranger@example.com"), api.get_review, review.name)
		with self.assertRaisesRegex(frappe.ValidationError, "hasn't sent their part"):
			as_user(self.mgr_user, api.save_review, review.name, {}, done=0)
		with self.assertRaisesRegex(frappe.ValidationError, "Answer these first"):
			as_user(self.emp_user, api.save_review, review.name, {}, done=1)
		# the employee's save ignores manager questions
		everything = {a.name: "5" if a.kind == "Rating" else "x" for a in review.answers}
		out = as_user(self.emp_user, api.save_review, review.name, everything, done=1)
		self.assertEqual(out.status, "Self done")
		self.assertFalse([a for a in frappe.get_doc("Review", review.name).answers if a.manager_answer])
		with self.assertRaisesRegex(frappe.ValidationError, "already sent"):
			as_user(self.emp_user, api.save_review, review.name, {}, done=0)
		bad = {a.name: "9" for a in review.answers if a.kind == "Rating" and a.answered_by == "Manager"}
		with self.assertRaisesRegex(frappe.ValidationError, "rating from 1 to 5"):
			as_user(self.mgr_user, api.save_review, review.name, bad, done=0)

	def test_completing_with_no_appraisal_posts_nothing(self):
		review = self.open_one()
		as_user(self.emp_user, api.save_review, review.name, self.answers(review, "Employee"), done=1)
		out = as_user(self.mgr_user, api.save_review, review.name, self.answers(review, "Manager"), "Good fortnight", done=1)
		self.assertEqual(out.status, "Completed")
		self.assertIsNone(out.feedback)
		self.assertIn("No appraisal open", out.rollup_note)

	def test_completing_rolls_into_the_appraisal(self):
		review = self.open_one()
		cycle = frappe.get_doc(dict(doctype="Appraisal Cycle", cycle_name=f"REVTEST {frappe.generate_hash(length=5)}",
		                            company=company(), start_date=add_days(nowdate(), -60), end_date=add_days(nowdate(), 60),
		                            kra_evaluation_method="Manual Rating")).insert(ignore_permissions=True)
		cycle.db_set("status", "In Progress")
		appraisal = frappe.get_doc(dict(doctype="Appraisal", employee=self.employee, appraisal_cycle=cycle.name,
		                                appraisal_template="Staff Appraisal")).insert(ignore_permissions=True)
		as_user(self.emp_user, api.save_review, review.name, self.answers(review, "Employee"), done=1)
		out = as_user(self.mgr_user, api.save_review, review.name, self.answers(review, "Manager"), "Good fortnight", done=1)
		self.assertEqual(out.appraisal, appraisal.name)
		feedback = frappe.get_doc("Employee Performance Feedback", out.feedback)
		self.assertEqual((feedback.docstatus, feedback.reviewer), (1, self.manager))
		self.assertEqual({round(r.rating, 2) for r in feedback.feedback_ratings}, {0.8})  # 4 of 5
		self.assertGreater(frappe.db.get_value("Appraisal", appraisal.name, "avg_feedback_score"), 0)
		# HR reopens: the feedback is cancelled and the manager can change it
		frappe.set_user("Administrator")
		self.assertEqual(api.reopen(review.name).status, "Self done")
		self.assertEqual(frappe.db.get_value("Employee Performance Feedback", feedback.name, "docstatus"), 2)

	def test_schedule_preview(self):
		out = api.preview_schedule(self.schedule.as_dict())
		self.assertEqual(len(out["windows"]), 3)
		self.assertIn(self.employee, [p.name for p in out["people"]])
		self.assertTrue(out["no_manager"])
