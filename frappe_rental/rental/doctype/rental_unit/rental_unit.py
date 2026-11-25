from frappe.utils.nestedset import NestedSet

from frappe_rental.services import unit as unit_service


class RentalUnit(NestedSet):
	nsm_parent_field = "parent_rental_unit"

	def validate(self):
		unit_service.validate_unit(self)

	def after_insert(self):
		unit_service.set_default_barcode(self)
