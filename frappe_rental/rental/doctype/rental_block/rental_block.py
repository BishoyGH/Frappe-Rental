from frappe.model.document import Document

from frappe_rental.services import availability


class RentalBlock(Document):
	def validate(self):
		availability.validate_range(self.from_datetime, self.to_datetime)

	def on_update(self):
		availability.reserve_block(self)

	def on_trash(self):
		availability.release("Rental Block", self.name)
