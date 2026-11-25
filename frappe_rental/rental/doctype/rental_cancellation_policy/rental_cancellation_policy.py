from frappe.model.document import Document

from frappe_rental.services import rate_card as rate_card_service


class RentalCancellationPolicy(Document):
	def validate(self):
		rate_card_service.validate_cancellation_policy(self)
