"""Branded 404. Frappe renders the "404" template for every unknown route (NotFoundPage), and
kenzcloudx's www/404.html wins over frappe's because later-installed apps are searched first."""

import frappe

from kenzcloudx.website.context import build_not_found_context, lang_from_path

no_cache = 1
sitemap = 0


def get_context(context):
	request = getattr(frappe.local, "request", None)
	build_not_found_context(context, lang_from_path(getattr(request, "path", "")))
