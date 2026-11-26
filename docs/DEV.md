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

Verified 2026-11-25 in a Linux sandbox (Ubuntu 24.04, MariaDB 10.11 for both, Redis, Python 3.11/3.14, Node 18/24 from nodejs.org): Frappe/ERPNext v15.128/15.127 and v16.61, `install-app frappe_rental`, `migrate` and `run-tests --app frappe_rental` all pass on both. Gotchas found:
- Run `bench` as a non-root user; it refuses root.
- `bench get-app erpnext` needs the full URL (`https://github.com/frappe/erpnext`); the bare name failed behind the proxy.
- Each Node version needs its own `yarn` (`npm i -g yarn@1`). Set `SKIP_ASSETS=1` to skip the JS build when only backend tests matter.
- Install `cron` (bench calls `crontab`), `mariadb-server`, `libmariadb-dev`, `build-essential`, `pkg-config`.
- Set the utf8mb4 settings in the MariaDB config (`character-set-server=utf8mb4`, `collation-server=utf8mb4_unicode_ci`, `character-set-client-handshake=FALSE`).
- v15 `yarn install` could not fetch a GitHub tarball through the sandbox proxy (not an app issue); the sandbox used a no-op yarn shim, so JS assets were not built on v15 there.
- Not yet verified: MariaDB 10.6 / 11.8 exact versions, and the JS asset build on v15.

## Staff app (frontend)

The staff app lives in `frontend/` (Vue 3, `frappe-ui`, Vite 5) and is served at `/rental`.

```
cd frontend && yarn install --frozen-lockfile
yarn dev            # proxies API calls to the bench site on port 8000
yarn build          # writes frappe_rental/public/frontend and frappe_rental/www/rental.html
cd ../e2e && yarn install && BASE_URL=http://127.0.0.1:8000 yarn test   # Playwright smoke (Node >=20)
```

`bench build` runs the root `package.json` build script, so a normal bench build also builds the app.
The built files are not committed. Guests are redirected to `/login`; users need a Rental role (or System Manager).
