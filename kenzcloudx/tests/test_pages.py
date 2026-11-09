import re

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.serve import get_response

SETTINGS = "KenzCloudX Settings"


def html(path):
	"""Render `path` as Guest through the normal website pipeline; return (status_code, html)."""
	user = frappe.session.user
	frappe.set_user("Guest")
	try:
		r = get_response(path)
		return r.status_code, r.get_data(as_text=True)
	finally:
		frappe.set_user(user)


def set_settings(**values):
	for field, value in values.items():
		frappe.db.set_single_value(SETTINGS, field, value)
	frappe.clear_document_cache(SETTINGS, SETTINGS)


class TestPages(FrappeTestCase):
	def test_home_en(self):
		code, h = html("/")
		self.assertEqual(code, 200)
		self.assertIn('lang="en"', h)
		self.assertIn('dir="ltr"', h)
		self.assertIn("hosted and run by people you can call", h)
		self.assertIn('hreflang="ar"', h)
		self.assertIn('href="/ar"', h)

	def test_home_ar(self):
		code, h = html("/ar")
		self.assertEqual(code, 200)
		self.assertIn('lang="ar"', h)
		self.assertIn('dir="rtl"', h)
		self.assertIn("يمكنك التواصل معه", h)
		self.assertIn('href="/"', h)

	def test_no_frappe_and_no_cdn(self):
		for p in ("/", "/ar"):
			_, h = html(p)
			self.assertNotIn("Frappe", h, p)
			self.assertNotIn("fonts.googleapis", h, p)
			self.assertNotIn("/assets/frappe", h, p)

	def test_head_meta(self):
		for p, lang in (("/", "en"), ("/ar", "ar")):
			_, h = html(p)
			stylesheets = re.findall(r'<link[^>]+rel="stylesheet"[^>]*>', h)
			self.assertEqual(len(stylesheets), 1, p)
			self.assertIn('href="/assets/kenzcloudx/css/kenz.css', stylesheets[0])
			self.assertNotIn("<script src=", h, p)
			for code in ("en", "ar", "x-default"):
				self.assertIn(f'hreflang="{code}"', h, p)
			canonical = "https://kenzcloudx.com" + ("/ar" if lang == "ar" else "/")
			self.assertIn(f'<link rel="canonical" href="{canonical}">', h, p)
			self.assertIn(f"/assets/kenzcloudx/images/og-{lang}.png", h, p)

	def test_home_sections_in_order(self):
		_, h = html("/")
		markers = [
			'<section class="hero"',
			"zatca-invoice",
			'<dl class="proof"',
			"what-we-do",
			"how-it-works",
			'<section class="demo-band"',
			'<footer class="site-footer"',
		]
		positions = [h.find(m) for m in markers]
		self.assertNotIn(-1, positions, dict(zip(markers, positions, strict=True)))
		self.assertEqual(positions, sorted(positions))
		self.assertIn('href="/demo"', h)
		self.assertIn('href="/plans"', h)

	def test_nav_links_every_page_in_language(self):
		_, h = html("/ar")
		for stem in ("erpnext", "zatca", "plans", "about", "demo", "privacy", "terms"):
			self.assertIn(f'href="/ar/{stem}"', h, stem)

	def test_proof_numbers_from_settings(self):
		old = frappe.get_single(SETTINGS)
		try:
			set_settings(stat_live_sites=91, stat_zatca_customers=23)
			_, h = html("/")
			self.assertIn(">91<", h)
			self.assertIn(">23+<", h)
		finally:
			set_settings(stat_live_sites=old.stat_live_sites, stat_zatca_customers=old.stat_zatca_customers)

	def test_whatsapp_button(self):
		old = frappe.get_single(SETTINGS)
		try:
			set_settings(whatsapp_number="")
			_, h = html("/")
			self.assertNotIn("wa.me", h)
			set_settings(whatsapp_number="+966 55 123 4567")
			_, h = html("/")
			self.assertIn('href="https://wa.me/966551234567"', h)
		finally:
			set_settings(whatsapp_number=old.whatsapp_number or "")

	def test_footer_contact_and_registration_only_when_set(self):
		old = frappe.get_single(SETTINGS)
		fields = ("phone", "email", "whatsapp_number", "cr_number", "vat_number")
		try:
			set_settings(**{f: "" for f in fields})
			_, h = html("/")
			self.assertNotIn("Contact</h2>", h)
			self.assertNotIn("CR No.", h)
			set_settings(phone="+966 11 000 0000", cr_number="1010000000", vat_number="300000000000003")
			_, h = html("/ar")
			self.assertIn('href="tel:+966110000000"', h)
			self.assertIn("1010000000", h)
			self.assertIn("300000000000003", h)
			self.assertIn('href="/ar/privacy"', h)
		finally:
			set_settings(**{f: old.get(f) or "" for f in fields})
