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
	**{
		dt: {"after_insert": "frappe_rental.services.onboarding.on_insert"}
		for dt in (
			"Rental Type",
			"Rental Rate Card",
			"Rental Item",
			"Rental Unit",
			"Rental Booking",
			"Rental Alert Rule",
			"Rental Contract",
		)
	},
	"Company": {"after_insert": "frappe_rental.install.company_after_insert"},
	"Item": {"on_update": "frappe_rental.services.rental_item.item_on_update"},
	"Timesheet": {"on_submit": "frappe_rental.services.provider.on_timesheet_submit"},
}
setup_wizard_complete = "frappe_rental.install.setup_wizard_complete"

jinja = {"methods": ["frappe_rental.services.unit.qr_data_uri"]}

# Other apps may append dotted paths to fn(request, result) -> result to adjust quotes.
rental_pricing_hooks = []

scheduler_events = {
	"cron": {
		"*/5 * * * *": [
			"frappe_rental.services.lifecycle.expire_holds",
			"frappe_rental.services.events.remind_expiring_holds",
		]
	},
	"daily": [
		"frappe_rental.services.invoicing.run_due_invoices",
		"frappe_rental.services.waitlist.expire",
		"frappe_rental.services.esign.remind_unsigned",
		"frappe_rental.services.renewal.run",
	],
	"hourly": [
		"frappe_rental.services.handover.check_overdue",
		"frappe_rental.services.visits.check_sla",
		"frappe_rental.services.housekeeping.check_overdue",
	],
}

website_route_rules = [{"from_route": "/rental/<path:app_path>", "to_route": "rental"}]
