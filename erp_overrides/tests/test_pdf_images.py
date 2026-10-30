# Copyright (c) 2026, Kelvin Zawala and contributors
# For license information, please see license.txt
import os

import frappe
from frappe.tests import IntegrationTestCase

from erp_overrides.pdf_images import embed_local_images, install

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


class TestPdfImages(IntegrationTestCase):
	def setUp(self):
		self.logo = frappe.get_site_path("public", "files", "pdf-images-test.png")
		with open(self.logo, "wb") as f:
			f.write(PNG)
		self.addCleanup(os.remove, self.logo)

	def test_site_images_are_embedded_and_missing_ones_dropped(self):
		site = frappe.utils.get_url()
		out = embed_local_images(
			f'<img src="{site}/files/pdf-images-test.png"><img src="/files/pdf-images-test.png">'
			'<img src="/files/not-on-disk.png"><img src="https://example.com/x.png">'
			'<img src="/private/files/secret.png"><img src="/files/../../site_config.json">')
		self.assertEqual(out.count("data:image/png;base64,"), 2)
		self.assertNotIn("not-on-disk", out)
		self.assertIn("https://example.com/x.png", out)  # not ours: left alone
		self.assertNotIn("secret.png", out)  # private, no letter head uses it, not the user's: dropped, never fetched
		self.assertIn("site_config.json", out)  # outside public/files: never read

	def test_footer_logo_missing_from_disk_still_prints(self):
		"""The test site's payslip emails: a letter-head footer image that 404s."""
		from frappe.utils.pdf import get_pdf

		install()
		html = ('<html><head></head><body><div id="footer-html"><img src="/files/pdf-images-test.png">'
		        '<img src="/files/not-on-disk.png"></div><p>Payslip</p></body></html>')
		self.assertTrue(get_pdf(html).startswith(b"%PDF"))

	def test_letter_head_private_logo_is_embedded_for_anyone(self):
		"""The payroll job prints as HR, who can't open an unattached private logo: a 403
		(ContentOperationNotPermittedError) used to fail every payslip email."""
		from frappe.utils.pdf import get_pdf

		private = frappe.get_site_path("private", "files", "pdf-images-partner.png")
		with open(private, "wb") as f:
			f.write(PNG)
		self.addCleanup(os.remove, private)
		# as on a site the letterhead patch couldn't fix (db_insert: the Letter Head hook would make it public)
		frappe.get_doc(dict(doctype="Letter Head", name="PDF images test", letter_head_name="PDF images test",
		                    source="HTML", footer_source="HTML", content="<p>x</p>",
		                    footer='<img src="/private/files/pdf-images-partner.png">')).db_insert()
		install()
		frappe.set_user("Guest")  # may download nothing
		self.addCleanup(frappe.set_user, "Administrator")
		out = embed_local_images('<img src="/private/files/pdf-images-partner.png"><img src="/private/files/other.png">')
		self.assertEqual(out.count("data:image/png;base64,"), 1)
		self.assertNotIn("other.png", out)
		html = ('<html><head></head><body><div id="footer-html"><img src="/private/files/pdf-images-partner.png">'
		        '</div><p>Payslip</p></body></html>')
		self.assertTrue(get_pdf(html).startswith(b"%PDF"))
