from frappe.model.document import Document

from frappe_rental.services import billing, calloff, lifecycle, provider
from frappe_rental.services import booking as booking_service


class RentalBooking(Document):
	def validate(self):
		booking_service.validate_booking(self)
		booking_service.apply_pricing(self)
		calloff.validate(self)
		provider.validate_booking(self)
		billing.update_schedule(self)

	def on_update(self):
		lifecycle.on_update(self)

	def before_submit(self):
		lifecycle.before_submit(self)

	def on_submit(self):
		lifecycle.on_submit(self)
		provider.ensure_project(self)

	def before_cancel(self):
		# Our Sales Order and Invoice link back here; lifecycle.on_cancel reverses them itself.
		self.ignore_linked_doctypes = ("Sales Order", "Sales Invoice", "Rental Availability Cache")

	def on_cancel(self):
		lifecycle.on_cancel(self)

	def on_trash(self):
		lifecycle.on_trash(self)
