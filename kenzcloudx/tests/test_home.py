"""Redesign v2, task B: the new home page, the /compliance page and the shared country tabs."""

import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from kenzcloudx.tests.test_pages import SETTINGS, html, set_settings
from kenzcloudx.website.context import PAGES, load_content, qr_path

APP = frappe.get_app_path("kenzcloudx")
COUNTRY_IDS = ("saudi-arabia", "india", "uae", "oman")
CURRENCIES = ("SAR", "INR", "AED", "OMR")
TAB_PAGES = ("/", "/ar", "/compliance", "/ar/compliance")


def _section(h, marker):
	"""The <section ...> element whose opening tag contains `marker`, up to its closing tag (no nesting)."""
	start = h.rfind("<section", 0, h.index(marker) + len(marker))
	return h[start : h.index("</section>", start)]


def _lp(path):
	return "/ar" if path.startswith("/ar") else ""


class TestHomeContent(FrappeTestCase):
	def test_compliance_is_a_page(self):
		self.assertIn("compliance", PAGES)

	def test_accent_headings_follow_the_pre_acc_post_convention(self):
		for lang in ("en", "ar"):
			home = load_content(lang)["home"]
			heads = [home["hero"]["h1"], home["demo_band"]["heading"]]
			heads += [home[k]["heading"] for k in ("benefits", "erp", "compliance", "looks", "how", "plans", "quotes", "faq")]
			heads.append(load_content(lang)["compliance"]["hero"]["h1"])
			heads.append(load_content(lang)["compliance"]["same"]["heading"])
			for hd in heads:
				self.assertEqual(set(hd), {"pre", "acc", "post"}, (lang, hd))
				self.assertTrue(hd["acc"].strip(), (lang, hd))
				# the accent is a word or a short phrase on one line (prototype: "for you")
				self.assertNotIn("\n", hd["acc"], (lang, hd))
				self.assertLessEqual(len(hd["acc"].split()), 2, (lang, hd))

	def test_countries_single_source(self):
		for lang in ("en", "ar"):
			c = load_content(lang)["compliance"]
			self.assertEqual([x["key"] for x in c["countries"]], list(COUNTRY_IDS), lang)
			self.assertEqual([x["invoice"]["currency"] for x in c["countries"]], list(CURRENCIES), lang)
			for x in c["countries"]:
				self.assertTrue(3 <= len(x["points"]) <= 4, (lang, x["key"]))
				for k in ("name", "code", "eyebrow", "heading", "intro"):
					self.assertTrue(x[k], (lang, x["key"], k))
			self.assertEqual(c["countries"][0]["more_stem"], "zatca")
			self.assertNotIn("countries", load_content(lang)["home"], "one source only: compliance.countries")

	def test_plans_teaser_has_three_plans(self):
		self.assertEqual(len(load_content("en")["plans"]["items"]), 3)

	def test_qr_path_is_deterministic_and_plain(self):
		a = qr_path("saudi-arabia")
		self.assertEqual(a, qr_path("saudi-arabia"))
		self.assertNotEqual(a, qr_path("india"))
		self.assertRegex(a, r"^[Mhvz0-9 \-]+$")


