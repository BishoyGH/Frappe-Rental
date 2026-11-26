frappe.query_reports["Rental Unit History"] = {
	filters: [
		{ fieldname: "rental_unit", label: __("Unit"), fieldtype: "Link", options: "Rental Unit", reqd: 1 },
	],
};
