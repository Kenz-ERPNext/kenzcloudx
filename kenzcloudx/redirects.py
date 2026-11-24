"""Canonical host: send visitors on alias hosts (www., app., kenzweb.) to one public address.

Runs as a before_request hook (hooks.py). It does nothing unless site_config sets

    "kcx_canonical_host": "kenzcloudx.com"

and then answers GET/HEAD requests whose Host is a known alias with a 301 to
https://<canonical host><same path>?<same query>. The alias list is the optional site_config key
"kcx_alias_hosts" (a list, or a comma-separated string); by default it is www., app. and kenzweb. in front
of the canonical host's root domain. The target host only ever comes from site_config, never from the
request, and an unknown Host is left alone, so a forged Host header cannot steer the redirect. API calls,
assets, files, the desk, health checks and every non-GET/HEAD request are never redirected.
"""

import re
from urllib.parse import quote

import frappe
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect

DEFAULT_ALIAS_PREFIXES = ("www.", "app.", "kenzweb.")
# whole path segments that are never redirected
EXCLUDED_PREFIXES = (
	"/api",
	"/assets",
	"/files",
	"/private",
	"/app",
	"/desk",
	"/socket.io",
	"/backups",
	"/.well-known",
	"/health",
	"/healthz",
)
_HOSTNAME = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
# characters left as they are in the path / query of the Location (everything else is percent-encoded)
_SAFE_PATH = "/%:@!$&'()*+,;=-._~"
_SAFE_QUERY = _SAFE_PATH + "?"


def _host(value) -> str:
	"""Host name without port or trailing dot, lowercased."""
	value = str(value or "").strip().lower()
	if value.startswith("["):  # IPv6 literal: never one of ours
		return ""
	return value.rsplit(":", 1)[0].rstrip(".") if ":" in value else value.rstrip(".")


def _canonical() -> str | None:
	value = str(frappe.conf.get("kcx_canonical_host") or "").strip().lower()
	return value if value and _HOSTNAME.fullmatch(value) else None


def _aliases(canonical: str) -> set[str]:
	configured = frappe.conf.get("kcx_alias_hosts")
	if configured:
		if isinstance(configured, str):
			configured = configured.split(",")
		hosts = {_host(h) for h in configured}
	else:
		root = canonical
		for prefix in DEFAULT_ALIAS_PREFIXES:
			if root.startswith(prefix):
				root = root[len(prefix) :]
				break
		hosts = {prefix + root for prefix in DEFAULT_ALIAS_PREFIXES}
	return {h for h in hosts if h and h != canonical}


def _excluded(path: str) -> bool:
	return any(path == p or path.startswith(p + "/") for p in EXCLUDED_PREFIXES)


def canonical_host() -> None:
	request = getattr(frappe.local, "request", None)
	if request is None or request.method not in ("GET", "HEAD"):
		return
	canonical = _canonical()
	if not canonical:
		return
	host = _host(request.host)
	if host == canonical or host not in _aliases(canonical):
		return
	path = request.path or "/"
	if _excluded(path):
		return
	location = f"https://{canonical}{quote(path, safe=_SAFE_PATH)}"
	query = request.query_string.decode("latin-1")
	if query:
		location += "?" + quote(query, safe=_SAFE_QUERY)
	raise HTTPException(response=redirect(location, code=301))