class TestHomePage(FrappeTestCase):
	def test_sections_in_prototype_order(self):
		for p in ("/", "/ar"):
			_, h = html(p)
			markers = [
				'data-pose="hero"',
				'class="stats',
				'data-pose="benefits"',
				'data-pose="erp"',
				'data-pose="compliance"',
				'data-pose="looks"',
				'id="how"',
				'data-pose="plans"',
				'data-pose="quotes"',
				'data-pose="faq"',
				'<section class="demo-band"',
				'<footer class="site-footer"',
			]
			pos = [h.find(m) for m in markers]
			self.assertNotIn(-1, pos, (p, dict(zip(markers, pos, strict=True))))
			self.assertEqual(pos, sorted(pos), p)
			self.assertEqual(h.count("<h1"), 1, p)

	def test_hero(self):
		for p, lang in (("/", "en"), ("/ar", "ar")):
			_, h = html(p)
			hero = _section(h, 'data-pose="hero"')
			h1 = load_content(lang)["home"]["hero"]["h1"]
			self.assertIn(f'<span class="acc">{h1["acc"]}</span>', hero, p)
			self.assertIn(f'href="{_lp(p)}/demo"', hero, p)
			self.assertIn('href="#how"', hero, p)
			self.assertIn('class="scroll-cue"', hero, p)
			self.assertIn('class="hero-tag', hero, p)

	def test_every_section_heading_has_an_accent_word(self):
		_, h = html("/")
		for pose in ("benefits", "erp", "compliance", "looks", "how", "plans", "quotes", "faq"):
			sec = _section(h, f'data-pose="{pose}"')
			self.assertIn('<span class="acc">', sec, pose)
		band = _section(h, '<section class="demo-band"')
		self.assertIn('<span class="acc">demo</span>', band)

	def test_stats_from_settings(self):
		old = frappe.get_single(SETTINGS)
		try:
			set_settings(stat_live_sites=91, stat_zatca_customers=23)
			for p in ("/", "/ar"):
				_, h = html(p)
				stats = _section(h, 'class="stats')
				self.assertIn('data-count="91">91<', stats, p)
				self.assertIn('data-count="4">4<', stats, p)
				self.assertEqual(stats.count('class="stat"'), 4, p)
				# the ZATCA customer count lives on the Saudi tab
				sa = h[h.index('id="saudi-arabia"') : h.index('id="india"', h.index('id="saudi-arabia"'))]
				self.assertIn(">23+<", sa, p)
			set_settings(stat_live_sites=0, stat_zatca_customers=0)
			for p in ("/", "/ar", "/compliance", "/ar/compliance"):
				_, h = html(p)
				self.assertNotIn("None", h, p)
				self.assertNotIn('data-count="0"', h, p)
				self.assertNotIn(">0+<", h, p)
			_, h = html("/")
			self.assertEqual(_section(h, 'class="stats').count('class="stat"'), 3)
		finally:
			set_settings(stat_live_sites=old.stat_live_sites, stat_zatca_customers=old.stat_zatca_customers)

	def test_benefits_erp_mock_and_looks(self):
		for p, tag in (("/", "Demo data"), ("/ar", "بيانات تجريبية")):
			_, h = html(p)
			self.assertEqual(_section(h, 'data-pose="benefits"').count('class="card glass'), 3, p)
			erp = _section(h, 'data-pose="erp"')
			self.assertRegex(erp, r'class="win"[^>]*aria-hidden="true"', p)
			self.assertIn(tag, erp, p)
			self.assertEqual(_section(h, 'data-pose="looks"').count('class="look look-'), 3, p)

	def test_how_timeline(self):
		for p in ("/", "/ar"):
			_, h = html(p)
			how = _section(h, 'id="how"')
			self.assertEqual(how.count('class="tl-step'), 4, p)
			self.assertIn('class="timeline"', how, p)

	def test_plans_teaser_no_prices_and_quote_links(self):
		for p in ("/", "/ar"):
			_, h = html(p)
			plans = _section(h, 'data-pose="plans"')
			for bad in ("SAR", "ر.س", "ريال", "INR", "AED", "OMR"):
				self.assertNotIn(bad, plans, (p, bad))
			self.assertIsNone(re.search(r'class="[^"]*price(?!-line)', plans), p)
			for key in ("starter", "business", "enterprise"):
				self.assertIn(f'href="{_lp(p)}/demo?plan={key}"', plans, (p, key))
			self.assertEqual(plans.count('class="plan-card'), 3, p)
			self.assertEqual(plans.count('class="badge"'), 1, p)
			self.assertLess(plans.index("plan=starter"), plans.index('class="badge"'))
			self.assertLess(plans.index('class="badge"'), plans.index("plan=business"))
			self.assertNotIn("[PLACEHOLDER]", plans, p)
		_, h = html("/")
		self.assertEqual(_section(h, 'data-pose="plans"').count(">Request a quote<"), 3)

	def test_testimonials_are_tagged_sample(self):
		for p, word in (("/", "Sample"), ("/ar", "نموذج")):
			_, h = html(p)
			quotes = _section(h, 'data-pose="quotes"')
			self.assertEqual(quotes.count(f'<span class="sample">{word}</span>'), 3, p)
			self.assertEqual(quotes.count("<blockquote"), 3, p)

	def test_faq_uses_details(self):
		for p, lang in (("/", "en"), ("/ar", "ar")):
			_, h = html(p)
			faq = _section(h, 'data-pose="faq"')
			n = len(load_content(lang)["home"]["faq"]["items"])
			self.assertEqual(faq.count("<details"), n, p)
			self.assertEqual(faq.count("<summary"), n, p)
			self.assertGreaterEqual(n, 5)

	def test_cta_band_links_to_demo(self):
		for p in ("/", "/ar"):
			_, h = html(p)
			band = _section(h, '<section class="demo-band"')
			self.assertIn(f'href="{_lp(p)}/demo"', band, p)


