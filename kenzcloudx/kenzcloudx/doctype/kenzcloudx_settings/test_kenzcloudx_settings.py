import frappe
from frappe.tests.utils import FrappeTestCase


class TestKenzCloudXSettings(FrappeTestCase):
	def test_settings_defaults(self):
		s = frappe.get_single("KenzCloudX Settings")
		self.assertEqual(s.stat_live_sites, 87)
		self.assertEqual(s.stat_zatca_customers, 20)

	def test_lead_custom_fields_exist(self):
		for f in ("kcx_users", "kcx_zatca_required", "kcx_plan", "kcx_language"):
			self.assertTrue(frappe.get_meta("Lead").has_field(f), f)
		self.assertTrue(frappe.db.exists("Lead Source", "Website"))
