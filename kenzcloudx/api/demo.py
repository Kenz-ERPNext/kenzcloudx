"""Demo / quote request form: every valid submission becomes (or updates) an ERPNext Lead."""

import re
from html import escape

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_url_to_form, now, validate_email_address

from kenzcloudx.website.context import _DIGITS, LANGS, PLAN_KEYS, load_content

SETTINGS = "KenzCloudX Settings"
CLOSED_STATUSES = ("Converted", "Do Not Contact")
MAX_NAME = 140
MAX_MESSAGE = 2000

# spaces (incl. NBSP), dashes, brackets and bidi marks that phones and copy-paste add
_PHONE_JUNK = re.compile(r"[\s\-\u2010-\u2015()\[\]{}\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_KSA_MOBILE = re.compile(r"(?:\+966|00966|966|0)?(5\d{8})")


def normalize_ksa_phone(raw) -> str | None:
	"""Return a Saudi mobile number as +9665XXXXXXXX, or None.

	Accepts Arabic-Indic/Persian digits, spaces, dashes and brackets, and the forms 05XXXXXXXX,
	5XXXXXXXX, 9665XXXXXXXX, +9665XXXXXXXX (and 009665XXXXXXXX).
	"""
	value = _PHONE_JUNK.sub("", str(raw or "").translate(_DIGITS))
	match = _KSA_MOBILE.fullmatch(value)
	return f"+966{match.group(1)}" if match else None


def _line(value, limit=MAX_NAME) -> str:
	"""Single-line text: whitespace collapsed, trimmed, capped."""
	return " ".join(str(value or "").split())[:limit]


def _fail(lang: str, key: str):
	frappe.throw(load_content(lang)["demo"]["errors"][key], frappe.ValidationError)


def _users(value, lang: str) -> int | None:
	value = str(value if value is not None else "").translate(_DIGITS).strip()
	if not value:
		return None
	if not value.isdigit() or int(value) < 1:
		_fail(lang, "users")
	return int(value)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=3600)
def submit_demo_request(
	full_name,
	company,
	phone,
	email,
	users=None,
	zatca_required=0,
	plan=None,
	message=None,
	lang="en",
	website=None,
) -> dict:
	if str(website or "").strip():
		return {"ok": True}  # honeypot: bots get the normal answer and nothing is stored

	lang = lang if lang in LANGS else "en"
	data = frappe._dict(
		full_name=_line(full_name),
		company=_line(company),
		email=_line(email).lower(),
		raw_phone=_line(phone),
		message=str(message or "").strip()[:MAX_MESSAGE],
		lang=lang,
		plan=plan if plan in PLAN_KEYS else None,
		zatca_required=1 if cint(zatca_required) else 0,
	)
	for field in ("full_name", "company", "raw_phone", "email"):
		if not data[field]:
			_fail(lang, "required")
	data.phone = normalize_ksa_phone(data.raw_phone)
	if not data.phone:
		_fail(lang, "phone")
	if not validate_email_address(data.email, throw=False):
		_fail(lang, "email")
	data.users = _users(users, lang)

	existing = _existing_lead(data.email)
	if existing:
		_add_comment(existing, data)
		lead_name = existing
	else:
		lead_name = _create_lead(data)

	_notify(lead_name, data, is_new=not existing)
	return {"ok": True}


def _existing_lead(email: str) -> str | None:
	"""The open Lead with this email; else any Lead with it.

	ERPNext refuses a second Lead with the same email (CRM Settings
	"allow_lead_duplication_based_on_emails" off), so a closed Lead gets the Comment instead.
	"""
	for status in (["not in", CLOSED_STATUSES], None):
		filters = {"email_id": email}
		if status:
			filters["status"] = status
		names = frappe.get_all("Lead", filters=filters, order_by="creation desc", limit=1, pluck="name")
		if names:
			return names[0]
	return None


def _summary_lines(data) -> list[tuple[str, str]]:
	return [
		("Name", data.full_name),
		("Company", data.company),
		("Mobile", data.phone),
		("Email", data.email),
		("Users", str(data.users) if data.users else "-"),
		("ZATCA Phase 2 needed", "Yes" if data.zatca_required else "No"),
		("Plan", data.plan or "-"),
		("Language", data.lang),
		("Message", data.message or "-"),
	]


def _html(text: str) -> str:
	return escape(text).replace("\r\n", "\n").replace("\n", "<br>")


def _summary_html(data) -> str:
	return "<br>".join(f"<b>{escape(label)}:</b> {_html(value)}" for label, value in _summary_lines(data))


def _create_lead(data) -> str:
	lead = frappe.get_doc(
		{
			"doctype": "Lead",
			"first_name": data.full_name,
			"company_name": data.company,
			"email_id": data.email,
			"mobile_no": data.phone,
			"source": "Website",
			"kcx_users": data.users,
			"kcx_zatca_required": data.zatca_required,
			"kcx_plan": data.plan,
			"kcx_language": data.lang,
		}
	)
	if data.message:
		# the Lead's Notes section (CRM Note), where sales read it
		lead.append(
			"notes", {"note": _html(data.message), "added_by": frappe.session.user, "added_on": now()}
		)
	lead.insert(ignore_permissions=True)
	return lead.name


def _add_comment(lead_name: str, data) -> None:
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "Lead",
			"reference_name": lead_name,
			"comment_email": data.email,
			"comment_by": data.full_name,
			"content": "<p>New demo request from the website:</p><p>" + _summary_html(data) + "</p>",
		}
	).insert(ignore_permissions=True)


def _recipients() -> list[str]:
	raw = frappe.db.get_single_value(SETTINGS, "notify_emails") or ""
	return [line.strip() for line in raw.splitlines() if line.strip()]


def _notify(lead_name: str, data, is_new: bool) -> None:
	"""Email the sales team. Never lets a mail problem fail the request."""
	messages_before = len(frappe.local.message_log)
	try:
		recipients = _recipients()
		if not recipients:
			return
		intro = "New Lead" if is_new else "Repeat request on an existing Lead"
		link = get_url_to_form("Lead", lead_name)
		frappe.sendmail(
			recipients=recipients,
			subject=f"New demo request: {data.company}",
			message=f'<p>{escape(intro)}: <a href="{escape(link)}">{escape(lead_name)}</a></p>'
			f"<p>{_summary_html(data)}</p>",
			delayed=True,
		)
	except Exception:
		# e.g. no outgoing Email Account: keep its error out of the visitor's response
		frappe.local.message_log = frappe.local.message_log[:messages_before]
		frappe.log_error(title="KenzCloudX demo request: notification email failed")
