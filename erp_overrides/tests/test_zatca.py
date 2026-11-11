# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""ZATCA outbox: the queued job, the sweeper, retry backoff and the row lock (erp_overrides.zatca.submit).

ZATCA itself is replaced by a fake client, so these run offline. They need the ZATCA demo
seeded and onboarded:
	bench --site <site> execute erp_overrides.zatca.demo.seed
	bench --site <site> execute erp_overrides.zatca.onboarding.run
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from erp_overrides.zatca import client, demo, submit


class FakeZATCA:
	"""Stands in for client.Client: answers every call with the next queued (status, body)."""

	def __init__(self, *answers):
		self.answers, self.calls = list(answers), []

	def _answer(self, what, uuid):
		self.calls.append((what, uuid))
		status, body = self.answers.pop(0) if self.answers else (200, {})
		if isinstance(status, Exception):
			raise status
		return client.Response(status, body)

	def clear(self, xml, invoice_hash, uuid):
		return self._answer("clear", uuid)

	def report(self, xml, invoice_hash, uuid):
		return self._answer("report", uuid)


REPORTED = (200, {"reportingStatus": "REPORTED", "validationResults": {"status": "PASS"}})


class TestZATCAOutbox(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Company", demo.COMPANY) or not frappe.db.get_single_value(
			"ZATCA Settings", "certificate_expiry"
		):
			self.skipTest("seed and onboard the ZATCA demo first (see the module docstring)")
		frappe.db.set_single_value("ZATCA Settings", "enabled", 1)

	def b2c(self):
		"""A submitted B2C invoice whose queued job hasn't run (tests don't run workers)."""
		with patch.object(frappe, "enqueue"):
			inv = demo.invoice(demo.B2C, [("Test cable", 1, 10)])
		frappe.db.commit()
		return inv

	def run_with(self, fake, fn, *args):
		with patch.object(submit, "_client", return_value=fake):
			return fn(*args)

	def sub(self, inv):
		return frappe.get_doc("ZATCA Submission", frappe.db.get_value("Sales Invoice", inv.name, "zatca_submission"))

	def age(self, inv, minutes):
		frappe.db.set_value("ZATCA Submission", self.sub(inv).name, "creation",
		                    add_to_date(now_datetime(), minutes=-minutes), update_modified=False)
		frappe.db.commit()

	def test_sweeper_sends_what_the_job_missed(self):
		inv = self.b2c()
		self.assertEqual(self.sub(inv).status, "Pending")
		self.assertNotIn(self.sub(inv).name, submit.due())  # fresh: still the queued job's to send
		self.age(inv, submit.STALE_PENDING_MINUTES + 1)
		self.assertIn(self.sub(inv).name, submit.due())
		fake = FakeZATCA(REPORTED)
		self.run_with(fake, submit.sweep)
		self.assertEqual(self.sub(inv).status, "Reported")
		self.assertEqual(frappe.db.get_value("Sales Invoice", inv.name, "zatca_status"), "Reported")

	def test_failed_send_backs_off_then_succeeds(self):
		inv = self.b2c()
		name = self.sub(inv).name
		self.run_with(FakeZATCA((503, {"raw": "Service Unavailable"})), submit.send, name)
		sub = self.sub(inv)
		self.assertEqual((sub.status, sub.attempts), ("Failed", 1))
		self.assertIn("HTTP 503", sub.errors)
		self.assertGreater(sub.next_attempt, now_datetime())  # 1 minute out
		self.assertNotIn(name, submit.due())  # not due yet

		frappe.db.set_value("ZATCA Submission", name, "next_attempt", add_to_date(now_datetime(), minutes=-1))
		frappe.db.commit()
		self.run_with(FakeZATCA(REPORTED), submit.sweep)
		sub = self.sub(inv)
		self.assertEqual((sub.status, sub.attempts, sub.next_attempt), ("Reported", 2, None))

	def test_network_error_is_retried(self):
		inv = self.b2c()
		self.run_with(FakeZATCA((ConnectionError("no route to host"), None)), submit.send, self.sub(inv).name)
		sub = self.sub(inv)
		self.assertEqual(sub.status, "Failed")
		self.assertIsNotNone(sub.next_attempt)

	def test_gives_up_after_max_attempts(self):
		inv = self.b2c()
		name = self.sub(inv).name
		frappe.db.set_value("ZATCA Submission", name, "attempts", submit.MAX_ATTEMPTS - 1)
		frappe.db.commit()
		self.run_with(FakeZATCA((500, {"code": "500", "message": "boom"})), submit.send, name)
		sub = self.sub(inv)
		self.assertEqual((sub.status, sub.next_attempt), ("Failed", None))
		self.assertNotIn(name, submit.due())  # left for a person

	def test_settled_submissions_are_not_sent_again(self):
		inv = self.b2c()
		name = self.sub(inv).name
		self.run_with(FakeZATCA(REPORTED), submit.send, name)
		fake = FakeZATCA(REPORTED)
		self.assertEqual(self.run_with(fake, submit.send, name), "Reported")
		self.assertEqual(fake.calls, [])

	def test_locked_submission_is_skipped(self):
		inv = self.b2c()
		name = self.sub(inv).name
		fake = FakeZATCA(REPORTED)
		with patch.object(submit, "_lock", return_value=False):  # another sender holds the row
			self.assertEqual(self.run_with(fake, submit.send, name), "Busy")
		self.assertEqual(fake.calls, [])
		self.assertEqual(self.sub(inv).status, "Pending")

	def test_overdue_simplified_invoices_are_flagged(self):
		inv = self.b2c()
		self.assertNotIn(inv.name, [r.sales_invoice for r in submit.overdue()])
		frappe.db.set_value("Sales Invoice", inv.name, "posting_date", add_to_date(now_datetime(), days=-1).date(),
		                    update_modified=False)
		frappe.db.commit()
		self.assertIn(inv.name, [r.sales_invoice for r in submit.overdue()])
		before = frappe.db.count("Error Log", {"method": ["like", "ZATCA:%"]})
		submit.check_overdue()
		self.assertGreater(frappe.db.count("Error Log", {"method": ["like", "ZATCA:%"]}), before)
		# settle it so it doesn't linger in the backlog
		self.run_with(FakeZATCA(REPORTED), submit.send, self.sub(inv).name)
