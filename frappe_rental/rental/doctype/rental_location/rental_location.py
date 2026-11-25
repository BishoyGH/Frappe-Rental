from frappe.utils.nestedset import NestedSet

from frappe_rental.services import location as location_service


class RentalLocation(NestedSet):
	nsm_parent_field = "parent_rental_location"

	def validate(self):
		location_service.validate_timezone(self.timezone)

	def after_insert(self):
		location_service.ensure_cost_center(self)

	def on_update(self):
		super().on_update()
