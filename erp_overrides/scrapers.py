# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt

"""Stubs for the data feeds: public tenders and central-bank exchange rates.

The working version logged into the Zimbabwe e-GP portal and searched the Zambia ZPPA
portal (Playwright, captcha OCR), and read the RBZ's daily rate-sheet PDFs. That code is
left out of this repo. These stubs keep the same entry points, so the scheduler, the
Tenders page and the Accounts "Fetch from RBZ" button all still work, they just fetch
nothing. Fill in ``fetch_*`` to connect a source; see docs/sadc-data-feeds.md.
"""

import frappe
from frappe.utils import nowdate


def _stub(source):
	frappe.logger("erp_overrides").info(f"{source}: no scraper in this build, nothing fetched")
	return {"count": 0, "source": source, "stub": True}


# ── Tenders ──────────────────────────────────────────────────────────────────

def fetch_zimbabwe_tenders() -> list[dict]:
	"""Open tenders from the Zimbabwe e-GP portal, as Egp Tender field dicts."""
	return []


def fetch_zambia_tenders() -> list[dict]:
	"""Open tenders from the Zambia ZPPA portal, as Eprocure Tender field dicts."""
	return []


def _save(doctype, key, rows):
	for row in rows:
		if not frappe.db.exists(doctype, {key: row[key]}):
			frappe.get_doc({"doctype": doctype, **row}).insert(ignore_permissions=True)
	return {"count": len(rows)}


@frappe.whitelist()
def get_tenders():
	"""Zimbabwe e-GP → Egp Tender (button on Egp Settings, and the 08:00/16:00/00:00 cron)."""
	rows = fetch_zimbabwe_tenders()
	return _save("Egp Tender", "id", rows) if rows else _stub("Zimbabwe e-GP")


@frappe.whitelist()
def get_zppa_portal_tenders():
	"""Zambia ZPPA → Eprocure Tender."""
	rows = fetch_zambia_tenders()
	return _save("Eprocure Tender", "reference_id", rows) if rows else _stub("Zambia ZPPA")


def enqueue_get_tenders():
	frappe.enqueue("erp_overrides.scrapers.get_tenders", queue="long")


def enqueue_get_zppa_portal_tenders():
	frappe.enqueue("erp_overrides.scrapers.get_zppa_portal_tenders", queue="long")


# ── Exchange rates ───────────────────────────────────────────────────────────

def fetch_rates(start: str, end: str) -> list[tuple[str, str, str, float]]:
	"""(date, from currency, to currency, rate) from a central bank, e.g. RBZ USD/ZWG mid-rates."""
	return []


def sync_rates(start: str | None = None, end: str | None = None, **kwargs) -> dict:
	"""Write fetched rates into ERPNext's Currency Exchange; days already there are skipped."""
	start, end = start or nowdate(), end or nowdate()
	created = 0
	for day, from_currency, to_currency, rate in fetch_rates(start, end):
		filters = {"date": day, "from_currency": from_currency, "to_currency": to_currency}
		if not frappe.db.exists("Currency Exchange", filters):
			frappe.get_doc({"doctype": "Currency Exchange", **filters, "exchange_rate": rate,
			                "for_buying": 1, "for_selling": 1}).insert(ignore_permissions=True)
			created += 1
	if not created:
		_stub("RBZ rates")
	return {"start": start, "end": end, "created": created}


def enqueue_sync_rates():
	frappe.enqueue("erp_overrides.scrapers.sync_rates", queue="long")
