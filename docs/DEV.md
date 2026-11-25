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

## Two benches side by side

```
scripts/bench-setup.sh 15   # ~/bench-v15, site rental15.localhost
scripts/bench-setup.sh 16   # ~/bench-v16, site rental16.localhost
scripts/test-both.sh        # run the app tests on both, non-zero if either fails
```

The script reads branches, Python and Node from `ci/versions.yml`. Optional env: `SITE`, `ADMIN_PASSWORD`, `DB_ROOT_PASSWORD`, `BENCH_DIR_V15`, `BENCH_DIR_V16` (for the test helper). Prerequisites: `bench` CLI, git, running MariaDB (10.6 for v15, 11.8 for v16; use separate servers or ports, or one 10.6-compatible server for dev) and Redis, plus `nvm` and the required Python. The app is installed once `pyproject.toml` exists (T01). `.devcontainer/` is a minimal starting point.

Status: scripts are syntax-checked only; they have not been run end to end in this sandbox (no MariaDB or bench here). Run them on a real machine before relying on them.
