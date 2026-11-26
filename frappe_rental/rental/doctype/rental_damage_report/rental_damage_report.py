from frappe.model.document import Document

from frappe_rental.services import damage


class RentalDamageReport(Document):
	def validate(self):
		damage.validate(self)

	def after_insert(self):
		damage.after_insert(self)

	def on_update(self):
		damage.on_update(self)
