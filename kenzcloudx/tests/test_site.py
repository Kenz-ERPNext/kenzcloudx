"""Redesign v2, task C: site-level behaviour.

Settings save clears the website cache, pages behave correctly with the page cache ON, the canonical-host
redirect (before_request hook), redirects for stock routes that show the framework's branding, and the app
metadata / repository hygiene.
"""

import os
from unittest.mock import patch
from urllib.parse import urlparse

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request
from frappe.website.utils import clear_website_cache
from werkzeug.exceptions import HTTPException

from kenzcloudx import hooks
from kenzcloudx.redirects import canonical_host
from kenzcloudx.tests.test_pages import response

SETTINGS = "KenzCloudX Settings"
APP_ROOT = os.path.dirname(frappe.get_app_path("kenzcloudx"))
# sha1 of the phase-1 navy/mint social images, which must not come back
OLD_OG_SHA1 = ("a1cd661619ba410068e59a6c92714ab59e3b3e66", "af06420a61881edc5e35151c4cffb591c1a05209")


class TestSettingsClearCache(FrappeTestCase):
	def test_saving_settings_clears_website_cache(self):
		"""Stats and contact details are rendered into cached pages: a save must drop the page cache."""
		frappe.cache.hset("website_page", "kcx-cache-probe", {"en": "stale html"})
		self.assertTrue(frappe.cache.hget("website_page", "kcx-cache-probe"))
		frappe.get_single(SETTINGS).save(ignore_permissions=True)
		self.assertIsNone(frappe.cache.hget("website_page", "kcx-cache-probe"))

	def test_on_update_calls_clear_website_cache(self):
		with patch("frappe.website.utils.clear_website_cache") as clear:
			frappe.get_single(SETTINGS).save(ignore_permissions=True)
		clear.assert_called_once_with()


class TestPageCacheOn(FrappeTestCase):
	"""The test site runs in developer mode, which turns the page cache off. These tests switch it on
	(developer_mode 0, disable_website_cache 0) the way production runs, and render through the normal
	website pipeline, so they check the real cache_html behaviour and the X-From-Cache header."""

	def setUp(self):
		clear_website_cache()
		self.conf = patch.dict(frappe.local.conf, {"developer_mode": 0, "disable_website_cache": 0})
		self.conf.start()

	def tearDown(self):
		self.conf.stop()
		clear_website_cache()

	def get(self, path):
		frappe.local.response = frappe._dict()  # a fresh response per request, as in a real request
		r = response(path)
		return r, r.get_data(as_text=True)

	def test_cache_is_really_on(self):
		from frappe.website.utils import can_cache

		self.assertTrue(can_cache())

	def test_home_is_cacheable(self):
		r, first = self.get("/")
		self.assertEqual(r.headers["X-From-Cache"], "False")
		r, second = self.get("/")
		self.assertEqual(r.status_code, 200)
		self.assertEqual(r.headers["X-From-Cache"], "True")
		self.assertEqual(first, second)

	def test_demo_plan_is_never_served_from_cache(self):
		r, h = self.get("/demo?plan=starter")
		self.assertEqual(r.headers["X-From-Cache"], "False")
		self.assertIn('<option value="starter" selected>', h)
		r, h = self.get("/demo?plan=business")
		self.assertEqual(r.headers["X-From-Cache"], "False")
		self.assertIn('<option value="business" selected>', h)
		self.assertNotIn('<option value="starter" selected>', h)
		r, h = self.get("/ar/demo?plan=enterprise")
		self.assertEqual(r.headers["X-From-Cache"], "False")
		self.assertIn('<option value="enterprise" selected>', h)
		self.assertIn('dir="rtl"', h)

	def test_404_language_follows_the_url_every_time(self):
		for path, dir_ in (("/nope", "ltr"), ("/ar/nope", "rtl"), ("/nope", "ltr"), ("/ar/nope-2", "rtl")):
			r, h = self.get(path)
			self.assertEqual(r.status_code, 404, path)
			self.assertEqual(r.headers["X-From-Cache"], "False", path)
			self.assertIn(f'dir="{dir_}"', h, path)

	def test_settings_save_shows_new_stats_on_cached_home(self):
		r, h = self.get("/")
		r, h = self.get("/")
		self.assertEqual(r.headers["X-From-Cache"], "True")
		doc = frappe.get_single(SETTINGS)
		doc.stat_live_sites = 4321
		doc.save(ignore_permissions=True)
		r, h = self.get("/")
		self.assertEqual(r.headers["X-From-Cache"], "False")
		self.assertIn('data-count="4321"', h)


