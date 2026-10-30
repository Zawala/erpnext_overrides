# Copyright (c) 2025, Kelvin Zawala and contributors
# For license information, please see license.txt

"""Backfill ``notification_sent`` on tenders that pre-date the digest.

Notifications used to go out one email per tender from ``after_insert``, so
everything already in the table has been announced. Without this the first
digest run would re-send the entire backlog in one enormous email.
"""

import frappe


def execute():
	for doctype in ("Egp Tender", "Eprocure Tender"):
		if not frappe.db.has_column(doctype, "notification_sent"):
			continue
		frappe.db.sql(f"update `tab{doctype}` set notification_sent = 1")
