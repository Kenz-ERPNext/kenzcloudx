import re

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response

SETTINGS = "KenzCloudX Settings"
ROUTES = ["/", "/erpnext", "/zatca", "/plans", "/about", "/demo", "/privacy", "/terms"]


def html(path):
	"""Render `path` as Guest through the normal website pipeline; return (status_code, html)."""
	user = frappe.session.user
	request = getattr(frappe.local, "request", None)
	frappe.set_user("Guest")
	set_request(method="GET", path=path)
	try:
		r = get_response(path)
		return r.status_code, r.get_data(as_text=True)
	finally:
		frappe.local.request = request
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

	def test_footer_hides_contact_when_values_are_blank(self):
		fields = ("phone", "email", "whatsapp_number", "office_address_en", "office_address_ar")
		old = frappe.get_single(SETTINGS)
		try:
			set_settings(**{f: "   " for f in fields})
			for p in ("/", "/ar"):
				_, h = html(p)
				self.assertNotIn('id="footer-contact"', h, p)
				self.assertNotIn("wa.me", h, p)
				self.assertNotIn('href="tel:', h, p)
		finally:
			set_settings(**{f: old.get(f) or "" for f in fields})

	def test_settings_values_are_escaped(self):
		payload = '"<b>x</b>'
		fields = ("phone", "email", "office_address_en", "cr_number", "vat_number")
		old = frappe.get_single(SETTINGS)
		try:
			set_settings(**{f: payload for f in fields})
			_, h = html("/")
			self.assertNotIn("<b>x</b>", h)
			self.assertIn("&#34;&lt;b&gt;x&lt;/b&gt;", h)
		finally:
			set_settings(**{f: old.get(f) or "" for f in fields})

	# ---------- Task 4: remaining pages, sitemap, 404 ----------

	def test_all_routes_both_langs(self):
		for r in ROUTES:
			for p in (r, "/ar" if r == "/" else "/ar" + r):
				code, h = html(p)
				self.assertEqual(code, 200, p)
				self.assertNotIn("Frappe", h, p)
				self.assertEqual(h.count('rel="alternate"'), 3, p)
				self.assertEqual(h.count("<h1"), 1, p)
				self.assertNotIn("{{", h, p)
				self.assertIn('dir="rtl"' if p.startswith("/ar") else 'dir="ltr"', h, p)

	def test_plans_no_prices(self):
		for p in ("/plans", "/ar/plans"):
			_, h = html(p)
			self.assertNotIn("SAR", h, p)
			self.assertNotIn("ر.س", h, p)
			self.assertNotIn("ريال", h, p)
			self.assertIsNone(re.search(r'class="[^"]*price', h), p)
			lp = "/ar" if p.startswith("/ar") else ""
			for key in ("starter", "business", "enterprise"):
				self.assertIn(f'href="{lp}/demo?plan={key}"', h, (p, key))
			self.assertIn("/demo?plan=business", h.replace("/ar/demo", "/demo"))
		_, h = html("/plans")
		self.assertEqual(h.count(">Request a quote<"), 3)

	def test_404_branded_by_lang(self):
		code, h = html("/ar/does-not-exist")
		self.assertEqual(code, 404)
		self.assertIn('dir="rtl"', h)
		self.assertIn('lang="ar"', h)
		self.assertNotIn("Frappe", h)
		self.assertIn('<meta name="robots" content="noindex">', h)
		self.assertIn('href="/ar"', h)
		code, h = html("/does-not-exist")
		self.assertEqual(code, 404)
		self.assertIn('dir="ltr"', h)
		self.assertNotIn("Frappe", h)
		self.assertIn('<meta name="robots" content="noindex">', h)
		self.assertNotIn("{{", h)
		self.assertNotIn('rel="canonical"', h)

	def test_real_routes_still_work(self):
		code, _ = html("/login")
		self.assertEqual(code, 200)

	def test_sitemap_lists_both_langs(self):
		frappe.cache.delete_value("website_pages")
		_, h = html("/sitemap.xml")
		self.assertIn("/ar/zatca", h)
		self.assertIn("/zatca", h)
		for stem in ("erpnext", "zatca", "plans", "about", "demo", "privacy", "terms"):
			self.assertIn(f"/{stem}</loc>", h, stem)
			self.assertIn(f"/ar/{stem}</loc>", h, stem)
		self.assertNotIn("404</loc>", h)

	def test_zatca_steps_and_faq(self):
		_, h = html("/zatca")
		self.assertEqual(h.count('class="step"'), 5)
		self.assertEqual(h.count("<details"), 5)
		self.assertEqual(h.count("<summary"), 5)
		self.assertIn("Do I need new hardware?", h)
		self.assertIn('<section class="demo-band"', h)

	def test_erpnext_modules(self):
		_, h = html("/ar/erpnext")
		self.assertEqual(h.count('class="numbered-block"'), 6)
		self.assertIn('href="/ar/demo"', h)

	def test_legal_pages_are_placeholders(self):
		for p in ("/privacy", "/terms", "/ar/privacy", "/ar/terms"):
			_, h = html(p)
			self.assertIn("[PLACEHOLDER]", h, p)
			self.assertGreaterEqual(h.count("<h2"), 5, p)

	def test_demo_skeleton_has_no_demo_band(self):
		for p in ("/demo", "/ar/demo"):
			_, h = html(p)
			self.assertNotIn('<section class="demo-band"', h, p)
		_, h = html("/demo")
		self.assertIn("Request a demo</h1>", h)

	def test_about_contact_from_settings(self):
		fields = (
			"phone",
			"email",
			"whatsapp_number",
			"office_address_en",
			"office_address_ar",
			"cr_number",
			"vat_number",
		)
		old = frappe.get_single(SETTINGS)
		try:
			set_settings(
				phone="+966 11 000 0000",
				email="hello@kenzcloudx.com",
				whatsapp_number="0551234567",
				office_address_en="Riyadh office",
				office_address_ar="مكتب الرياض",
				cr_number="1010000000",
				vat_number="",
			)
			_, h = html("/about")
			about = h.split('<footer class="site-footer"')[0]
			self.assertIn('href="tel:+966110000000"', about)
			self.assertIn('href="mailto:hello@kenzcloudx.com"', about)
			self.assertIn('href="https://wa.me/966551234567"', about)
			self.assertIn("Riyadh office", about)
			self.assertNotIn("مكتب الرياض", about)
			self.assertIn("Commercial registration", about)
			self.assertIn('<span dir="ltr">1010000000</span>', about)
			self.assertNotIn("VAT number", about)
			_, h = html("/ar/about")
			about = h.split('<footer class="site-footer"')[0]
			self.assertIn("مكتب الرياض", about)
			self.assertNotIn("Riyadh office", about)
		finally:
			set_settings(**{f: old.get(f) or "" for f in fields})
