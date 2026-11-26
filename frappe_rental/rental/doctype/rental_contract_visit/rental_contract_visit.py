from frappe.model.document import Document


class RentalContractVisit(Document):
	pass


def on_doctype_update():
	from frappe_rental.services import indexes

	indexes.apply("Rental Contract Visit")
