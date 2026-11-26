from frappe.model.document import Document

from frappe_rental.services import waitlist


class RentalWaitlistEntry(Document):
	def validate(self):
		waitlist.validate(self)
