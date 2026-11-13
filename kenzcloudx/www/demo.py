from kenzcloudx.website.context import build_page_context

sitemap = 1


def get_context(context):
	build_page_context(context, "demo", "en")
