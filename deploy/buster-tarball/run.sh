#!/usr/bin/env bash
#
# No-sudo runner for the throwaway Buster card: starts the collector and a
# home-dir Grafana (from the extracted tarball) as the current user, both
# detached via nohup. Not reboot-persistent; that's fine for a card that gets
# wiped at the 64-bit reflash. Re-running is safe (skips already-running procs).
#
#     bash deploy/buster-tarball/run.sh
#
set -euo pipefail

ROOT="/home/mikandro/telemetry-pi"
HP="${ROOT}/grafana-v9.5.21"
CFG="${ROOT}/deploy/buster-tarball/custom.ini"
DB="${ROOT}/data/telemetry.sqlite"

mkdir -p "${ROOT}/data" "${ROOT}/logs"

if ! pgrep -f "collector.collector" > /dev/null; then
    # PYTHONPATH so `-m collector.collector` resolves regardless of cwd.
    nohup env PYTHONPATH="${ROOT}" "${ROOT}/.venv/bin/python" -m collector.collector \
        --interval 15 --db "${DB}" \
        > "${ROOT}/logs/collector.log" 2>&1 &
    echo "collector started (pid $!)"
else
    echo "collector already running"
fi

if ! pgrep -f "grafana-server" > /dev/null; then
    nohup "${HP}/bin/grafana-server" -homepath "${HP}" -config "${CFG}" \
        > "${ROOT}/logs/grafana.log" 2>&1 &
    echo "grafana started (pid $!)"
else
    echo "grafana already running"
fi
