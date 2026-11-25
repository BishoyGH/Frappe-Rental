"""Install defaults (T04). Everything here is idempotent: safe to run on every install/migrate.

Names are constants because they are product concepts; company-specific values (accounts, warehouse)
are stored in Rental Settings and read from there by the rest of the app.
"""

import frappe

ROLES = (
	"Rental Admin",
	"Rental Manager",
	"Rental Agent",
	"Rental Provider",
	"Rental Accountant",
	"Rental Customer",
)
ITEM_GROUP = "Rentals"
WAREHOUSE = "Rented Out"

# settings fieldname -> (account name, root_type, parent hint account_type)
ACCOUNTS = {
	"rental_income_account": ("Rental Income", "Income"),
	"late_fee_income_account": ("Late Fee Income", "Income"),
	"damage_recovery_account": ("Damage Recovery", "Income"),
	"deposit_forfeiture_income_account": ("Deposit Forfeiture Income", "Income"),
	"deposit_liability_account": ("Customer Deposits (Rental)", "Liability"),
}


def create_defaults() -> None:
	"""Create global defaults and, if a company exists, its accounts and warehouse."""
	create_roles()
	create_item_group()
	company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	if company:
		create_company_defaults(company)


def create_roles() -> None:
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True  # install-time bootstrap, no user context
			)


def create_item_group() -> None:
	"""Create the Rentals item group. On a bare site (setup wizard not run) there is no root Item Group
	yet, so this is skipped and retried from the setup_wizard_complete and after_migrate hooks."""
	if frappe.db.exists("Item Group", ITEM_GROUP):
		return
	parent = frappe.db.get_value(
		"Item Group", {"is_group": 1, "parent_item_group": ["is", "not set"]}, "name"
	)
	if not parent:
		return
	frappe.get_doc(
		{"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": parent, "is_group": 0}
	).insert(ignore_permissions=True)  # install-time bootstrap


def create_company_defaults(company: str) -> None:
	"""Accounts and warehouse for one company; fill Rental Settings blanks (never overwrite)."""
	if not frappe.db.exists("Account", {"company": company}):
		# Chart of accounts not created yet; the setup_wizard_complete and after_migrate hooks retry.
		return
	settings = frappe.get_single("Rental Settings")
	if not settings.default_company:
		settings.default_company = company
	if settings.default_company != company:
		return
	for field, (name, root_type) in ACCOUNTS.items():
		if not settings.get(field):
			account = _ensure_account(company, name, root_type)
			if account:
				settings.set(field, account)
	if not settings.rented_out_warehouse:
		settings.rented_out_warehouse = _ensure_warehouse(company)
	settings.save(ignore_permissions=True)  # install-time bootstrap


def _ensure_account(company: str, name: str, root_type: str) -> str | None:
	"""Create the account under a group of root_type; None if the chart is not there yet."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	full = f"{name} - {abbr}"
	if frappe.db.exists("Account", full):
		return full
	# Prefer a non-root group of the right root type (e.g. Direct Income, Current Liabilities).
	parent = frappe.db.get_value(
		"Account",
		{"company": company, "root_type": root_type, "is_group": 1, "parent_account": ["is", "set"]},
		"name",
		order_by="lft asc",
	) or frappe.db.get_value(
		"Account", {"company": company, "root_type": root_type, "is_group": 1}, "name", order_by="lft asc"
	)
	if not parent:
		# Chart not created yet (Company insert runs before it); after_migrate or the wizard hook retries.
		return None
	frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": name,
			"company": company,
			"parent_account": parent,
			"is_group": 0,
			"root_type": root_type,
		}
	).insert(ignore_permissions=True)  # install-time bootstrap
	return full


def _ensure_warehouse(company: str) -> str:
	abbr = frappe.get_cached_value("Company", company, "abbr")
	full = f"{WAREHOUSE} - {abbr}"
	if frappe.db.exists("Warehouse", full):
		return full
	frappe.get_doc({"doctype": "Warehouse", "warehouse_name": WAREHOUSE, "company": company}).insert(
		ignore_permissions=True  # install-time bootstrap
	)
	return full
