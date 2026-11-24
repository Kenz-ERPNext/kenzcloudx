"""Redesign v2, task A: shared page chrome (base, header, footer), self-hosted assets, ribbon."""

import json
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from kenzcloudx.tests.test_pages import ROUTES, html
from kenzcloudx.website.context import load_content

APP = frappe.get_app_path("kenzcloudx")
ASSETS = "/assets/kenzcloudx"
THREE = f"{ASSETS}/js/vendor/three-0.160.0"


def _routes_both_langs():
	for r in ROUTES:
		yield r
		yield "/ar" if r == "/" else "/ar" + r


def _read(*parts):
	with open(os.path.join(APP, *parts), encoding="utf-8") as f:
		return f.read()


class TestChromeMarkup(FrappeTestCase):
	def test_html_lang_and_dir(self):
		for p in ("/", "/plans", "/demo", "/ar", "/ar/plans", "/ar/demo"):
			_, h = html(p)
			expected = '<html lang="ar" dir="rtl"' if p.startswith("/ar") else '<html lang="en" dir="ltr"'
			self.assertIn(expected, h, p)

	def test_ribbon_canvas_and_scripts(self):
		for p in ("/", "/ar", "/about", "/ar/about"):
			_, h = html(p)
			self.assertIn('<canvas id="ribbon" aria-hidden="true"', h, p)
			self.assertIn('class="ribbon-fallback"', h, p)
			self.assertRegex(h, rf'<script type="module" src="{ASSETS}/js/ribbon\.js\?v=[^"]*"></script>', p)
			self.assertRegex(h, rf'<script src="{ASSETS}/js/main\.js\?v=[^"]*" defer></script>', p)
			importmap = re.search(r'<script type="importmap">(.*?)</script>', h, re.S)
			self.assertTrue(importmap, p)
			imports = json.loads(importmap.group(1))["imports"]
			self.assertEqual(imports["three"], f"{THREE}/three.module.min.js")
			self.assertEqual(imports["three/addons/"], f"{THREE}/addons/")
			# the import map must come before any module script
			self.assertLess(h.index('type="importmap"'), h.index('type="module"'), p)

	def test_ribbon_on_404_too(self):
		code, h = html("/ar/no-such-page")
		self.assertEqual(code, 404)
		self.assertIn('<canvas id="ribbon"', h)
		self.assertIn("/js/ribbon.js", h)

	def test_no_external_hosts_in_assets(self):
		"""Scripts, stylesheets, fonts and images are self-hosted; only canonical/hreflang/og may be absolute."""
		for p in ("/", "/ar", "/plans", "/ar/demo"):
			_, h = html(p)
			for tag in re.findall(r"<(?:script|link|img|source|iframe)\b[^>]*>", h):
				for url in re.findall(r'\b(?:src|href)="([^"]*)"', tag):
					if url.startswith(("http://", "https://", "//")):
						self.assertTrue(
							url.startswith("https://kenzcloudx.com/") or url == "https://kenzcloudx.com",
							(p, tag),
						)
						self.assertNotIn('rel="stylesheet"', tag, p)
						self.assertNotIn("<script", tag, p)
			importmap = re.search(r'<script type="importmap">(.*?)</script>', h, re.S).group(1)
			self.assertNotIn("http", importmap, p)
			for host in ("jsdelivr", "unpkg", "googleapis", "gstatic", "cdnjs"):
				self.assertNotIn(host, h, (p, host))

	def test_no_frappe_string_anywhere_public(self):
		for p in _routes_both_langs():
			_, h = html(p)
			self.assertNotIn("Frappe", h, p)
			self.assertNotIn("{{", h, p)

	def test_skip_link_and_main(self):
		for p in ("/", "/ar/zatca"):
			_, h = html(p)
			self.assertIn('href="#main"', h, p)
			self.assertIn('<main id="main"', h, p)
			self.assertLess(h.index('href="#main"'), h.index('<main id="main"'), p)

	def test_header_nav(self):
		en, ar = load_content("en")["common"], load_content("ar")["common"]
		_, h = html("/plans")
		header = h[h.index('<header class="nav"') : h.index("</header>")]
		for href in ('href="/erpnext"', 'href="/compliance"', 'href="/#how"', 'href="/plans"', 'href="/about"', 'href="/demo"', 'href="/login"'):
			self.assertIn(href, header, href)
		self.assertIn(f">{en['nav']['compliance']}<", header)
		self.assertIn(f">{en['nav']['how']}<", header)
		self.assertIn('aria-current="page"', header)
		self.assertNotIn('href="/zatca"', header)  # Compliance now has its own page (task B)
		# language switch: a real link to the Arabic version of the same page
		self.assertRegex(header, r'<a [^>]*href="/ar/plans"[^>]*hreflang="ar"[^>]*lang="ar"[^>]*>عربي</a>')
		_, h = html("/")
		header = h[h.index('<header class="nav"') : h.index("</header>")]
		self.assertIn('href="#how"', header)
		_, h = html("/ar/plans")
		header = h[h.index('<header class="nav"') : h.index("</header>")]
		for href in ('href="/ar/erpnext"', 'href="/ar#how"', 'href="/ar/demo"', 'href="/login"'):
			self.assertIn(href, header, href)
		self.assertIn(f">{ar['nav']['compliance']}<", header)
		self.assertRegex(header, r'<a [^>]*href="/plans"[^>]*hreflang="en"[^>]*lang="en"[^>]*>EN</a>')
		self.assertIn('aria-controls="mobile-panel"', header)

	def test_home_has_how_anchor(self):
		for p in ("/", "/ar"):
			_, h = html(p)
			self.assertIn('id="how"', h, p)

	def test_footer_marquee_translated(self):
		for p, lang in (("/", "en"), ("/ar", "ar")):
			_, h = html(p)
			footer = h[h.index('<footer class="site-footer"') :]
			self.assertIn('class="marquee"', footer, p)
			for word in load_content(lang)["common"]["footer"]["marquee"]:
				self.assertIn(f"<span>{word}</span>", footer, (p, word))
			self.assertIn(load_content(lang)["common"]["footer"]["marquee_label"], footer, p)

	def test_demo_band_links_to_demo(self):
		_, h = html("/ar/zatca")
		band = h[h.index('<section class="demo-band"') : h.index("</section>", h.index('<section class="demo-band"'))]
		self.assertIn('href="/ar/demo"', band)
		self.assertIn('data-pose="cta"', band)


