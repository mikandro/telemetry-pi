# Pi Telemetry

A home telemetry pipeline: a Raspberry Pi 4 collects system and sensor metrics,
ships them to AWS (Lambda + DynamoDB), and visualises them in a self-hosted
Grafana dashboard.

This is a portfolio project. It is built in phases, local-first, so each stage
works end to end before the next is added. The commit history and PR
descriptions deliberately document an AI-assisted development workflow.

## Architecture (target)

```
Raspberry Pi 4                         AWS                         Pi
+------------------+   HTTPS   +---------------------+       +-----------+
| collector (this) | --------> | API GW / IoT Core   |       |  Grafana  |
|  psutil+vcgencmd |           |   -> Lambda         | <---- |  (reads   |
|  -> SQLite (P1)  |           |   -> DynamoDB       |       |   DynamoDB|
+------------------+           +---------------------+       |   or SQL) |
                                                             +-----------+
```

## Build phases

| Phase | Scope | AWS cost |
|-------|-------|----------|
| 0 | Headless Pi foundation (SSH, OS updates) | none |
| 1 | **Local collection** — this collector, writing to SQLite | none |
| 2 | Local visualisation — Grafana on the Pi over the SQLite data | none |
| 3 | Cloud ingestion — API Gateway/IoT Core -> Lambda -> DynamoDB | ~$0.50-1.50/mo |
| 4 | Cloud-backed dashboard — Grafana points at DynamoDB | as above |
| 5 | Hardening — log retention, least-privilege IAM, retries/DLQ | as above |
| 6 | Optional — BME280 sensor, Alexa skill extension | small |

Currently at **Phase 1**.

## Metrics collected

Per sample (default every 60s):

- **CPU**: utilisation %, load averages (1/5/15 min)
- **Memory**: used/total bytes, percent, swap percent
- **Disk**: used/total bytes, percent (root filesystem by default)
- **Network**: cumulative tx/rx bytes plus per-interval tx/rx rate
- **Uptime**
- **Pi power/thermal** (via `vcgencmd`, when present): SoC temperature, core
  voltage, and decoded throttling/under-voltage flags (now + since-boot)

Off-device (no `vcgencmd`), the Pi-specific fields are recorded as `NULL` so the
collector runs anywhere for development.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# One sample, printed as JSON (good first sanity check):
python -m collector.collector --once

# Run the loop, writing to data/telemetry.sqlite every 60s:
python -m collector.collector --interval 60
```

Inspect what landed:

```bash
sqlite3 data/telemetry.sqlite "SELECT ts, cpu_percent, mem_percent, cpu_temp_c FROM readings ORDER BY ts DESC LIMIT 5;"
```

## Running as a service (on the Pi)

Once the data looks sane, run it under systemd so it survives reboots. A unit
file will be added in Phase 2; for now the loop can be started manually or via
`nohup`/`tmux`.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

Tests cover metric collection, `vcgencmd` output parsing (via mocked output, so
they pass off-device), and SQLite persistence.

## Design notes

- **DynamoDB over Timestream** for storage: cheaper and simpler to reason about
  at hobby volume.
- **Grafana self-hosted on the Pi** rather than Managed Grafana or EC2: the
  footprint is negligible at ~1 reading/minute, and running the full stack on
  one Pi is the better portfolio story.
- Reading field names are kept storage-friendly so they map cleanly onto both
  SQLite columns now and DynamoDB attributes later.
