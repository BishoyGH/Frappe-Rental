from frappe.model.document import Document

from frappe_rental.services import rental_type as rental_type_service


class RentalType(Document):
	def validate(self):
		rental_type_service.validate_custom_fields(self)

	def on_update(self):
		rental_type_service.sync_custom_fields(self)
