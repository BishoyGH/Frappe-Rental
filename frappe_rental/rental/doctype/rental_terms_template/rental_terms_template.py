from frappe.model.document import Document

from frappe_rental.services import terms


class RentalTermsTemplate(Document):
	def validate(self):
		terms.validate_template(self)
