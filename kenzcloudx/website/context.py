import json
import os
import re

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

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

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


def whatsapp_number(raw) -> str | None:
	"""Normalise a phone number for https://wa.me/<digits>.

	Accepts Arabic-Indic digits, spaces and punctuation. Saudi local forms (05XXXXXXXX, 5XXXXXXXX)
	become 9665XXXXXXXX; a 00 prefix is dropped. Returns None when no valid number remains.
	"""
	digits = re.sub(r"\D", "", str(raw or "").translate(_DIGITS))
	if digits.startswith("00"):
		digits = digits[2:]
	if re.fullmatch(r"05\d{8}", digits):
		digits = "966" + digits[1:]
	elif re.fullmatch(r"5\d{8}", digits):
		digits = "966" + digits
	if digits.startswith("966") and not re.fullmatch(r"966\d{9}", digits):
		return None
	return digits if re.fullmatch(r"[1-9]\d{7,14}", digits) else None


def _clean(value):
	if isinstance(value, str):
		return value.strip() or None
	return value


def _base_context(context, lang: str, t: dict) -> None:
	"""Language, direction, shared content and public settings for any KenzCloudX page."""
	content = load_content(lang)
	context.lang = lang
	context.dir = "rtl" if lang == "ar" else "ltr"
	context.t = t
	context.common = content["common"]
	context.alt_lang = _other(lang)
	settings = frappe.get_cached_doc("KenzCloudX Settings")
	context.settings = {f: _clean(settings.get(f)) for f in PUBLIC_SETTINGS_FIELDS}
	context.wa_number = whatsapp_number(context.settings["whatsapp_number"])
	context.title = t["meta"]["title"]
	context.description = t["meta"]["description"]


def build_page_context(context, stem: str, lang: str) -> None:
	if lang not in LANGS:
		raise ValueError(f"Unsupported language: {lang!r}")
	if stem not in PAGES:
		raise ValueError(f"Unknown page stem: {stem!r}")
	_base_context(context, lang, load_content(lang)[stem or "home"])
	context.page_url = page_url(stem, lang)
	context.alt_url = alt_url(stem, lang)
	context.canonical = BASE_URL + context.page_url
	context.hreflang = [
		("en", BASE_URL + page_url(stem, "en")),
		("ar", BASE_URL + page_url(stem, "ar")),
		("x-default", BASE_URL + page_url(stem, "en")),
	]
	context.no_cache = 0
	context.sitemap = 1


def build_not_found_context(context, lang: str) -> None:
	"""Context for the branded 404 page: no canonical/hreflang, never cached, not in the sitemap.

	The website page cache is keyed by template path ("404"), not by URL, so caching it
	would serve one language's 404 for both.
	"""
	if lang not in LANGS:
		raise ValueError(f"Unsupported language: {lang!r}")
	_base_context(context, lang, load_content(lang)["not_found"])
	context.page_url = None
	context.alt_url = page_url("", _other(lang))
	context.hreflang = []
	context.http_status_code = 404
	context.no_cache = 1
	context.sitemap = 0


def lang_from_path(path) -> str:
	"""Return "ar" for /ar and /ar/..., else "en"."""
	path = "/" + (path or "").strip("/")
	return "ar" if path == "/ar" or path.startswith("/ar/") else "en"
