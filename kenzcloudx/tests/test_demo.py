"""Task 5: the demo / quote form creates ERPNext Leads.

Review Focus items tested here: 1 (Arabic submission), 2 (repeat submissions), 3 (honeypot and
rate limit), 5 (bad plan in the URL).
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_test_client

from kenzcloudx.api.demo import normalize_ksa_phone, submit_demo_request
from kenzcloudx.tests.test_pages import html
from kenzcloudx.website.context import load_content

SETTINGS = "KenzCloudX Settings"
METHOD = "kenzcloudx.api.demo.submit_demo_request"
ERR_EN = load_content("en")["demo"]["errors"]
ERR_AR = load_content("ar")["demo"]["errors"]


def submit(**kw):
	"""Call the API function directly as Guest, outside any HTTP request (no rate limit)."""
	base = dict(
		full_name="Ali Hassan",
		company="Nesco",
		phone="0551234567",
		email="ali@nesco.sa",
		users=5,
		zatca_required=1,
		plan="business",
		lang="en",
	)
	base.update(kw)
	request = getattr(frappe.local, "request", None)
	frappe.local.request = None
	frappe.set_user("Guest")
	try:
		return submit_demo_request(**base)
	finally:
		frappe.local.request = request
		frappe.set_user("Administrator")


def lead_for(email):
	name = frappe.db.get_value("Lead", {"email_id": email})
	return frappe.get_doc("Lead", name) if name else None


def comments_on(lead_name):
	return frappe.get_all(
		"Comment",
		filters={"reference_doctype": "Lead", "reference_name": lead_name, "comment_type": "Comment"},
		pluck="content",
	)


class TestDemoRequest(FrappeTestCase):
	"""Direct calls. FrappeTestCase rolls the transaction back after the class, so every
	Lead/Contact/Comment made here disappears; each test uses its own email."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_creates_lead(self):
		self.assertEqual(submit(message="Two branches\nNeed POS"), {"ok": True})
		lead = lead_for("ali@nesco.sa")
		self.assertIsNotNone(lead)
		self.assertEqual(lead.first_name, "Ali Hassan")
		self.assertEqual(lead.company_name, "Nesco")
		self.assertEqual(lead.mobile_no, "+966551234567")
		self.assertEqual(lead.source, "Website")
		self.assertEqual(lead.kcx_users, 5)
		self.assertEqual(lead.kcx_zatca_required, 1)
		self.assertEqual(lead.kcx_plan, "business")
		self.assertEqual(lead.kcx_language, "en")
		self.assertEqual(lead.status, "Lead")
		self.assertEqual(len(lead.notes), 1)
		self.assertIn("Two branches<br>Need POS", lead.notes[0].note)

	def test_optional_fields_may_be_empty(self):
		submit(email="min@x.sa", users=None, zatca_required=None, plan=None, message=None, lang=None)
		lead = lead_for("min@x.sa")
		self.assertFalse(lead.kcx_users)
		self.assertEqual(lead.kcx_zatca_required, 0)
		self.assertIsNone(lead.kcx_plan)
		self.assertEqual(lead.kcx_language, "en")
		self.assertEqual(len(lead.notes), 0)

	def test_form_strings_are_coerced(self):
		# an HTML form posts every value as a string
		submit(email="str@x.sa", users="٧", zatca_required="0", lang="ar")  # noqa: RUF001
		lead = lead_for("str@x.sa")
		self.assertEqual(lead.kcx_users, 7)
		self.assertEqual(lead.kcx_zatca_required, 0)
		self.assertEqual(lead.kcx_language, "ar")

	# Review Focus 2
	def test_duplicate_email_adds_comment(self):
		submit(email="dup@x.sa")
		submit(email=" DUP@x.sa ", message="again", company="Nesco Two")
		self.assertEqual(frappe.db.count("Lead", {"email_id": "dup@x.sa"}), 1)
		lead = frappe.db.get_value("Lead", {"email_id": "dup@x.sa"})
		comments = comments_on(lead)
		self.assertEqual(len(comments), 1)
		self.assertIn("again", comments[0])
		self.assertIn("Nesco Two", comments[0])

	def test_duplicate_of_closed_lead_does_not_fail(self):
		# ERPNext forbids two Leads with the same email, so a closed Lead gets the Comment too.
		submit(email="closed@x.sa")
		lead = frappe.db.get_value("Lead", {"email_id": "closed@x.sa"})
		frappe.db.set_value("Lead", lead, "status", "Converted")
		self.assertEqual(submit(email="closed@x.sa", message="back again"), {"ok": True})
		self.assertEqual(frappe.db.count("Lead", {"email_id": "closed@x.sa"}), 1)
		self.assertIn("back again", comments_on(lead)[0])

	def test_open_lead_preferred_over_closed_for_comment(self):
		submit(email="two@x.sa")
		lead = frappe.db.get_value("Lead", {"email_id": "two@x.sa"})
		self.assertEqual(submit(email="two@x.sa", message="m2"), {"ok": True})
		self.assertEqual(len(comments_on(lead)), 1)

	# Review Focus 1
	def test_arabic_digits_and_text(self):
		submit(
			full_name="علي حسن",
			company="شركة نسكو",
			phone="٠٥٥١٢٣٤٥٦٧",
			email="ar@x.sa",
			message="نحتاج نقاط البيع",
			lang="ar",
		)
		lead = lead_for("ar@x.sa")
		self.assertEqual(lead.mobile_no, "+966551234567")
		self.assertEqual(lead.first_name, "علي حسن")
		self.assertEqual(lead.company_name, "شركة نسكو")
		self.assertEqual(lead.kcx_language, "ar")
		self.assertIn("نحتاج نقاط البيع", lead.notes[0].note)

	# Review Focus 3 (honeypot)
	def test_honeypot_no_lead(self):
		self.assertEqual(submit(email="bot@x.sa", website="http://spam"), {"ok": True})
		self.assertFalse(frappe.db.exists("Lead", {"email_id": "bot@x.sa"}))
		# even an invalid bot submission gets the normal answer
		self.assertEqual(submit(email="nope", website="x"), {"ok": True})

	def test_invalid_inputs(self):
		cases = (
			(dict(email="nope"), "email"),
			(dict(email=" "), "required"),
			(dict(phone="12345"), "phone"),
			(dict(phone="0451234567"), "phone"),
			(dict(phone=""), "required"),
			(dict(full_name=" "), "required"),
			(dict(company=""), "required"),
			(dict(company=None), "required"),
			(dict(users=0), "users"),
			(dict(users="-3"), "users"),
			(dict(users="abc"), "users"),
		)
		before = frappe.db.count("Lead")
		for kw, key in cases:
			with self.assertRaises(frappe.ValidationError, msg=kw) as cm:
				submit(**{"email": "invalid@x.sa", **kw})
			self.assertEqual(str(cm.exception), ERR_EN[key], kw)
		self.assertEqual(frappe.db.count("Lead"), before)

	def test_errors_in_page_language(self):
		with self.assertRaises(frappe.ValidationError) as cm:
			submit(email="nope", lang="ar")
		self.assertEqual(str(cm.exception), ERR_AR["email"])
		with self.assertRaises(frappe.ValidationError) as cm:
			submit(email="nope", lang="fr")
		self.assertEqual(str(cm.exception), ERR_EN["email"])

	def test_unknown_plan_dropped(self):
		submit(email="p@x.sa", plan="<script>")
		self.assertIsNone(frappe.db.get_value("Lead", {"email_id": "p@x.sa"}, "kcx_plan"))

	def test_lengths_capped(self):
		submit(email="long@x.sa", full_name="A" * 500, company="B" * 500, message="C" * 5000)
		lead = lead_for("long@x.sa")
		self.assertEqual(lead.first_name, "A" * 140)
		self.assertEqual(lead.company_name, "B" * 140)
		self.assertIn("C" * 2000, lead.notes[0].note)
		self.assertNotIn("C" * 2001, lead.notes[0].note)

	def test_html_in_message_is_escaped(self):
		submit(email="xss@x.sa", message='<img src=x onerror="alert(1)">')
		note = lead_for("xss@x.sa").notes[0].note
		self.assertNotIn("<img", note)
		self.assertIn("&lt;img", note)
		submit(email="xss@x.sa", message="<b>again</b>", company="<i>Co</i>")
		comment = comments_on(frappe.db.get_value("Lead", {"email_id": "xss@x.sa"}))[0]
		self.assertNotIn("<b>again", comment)
		self.assertNotIn("<i>Co", comment)

	def test_normalize_ksa_phone(self):
		ok = (
			"0551234567",
			"551234567",
			"966551234567",
			"+966551234567",
			"+966 55 123 4567",
			"055-123-4567",
			"(055) 123 4567",
			"٠٥٥١٢٣٤٥٦٧",
			"۰۵۵۱۲۳۴۵۶۷",
			"+٩٦٦٥٥١٢٣٤٥٦٧",
			"+9660551234567",  # "+966 05…" is a common way to write it
			"96605 5123 4567",
			"009660551234567",
		)
		for raw in ok:
			self.assertEqual(normalize_ksa_phone(raw), "+966551234567", raw)
		for raw in (
			"",
			None,
			"12345",
			"0451234567",
			"05512345678",
			"+44 20 7946 0958",
			"abc",
			"０５５１２３４５６７",  # fullwidth digits  # noqa: RUF001
			"०५५१२३४५६७",  # Devanagari digits
			"+96605512345678",
		):
			self.assertIsNone(normalize_ksa_phone(raw), raw)


