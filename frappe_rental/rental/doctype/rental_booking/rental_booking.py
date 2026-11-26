from frappe.model.document import Document

from frappe_rental.services import booking as booking_service
from frappe_rental.services import lifecycle


class RentalBooking(Document):
	def validate(self):
		booking_service.validate_booking(self)
		booking_service.apply_pricing(self)

	def on_update(self):
		lifecycle.on_update(self)

	def before_submit(self):
		lifecycle.before_submit(self)

	def on_cancel(self):
		lifecycle.on_cancel(self)

	def on_trash(self):
		lifecycle.on_trash(self)
