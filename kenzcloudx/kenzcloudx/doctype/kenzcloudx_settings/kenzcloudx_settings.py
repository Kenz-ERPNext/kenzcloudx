from frappe.model.document import Document


class KenzCloudXSettings(Document):
	def on_update(self):
		# stats and contact details are rendered into cached pages: drop the page cache on every save
		from frappe.website import utils

		utils.clear_website_cache()
