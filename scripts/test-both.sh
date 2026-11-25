#!/usr/bin/env bash
# Run the app test suite on both benches. Usage: scripts/test-both.sh [extra run-tests args]
set -uo pipefail
rc=0
for m in 15 16; do
  dir="${BENCH_DIR_V$m:-$HOME/bench-v$m}"
  echo "=== v$m ($dir)"
  (cd "$dir" && bench --site "rental$m.localhost" run-tests --app frappe_rental "$@") || rc=1
done
exit $rc
