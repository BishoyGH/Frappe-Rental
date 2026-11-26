from frappe.model.document import Document

from frappe_rental.services import terms


class RentalClause(Document):
	def validate(self):
		terms.validate_jinja(self.body)
