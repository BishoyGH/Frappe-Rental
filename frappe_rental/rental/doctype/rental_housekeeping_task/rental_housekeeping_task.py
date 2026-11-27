from frappe.model.document import Document

from frappe_rental.services import housekeeping


class RentalHousekeepingTask(Document):
	def on_update(self):
		housekeeping.on_task_update(self)


def on_doctype_update():
	from frappe_rental.services import indexes

	indexes.apply("Rental Housekeeping Task")
