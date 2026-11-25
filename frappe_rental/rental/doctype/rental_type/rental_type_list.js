frappe.listview_settings["Rental Type"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Install Presets"), () => {
			frappe.call({
				method: "frappe_rental.api.setup.install_presets",
				freeze: true,
				callback: (r) => {
					frappe.show_alert({ message: __("Installed: {0}", [(r.message || []).join(", ") || "-"]), indicator: "green" });
					listview.refresh();
				},
			});
		});
	},
};
