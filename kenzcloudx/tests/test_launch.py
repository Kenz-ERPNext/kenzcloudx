"""Pre-launch pass: no unfinished text on any public page, testimonials removed, the logo mark is never
mirrored, and the privacy policy / terms are complete in both languages."""

import json
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from kenzcloudx.tests.test_pages import ROUTES, html
from kenzcloudx.website.context import load_content

APP = frappe.get_app_path("kenzcloudx")
APP_ROOT = os.path.dirname(APP)
PRIVACY_SECTIONS = 12
TERMS_SECTIONS = 11


def _public_paths():
	for r in ROUTES:
		yield r
		yield "/ar" if r == "/" else "/ar" + r
	yield "/no-such-page"
	yield "/ar/no-such-page"


def _read(*parts):
	with open(os.path.join(*parts), encoding="utf-8") as f:
		return f.read()


class TestNothingUnfinished(FrappeTestCase):
	def test_no_placeholder_or_sample_on_any_public_page(self):
		for p in _public_paths():
			_, h = html(p)
			for word in ("PLACEHOLDER", "Sample", "sample customer", "TODO", "lorem", "Lorem"):
				self.assertNotIn(word, h, (p, word))
			# ("مسودة" is not checked: it is the "Draft" invoice status in the demo-data mocks)
			for word in ("النموذج)", "أغذية النموذج", "عيادات النموذج", "العيّنة"):
				self.assertNotIn(word, h, (p, word))

	def test_no_placeholder_in_content(self):
		for lang in ("en", "ar"):
			raw = json.dumps(load_content(lang), ensure_ascii=False)
			self.assertNotIn("PLACEHOLDER", raw, lang)
			self.assertNotIn('"_placeholder"', raw, lang)
			self.assertNotIn("Sample", raw, lang)


class TestTestimonialsRemoved(FrappeTestCase):
	def test_home_has_no_testimonials(self):
		for p in ("/", "/ar"):
			_, h = html(p)
			for marker in ('data-pose="quotes"', "quotes-heading", "<blockquote", 'class="quote', "qmark"):
				self.assertNotIn(marker, h, (p, marker))
		for lang in ("en", "ar"):
			self.assertNotIn("quotes", load_content(lang)["home"], lang)
		css = _read(APP, "public", "css", "kenz.css")
		for selector in (".qmark", ".quote-top", ".qav", ".quote blockquote", ".sample"):
			self.assertNotIn(selector, css, selector)


class TestLogoNotMirrored(FrappeTestCase):
	def test_logo_mark_points_the_same_way_in_both_languages(self):
		css = _read(APP, "public", "css", "kenz.css")
		self.assertIsNone(re.search(r"\.logo-mark[^{]*\{[^}]*transform", css))
		self.assertNotIn("[dir=rtl] .logo-mark", css)
		og = _read(APP_ROOT, "scripts", "og", "og.html")
		self.assertNotIn(".brand svg { transform", og)
		_, en = html("/")
		_, ar = html("/ar")
		mark = re.search(r'<svg class="logo-mark".*?</svg>', en, re.S).group(0)
		self.assertIn(mark, ar)


class TestLegalPages(FrappeTestCase):
	def test_sections_and_updated_line(self):
		for lang in ("en", "ar"):
			c = load_content(lang)
			self.assertEqual(len(c["privacy"]["sections"]), PRIVACY_SECTIONS, lang)
			self.assertEqual(len(c["terms"]["sections"]), TERMS_SECTIONS, lang)
			for stem in ("privacy", "terms"):
				self.assertIn("2026", c[stem]["hero"]["updated"], (lang, stem))
				for s in c[stem]["sections"]:
					self.assertTrue(s["heading"].strip() and len(s["body"]) > 40, (lang, stem, s["heading"]))
		for p, n in (
			("/privacy", PRIVACY_SECTIONS),
			("/ar/privacy", PRIVACY_SECTIONS),
			("/terms", TERMS_SECTIONS),
			("/ar/terms", TERMS_SECTIONS),
		):
			_, h = html(p)
			self.assertEqual(h.count('<section class="legal-sec"'), n, p)

	def test_privacy_states_the_checked_facts(self):
		en = " ".join(s["body"] for s in load_content("en")["privacy"]["sections"])
		ar = " ".join(s["body"] for s in load_content("ar")["privacy"]["sections"])
		self.assertIn("Germany", en)
		self.assertIn("ألمانيا", ar)
		for field in (
			"name",
			"company",
			"mobile number",
			"email",
			"country",
			"number of users",
			"plan",
			"ZATCA",
			"message",
			"language",
		):
			self.assertIn(field, en, field)
		self.assertIn("advertising or tracking cookies", en)
		self.assertIn("do not sell", en)
		terms_en = " ".join(s["body"] for s in load_content("en")["terms"]["sections"])
		self.assertIn("laws of the Kingdom of Saudi Arabia", terms_en)
		# governing law only because the company is stated to be registered in Saudi Arabia
		self.assertIn("registered in Saudi Arabia", load_content("en")["about"]["company"]["body"])

	def test_no_tracking_on_the_site(self):
		for p in ("/", "/ar", "/demo", "/privacy"):
			_, h = html(p)
			for host in (
				"googletagmanager",
				"google-analytics",
				"gtag(",
				"facebook",
				"hotjar",
				"clarity.ms",
				"plausible",
			):
				self.assertNotIn(host, h, (p, host))
		for name in ("main.js", "demo.js", "ribbon.js"):
			js = _read(APP, "public", "js", name)
			for api in ("document.cookie", "localStorage", "sessionStorage"):
				self.assertNotIn(api, js, (name, api))