class TestCanonicalHost(FrappeTestCase):
	CANONICAL = {"kcx_canonical_host": "kenzcloudx.com"}  # noqa: RUF012

	def tearDown(self):
		frappe.local.request = None

	def run_hook(self, host, path="/", method="GET", query="", conf=None):
		"""Run the before_request hook for a request to http://<host><path>; return the redirect
		response, or None when the hook lets the request through."""
		set_request(method=method, path=path, query_string=query, base_url=f"http://{host}")
		conf = self.CANONICAL if conf is None else conf
		saved = {k: frappe.local.conf.get(k) for k in ("kcx_canonical_host", "kcx_alias_hosts")}
		for k in saved:
			frappe.local.conf.pop(k, None)
		frappe.local.conf.update(conf)
		try:
			canonical_host()
		except HTTPException as e:
			return e.get_response()
		finally:
			for k, v in saved.items():
				frappe.local.conf.pop(k, None)
				if v is not None:
					frappe.local.conf[k] = v
		return None

	def assertRedirect(self, r, location):
		self.assertIsNotNone(r)
		self.assertEqual(r.status_code, 301)
		self.assertEqual(r.headers["Location"], location)

	def test_hook_is_registered(self):
		self.assertIn("kenzcloudx.redirects.canonical_host", hooks.before_request)

	def test_does_nothing_when_not_configured(self):
		self.assertIsNone(self.run_hook("www.kenzcloudx.com", "/plans", conf={}))
		self.assertIsNone(self.run_hook("app.kenzcloudx.com", "/", conf={"kcx_canonical_host": ""}))

	def test_alias_hosts_redirect_with_path_and_query(self):
		for host in ("www.kenzcloudx.com", "kenzweb.kenzcloudx.com"):
			r = self.run_hook(host, "/plans", query="utm_source=x&a=%C3%A9")
			self.assertRedirect(r, "https://kenzcloudx.com/plans?utm_source=x&a=%C3%A9")
		self.assertRedirect(self.run_hook("www.kenzcloudx.com", "/"), "https://kenzcloudx.com/")
		self.assertRedirect(
			self.run_hook("www.kenzcloudx.com", "/ar/%D8%A7"), "https://kenzcloudx.com/ar/%D8%A7"
		)

	def test_host_matching_ignores_case_port_and_trailing_dot(self):
		for host in ("WWW.KenzCloudX.com", "www.kenzcloudx.com:8080", "www.kenzcloudx.com."):
			self.assertRedirect(self.run_hook(host, "/about"), "https://kenzcloudx.com/about")

	def test_head_redirects_but_other_methods_do_not(self):
		self.assertRedirect(
			self.run_hook("www.kenzcloudx.com", "/", method="HEAD"), "https://kenzcloudx.com/"
		)
		for method in ("POST", "PUT", "DELETE", "OPTIONS", "PATCH"):
			self.assertIsNone(self.run_hook("www.kenzcloudx.com", "/", method=method), method)

	def test_canonical_host_itself_is_left_alone(self):
		for host in ("kenzcloudx.com", "KENZCLOUDX.COM", "kenzcloudx.com:443"):
			self.assertIsNone(self.run_hook(host, "/plans"), host)

	def test_excluded_paths(self):
		for path in (
			"/api/method/ping",
			"/api/method/kenzcloudx.api.demo.submit_demo_request",
			"/assets/kenzcloudx/css/kenz.css",
			"/files/logo.png",
			"/private/files/x.pdf",
			"/app",
			"/app/lead",
			"/desk",
			"/socket.io/",
			"/backups/x.sql.gz",
			"/.well-known/acme-challenge/token",
			"/health",
			"/healthz",
		):
			self.assertIsNone(self.run_hook("www.kenzcloudx.com", path), path)
		# only whole path segments are excluded
		self.assertRedirect(
			self.run_hook("www.kenzcloudx.com", "/apps-list"), "https://kenzcloudx.com/apps-list"
		)

	def test_unknown_hosts_are_never_redirected(self):
		"""Host header injection: only listed alias hosts redirect, and only ever to the configured host."""
		for host in (
			"evil.com",
			"www.kenzcloudx.com.evil.com",
			"evilkenzcloudx.com",
			"www-kenzcloudx.com",
			"kenzcloudx.com.evil.com",
			"x.www.kenzcloudx.com",
			"localhost",
			"127.0.0.1",
		):
			self.assertIsNone(self.run_hook(host, "/plans"), host)

	def test_location_never_leaves_the_canonical_host(self):
		r = self.run_hook("www.kenzcloudx.com", "//evil.com/x")
		self.assertTrue(r.headers["Location"].startswith("https://kenzcloudx.com/"), r.headers["Location"])
		r = self.run_hook("www.kenzcloudx.com", "/a b", query="q=<x>")
		self.assertNotIn(" ", r.headers["Location"])
		self.assertNotIn("<", r.headers["Location"])

	def test_alias_hosts_from_config(self):
		conf = {
			"kcx_canonical_host": "kenzcloudx.com",
			"kcx_alias_hosts": ["old.example.com", "KenzCloudX.com"],
		}
		self.assertRedirect(self.run_hook("old.example.com", "/x", conf=conf), "https://kenzcloudx.com/x")
		# the defaults are replaced, not extended
		self.assertIsNone(self.run_hook("www.kenzcloudx.com", "/x", conf=conf))
		# a configured alias equal to the canonical host can never cause a loop
		self.assertIsNone(self.run_hook("kenzcloudx.com", "/x", conf=conf))
		conf["kcx_alias_hosts"] = "a.example.com, b.example.com"
		self.assertRedirect(self.run_hook("b.example.com", "/", conf=conf), "https://kenzcloudx.com/")

	def test_default_aliases_from_a_www_canonical_host(self):
		conf = {"kcx_canonical_host": "www.kenzcloudx.com"}
		self.assertIsNone(self.run_hook("www.kenzcloudx.com", "/", conf=conf))
		self.assertRedirect(
			self.run_hook("kenzweb.kenzcloudx.com", "/", conf=conf), "https://www.kenzcloudx.com/"
		)
		self.assertIsNone(self.run_hook("app.kenzcloudx.com", "/", conf=conf))

	def test_app_host_is_never_a_default_alias(self):
		"""app.kenzcloudx.com is reserved for the customer portal on this site: a cached 301 would bounce it."""
		from kenzcloudx.redirects import DEFAULT_ALIAS_PREFIXES

		self.assertEqual(DEFAULT_ALIAS_PREFIXES, ("www.", "kenzweb."))
		for path in ("/", "/plans", "/login"):
			self.assertIsNone(self.run_hook("app.kenzcloudx.com", path), path)
		# only when listed explicitly
		conf = {"kcx_canonical_host": "kenzcloudx.com", "kcx_alias_hosts": ["app.kenzcloudx.com"]}
		self.assertRedirect(self.run_hook("app.kenzcloudx.com", "/x", conf=conf), "https://kenzcloudx.com/x")

	def test_invalid_canonical_host_does_nothing(self):
		for bad in (
			"https://kenzcloudx.com",
			"kenzcloudx.com/x",
			"kenz cloudx.com",
			"kenzcloudx.com:8000",
			"-x.com",
		):
			self.assertIsNone(self.run_hook("www.kenzcloudx.com", "/", conf={"kcx_canonical_host": bad}), bad)


