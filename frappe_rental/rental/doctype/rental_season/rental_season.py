from frappe.model.document import Document

from frappe_rental.services import rate_card as rate_card_service


class RentalSeason(Document):
	def validate(self):
		rate_card_service.validate_season(self)
