"""Role permission matrix (T09). The single source of truth for desk permissions on our doctypes.

Letters: r=read, w=write, c=create, d=delete. Customer and Provider are portal roles and get no desk
rights on master data yet; their portal access arrives with the portal tasks.
"""

PERMS = {"r": "read", "w": "write", "c": "create", "d": "delete"}

MATRIX = {
	"Rental Item": {
		"Rental Admin": "rwcd",
		"Rental Manager": "rwc",
		"Rental Agent": "r",
		"Rental Accountant": "r",
		"Rental Provider": "r",
	},
	"Rental Location": {
		"Rental Admin": "rwcd",
		"Rental Manager": "rwc",
		"Rental Agent": "r",
		"Rental Accountant": "r",
	},
	"Rental Type": {
		"Rental Admin": "rwcd",
		"Rental Manager": "r",
		"Rental Agent": "r",
		"Rental Accountant": "r",
	},
	"Rental Unit": {
		"Rental Admin": "rwcd",
		"Rental Manager": "rwc",
		"Rental Agent": "rw",
		"Rental Accountant": "r",
		"Rental Provider": "r",
	},
	"Rental Settings": {
		"System Manager": "rwc",
		"Rental Admin": "rwc",
		"Rental Manager": "r",
		"Rental Accountant": "r",
	},
}


def docperms(doctype: str) -> list[dict]:
	"""DocPerm rows for a doctype's JSON, built from MATRIX."""
	rows = []
	for role, letters in MATRIX[doctype].items():
		row = {"role": role, **{PERMS[ch]: 1 for ch in letters}}
		if "r" in letters:
			row.update({"report": 1, "export": 1, "print": 1, "email": 1, "share": 1})
		rows.append(row)
	return rows
