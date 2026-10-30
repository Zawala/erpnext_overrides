# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt

"""Make images used by Letter Heads public.

A letter head can show logos that were uploaded as private,
unattached files. wkhtmltopdf fetches every image over HTTP with the printing
user's session, and Frappe only serves an unattached private file to its owner,
so for everyone else each logo is a 403 and the whole PDF fails with
"PDF generation failed because of broken image links".

Logos are not confidential. This moves every private file a Letter Head
references to public/files, repoints all File records for it, and rewrites the
Letter Head HTML. Files that cannot be moved safely are left alone and logged.
Re-running finds nothing to do.
"""

import filecmp
import re
import shutil
from pathlib import Path
from urllib.parse import quote, unquote

import frappe

HTML_FIELDS = ("content", "footer")
IMAGE_FIELDS = ("image", "footer_image")
PRIVATE_URL = re.compile(r"""/private/files/[^"'()<>]+""")


def execute():
	run()


def on_letter_head_update(doc, method=None):
	"""Letter Head doc event: the same fix when a private image is added later."""
	if any(PRIVATE_URL.search(doc.get(f) or "") for f in HTML_FIELDS + IMAGE_FIELDS):
		run()
		doc.reload()


def run(dry_run=False):
	letter_heads = frappe.get_all("Letter Head", fields=["name", *HTML_FIELDS, *IMAGE_FIELDS])

	urls = set()
	for lh in letter_heads:
		for field in HTML_FIELDS + IMAGE_FIELDS:
			urls.update(unquote(u).strip() for u in PRIVATE_URL.findall(lh.get(field) or ""))

	moved = {url: new for url in sorted(urls) if (new := make_public(url, dry_run))}

	for lh in letter_heads:
		changes = {}
		for field in HTML_FIELDS + IMAGE_FIELDS:
			value = lh.get(field) or ""
			updated = value
			for old, new in moved.items():
				# HTML may carry the path raw (spaces) or percent-encoded
				updated = updated.replace(old, new).replace(quote(old), quote(new))
			if updated != value:
				changes[field] = updated
		if changes:
			log(f"Letter Head {lh.name}: repointed {', '.join(changes)}")
			if not dry_run:
				frappe.db.set_value("Letter Head", lh.name, changes, update_modified=False)

	return moved


def make_public(url, dry_run):
	"""Move one private file to public/files. Returns the new URL, or None if skipped."""
	file_name = url.removeprefix("/private/files/")
	if "/" in file_name:
		return log(f"Skipped {url}: nested path")

	private = Path(frappe.get_site_path("private", "files", file_name))
	public = Path(frappe.get_site_path("public", "files", file_name))
	new_url = f"/files/{file_name}"

	if public.exists():
		if private.exists() and not filecmp.cmp(private, public, shallow=False):
			return log(f"Skipped {url}: a different file named {file_name} is already public")
		# already public (or an identical copy is) — only the references need fixing
	elif not private.exists():
		return log(f"Skipped {url}: not found on disk")
	elif not dry_run:
		shutil.move(private, public)
		frappe.db.after_rollback.add(lambda: public.exists() and shutil.move(public, private))

	log(f"{'Would make' if dry_run else 'Made'} public: {file_name}")
	if not dry_run:
		frappe.db.set_value("File", {"file_url": url}, {"file_url": new_url, "is_private": 0}, update_modified=False)
	return new_url


def log(message):
	print(message)
	return None
