"""Redesign v2, task C: the inner pages in the new design system, multi-country wording, EN + AR."""

import json
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from kenzcloudx.tests.test_pages import html, set_settings
from kenzcloudx.website.context import load_content

INNER = ("erpnext", "zatca", "plans", "about", "demo", "privacy", "terms")
SETTINGS = "KenzCloudX Settings"


def _both(stem):
	return ((f"/{stem}", "en"), (f"/ar/{stem}", "ar"))


def _css():
	with open(frappe.get_app_path("kenzcloudx", "public", "css", "kenz.css"), encoding="utf-8") as f:
		return f.read()


class TestInnerContent(FrappeTestCase):
	def test_accent_headings_on_inner_pages(self):
		for lang in ("en", "ar"):
			c = load_content(lang)
			heads = [c[stem]["hero"]["h1"] for stem in INNER] + [c["not_found"]["h1"]]
			heads += [c["erpnext"][k]["heading"] for k in ("modules", "countries", "hosting", "cta")]
			heads += [c["zatca"][k]["heading"] for k in ("phase2", "onboarding", "faq", "cta")]
			heads += [c["plans"][k]["heading"] for k in ("includes", "cta")]
			heads += [c["about"][k]["heading"] for k in ("company", "regions", "team", "contact", "cta")]
			for hd in heads:
				self.assertEqual(set(hd), {"pre", "acc", "post"}, (lang, hd))
				self.assertTrue(hd["acc"].strip(), (lang, hd))
				self.assertLessEqual(len(hd["acc"].split()), 2, (lang, hd))
			for stem in INNER:
				self.assertTrue(c[stem]["hero"]["eyebrow"], (lang, stem))

	def test_meta_is_multi_country(self):
		for stem in ("erpnext", "plans", "about", "demo"):
			en = load_content("en")[stem]["meta"]
			text = en["title"] + " " + en["description"]
			self.assertNotIn("Saudi businesses", text, stem)
			self.assertNotIn("in the Kingdom", text, stem)
		for stem in ("erpnext", "plans", "about"):
			for lang, names in (("en", ("UAE", "Oman", "India")), ("ar", ("الإمارات", "عُمان", "الهند"))):
				desc = load_content(lang)[stem]["meta"]["description"]
				for name in names:
					self.assertIn(name, desc, (lang, stem, name))
		# /zatca stays the Saudi page and says so
		self.assertIn("Saudi Arabia", load_content("en")["zatca"]["meta"]["title"])
		self.assertIn("السعودية", load_content("ar")["zatca"]["meta"]["title"])

	def test_set_up_uses_a_non_breaking_hyphen(self):
		raw = json.dumps(load_content("en"), ensure_ascii=False)
		self.assertNotIn("set-up", raw)
		self.assertNotIn("Set-up", raw)
		self.assertIn("set\u2011up", raw)

	def test_legal_bodies_keep_their_placeholders(self):
		for lang in ("en", "ar"):
			for stem in ("privacy", "terms"):
				page = load_content(lang)[stem]
				self.assertTrue(page["hero"]["updated"].startswith("[PLACEHOLDER]"), (lang, stem))
				for s in page["sections"]:
					self.assertTrue(s["body"].startswith("[PLACEHOLDER]"), (lang, stem, s["heading"]))
			self.assertTrue(load_content(lang)["about"]["team"]["body"].startswith("[PLACEHOLDER]"), lang)