class TestStockRouteRedirects(FrappeTestCase):
	def test_branded_stock_routes_redirect_home(self):
		for src in ("/blog", "/blog/some-post", "/support", "/partners", "/search_help", "/help"):
			frappe.cache.delete_value("website_redirects")
			r = response(src)
			self.assertEqual(r.status_code, 301, src)
			self.assertEqual(urlparse(r.headers["Location"]).path, "/", (src, r.headers["Location"]))

	def test_login_and_password_pages_untouched(self):
		frappe.cache.delete_value("website_redirects")
		for path in ("/login", "/update-password"):
			r = response(path)
			self.assertEqual(r.status_code, 200, path)
		self.assertNotEqual(response("/blogger").status_code, 301)


class TestAppMetadata(FrappeTestCase):
	def test_hooks_metadata(self):
		self.assertEqual(hooks.app_title, "KenzCloudX")
		self.assertEqual(hooks.app_publisher, "Kenz Technology")
		self.assertEqual(hooks.app_email, "hello@kenzcloudx.com")
		self.assertTrue(hooks.app_description and hooks.app_description != "kenzcloudx")
		self.assertEqual(hooks.required_apps, ["frappe/erpnext"])

	def test_repository_files(self):
		self.assertFalse(os.path.exists(os.path.join(APP_ROOT, ".github", "workflows")))
		with open(os.path.join(APP_ROOT, "license.txt"), encoding="utf-8") as f:
			self.assertIn("Copyright (c) 2026 Kenz Technology", f.read())
		with open(os.path.join(APP_ROOT, "NOTICE"), encoding="utf-8") as f:
			notice = f.read()
		self.assertIn("kenzcloudx/public/images", notice)
		self.assertIn("kenzcloudx/website/content", notice)
		with open(os.path.join(APP_ROOT, "pyproject.toml"), encoding="utf-8") as f:
			pyproject = f.read()
		self.assertNotIn("gmail.com", pyproject)
		self.assertIn("hello@kenzcloudx.com", pyproject)
		with open(os.path.join(APP_ROOT, "README.md"), encoding="utf-8") as f:
			readme = f.read()
		self.assertIn("run-tests", readme)
		self.assertIn("production", readme)

	def test_social_images_are_regenerated_and_reproducible(self):
		import hashlib
		import struct

		for lang in ("en", "ar"):
			path = frappe.get_app_path("kenzcloudx", "public", "images", f"og-{lang}.png")
			with open(path, "rb") as f:
				head = f.read(24)
			self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
			self.assertEqual(struct.unpack(">II", head[16:24]), (1200, 630), lang)
			with open(path, "rb") as f:
				self.assertNotIn(hashlib.sha1(f.read()).hexdigest(), OLD_OG_SHA1, lang)
		for name in ("render.mjs", "og.html"):
			self.assertTrue(os.path.exists(os.path.join(APP_ROOT, "scripts", "og", name)), name)
