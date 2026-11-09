import json

import frappe
from frappe.tests.utils import FrappeTestCase

from kenzcloudx.website.context import (
	PAGES,
	PLAN_KEYS,
	alt_url,
	build_page_context,
	load_content,
	page_url,
)

BANNED = (
	"frappe",
	"empower",
	"next-gen",
	"seamless",
	"unlock",
	"revolutionize",
	"cutting-edge",
	"leverage",
	"elevate",
	"journey",
	"game-changer",
)


def _keys(d, p=""):
	return {p + k for k, v in d.items() if not k.startswith("_")} | {
		x for k, v in d.items() if isinstance(v, dict) for x in _keys(v, p + k + ".")
	}


class TestContext(FrappeTestCase):
	def test_page_url_and_alt(self):
		self.assertEqual(page_url("", "en"), "/")
		self.assertEqual(page_url("", "ar"), "/ar")
		self.assertEqual(page_url("erpnext", "en"), "/erpnext")
		self.assertEqual(page_url("zatca", "ar"), "/ar/zatca")
		self.assertEqual(alt_url("zatca", "en"), "/ar/zatca")
		self.assertEqual(alt_url("", "ar"), "/")

	def test_content_parity(self):
		en, ar = load_content("en"), load_content("ar")
		self.assertEqual(_keys(en), _keys(ar))
		self.assertEqual([p["key"] for p in en["plans"]["items"]], list(PLAN_KEYS))
		self.assertEqual([p["key"] for p in ar["plans"]["items"]], list(PLAN_KEYS))
		self.assertEqual(ar.get("_review"), "Arabic draft \u2013 needs native-speaker review")

	def test_every_page_has_meta(self):
		for lang in ("en", "ar"):
			content = load_content(lang)
			self.assertIn("common", content)
			for stem in PAGES:
				page = content[stem or "home"]
				self.assertTrue(page["meta"]["title"], (lang, stem))
				self.assertTrue(page["meta"]["description"], (lang, stem))
			for k in ("required", "email", "phone", "rate_limited", "generic"):
				self.assertTrue(content["demo"]["errors"][k], (lang, k))

	def test_build_context_ar(self):
		ctx = frappe._dict()
		build_page_context(ctx, "zatca", "ar")
		self.assertEqual(ctx.dir, "rtl")
		self.assertEqual(ctx.lang, "ar")
		self.assertEqual(ctx.alt_lang, "en")
		self.assertEqual(ctx.page_url, "/ar/zatca")
		self.assertEqual(ctx.alt_url, "/zatca")
		self.assertEqual(ctx.canonical, "https://kenzcloudx.com/ar/zatca")
		self.assertIn(("x-default", "https://kenzcloudx.com/zatca"), ctx.hreflang)
		self.assertIn(("en", "https://kenzcloudx.com/zatca"), ctx.hreflang)
		self.assertIn(("ar", "https://kenzcloudx.com/ar/zatca"), ctx.hreflang)
		self.assertEqual(ctx.title, load_content("ar")["zatca"]["meta"]["title"])
		self.assertEqual(ctx.description, load_content("ar")["zatca"]["meta"]["description"])
		self.assertIs(ctx.t, load_content("ar")["zatca"])
		self.assertIs(ctx.common, load_content("ar")["common"])
		self.assertEqual(ctx.settings["stat_live_sites"], 87)
		self.assertEqual(ctx.no_cache, 0)
		self.assertEqual(ctx.sitemap, 1)

	def test_build_context_en_home(self):
		ctx = frappe._dict()
		build_page_context(ctx, "", "en")
		self.assertEqual(ctx.dir, "ltr")
		self.assertEqual(ctx.page_url, "/")
		self.assertEqual(ctx.alt_url, "/ar")
		self.assertEqual(ctx.canonical, "https://kenzcloudx.com/")
		self.assertIs(ctx.t, load_content("en")["home"])

	def test_unknown_lang(self):
		with self.assertRaises(ValueError):
			load_content("fr")

	def test_no_banned_words(self):
		for lang in ("en", "ar"):
			raw = json.dumps(load_content(lang), ensure_ascii=False).lower()
			for w in BANNED:
				self.assertNotIn(w, raw, (lang, w))