class TestChromeSources(FrappeTestCase):
	def test_every_interpolation_is_escaped(self):
		"""Frappe's website Jinja has no autoescape: every {{ }} must end in |e (super() excepted)."""
		roots = [os.path.join(APP, "templates", "kenz"), os.path.join(APP, "www")]
		checked = 0
		for root in roots:
			for folder, _dirs, files in os.walk(root):
				for name in files:
					if not name.endswith(".html"):
						continue
					path = os.path.join(folder, name)
					with open(path, encoding="utf-8") as f:
						src = f.read()
					for expr in re.findall(r"\{\{(.*?)\}\}", src, re.S):
						checked += 1
						expr = expr.strip()
						self.assertTrue(expr == "super()" or expr.endswith("|e"), (os.path.relpath(path, APP), expr))
		self.assertGreater(checked, 50)

	def test_new_common_keys_in_both_languages(self):
		for lang in ("en", "ar"):
			c = load_content(lang)["common"]
			for key in ("compliance", "how"):
				self.assertTrue(c["nav"][key], (lang, key))
			for key in ("language", "menu_open", "menu_close"):
				self.assertTrue(c[key], (lang, key))
			self.assertEqual(c["lang_names"], {"en": "EN", "ar": "عربي"})
			f = c["footer"]
			for key in ("product_heading", "company_heading", "contact_heading", "legal_heading", "marquee_label", "ask"):
				self.assertTrue(f[key], (lang, key))
			self.assertEqual(len(f["marquee"]), 6, lang)
		self.assertEqual(load_content("ar")["common"]["nav"]["compliance"], "الامتثال الضريبي")
		self.assertEqual(load_content("ar")["common"]["nav"]["how"], "كيف نعمل")

	def test_css_uses_logical_properties_only(self):
		css = _read("public", "css", "kenz.css")
		css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
		bad = re.findall(
			r"(?<![\w-])(?:margin-left|margin-right|padding-left|padding-right|border-left|border-right"
			r"|left|right)\s*:|text-align\s*:\s*(?:left|right)|float\s*:\s*(?:left|right)",
			css,
		)
		self.assertEqual(bad, [])

	def test_fonts_referenced_exist_and_none_unused(self):
		css = _read("public", "css", "kenz.css")
		referenced = set(re.findall(r'url\("\.\./fonts/([^"]+)"\)', css))
		on_disk = {f for f in os.listdir(os.path.join(APP, "public", "fonts")) if f.endswith(".woff2")}
		self.assertEqual(referenced, on_disk)
		for family in ("Archivo", "Playfair Display", "Amiri", "IBM Plex Sans Arabic"):
			self.assertIn(f'font-family: "{family}"', css, family)
		ofl = _read("public", "fonts", "OFL.txt")
		for family in ("Archivo", "Playfair Display", "Amiri", "IBM Plex Sans Arabic"):
			self.assertIn(family, ofl)
		self.assertNotIn("http", css)

	def test_vendored_three_is_pinned_and_licensed(self):
		base = os.path.join(APP, "public", "js", "vendor", "three-0.160.0")
		self.assertTrue(os.path.isfile(os.path.join(base, "three.module.min.js")))
		self.assertTrue(os.path.isfile(os.path.join(base, "addons", "geometries", "RoundedBoxGeometry.js")))
		self.assertIn("MIT", _read("public", "js", "vendor", "three-0.160.0", "LICENSE"))
		with open(os.path.join(base, "three.module.min.js"), encoding="utf-8") as f:
			self.assertIn('const t="160"', f.read(1000))

	def test_scripts_have_no_cdn_imports(self):
		for name in ("ribbon.js", "main.js"):
			src = _read("public", "js", name)
			self.assertNotIn("http", src, name)
		self.assertIn("from 'three'", _read("public", "js", "ribbon.js"))
		self.assertIn("prefers-reduced-motion", _read("public", "js", "ribbon.js"))
		self.assertIn("no-webgl", _read("public", "js", "ribbon.js"))

