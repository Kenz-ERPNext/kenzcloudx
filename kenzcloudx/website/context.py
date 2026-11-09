import json
import os

import frappe

PAGES: tuple[str, ...] = ("", "erpnext", "zatca", "plans", "about", "demo", "privacy", "terms")
PLAN_KEYS: tuple[str, ...] = ("starter", "business", "enterprise")
LANGS: tuple[str, ...] = ("en", "ar")
BASE_URL = "https://kenzcloudx.com"

PUBLIC_SETTINGS_FIELDS: tuple[str, ...] = (
	"whatsapp_number",
	"phone",
	"email",
	"office_address_en",
	"office_address_ar",
	"cr_number",
	"vat_number",
	"stat_live_sites",
	"stat_zatca_customers",
)

_CONTENT_DIR = os.path.join(os.path.dirname(__file__), "content")
_cache: dict[str, dict] = {}


def load_content(lang: str) -> dict:
	"""Return the content dict for `lang`, read once per process.

	The returned dict is shared and cached: treat it as read-only.
	"""
	if lang not in LANGS:
		raise ValueError(f"Unsupported language: {lang!r}")
	if lang not in _cache:
		with open(os.path.join(_CONTENT_DIR, f"{lang}.json"), encoding="utf-8") as f:
			_cache[lang] = json.load(f)
	return _cache[lang]


def page_url(stem: str, lang: str) -> str:
	if lang == "ar":
		return f"/ar/{stem}" if stem else "/ar"
	return f"/{stem}"


def _other(lang: str) -> str:
	return "en" if lang == "ar" else "ar"


def alt_url(stem: str, lang: str) -> str:
	return page_url(stem, _other(lang))


def build_page_context(context, stem: str, lang: str) -> None:
	if lang not in LANGS:
		raise ValueError(f"Unsupported language: {lang!r}")
	if stem not in PAGES:
		raise ValueError(f"Unknown page stem: {stem!r}")
	content = load_content(lang)
	t = content[stem or "home"]

	context.lang = lang
	context.dir = "rtl" if lang == "ar" else "ltr"
	context.t = t
	context.common = content["common"]
	context.page_url = page_url(stem, lang)
	context.alt_url = alt_url(stem, lang)
	context.alt_lang = _other(lang)
	context.canonical = BASE_URL + context.page_url
	context.hreflang = [
		("en", BASE_URL + page_url(stem, "en")),
		("ar", BASE_URL + page_url(stem, "ar")),
		("x-default", BASE_URL + page_url(stem, "en")),
	]
	settings = frappe.get_cached_doc("KenzCloudX Settings")
	context.settings = {f: settings.get(f) for f in PUBLIC_SETTINGS_FIELDS}
	context.title = t["meta"]["title"]
	context.description = t["meta"]["description"]
	context.no_cache = 0
	context.sitemap = 1
