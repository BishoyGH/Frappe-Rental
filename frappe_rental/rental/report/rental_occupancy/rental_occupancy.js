frappe.query_reports["Rental Occupancy"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_end() },
		{ fieldname: "location", label: __("Location"), fieldtype: "Link", options: "Rental Location" },
		{ fieldname: "rental_type", label: __("Rental Type"), fieldtype: "Link", options: "Rental Type" },
	],
};
