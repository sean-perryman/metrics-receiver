# Metrics Receiver (dockerized)

A lightweight, self-hosted receiver for your Windows MetricsAgent JSON snapshots.

It provides:
- **JSON ingest API** (`POST /api/v1/ingest`) with **JSON Schema validation**
- **PostgreSQL** storage (historical data)
- **Web UI** (Tailwind) with:
  - Fleet **dashboard**
  - Per-host drilldown + **graphs** (CPU, mem, disk queue/latency, per-volume free%, NIC throughput/errors)
  - Global search (hostname | machine_id | username)
  - Low-disk table across all hosts/volumes
- **Alerting** (email/webhook/Discord webhook) for:
  - Missing heartbeats
  - Low disk (latest snapshots)
- **Multi-user + RBAC** (admin/viewer)
- Endpoint provisioning + **downloadable agent config**

> This receiver does **not require Grafana.** Grafana would only be needed if you want a separate dashboard system; this project already includes a built-in UI and charts.

## Quick start (VPS)

1. Install Docker + Docker Compose.
2. Clone and start:

```bash
git clone <this repo>
cd metrics-receiver
cp .env.example .env
# edit .env (at least SECRET_KEY + BOOTSTRAP_ADMIN_...)

docker compose up -d --build
```

3. Open:
- Web UI: `http://<VPS-IP>:8000/login`
- Login using `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` (created on first run).

## Security / TLS

Run the container behind a TLS-terminating reverse proxy (Caddy / Nginx / Traefik). The app sets secure cookies when `ENVIRONMENT=production`.

## Ingest API

**Endpoint:** `POST /api/v1/ingest`

- Authorization: `Bearer <endpoint token>`
- Body: either a single snapshot object or a 1-element array containing the snapshot (your current agent sample does this).

Example:

```bash
curl -X POST "https://receiver.example.com/api/v1/ingest" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d @sample.json
```

### Provision a new endpoint token + config

In the UI:
- **Admin → Endpoints → Create Endpoint**
- Then click **Download config** (JSON). This gives:
  - server_url
  - bearer_token
  - interval_seconds
  - per-metric enable flags

## Alerting

Alert checks run in-process via APScheduler (see `SCHEDULER_INTERVAL_SECONDS`).

Configure alerts in **Admin → Settings**. Example settings snippet:

```json
{
  "alerts": {
    "enabled": true,
    "dedup_minutes": 15,
    "low_disk_free_pct_threshold": 10.0,
    "heartbeat_grace_multiplier": 3,
    "heartbeat_min_grace_seconds": 120,
    "notify": {
      "email": {"enabled": true, "to": ["you@example.com"]},
      "webhook": {"enabled": false, "url": null},
      "discord": {"enabled": true, "webhook_url": "https://discord.com/api/webhooks/..."}
    }
  }
}
```

Email requires SMTP env vars (`SMTP_HOST`, etc.).

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# run db separately or use docker compose
alembic upgrade head
uvicorn app.main:app --reload
```

## Notes / Next upgrades

If you outgrow the simple token scan during ingest, switch to an indexed token scheme (HMAC with prefix) to avoid scanning endpoint rows.

You can also add:
- More alert types (CPU/RAM thresholds, per-volume thresholds, NIC errors)
- API keys for UI automation
- TimescaleDB for improved time-series performance

