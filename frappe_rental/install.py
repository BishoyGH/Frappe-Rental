from frappe_rental.services.setup import create_defaults


def after_install():
	from frappe_rental.services import custom_fields

	custom_fields.install()
	create_defaults()


def company_after_insert(doc, method=None):
	"""Create rental accounts and warehouse for companies created after install."""
	from frappe_rental.services.setup import create_company_defaults

	create_company_defaults(doc.name)


def setup_wizard_complete(args=None):
	"""Frappe calls this with the wizard args once setup completes; create anything skipped on a bare site."""
	create_defaults()
