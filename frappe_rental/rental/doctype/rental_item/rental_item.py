import frappe
from frappe.model.naming import make_autoname
from frappe.website.website_generator import WebsiteGenerator

from frappe_rental.services import rental_item as rental_item_service


class RentalItem(WebsiteGenerator):
	website = frappe._dict(
		condition_field="is_published",
		page_title_field="item_name",
	)

	def autoname(self):
		# WebsiteGenerator would name by scrubbed title, which collides for same-named items.
		self.name = make_autoname("RI-.#####", doc=self)

	def validate(self):
		super().validate()
		if not self.image and self.images:
			self.image = self.images[0].image

	def on_update(self):
		super().on_update()
		rental_item_service.sync_item(self)

	def get_context(self, context):
		context.no_cache = 1
		context.rental_type = frappe.get_cached_doc("Rental Type", self.rental_type)
		from frappe_rental.services.public_site import item_context

		context.update(item_context(self))
