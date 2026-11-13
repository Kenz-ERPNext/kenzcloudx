"""Overrides the framework's stock /contact page so it is not listed in sitemap.xml.

hooks.website_redirects sends /contact to /about before this page is ever rendered;
get_context redirects too, in case the hook is bypassed.
"""

import frappe

sitemap = 0
no_cache = 1


def get_context(context):
	frappe.flags.redirect_location = "/about"
	raise frappe.Redirect(301)
