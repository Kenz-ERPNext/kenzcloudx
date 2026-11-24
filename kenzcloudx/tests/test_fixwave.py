"""Redesign v2, fix wave after the whole-branch review: ribbon budget, no-JS navigation, hero visibility,
font preloads, hero tag contrast, marquee pause."""

import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from kenzcloudx.tests.test_pages import html

APP = frappe.get_app_path("kenzcloudx")
RIBBON_ON = (
	"/",
	"/ar",
	"/erpnext",
	"/ar/erpnext",
	"/zatca",
	"/compliance",
	"/ar/compliance",
	"/plans",
	"/about",
	"/ar/about",
)
RIBBON_OFF = (
	"/demo",
	"/ar/demo",
	"/privacy",
	"/ar/privacy",
	"/terms",
	"/ar/terms",
	"/no-such-page",
	"/ar/no-such-page",
)


def _read(*parts):
	with open(os.path.join(APP, *parts), encoding="utf-8") as f:
		return f.read()


def _rule(css, selector):
	start = css.index(selector)
	return css[start : css.index("}", start)]


class TestRibbonBudget(FrappeTestCase):
	def test_ribbon_only_where_it_is_needed(self):
		for p in RIBBON_ON:
			_, h = html(p)
			self.assertIn('<canvas id="ribbon"', h, p)
			self.assertIn("/js/ribbon.js", h, p)
			self.assertIn('type="importmap"', h, p)
			self.assertNotIn("ribbon-off", h, p)
		for p in RIBBON_OFF:
			_, h = html(p)
			self.assertNotIn('<canvas id="ribbon"', h, p)
			self.assertNotIn("ribbon.js", h, p)
			self.assertNotIn("three.module", h, p)
			self.assertNotIn('type="importmap"', h, p)
			# the static CSS shape is shown instead, from the first paint
			self.assertRegex(h, r'<html lang="(en|ar)" dir="(ltr|rtl)" class="no-webgl ribbon-off">', p)
			self.assertIn('class="ribbon-fallback"', h, p)
			self.assertIn("/js/main.js", h, p)

	def test_ribbon_script_budget(self):
		js = _read("public", "js", "ribbon.js")
		self.assertIn("powerPreference: 'low-power'", js)
		self.assertNotIn("high-performance", js)
		self.assertIn("saveData", js)
		self.assertIn("deviceMemory", js)
		self.assertIn("webglcontextlost", js)
		self.assertRegex(js, r"if \(lost\)|!lost|lost =")
		self.assertIn("1000 / 30", js)
		# no object allocation per tile per frame
		self.assertNotIn("tmp.push({", js)


class TestNoJsNavigation(FrappeTestCase):
	def test_mobile_links_without_js(self):
		css = _read("public", "css", "kenz.css")
		self.assertIn(":root:not(.js) .mobile-panel", css)
		self.assertIn(".no-main .mobile-panel", css)
		self.assertIn(".no-main .menu-btn", css)
		_, h = html("/")
		self.assertIn('id="mobile-panel"', h)
		# the safety net marks a page whose main.js never started
		self.assertIn('r.classList.add("no-main")', h)


class TestHero(FrappeTestCase):
	def test_hero_heading_does_not_wait_for_js(self):
		for p in ("/", "/ar"):
			_, h = html(p)
			tag = re.search(r'<h1 [^>]*id="hero-heading"[^>]*>', h).group(0)
			self.assertNotIn("reveal", tag, p)
			self.assertIn("hero-in", tag, p)
		css = _read("public", "css", "kenz.css")
		self.assertIn("@keyframes hero-rise", css)
		rule = _rule(css, ".hero-in {")
		self.assertIn("animation: hero-rise", rule)
		reduced = css[css.index("@media (prefers-reduced-motion: reduce)") :]
		self.assertIn(".hero-in { animation: none", reduced)

	def test_font_preloads_match_the_hero_per_language(self):
		en = ("archivo-latin-wdth-normal.woff2", "playfair-display-latin-400-italic.woff2")
		ar = ("ibm-plex-sans-arabic-arabic-500-normal.woff2", "amiri-arabic-700-normal.woff2")
		for p, want, not_want in (("/", en, ar), ("/plans", en, ar), ("/ar", ar, en), ("/ar/plans", ar, en)):
			_, h = html(p)
			preloads = re.findall(
				r'<link rel="preload" href="/assets/kenzcloudx/fonts/([^"]+)" as="font" type="font/woff2" crossorigin>',
				h,
			)
			self.assertEqual(sorted(preloads), sorted(want), p)
			for f in not_want:
				self.assertNotIn(f, preloads, p)

	def test_hero_tag_contrast(self):
		css = _read("public", "css", "kenz.css")
		rule = _rule(css, ".hero-tag {")
		self.assertIn("color: var(--ink-2)", rule)


class TestMarquee(FrappeTestCase):
	def test_marquee_pauses_on_keyboard_focus(self):
		css = _read("public", "css", "kenz.css")
		self.assertIn(".marquee:hover .marquee-track", css)
		self.assertIn(".site-footer:focus-within .marquee-track", css)
		reduced = css[css.index("@media (prefers-reduced-motion: reduce)") :]
		self.assertIn(".marquee-track { animation: none", reduced)
