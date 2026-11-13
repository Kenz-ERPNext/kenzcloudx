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


def _shape_diff(a, b, path="$"):
	"""Return a list of structural differences between a and b (keys starting with "_" are skipped)."""
	if type(a) is not type(b):
		return [f"{path}: {type(a).__name__} != {type(b).__name__}"]
	if isinstance(a, dict):
		ka = {k for k in a if not k.startswith("_")}
		kb = {k for k in b if not k.startswith("_")}
		diffs = [f"{path}.{k}: missing in second" for k in sorted(ka - kb)]
		diffs += [f"{path}.{k}: missing in first" for k in sorted(kb - ka)]
		for k in sorted(ka & kb):
			diffs += _shape_diff(a[k], b[k], f"{path}.{k}")
		return diffs
	if isinstance(a, list):
		if len(a) != len(b):
			return [f"{path}: list length {len(a)} != {len(b)}"]
		diffs = []
		for i, (x, y) in enumerate(zip(a, b, strict=True)):
			diffs += _shape_diff(x, y, f"{path}[{i}]")
		return diffs
	return []


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
		self.assertEqual(_shape_diff(en, ar), [])
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
		self.assertIsInstance(ctx.settings["stat_live_sites"], int)
		self.assertIsInstance(ctx.settings["stat_zatca_customers"], int)
		self.assertNotIn("notify_emails", ctx.settings)
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

	def test_shape_diff_detects_list_item_differences(self):
		a = {"x": [{"k": 1, "v": "a"}], "_skip": {"y": 1}}
		self.assertEqual(_shape_diff(a, {"x": [{"k": 2, "v": "b"}], "_skip": []}), [])
		self.assertTrue(_shape_diff(a, {"x": [{"k": 1}]}))
		self.assertTrue(_shape_diff(a, {"x": [{"k": 1, "v": "a"}, {"k": 1, "v": "a"}]}))
		self.assertTrue(_shape_diff(a, {"x": [{"k": "1", "v": "a"}]}))

	def test_build_context_rejects_bad_input(self):
		for stem, lang in (("does-not-exist", "en"), ("common", "en"), ("zatca", "fr")):
			with self.assertRaises(ValueError):
				build_page_context(frappe._dict(), stem, lang)

	def test_unknown_lang(self):
		with self.assertRaises(ValueError):
			load_content("fr")

	def test_no_banned_words(self):
		for lang in ("en", "ar"):
			raw = json.dumps(load_content(lang), ensure_ascii=False).lower()
			for w in BANNED:
				self.assertNotIn(w, raw, (lang, w))


class TestWhatsAppNumber(FrappeTestCase):
	def test_normalise_whatsapp_number(self):
		from kenzcloudx.website.context import whatsapp_number

		cases = {
			"+966 55 123 4567": "966551234567",
			"0551234567": "966551234567",
			"٠٥٥١٢٣٤٥٦٧": "966551234567",
			"۰۵۵۱۲۳۴۵۶۷": "966551234567",
			"00966551234567": "966551234567",
			"551234567": "966551234567",
			"+44 20 7946 0958": "442079460958",
			"": None,
			None: None,
			"   ": None,
			"abc": None,
			"12": None,
			"0123": None,
		}
		for raw, expected in cases.items():
			self.assertEqual(whatsapp_number(raw), expected, raw)

	def test_context_strips_settings_and_sets_wa_number(self):
		ctx = frappe._dict()
		with patch_settings(phone="  ", email=" a@b.co ", whatsapp_number="0551234567"):
			build_page_context(ctx, "", "en")
		self.assertIsNone(ctx.settings["phone"])
		self.assertEqual(ctx.settings["email"], "a@b.co")
		self.assertEqual(ctx.wa_number, "966551234567")


class patch_settings:
	"""Temporarily set KenzCloudX Settings fields (rolled back by the test transaction)."""

	def __init__(self, **values):
		self.values = values

	def __enter__(self):
		for k, v in self.values.items():
			frappe.db.set_single_value("KenzCloudX Settings", k, v)
		frappe.clear_document_cache("KenzCloudX Settings", "KenzCloudX Settings")

	def __exit__(self, *exc):
		frappe.db.rollback()
		frappe.clear_document_cache("KenzCloudX Settings", "KenzCloudX Settings")


class TestContactFormatting(FrappeTestCase):
	def test_tel_href_keeps_only_plus_and_digits(self):
		from kenzcloudx.website.context import tel_href

		self.assertEqual(tel_href("+966 (11) 000-0000"), "+966110000000")
		self.assertEqual(tel_href("٠١١ ٠٠٠ ٠٠٠٠"), "0110000000")  # noqa: RUF001
		self.assertIsNone(tel_href(""))
		self.assertIsNone(tel_href(None))
		self.assertIsNone(tel_href("call us"))

	def test_whatsapp_display(self):
		from kenzcloudx.website.context import whatsapp_display

		self.assertEqual(whatsapp_display("966551234567"), "+966 55 123 4567")
		self.assertEqual(whatsapp_display("442079460958"), "+442079460958")
		self.assertIsNone(whatsapp_display(None))