class TestDemoNotification(FrappeTestCase):
	def setUp(self):
		self.old = frappe.db.get_single_value(SETTINGS, "notify_emails")

	def tearDown(self):
		frappe.db.set_single_value(SETTINGS, "notify_emails", self.old)
		frappe.clear_document_cache(SETTINGS, SETTINGS)
		frappe.set_user("Administrator")

	def set_recipients(self, value):
		frappe.db.set_single_value(SETTINGS, "notify_emails", value)
		frappe.clear_document_cache(SETTINGS, SETTINGS)

	def test_email_to_each_recipient_line(self):
		self.set_recipients("sales@kenz.sa\n  ops@kenz.sa  \n\n")
		with patch("frappe.sendmail") as sendmail:
			submit(email="mail@x.sa", company="Nesco <b>")
		sendmail.assert_called_once()
		kw = sendmail.call_args.kwargs
		self.assertEqual(kw["recipients"], ["sales@kenz.sa", "ops@kenz.sa"])
		self.assertEqual(kw["subject"], "New demo request: Nesco <b>")
		self.assertTrue(kw["delayed"])
		self.assertIn("Nesco &lt;b&gt;", kw["message"])
		self.assertIn("+966551234567", kw["message"])

	def test_email_for_duplicate_too(self):
		self.set_recipients("sales@kenz.sa")
		with patch("frappe.sendmail") as sendmail:
			submit(email="mail2@x.sa")
			submit(email="mail2@x.sa")
		self.assertEqual(sendmail.call_count, 2)
		self.assertEqual(frappe.db.count("Lead", {"email_id": "mail2@x.sa"}), 1)

	def test_no_recipients_no_email(self):
		self.set_recipients("  \n ")
		with patch("frappe.sendmail") as sendmail:
			submit(email="quiet@x.sa")
		sendmail.assert_not_called()

	def test_email_failure_never_fails_request(self):
		self.set_recipients("sales@kenz.sa")

		def no_email_account(**kw):
			# what frappe.sendmail does when no outgoing Email Account is set up
			frappe.throw("Please setup default outgoing Email Account", frappe.OutgoingEmailError)

		frappe.local.message_log = []
		with patch("frappe.sendmail", side_effect=no_email_account), patch("frappe.log_error") as log:
			self.assertEqual(submit(email="fail@x.sa"), {"ok": True})
		log.assert_called_once()
		self.assertTrue(frappe.db.exists("Lead", {"email_id": "fail@x.sa"}))
		# the internal mail error must not reach the visitor's response
		self.assertEqual(frappe.local.message_log, [])


