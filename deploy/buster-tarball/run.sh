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

# Derive everything from where this script lives, so there are no hardcoded
# user or home paths. run.sh is at <repo>/deploy/buster-tarball/run.sh.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
HP="${ROOT}/grafana-v9.5.21"
DB="${ROOT}/data/telemetry.sqlite"
RUNTIME="${ROOT}/.grafana-runtime"
CFG="${RUNTIME}/custom.ini"
# Pico DHT20 sensor node serial port (override with PICO_PORT=... if it differs;
# /dev/ttyACM0 is stable here as the only USB-serial device). The collector runs
# fine without it, so it is safe even when no Pico is attached.
PICO_PORT="${PICO_PORT:-/dev/ttyACM0}"
# Ventilation advisor: outdoor conditions from Open-Meteo for this location.
LAT="${LAT:-48.137}"   # Munich
LON="${LON:-11.575}"
# Push the ventilation advice to the Pico LCD + RGB ring (firmware flashed and
# hardware wired). Set PICO_DISPLAY=0 to disable if the display is disconnected.
PICO_DISPLAY="${PICO_DISPLAY:-1}"
DISPLAY_FLAG=""
[ "${PICO_DISPLAY}" = "1" ] && DISPLAY_FLAG="--pico-display"

mkdir -p "${ROOT}/data" "${ROOT}/logs" \
    "${RUNTIME}/provisioning/datasources" "${RUNTIME}/provisioning/dashboards"

# Render config + provisioning templates with the resolved paths.
sed "s|@PROVISIONING@|${RUNTIME}/provisioning|g" \
    "${HERE}/custom.ini.in" > "${CFG}"
sed "s|@DB@|${DB}|g" \
    "${HERE}/provisioning/datasources/sqlite.yaml.in" \
    > "${RUNTIME}/provisioning/datasources/sqlite.yaml"
sed "s|@DASHBOARDS@|${ROOT}/grafana/dashboards|g" \
    "${HERE}/provisioning/dashboards/telemetry.yaml.in" \
    > "${RUNTIME}/provisioning/dashboards/telemetry.yaml"

if ! pgrep -f "collector.collector" > /dev/null; then
    # PYTHONPATH so `-m collector.collector` resolves regardless of cwd.
    nohup env PYTHONPATH="${ROOT}" "${ROOT}/.venv/bin/python" -m collector.collector \
        --interval 15 --db "${DB}" --serial-port "${PICO_PORT}" \
        --advisor --lat "${LAT}" --lon "${LON}" ${DISPLAY_FLAG} \
        > "${ROOT}/logs/collector.log" 2>&1 &
    echo "collector started (pid $!)"
else
    echo "collector already running"
fi

# The tarball's grafana-server launches a process that shows as "grafana
# server" (space), so match both spellings or the guard never detects it.
if ! pgrep -f "grafana[- ]server" > /dev/null; then
    nohup "${HP}/bin/grafana-server" -homepath "${HP}" -config "${CFG}" \
        > "${ROOT}/logs/grafana.log" 2>&1 &
    echo "grafana started (pid $!)"
else
    echo "grafana already running"
fi
