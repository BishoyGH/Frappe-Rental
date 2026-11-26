from frappe.model.document import Document

from frappe_rental.services import metering


class RentalMeterReading(Document):
	def validate(self):
		metering.validate_reading(self)


def on_doctype_update():
	from frappe_rental.services import indexes

	indexes.apply("Rental Meter Reading")
