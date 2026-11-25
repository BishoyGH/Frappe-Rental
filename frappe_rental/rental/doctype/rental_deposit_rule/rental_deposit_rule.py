from frappe.model.document import Document

from frappe_rental.services import rate_card as rate_card_service


class RentalDepositRule(Document):
	def validate(self):
		rate_card_service.validate_deposit_rule(self)