class TestInnerPages(FrappeTestCase):
	def test_new_hero_on_every_inner_page(self):
		for stem in INNER:
			for path, _lang in _both(stem):
				code, h = html(path)
				self.assertEqual(code, 200, path)
				self.assertIn('<section class="page-top wrap"', h, path)
				self.assertRegex(h, r'<h1 class="h1" id="page-h1">[^<]*<span class="acc">', path)
				self.assertNotIn('class="hero page-hero"', h, path)
				for legacy in (
					"section-mint",
					"point-list",
					"numbered-block",
					'class="container split"',
					'class="prose',
				):
					self.assertNotIn(legacy, h, (path, legacy))

	def test_erpnext_modules_countries_hosting(self):
		for path, lang in _both("erpnext"):
			_, h = html(path)
			lp = "/ar" if lang == "ar" else ""
			self.assertEqual(h.count('class="mod-card glass lift'), 6, path)
			for key in ("saudi-arabia", "uae", "oman", "india"):
				self.assertIn(f'href="{lp}/compliance#{key}"', h, (path, key))
			self.assertIn('class="split-card glass', h)
			self.assertIn('<section class="demo-band"', h)
			band = h[h.index('<section class="demo-band"') :]
			self.assertIn('<span class="acc">', band[: band.index("</h2>")], path)

	def test_zatca_is_the_saudi_page_and_links_to_compliance(self):
		old = frappe.db.get_single_value(SETTINGS, "stat_zatca_customers")
		try:
			for path, lang in _both("zatca"):
				_, h = html(path)
				lp = "/ar" if lang == "ar" else ""
				self.assertIn(f'href="{lp}/compliance"', h.split('<footer class="site-footer"')[0], path)
				self.assertIn(load_content(lang)["zatca"]["hero"]["eyebrow"], h, path)
				self.assertIn(f'<b dir="ltr">{old}+</b>', h, path)
				self.assertEqual(h.count('class="qa-item"'), 5, path)
			set_settings(stat_zatca_customers=0)
			_, h = html("/zatca")
			self.assertNotIn('class="meta-stat"', h)
		finally:
			set_settings(stat_zatca_customers=old)

	def test_plans_cards_and_every_plan(self):
		for path, _lang in _both("plans"):
			_, h = html(path)
			self.assertEqual(h.count('class="plan-card glass lift'), 3, path)
			self.assertEqual(h.count('<span class="badge">'), 1, path)
			self.assertIn('id="plan-business"', h)
			self.assertEqual(h.count('class="mini-card glass'), 4, path)
			self.assertIn("[PLACEHOLDER]", h, path)  # taglines still await the owner
			self.assertIn('<section class="demo-band"', h, path)
			for currency in ("SAR", "AED", "OMR", "INR", "₹"):
				self.assertNotIn(currency, h, (path, currency))
		_, h = html("/plans")
		self.assertIn("e-invoicing and tax set\u2011up for your country", h)

	def test_about_regions_team_and_contact_only_when_set(self):
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
			set_settings(**{f: "" for f in fields})
			for path, _lang in _both("about"):
				_, h = html(path)
				self.assertEqual(h.count('class="region-card glass'), 5, path)
				self.assertIn("[PLACEHOLDER]", h, path)
				self.assertNotIn('id="contact-heading"', h, path)
				self.assertIn('<section class="demo-band"', h, path)
			set_settings(email="hello@kenzcloudx.com")
			_, h = html("/ar/about")
			self.assertIn('id="contact-heading"', h)
			self.assertIn('href="mailto:hello@kenzcloudx.com"', h)
		finally:
			set_settings(**{f: old.get(f) or "" for f in fields})

	def test_legal_pages_in_a_glass_card(self):
		for stem in ("privacy", "terms"):
			for path, lang in _both(stem):
				_, h = html(path)
				self.assertIn('class="legal-card glass', h, path)
				self.assertEqual(
					h.count('<section class="legal-sec"'), len(load_content(lang)[stem]["sections"])
				)
				self.assertIn('class="page-updated">[PLACEHOLDER]', h, path)

	def test_404_new_look_both_languages(self):
		for path, lang in (("/nope-c", "en"), ("/ar/nope-c", "ar")):
			code, h = html(path)
			self.assertEqual(code, 404, path)
			lp = "/ar" if lang == "ar" else ""
			self.assertIn('class="page-top wrap nf"', h, path)
			self.assertIn('<span class="acc">', h, path)
			for stem in ("erpnext", "compliance", "plans", "about"):
				self.assertIn(f'href="{lp}/{stem}"', h, (path, stem))

	def test_demo_layout(self):
		for path, lang in _both("demo"):
			_, h = html(path)
			self.assertIn('class="demo-panel glass', h, path)
			self.assertEqual(h.count('<li><span class="step-n"'), 3, path)
			self.assertIn(load_content(lang)["demo"]["next"]["heading"], h, path)


class TestInnerCss(FrappeTestCase):
	def test_legacy_shims_removed(self):
		css = _css()
		for selector in (
			".section-mint",
			".point-list",
			".numbered-block",
			".page-hero",
			".hero-grid",
			".invoice-card",
			".proof {",
			".faq-item summary",
		):
			self.assertNotIn(selector, css, selector)

	def test_whatsapp_focus_ring(self):
		css = _css()
		rule = css[css.index(".whatsapp:focus-visible") :]
		rule = rule[: rule.index("}")]
		self.assertIn("outline: 3px solid var(--accent)", rule)
		self.assertIn("0 0 0 3px #fff", rule)

	def test_floating_button_never_covers_the_form_on_phones(self):
		css = _css()
		block = css[css.index("@media (max-width: 640px)", css.index("Inner pages (task C)")) :]
		block = block[: block.index("\n}\n")]
		self.assertRegex(block, r"\.demo-section \{ padding-block-end: (9[6-9]|1\d\d)px; \}")

	def test_only_logical_properties_still(self):
		css = _css()
		self.assertIsNone(re.search(r"(?<![-\w])(margin|padding)-(left|right)\s*:", css))
		self.assertIsNone(re.search(r"text-align:\s*(left|right)", css))

	def test_no_unused_svg_file(self):
		self.assertFalse(
			os.path.exists(frappe.get_app_path("kenzcloudx", "public", "images", "zatca-invoice.svg")),
			"the old navy/mint invoice illustration is no longer used",
		)


class TestArabicTerms(FrappeTestCase):
	"""Fix wave: consistent Arabic terms (review of the redesign branch)."""

	def test_terms(self):
		raw = json.dumps(load_content("ar"), ensure_ascii=False)
		for old in ("النامية", "أذونات النقل", "سندات النقل", "مذكرة التسليم"):
			self.assertNotIn(old, raw, old)
		self.assertIn("المتنامية", load_content("ar")["home"]["hero"]["tag"])
		self.assertIn("المتنامية", load_content("ar")["plans"]["items"][1]["tagline"])
		self.assertTrue(load_content("ar")["home"]["stats"]["live_sites_label"].startswith("نظامًا"))
		self.assertGreaterEqual(raw.count("سند النقل الإلكتروني (e-way bill)"), 4)
		self.assertIn("إشعار التسليم", raw)
		self.assertEqual(load_content("ar")["_review"], "Arabic draft \u2013 needs native-speaker review")