class TestDemoPage(FrappeTestCase):
	# Review Focus 5
	def test_demo_page_escapes_plan(self):
		code, h = html("/demo?plan=<script>alert(1)</script>")
		self.assertEqual(code, 200)
		self.assertNotIn("<script>alert(1)", h)
		self.assertNotIn("alert(1)", h)
		self.assertNotIn(" selected", h)

	def test_demo_page_preselects_known_plan(self):
		_, h = html("/ar/demo?plan=business")
		self.assertIn('<option value="business" selected>', h)
		self.assertIn("الأعمال", h)
		_, h = html("/demo?plan=enterprise")
		self.assertIn('<option value="enterprise" selected>', h)
		self.assertNotIn('<option value="business" selected>', h)

	def test_demo_page_not_cached(self):
		# the ?plan= pre-selection must never be served from the path-keyed page cache
		from kenzcloudx.www import demo
		from kenzcloudx.www.ar import demo as demo_ar

		for module in (demo, demo_ar):
			ctx = frappe._dict()
			module.get_context(ctx)
			self.assertEqual(ctx.no_cache, 1)

	def test_demo_form_markup(self):
		for path, lang in (("/demo", "en"), ("/ar/demo", "ar")):
			_, h = html(path)
			form = load_content(lang)["demo"]["form"]
			self.assertIn('<form class="demo-form"', h, path)
			for field in ("full_name", "company", "phone", "email", "users", "message"):
				self.assertIn(f'<label for="df-{field}"', h, (path, field))
				self.assertIn(f'id="df-{field}" name="{field}"', h, (path, field))
			self.assertIn('name="zatca_required" value="1"', h)
			self.assertIn('name="zatca_required" value="0"', h)
			self.assertIn("<fieldset", h)
			self.assertIn('<select id="df-plan" name="plan"', h)
			self.assertIn('<option value="">', h)
			self.assertIn(f'name="lang" value="{lang}"', h)
			self.assertIn('aria-live="polite"', h)
			self.assertIn(form["submit"], h)
			self.assertIn(load_content(lang)["demo"]["thanks"]["heading"], h)
			self.assertIn('data-msg-rate-limited="', h)
			self.assertIn("/assets/kenzcloudx/js/demo.js", h)
			self.assertIn("/api/method/kenzcloudx.api.demo.submit_demo_request", h)
			self.assertIn('type="tel" id="df-phone"', h.replace('<input type="tel"', 'type="tel"'))
			self.assertNotIn("Frappe", h)
			self.assertNotIn("{{", h)
			# the menu script from base.html is still there
			self.assertIn(".nav-toggle", h)

	def test_honeypot_markup(self):
		_, h = html("/demo")
		start = h.index('id="df-website"')
		tag = h[h.rindex("<input", 0, start) : h.index(">", start) + 1]
		self.assertIn('tabindex="-1"', tag)
		self.assertIn('autocomplete="off"', tag)
		self.assertIn('class="hp"', h)
		css = open(frappe.get_app_path("kenzcloudx", "public", "css", "kenz.css")).read()
		self.assertIn(".hp {", css)
		hp_rule = css[css.index(".hp {") : css.index("}", css.index(".hp {"))]
		self.assertIn("position: absolute", hp_rule)
		self.assertIn("inset-inline-start: -9999px", hp_rule)

	def test_phone_and_email_inputs_ltr_in_arabic(self):
		_, h = html("/ar/demo")
		for field in ("phone", "email"):
			start = h.index(f'id="df-{field}"')
			tag = h[h.rindex("<input", 0, start) : h.index(">", start) + 1]
			self.assertIn('dir="ltr"', tag, field)


