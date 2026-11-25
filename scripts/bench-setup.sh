#!/usr/bin/env bash
# Create a bench for Frappe/ERPNext v15 or v16 with this app installed.
# Usage: scripts/bench-setup.sh <15|16> [bench-dir]
# Versions (branches, Python, Node) are read from ci/versions.yml.
# Prereqs: frappe-bench CLI, git, MariaDB and Redis running, uv or pyenv for the Python version, nvm for Node.
set -euo pipefail
MAJOR="${1:?usage: bench-setup.sh <15|16> [bench-dir]}"
[[ "$MAJOR" =~ ^(15|16)$ ]] || { echo "major must be 15 or 16" >&2; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCH_DIR="${2:-$HOME/bench-v$MAJOR}"
# SKIP_ASSETS=1 skips the JS build (enough for backend tests)
SKIP=""; [ "${SKIP_ASSETS:-0}" = 1 ] && SKIP="--skip-assets"
SITE="${SITE:-rental$MAJOR.localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-root}"
v() { python3 "$ROOT/scripts/_versions.py" "$MAJOR" "$1"; }
PY="$(v python)"; NODE="$(v node)"; FB="$(v frappe_branch)"; EB="$(v erpnext_branch)"

[ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh" && nvm install "$NODE" && nvm use "$NODE"
if [ ! -d "$BENCH_DIR" ]; then
  bench init "$BENCH_DIR" --frappe-branch "$FB" --python "python$PY" --skip-redis-config-generation $SKIP
fi
cd "$BENCH_DIR"
# Redis endpoints (override with REDIS_CACHE / REDIS_QUEUE)
bench set-config -g redis_cache "${REDIS_CACHE:-redis://127.0.0.1:13000}"
bench set-config -g redis_queue "${REDIS_QUEUE:-redis://127.0.0.1:11000}"
bench set-config -g redis_socketio "${REDIS_QUEUE:-redis://127.0.0.1:11000}"
bench get-app https://github.com/frappe/erpnext --branch "$EB" $SKIP || true
if [ ! -d "sites/$SITE" ]; then
  bench new-site "$SITE" --mariadb-root-password "$DB_ROOT_PASSWORD" --admin-password "$ADMIN_PASSWORD"
fi
bench --site "$SITE" install-app erpnext
if [ -f "$ROOT/pyproject.toml" ]; then
  bench get-app "$ROOT" $SKIP || true
  bench --site "$SITE" install-app frappe_rental
  bench --site "$SITE" migrate
fi
bench --site "$SITE" set-config developer_mode 1
bench --site "$SITE" set-config allow_tests true
echo "Bench v$MAJOR ready at $BENCH_DIR, site $SITE"
