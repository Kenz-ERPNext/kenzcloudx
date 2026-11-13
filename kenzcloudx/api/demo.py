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
# ASCII digits only ([0-9], not \d, which also matches fullwidth or Devanagari digits).
# A trunk 0 is allowed after the country code: +966 05XXXXXXXX is a common way to write it.
_KSA_MOBILE = re.compile(r"(?:\+966|00966|966)?0?(5[0-9]{8})")
# A strict ASCII allowlist for one plain address (checked after lowercasing). IDN domains are
# accepted in their punycode form (xn--...).
_EMAIL = re.compile(
	r"[a-z0-9](?:[a-z0-9._%+-]*[a-z0-9_+-])?@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}"
)
# Lead.email_id is a 140-character column: longer addresses are refused, never truncated
MAX_EMAIL = 140
_USERS = re.compile(r"[0-9]{1,6}")
DASH = "\u2013"  # en dash, for the email subject and ToDo summary


def normalize_ksa_phone(raw) -> str | None:
	"""Return a Saudi mobile number as +9665XXXXXXXX, or None.

	Accepts Arabic-Indic/Persian digits, spaces, dashes and brackets, and the forms 05XXXXXXXX,
	5XXXXXXXX, 9665XXXXXXXX, +9665XXXXXXXX (and 009665XXXXXXXX), each also with a 0 before
	the 5 after the country code (+96605XXXXXXXX).
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
	if not _USERS.fullmatch(value) or int(value) < 1:
		_fail(lang, "users")
	return int(value)


def _clean_email(raw, lang: str) -> str:
	"""Return the address trimmed and lowercased, or fail with the `email` error.

	Only surrounding whitespace is removed (nothing is cut or rewritten). The value must be ASCII
	before lowercasing (e.g. the Kelvin sign would otherwise become "k") and must fullmatch the
	allowlist. validate_email_address must return it unchanged: on its own it accepts display-name
	forms and lists and returns the extracted address, not the input.
	"""
	email = str(raw or "").strip()
	if not email:
		_fail(lang, "required")
	if len(email) > MAX_EMAIL or not email.isascii():
		_fail(lang, "email")
	email = email.lower()
	if not _EMAIL.fullmatch(email) or validate_email_address(email) != email:
		_fail(lang, "email")
	return email


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
		raw_phone=_line(phone),
		message=str(message or "").strip()[:MAX_MESSAGE],
		lang=lang,
		plan=plan if plan in PLAN_KEYS else None,
		zatca_required=1 if cint(zatca_required) else 0,
	)
	for field in ("full_name", "company", "raw_phone"):
		if not data[field]:
			_fail(lang, "required")
	if not str(email or "").strip():
		_fail(lang, "required")
	data.phone = normalize_ksa_phone(data.raw_phone)
	if not data.phone:
		_fail(lang, "phone")
	data.email = _clean_email(email, lang)
	data.users = _users(users, lang)

	lead_name = _existing_lead(data.email)
	if not lead_name:
		lead_name, created = _create_lead_or_find(data)
		if created:
			_notify(lead_name, data, None)
			return {"ok": True}

	# repeat request: no new Lead (ERPNext allows one Lead per email)
	status, owner = frappe.db.get_value("Lead", lead_name, ["status", "lead_owner"])
	_add_comment(lead_name, data)
	if status in CLOSED_STATUSES:
		_add_todo(lead_name, status, owner, data)
	_notify(lead_name, data, status)
	return {"ok": True}


def _create_lead_or_find(data) -> tuple[str, bool]:
	"""Create the Lead and return (name, True); or, if the insert fails because a Lead with this
	email was committed after our lookup, return (its name, False) so the caller comments on it.

	Limit: ERPNext's unique-email rule is an application-level SELECT in Lead.validate, not a
	database unique index. Two truly concurrent first submissions (neither committed yet) can both
	pass it and create two Leads. This code only covers a Lead committed between our lookup and
	our insert; the 5-per-hour rate limit makes the concurrent case unlikely. No locking is added.

	ERPNext's own message is never shown: it is English and names the existing Lead.
	"""
	messages_before = len(frappe.local.message_log)
	frappe.db.savepoint("kcx_demo_lead")
	try:
		name = _create_lead(data)
		frappe.db.release_savepoint("kcx_demo_lead")
		return name, True
	except (frappe.DuplicateEntryError, frappe.ValidationError):
		# also undoes the Contact that ERPNext creates in Lead.before_insert
		frappe.db.rollback(save_point="kcx_demo_lead")
		frappe.local.message_log = frappe.local.message_log[:messages_before]
		existing = _existing_lead(data.email)
		if existing:
			return existing, False
		# Survives the request rollback only because Error Log is non-transactional (MyISAM in
		# Frappe v15); TestDemoHTTP.test_generic_failure_is_logged_through_http guards that.
		frappe.log_error(
			title="KenzCloudX demo request: Lead insert failed",
			message=frappe.get_traceback(with_context=True),
		)
		_fail(data.lang, "generic")


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


def _add_todo(lead_name: str, status: str, owner, data) -> None:
	"""A closed Lead asked again: make sure someone follows up."""
	allocated_to = owner if owner and frappe.db.get_value("User", owner, "enabled") else "Administrator"
	summary = f"{data.company} {DASH} {data.full_name} {DASH} {data.phone}"
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": allocated_to,
			"reference_type": "Lead",
			"reference_name": lead_name,
			"priority": "High",
			"description": f"<p>New website demo request on a closed Lead ({escape(status)}):</p>"
			f"<p>{escape(summary)}</p>",
		}
	).insert(ignore_permissions=True)


def _recipients() -> list[str]:
	raw = frappe.db.get_single_value(SETTINGS, "notify_emails") or ""
	return [line.strip() for line in raw.splitlines() if line.strip()]


def _notify(lead_name: str, data, status) -> None:
	"""Email the sales team. Never lets a mail problem fail the request."""
	messages_before = len(frappe.local.message_log)
	try:
		recipients = _recipients()
		if not recipients:
			return
		subject = f"New demo request: {data.company}"
		if status is None:
			intro = "New Lead"
		elif status in CLOSED_STATUSES:
			subject = f"CLOSED Lead ({status}) {DASH} new request: {data.company}"
			intro = f"This Lead is closed ({status}); a ToDo was created to follow up. Lead"
		else:
			intro = f"Repeat request on an open Lead (status: {status})"
		link = get_url_to_form("Lead", lead_name)
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=f'<p>{escape(intro)}: <a href="{escape(link)}">{escape(lead_name)}</a></p>'
			f"<p>{_summary_html(data)}</p>",
			delayed=True,
		)
	except Exception:
		# e.g. no outgoing Email Account: keep its error out of the visitor's response
		frappe.local.message_log = frappe.local.message_log[:messages_before]
		frappe.log_error(title="KenzCloudX demo request: notification email failed")
