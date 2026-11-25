frappe.treeview_settings["Rental Location"] = {
	get_tree_nodes: "frappe.desk.treeview.get_children",
	add_tree_node: "frappe.desk.treeview.add_node",
	filters: [{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company") }],
	breadcrumb: "Rental",
	root_label: "All Locations",
	get_tree_root: false,
	ignore_fields: ["parent_rental_location"],
};
