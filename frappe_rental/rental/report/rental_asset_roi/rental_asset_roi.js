frappe.query_reports["Rental Asset ROI"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
	],
};
