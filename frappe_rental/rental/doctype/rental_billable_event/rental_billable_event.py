from frappe.model.document import Document

from frappe_rental.services import billable_events


class RentalBillableEvent(Document):
	def validate(self):
		billable_events.validate(self)


def on_doctype_update():
	from frappe_rental.services import indexes

	indexes.apply("Rental Billable Event")
