from frappe.model.document import Document

from frappe_rental.services import handover


class RentalHandover(Document):
	def validate(self):
		handover.validate(self)

	def on_submit(self):
		handover.on_submit(self)

	def on_cancel(self):
		handover.on_cancel(self)
