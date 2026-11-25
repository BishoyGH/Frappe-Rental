app_name = "frappe_rental"
app_title = "Frappe Rental"
app_publisher = "Frappe Rental contributors"
app_description = "Generic rental engine for ERPNext: rent resources and services"
app_email = "noreply@example.com"
app_license = "gpl-3.0"
required_apps = ["erpnext"]

after_install = "frappe_rental.install.after_install"
after_migrate = ["frappe_rental.install.after_install"]

doc_events = {
	"Company": {"after_insert": "frappe_rental.install.company_after_insert"},
	"Item": {"on_update": "frappe_rental.services.rental_item.item_on_update"},
}
setup_wizard_complete = "frappe_rental.install.setup_wizard_complete"
