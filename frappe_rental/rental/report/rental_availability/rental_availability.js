frappe.query_reports["Rental Availability"] = {
	filters: [
		{ fieldname: "from_datetime", label: __("From"), fieldtype: "Datetime", reqd: 1 },
		{ fieldname: "to_datetime", label: __("To"), fieldtype: "Datetime", reqd: 1 },
		{ fieldname: "rental_type", label: __("Rental Type"), fieldtype: "Link", options: "Rental Type" },
		{ fieldname: "location", label: __("Location"), fieldtype: "Link", options: "Rental Location" },
	],
};
