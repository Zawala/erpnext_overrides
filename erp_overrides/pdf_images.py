# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
"""PDFs read the site's own images from disk instead of over HTTP.

wkhtmltopdf fetches every <img> from the site URL. In a background job (payslips
emailed on "Submit slips") that is whatever get_url() says, with no session: a
wrong host, a proxy or a file missing from disk is a 404, and one missing logo in
a letter head fails the whole PDF ("broken image links") and the payroll step.

So the site's /files/... images are embedded as data URIs in the body, header and
footer. A /private/files/... image is embedded when a Letter Head uses it (an admin
chose it for printing; the payroll job prints as HR, who can't open an unattached
logo) or the printing user may download it, Frappe's own rule. Any other image of
ours, private and not allowed or not on disk, is dropped and logged: fetching it
could only fail the whole PDF. Installed per request and job (hooks before_request,
before_job).
"""
import base64
import mimetypes
import os
import re
from urllib.parse import unquote, urlparse

import frappe
from bs4 import BeautifulSoup

logger = frappe.logger("pdf_images")


def install():
	import frappe.utils.pdf as pdf

	if getattr(pdf, "_erp_overrides_images", False):
		return
	original_inline, original_header_footer = pdf.inline_private_images, pdf.prepare_header_footer

	def inline_images(html):
		return embed_local_images(original_inline(html))

	def prepare_header_footer(soup):
		options = original_header_footer(soup)
		for key in ("header-html", "footer-html"):
			if (path := options.get(key)) and os.path.exists(path):
				with open(path, encoding="utf-8") as f:
					html = f.read()
				with open(path, "w", encoding="utf-8") as f:
					f.write(embed_local_images(html))
		return options

	pdf.inline_private_images = inline_images
	pdf.prepare_header_footer = prepare_header_footer
	pdf._erp_overrides_images = True


def _local_path(src):
	"""(disk path, site URL path) for one of this site's /files/ or /private/files/
	images, else None."""
	url = urlparse(src)
	if url.scheme not in ("", "http", "https"):
		return None  # data:, file:, …
	if url.netloc and url.netloc != urlparse(frappe.utils.get_url()).netloc:
		return None  # someone else's image
	path = unquote(url.path)
	for prefix, folder in (("/files/", ("public", "files")), ("/private/files/", ("private", "files"))):
		if path.startswith(prefix):
			base = os.path.realpath(frappe.get_site_path(*folder))
			full = os.path.realpath(os.path.join(base, path.removeprefix(prefix)))
			return (full, path) if os.path.commonpath([base, full]) == base else None
	return None


def _letter_head_images():
	urls = set()
	for lh in frappe.get_all("Letter Head", fields=["content", "footer", "image", "footer_image"]):
		for value in lh.values():
			urls.update(unquote(u) for u in re.findall(r"/private/files/[^\"'()<>?#]+", value or ""))
	return urls


def _may_embed_private(path, letter_heads):
	if path in letter_heads:
		return True
	from frappe.core.doctype.file.utils import find_file_by_url

	try:
		return bool(find_file_by_url(path))  # only returns a file the user may download
	except Exception:
		return False


def embed_local_images(html):
	if "<img" not in html:
		return html
	soup = BeautifulSoup(html, "html.parser")
	letter_heads = None
	for img in soup.find_all("img"):
		src = img.get("src") or ""
		found = _local_path(src)
		if not found:
			continue
		path, url_path = found
		mime = mimetypes.guess_type(path)[0]
		allowed = True
		if url_path.startswith("/private/"):
			if letter_heads is None:
				letter_heads = _letter_head_images()
			allowed = _may_embed_private(url_path, letter_heads)
		if not allowed or not os.path.isfile(path) or not (mime or "").startswith("image/"):
			logger.warning(f"PDF: dropped {'missing' if allowed else 'not permitted'} image {src}")
			img.decompose()
			continue
		with open(path, "rb") as f:
			img["src"] = f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"
	return str(soup)
