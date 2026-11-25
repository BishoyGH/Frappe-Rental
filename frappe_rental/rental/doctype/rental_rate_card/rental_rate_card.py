from frappe.model.document import Document

from frappe_rental.services import rate_card as rate_card_service


class RentalRateCard(Document):
	def validate(self):
		rate_card_service.validate_rate_card(self)
