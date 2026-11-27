from frappe.model.document import Document


class RentalAvailabilityCache(Document):
	"""Busy windows per unit, written only by `services.availability`."""


def on_doctype_update():
	from frappe_rental.services import indexes

	indexes.apply("Rental Availability Cache")
