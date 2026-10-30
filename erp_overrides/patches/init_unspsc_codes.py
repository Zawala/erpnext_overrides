"""Seed Eprocure Settings.unspsc_codes with the bundled defaults if it's empty.

The UNSPSC codes used to live hardcoded in EprocureSettings.get_unspsc_codes;
they now live in a JSON field so they can be edited from the UI. This patch
populates that field from DEFAULT_UNSPSC_CODES on first migrate, leaving any
value an operator has already set untouched.
"""

import json

import frappe

from erp_overrides.erp_overrides.doctype.eprocure_settings.eprocure_settings import (
	DEFAULT_UNSPSC_CODES,
)


def execute():
	# Eprocure Settings is a Single doctype (no tab* table), so check the meta
	# field, not a DB column. Field is added in the same migrate (post_model_sync).
	meta = frappe.get_meta("Eprocure Settings", cached=False)
	if not meta.has_field("unspsc_codes"):
		return

	existing = frappe.db.get_single_value("Eprocure Settings", "unspsc_codes")
	if existing:
		return

	frappe.db.set_single_value(
		"Eprocure Settings", "unspsc_codes", json.dumps(DEFAULT_UNSPSC_CODES)
	)
