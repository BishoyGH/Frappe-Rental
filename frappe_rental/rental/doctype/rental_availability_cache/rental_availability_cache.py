from frappe.model.document import Document


class RentalAvailabilityCache(Document):
	"""Busy windows per unit, written only by `services.availability`."""