class TestFixRound1(FrappeTestCase):
	"""Task 5 review, fix round 1."""

	def tearDown(self):
		frappe.set_user("Administrator")

	# 1. only a single bare address is accepted and stored
	def test_email_must_be_a_single_bare_address(self):
		for bad in (
			"x <a@x.sa>",
			"a@x.sa,b@y.sa",
			"<img src=x onerror=alert(1)> <a@x.sa>",
			"nope,a@x.sa",
			"a@x.sa;b@y.sa",
			'"a"@x.sa',
			"a b@x.sa",
			"a@x",
		):
			with self.assertRaises(frappe.ValidationError, msg=bad) as cm:
				submit(email=bad)
			self.assertEqual(str(cm.exception), ERR_EN["email"], bad)
		self.assertFalse(frappe.db.exists("Lead", {"email_id": ["like", "%a@x.sa%"]}))

	def test_valid_email_stored_bare_and_lowercase(self):
		submit(email="  Bare.Address+demo@Nesco.SA ")
		self.assertEqual(
			frappe.db.get_value("Lead", {"email_id": "bare.address+demo@nesco.sa"}, "email_id"),
			"bare.address+demo@nesco.sa",
		)

	# 2. repeat request on a closed Lead: Comment + ToDo + flagged notification
	def _closed_lead(self, email, owner=None, status="Converted"):
		submit(email=email)
		lead = frappe.db.get_value("Lead", {"email_id": email})
		frappe.db.set_value("Lead", lead, {"status": status, "lead_owner": owner})
		return lead

	def _todos(self, lead):
		return frappe.get_all(
			"ToDo",
			filters={"reference_type": "Lead", "reference_name": lead},
			fields=["allocated_to", "description", "status"],
		)

	def test_closed_lead_gets_comment_and_todo_for_administrator(self):
		lead = self._closed_lead("closed1@x.sa")
		with patch("frappe.sendmail"):
			self.assertEqual(submit(email="closed1@x.sa", company="<b>Nesco</b>"), {"ok": True})
		self.assertEqual(frappe.db.count("Lead", {"email_id": "closed1@x.sa"}), 1)
		self.assertEqual(len(comments_on(lead)), 1)
		todos = self._todos(lead)
		self.assertEqual(len(todos), 1)
		self.assertEqual(todos[0].allocated_to, "Administrator")
		self.assertEqual(todos[0].status, "Open")
		self.assertIn("+966551234567", todos[0].description)
		self.assertIn("Ali Hassan", todos[0].description)
		self.assertNotIn("<b>Nesco", todos[0].description)
		self.assertIn("&lt;b&gt;Nesco", todos[0].description)

	def test_closed_lead_todo_goes_to_enabled_lead_owner(self):
		owner = frappe.get_doc(
			{"doctype": "User", "email": "kcx-owner@x.sa", "first_name": "Owner", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		lead = self._closed_lead("closed2@x.sa", owner=owner.name, status="Do Not Contact")
		with patch("frappe.sendmail"):
			submit(email="closed2@x.sa")
		self.assertEqual(self._todos(lead)[0].allocated_to, owner.name)
		# a disabled owner falls back to Administrator
		frappe.db.set_value("User", owner.name, "enabled", 0)
		with patch("frappe.sendmail"):
			submit(email="closed2@x.sa")
		self.assertEqual(
			sorted(t.allocated_to for t in self._todos(lead)), sorted(["Administrator", owner.name])
		)

	def test_closed_lead_notification_is_flagged(self):
		old = frappe.db.get_single_value(SETTINGS, "notify_emails")
		try:
			frappe.db.set_single_value(SETTINGS, "notify_emails", "sales@kenz.sa")
			with patch("frappe.sendmail"):
				self._closed_lead("closed3@x.sa")
			with patch("frappe.sendmail") as sendmail:
				submit(email="closed3@x.sa")
			kw = sendmail.call_args.kwargs
			self.assertEqual(kw["subject"], "CLOSED Lead (Converted) – new request: Nesco")  # noqa: RUF001
			self.assertIn("closed", kw["message"])
			self.assertIn("ToDo", kw["message"])
		finally:
			frappe.db.set_single_value(SETTINGS, "notify_emails", old)

	def test_open_lead_repeat_has_no_todo_and_says_open(self):
		old = frappe.db.get_single_value(SETTINGS, "notify_emails")
		try:
			frappe.db.set_single_value(SETTINGS, "notify_emails", "sales@kenz.sa")
			with patch("frappe.sendmail"):
				submit(email="open1@x.sa")
			lead = frappe.db.get_value("Lead", {"email_id": "open1@x.sa"})
			with patch("frappe.sendmail") as sendmail:
				submit(email="open1@x.sa")
			self.assertEqual(self._todos(lead), [])
			kw = sendmail.call_args.kwargs
			self.assertEqual(kw["subject"], "New demo request: Nesco")
			self.assertIn("Repeat request on an open Lead (status: Lead)", kw["message"])
		finally:
			frappe.db.set_single_value(SETTINGS, "notify_emails", old)

	# 3. users parsing
	def test_users_parsing(self):
		for bad in ("²", "1" * 20, "0", "-3", "1.5", "١٢٣٤٥٦٧"):
			with self.assertRaises(frappe.ValidationError, msg=bad) as cm:
				submit(email="users-bad@x.sa", users=bad)
			self.assertEqual(str(cm.exception), ERR_EN["users"], bad)
		submit(email="users12@x.sa", users="12")
		submit(email="users-ar@x.sa", users="١٢")
		submit(email="users-max@x.sa", users="999999")
		self.assertEqual(frappe.db.get_value("Lead", {"email_id": "users12@x.sa"}, "kcx_users"), 12)
		self.assertEqual(frappe.db.get_value("Lead", {"email_id": "users-ar@x.sa"}, "kcx_users"), 12)
		self.assertEqual(frappe.db.get_value("Lead", {"email_id": "users-max@x.sa"}, "kcx_users"), 999999)

	# 4. a Lead that appears between the check and the insert (concurrent first submissions)
	def test_race_on_first_submission_falls_back_to_comment(self):
		from kenzcloudx.api import demo

		submit(email="race@x.sa")
		lead = frappe.db.get_value("Lead", {"email_id": "race@x.sa"})
		real = demo._existing_lead
		calls = []

		def first_miss(email):
			calls.append(email)
			return None if len(calls) == 1 else real(email)

		frappe.local.message_log = []
		with patch.object(demo, "_existing_lead", side_effect=first_miss):
			self.assertEqual(submit(email="race@x.sa", message="second"), {"ok": True})
		self.assertEqual(frappe.db.count("Lead", {"email_id": "race@x.sa"}), 1)
		self.assertIn("second", comments_on(lead)[0])
		self.assertEqual(frappe.local.message_log, [])  # ERPNext's English message is not leaked
		# the Contact made by the failed insert's before_insert was rolled back too
		self.assertEqual(frappe.db.count("Contact Email", {"email_id": "race@x.sa"}), 1)

	def test_insert_failure_gives_localized_generic_error(self):
		from kenzcloudx.api import demo

		submit(email="race2@x.sa")
		lead = frappe.db.get_value("Lead", {"email_id": "race2@x.sa"})
		frappe.local.message_log = []
		with patch.object(demo, "_existing_lead", return_value=None), patch("frappe.log_error") as log:
			with self.assertRaises(frappe.ValidationError) as cm:
				submit(email="race2@x.sa", lang="ar")
		log.assert_called_once()
		self.assertEqual(str(cm.exception), ERR_AR["generic"])
		self.assertNotIn(lead, str(cm.exception))
		messages = [m.get("message", "") for m in frappe.local.message_log]
		self.assertEqual(messages, [ERR_AR["generic"]])
		self.assertEqual(frappe.db.count("Lead", {"email_id": "race2@x.sa"}), 1)

	# 6. no invisible bidi controls in source
	def test_no_invisible_bidi_characters_in_source(self):
		import re

		for parts in (("public", "js", "demo.js"), ("api", "demo.py")):
			with open(frappe.get_app_path("kenzcloudx", *parts), encoding="utf-8") as f:
				src = f.read()
			self.assertIsNone(re.search("[‎‏‪-‮⁦-⁩]", src), parts)

	# 7. browser validation still works without JS
	def test_form_has_no_novalidate_attribute(self):
		_, h = html("/demo")
		start = h.index('<form class="demo-form"')
		self.assertNotIn("novalidate", h[start : h.index(">", start)])
		with open(frappe.get_app_path("kenzcloudx", "public", "js", "demo.js"), encoding="utf-8") as f:
			self.assertIn("form.noValidate = true", f.read())


class TestDemoHTTP(FrappeTestCase):
	"""Real HTTP requests through the WSGI app (in a thread, like Frappe's own API tests).

	These commit, so whatever they create is deleted in tearDown.
	"""

	EMAIL = "http-test@kenzcloudx-test.sa"

	def setUp(self):
		frappe.cache.delete_keys(f"rl:{METHOD}")
		self.client = get_test_client()
		self.started = frappe.utils.now()
		# the HTTP requests run on their own connection: commit a blank recipient list so the
		# suite never queues real emails on a site that has notify_emails configured
		self.notify_emails = frappe.db.get_single_value(SETTINGS, "notify_emails")
		frappe.db.set_single_value(SETTINGS, "notify_emails", "")
		frappe.db.commit()

	def tearDown(self):
		frappe.cache.delete_keys(f"rl:{METHOD}")
		frappe.set_user("Administrator")
		for name in frappe.get_all("Lead", filters={"email_id": self.EMAIL}, pluck="name"):
			frappe.delete_doc("Lead", name, force=True, ignore_permissions=True)
		# and the audit trail of those deletes (Lead and its auto-created Contact)
		since = {"creation": [">=", self.started]}
		frappe.db.delete("Deleted Document", {"deleted_doctype": ["in", ["Lead", "Contact"]], **since})
		frappe.db.delete(
			"Comment", {"comment_type": "Deleted", "reference_doctype": ["in", ["Lead", "Contact"]], **since}
		)
		frappe.db.set_single_value(SETTINGS, "notify_emails", self.notify_emails or "")
		frappe.db.commit()

	def post(self, **data):
		from frappe.tests.test_api import make_request

		payload = dict(
			full_name="HTTP Test",
			company="HTTP Co",
			phone="0551234567",
			email=self.EMAIL,
			users="3",
			zatca_required="1",
			plan="starter",
			lang="en",
			website="",
		)
		payload.update(data)
		return make_request(
			target=self.client.post,
			args=(f"/api/method/{METHOD}",),
			kwargs={"data": payload},
			site=frappe.local.site,
		)

	def test_http_tests_run_without_recipients(self):
		self.assertFalse(frappe.db.get_single_value(SETTINGS, "notify_emails"))

	def test_guest_post_without_csrf_creates_lead(self):
		r = self.post()
		self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
		self.assertEqual(r.json["message"], {"ok": True})
		frappe.db.rollback()  # see the other connection's commit
		lead = lead_for(self.EMAIL)
		self.assertEqual(lead.owner, "Guest")
		self.assertEqual(lead.kcx_plan, "starter")

	def test_validation_error_message_reaches_client(self):
		r = self.post(email="nope", lang="ar")
		self.assertEqual(r.status_code, 417)
		messages = [json.loads(m)["message"] for m in json.loads(r.json["_server_messages"])]
		self.assertEqual(messages, [ERR_AR["email"]])

	# Review Focus 3 (rate limit)
	def test_rate_limit(self):
		codes = [self.post(website="bot").status_code for _ in range(6)]
		self.assertEqual(codes, [200, 200, 200, 200, 200, 429])
		self.assertFalse(frappe.db.exists("Lead", {"email_id": self.EMAIL}))
