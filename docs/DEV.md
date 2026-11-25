# Development guide

## Supported toolchain per Frappe major

Values come from `ci/versions.yml` (single source of truth, each value cites its upstream source). Do not copy them into other files; update the YAML and this table together.

| | Frappe/ERPNext v15 | Frappe/ERPNext v16 |
|---|---|---|
| Branch | `version-15` | `version-16` |
| Python | 3.11 (supports 3.11 to 3.14) | 3.14 |
| Node | 18 | 24 |
| MariaDB | 10.6 | 11.8 |
| Redis | 6.2 | 6.2 |

Notes:
- MariaDB: Frappe v15 warns outside 10.6 to 10.8; v16 warns above 11.8. CI uses the versions in the table.
- Redis: the table follows the `frappe_docker` reference stack. Official docs do not set a hard minimum.
- App bounds for `pyproject.toml` (T01): `frappe>=15,<17`, `erpnext>=15,<17`, Python `>=3.11`, declared through `[tool.bench.frappe-dependencies]`. ERPNext v15 itself needs Frappe >=15.111, v16 needs >=16.60.
- The app targets the lowest Python (3.11), so ruff uses `py311`.

Dev environment setup (two benches) is added by T00B.
