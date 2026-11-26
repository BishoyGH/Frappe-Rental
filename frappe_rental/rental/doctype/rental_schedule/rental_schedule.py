from frappe.model.document import Document

from frappe_rental.services import provider


class RentalSchedule(Document):
	def validate(self):
		provider.validate_schedule(self)
