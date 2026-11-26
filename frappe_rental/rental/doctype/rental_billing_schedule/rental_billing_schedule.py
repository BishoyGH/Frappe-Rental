from frappe.model.document import Document


class RentalBillingSchedule(Document):
	pass


def on_doctype_update():
	from frappe_rental.services import indexes

	indexes.apply("Rental Billing Schedule")