class TestCountryTabs(FrappeTestCase):
	def test_tabs_markup(self):
		"""Fix wave: without JS the HTML is plain in-page navigation (no tab semantics claiming 3 hidden
		panels while all 4 are shown); main.js adds role=tablist/tab/tabpanel and the aria-* on init."""
		for p in TAB_PAGES:
			_, h = html(p)
			for attr in ('role="tablist"', 'role="tab"', 'role="tabpanel"', "aria-selected", 'aria-controls="saudi'):
				self.assertNotIn(attr, h, (p, attr))
			self.assertEqual(len(re.findall(r'<nav class="tabs reveal" aria-label="[^"]+"', h)), 1, p)
			for cid in COUNTRY_IDS:
				# no-JS: each tab is an in-page link to its panel, every panel is shown
				self.assertRegex(h, rf'<a class="tab" id="tab-{cid}" href="#{cid}">', (p, cid))
				self.assertRegex(h, rf'<div class="tabpanel glass" id="{cid}">', (p, cid))
			self.assertNotRegex(h, r'class="tabpanel[^"]*"[^>]*hidden', p)
			for cur in CURRENCIES:
				self.assertIn(cur, h, (p, cur))
			start = h.index('id="saudi-arabia"')
			self.assertIn(f'href="{_lp(p)}/zatca"', h[start : h.index('id="india"', start)], p)

	def test_status_pills(self):
		_, h = html("/")
		for word in ("Cleared", "IRN generated", "Tax invoice"):
			self.assertIn(f">{word}</span>", h, word)
		self.assertIn("3XXXXXXXXXXXXX3", h)
		self.assertIn("27XXXXX0000X1Z5", h)
		self.assertIn("100XXXXXXXXXXX3", h)

	def test_mock_invoices_are_images_with_a_label_and_svg_qr(self):
		_, h = html("/compliance")
		self.assertEqual(len(re.findall(r'class="tinv"[^>]*role="img"[^>]*aria-label="[^"]+"', h)), 4)
		self.assertEqual(h.count('class="qr"'), 4)
		self.assertGreaterEqual(h.count("<svg viewBox=\"0 0 21 21\""), 4)

	def test_tab_script_is_shipped(self):
		with open(os.path.join(APP, "public", "js", "main.js"), encoding="utf-8") as f:
			js = f.read()
		for needle in ("ArrowLeft", "ArrowRight", "Home", "End", "hashchange", "rtl", "aria-selected", "tabIndex"):
			self.assertIn(needle, js, needle)
		# the tab semantics are added by the script, not sent in the HTML
		for needle in ('"role", "tablist"', '"role", "tab"', '"role", "tabpanel"', '"aria-controls"', '"aria-labelledby"'):
			self.assertIn(needle, js, needle)


class TestCompliancePage(FrappeTestCase):
	def test_compliance_page_both_langs(self):
		for p, lang, d in (("/compliance", "en", "ltr"), ("/ar/compliance", "ar", "rtl")):
			code, h = html(p)
			self.assertEqual(code, 200, p)
			self.assertIn(f'<html lang="{lang}" dir="{d}"', h, p)
			self.assertEqual(h.count("<h1"), 1, p)
			self.assertNotIn("Frappe", h, p)
			c = load_content(lang)["compliance"]
			self.assertIn(f'<span class="acc">{c["hero"]["h1"]["acc"]}</span>', h, p)
			self.assertIn(f'<link rel="canonical" href="https://kenzcloudx.com{p}">', h, p)
			self.assertEqual(h.count('rel="alternate"'), 3, p)
			same = _section(h, 'id="same-everywhere"')
			self.assertEqual(same.count("<h3"), len(c["same"]["items"]), p)
			self.assertEqual(len(c["same"]["items"]), 4)
			band = _section(h, '<section class="demo-band"')
			self.assertIn(f'href="{_lp(p)}/demo"', band, p)
			# the expanded tabs show each country's details
			self.assertEqual(h.count('class="tab-details"'), 4, p)

	def test_nav_points_at_compliance(self):
		for p in ("/", "/plans", "/ar/about"):
			_, h = html(p)
			header = h[h.index('<header class="nav"') : h.index("</header>")]
			self.assertIn(f'href="{_lp(p)}/compliance"', header, p)
			self.assertNotIn(f'href="{_lp(p)}/zatca"', header, p)
			footer = h[h.index('<footer class="site-footer"') :]
			self.assertIn(f'href="{_lp(p)}/compliance"', footer, p)
			self.assertIn(f'href="{_lp(p)}/zatca"', footer, p)
		_, h = html("/compliance")
		header = h[h.index('<header class="nav"') : h.index("</header>")]
		self.assertIn('href="/compliance" aria-current="page"', header)

	def test_home_links_to_compliance_page(self):
		for p in ("/", "/ar"):
			_, h = html(p)
			self.assertIn(f'href="{_lp(p)}/compliance"', _section(h, 'data-pose="compliance"'), p)
