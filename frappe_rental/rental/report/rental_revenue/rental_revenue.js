frappe.query_reports["Rental Revenue"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "group_by", label: __("Group by"), fieldtype: "Select", options: "rental_type\nlocation", reqd: 1, default: 'rental_type' },
	],
};
