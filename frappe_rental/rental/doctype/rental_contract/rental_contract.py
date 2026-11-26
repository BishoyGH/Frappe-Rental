from frappe.model.document import Document

from frappe_rental.services import contracts


class RentalContract(Document):
	def validate(self):
		contracts.validate(self)
