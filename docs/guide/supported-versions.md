# Supported versions

| Component | Supported |
| --- | --- |
| Frappe and ERPNext | v15 and v16 (one codebase) |
| Python, Node, MariaDB, Redis | as listed per major in [`ci/versions.yml`](../../ci/versions.yml) |
| Database | MariaDB. Postgres is planned (T54b) and not supported yet |

Every change is tested on both majors in CI. Version-specific code lives in `frappe_rental/compat/`; see
[`docs/COMPATIBILITY.md`](../COMPATIBILITY.md) for the rules. A nightly job tracks the next major (v17) and
is not a support promise until it is promoted.
