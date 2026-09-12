#!/usr/bin/env bash
#
# Phase 2 deploy: install Grafana + the SQLite datasource plugin on the Pi,
# run the collector as a systemd service, and provision the datasource and
# dashboard from this repo. Idempotent enough to re-run.
#
# Run on the Pi, from the repo root, as root:
#     sudo bash deploy/pi-grafana-setup.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COLLECTOR_USER="mikandro"
DATA_DIR="/home/${COLLECTOR_USER}/telemetry-pi/data"
DB_PATH="${DATA_DIR}/telemetry.sqlite"

if [[ "${EUID}" -ne 0 ]]; then
    echo "This script must run as root (use: sudo bash $0)" >&2
    exit 1
fi

echo "==> [1/6] Installing Grafana APT repository"
apt-get update -qq
apt-get install -y -qq apt-transport-https software-properties-common wget gnupg
mkdir -p /etc/apt/keyrings/
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor \
    | tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
    > /etc/apt/sources.list.d/grafana.list

echo "==> [2/6] Installing Grafana"
apt-get update -qq
apt-get install -y grafana

echo "==> [3/6] Installing SQLite datasource plugin"
grafana-cli plugins install frser-sqlite-datasource

echo "==> [4/6] Setting up shared 'telemetry' group and data dir permissions"
# grafana (reader) and the collector (writer) share a group so Grafana can read
# the WAL sidecar files the collector writes.
groupadd -f telemetry
usermod -aG telemetry "${COLLECTOR_USER}"
usermod -aG telemetry grafana
mkdir -p "${DATA_DIR}"
chgrp -R telemetry "${DATA_DIR}"
chmod 2775 "${DATA_DIR}"            # setgid so new files inherit the group
if compgen -G "${DB_PATH}*" > /dev/null; then
    chgrp telemetry "${DB_PATH}"* || true
    chmod 664 "${DB_PATH}"* || true
fi

echo "==> [5/6] Installing collector systemd service"
install -m 644 "${REPO_DIR}/systemd/telemetry-collector.service" \
    /etc/systemd/system/telemetry-collector.service
systemctl daemon-reload
systemctl enable --now telemetry-collector.service

echo "==> [6/6] Provisioning Grafana datasource + dashboard"
install -m 644 "${REPO_DIR}/grafana/provisioning/datasources/sqlite.yaml" \
    /etc/grafana/provisioning/datasources/pi-telemetry.yaml
install -m 644 "${REPO_DIR}/grafana/provisioning/dashboards/telemetry.yaml" \
    /etc/grafana/provisioning/dashboards/pi-telemetry.yaml
mkdir -p /var/lib/grafana/dashboards
install -m 644 "${REPO_DIR}/grafana/dashboards/pi-telemetry.json" \
    /var/lib/grafana/dashboards/pi-telemetry.json
chown -R grafana:grafana /var/lib/grafana/dashboards

systemctl enable grafana-server
systemctl restart grafana-server

echo
echo "Done. Grafana is starting on http://$(hostname).local:3000 (admin/admin)."
echo "Collector service status:  systemctl status telemetry-collector"
echo "Grafana service status:    systemctl status grafana-server"
