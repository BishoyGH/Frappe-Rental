from frappe.model.document import Document

from frappe_rental.services import booking as booking_service


class RentalBooking(Document):
	def validate(self):
		booking_service.validate_booking(self)
		booking_service.apply_pricing(self)
