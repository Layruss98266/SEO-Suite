# Deploying SEO Suite

SEO Suite is a stateful Flask app: it runs background jobs, streams live progress
over SSE, drives a real Chromium browser (Playwright) for indexation, and writes
reports and accounts to disk. That means it needs **a persistent server or
container running a single process**, not a serverless/functions platform.

## Will it run on Vercel / Netlify?

**No, not the app.** Serverless platforms give you short-lived function
invocations, a read-only filesystem, no background threads, and tight bundle-size
limits. SEO Suite needs the opposite on every count (long-running jobs, SSE,
Playwright, a writable data directory). A Vercel deploy fails with
`FUNCTION_INVOCATION_FAILED`. Use one of the options below instead. If you only
want the public marketing pages somewhere fast, host the app on Render/Fly and
point a domain at it — the marketing pages are served by the same app.

## Recommended: Render (one click)

1. Push this repo to GitHub (done).
2. In Render: **New → Blueprint**, select the repo. Render reads `render.yaml`.
3. It builds the `Dockerfile` and sets a generated `SEO_SUITE_SECRET`.
4. Open the URL. Create your admin account at `/signup` (the first account is an
   admin), or set `SEO_SUITE_USERNAME` / `SEO_SUITE_PASSWORD_HASH` env vars.

`render.yaml` ships on the **free** tier so you can deploy at zero cost. Free
instances have no persistent disk and sleep when idle, so `/app/data` (reports,
accounts, saved API keys) resets on redeploy/cold start.

**Upgrade to persistent (production):** in `render.yaml`, change `plan: free` to
`plan: starter` and uncomment the `disk:` block, then redeploy. Now `/app/data`
survives restarts.

## Fly.io

```bash
fly launch --copy-config --no-deploy     # uses fly.toml
fly volumes create seo_suite_data --size 1
fly secrets set SEO_SUITE_SECRET=$(python -c "import secrets;print(secrets.token_hex(32))")
fly deploy
```

## Docker (any host / VPS)

```bash
docker build -t seo-suite .
docker run -d -p 8080:8080 \
  -e SEO_SUITE_SECRET=$(python -c "import secrets;print(secrets.token_hex(32))") \
  -v seo_suite_data:/app/data \
  --name seo-suite seo-suite
```

Open http://localhost:8080.

## Plain VPS (no Docker)

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium
export SEO_SUITE_SECRET=...          # random 32+ char hex
gunicorn --workers 1 --threads 8 --worker-class gthread --timeout 300 \
  --bind 0.0.0.0:8080 app.server:app
```

Put nginx (or Caddy) in front for TLS.

## Key rules for any host

- **One instance / one process.** Run state and SSE subscriber queues live in
  memory, so multiple workers or instances would split the state. Scale up (more
  CPU/RAM), not out.
- **Persistent volume at `SEO_SUITE_DATA_DIR`** (default `/app/data`) for reports,
  uploads, and `seo_suite.db` (users, sessions, login history).
- **Set `SEO_SUITE_SECRET`** to a stable random value so logins survive restarts.
- **Auth:** either set `SEO_SUITE_USERNAME` + `SEO_SUITE_PASSWORD_HASH`, or just
  create the first account at `/signup` (it becomes the admin and turns auth on).
  On public cloud/PaaS hosting (like Render), authentication is strictly forced
  from first boot to prevent unauthorized public access before signup.
- **API keys** (PageSpeed, GSC, Moz, DataForSEO, SerpAPI, Groq) are entered in
  Settings and stored in `config.json` under the data directory.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `SEO_SUITE_SECRET` | Signs session cookies. Set a stable random value. |
| `SEO_SUITE_DATA_DIR` | Writable dir for data/reports/uploads (default `/app/data`). |
| `SEO_SUITE_USERNAME` / `SEO_SUITE_PASSWORD_HASH` | Optional env superadmin. |
| `SEO_SUITE_FORCE_AUTH` | Force authentication strictly (automatically true on Render). |
| `SEO_SUITE_COOKIE_SECURE` | Set to `1` for HTTPS-only session cookies + HSTS header. |
| `SEO_SUITE_HOST` / `PORT` | Bind host/port (Render and Fly set `PORT`). |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed origins. |
| `SENTRY_DSN` | Optional error tracking. |
| `SEO_SUITE_LOG_JSON` | Set to `1` to emit structured JSON logs (for ELK / Datadog / Loki). |
| `SEO_SUITE_USERS_BACKEND` | `sqlite` (default) or `json` for emergency rollback to the legacy file backend. |

## Health checks

| Endpoint | Purpose | Status codes |
|----------|---------|--------------|
| `GET /health` | Liveness probe — minimal, no auth, no run-state. | Always 200 if the process is alive. |
| `GET /health/ready` | Readiness probe — checks data dir is writable + sub-directories exist. | 200 healthy, 503 degraded (with per-check details in JSON body). |

Configure your load balancer / orchestrator to use `/health/ready` for readiness gating and `/health` for liveness checks. On Render, the default health check path is `/`; you can override to `/health` in `render.yaml`'s `healthCheckPath`.

## Prometheus metrics

`GET /metrics` exposes counters, histograms, and gauges in the standard Prometheus text format.

```
# example scrape config
scrape_configs:
  - job_name: seo-suite
    scrape_interval: 15s
    static_configs:
      - targets: ['seo-suite.example.com:8080']
```

**Security:** the endpoint is intentionally unauthenticated so Prometheus scrapers don't need credentials. Restrict access at the network layer:

* **Kubernetes:** NetworkPolicy allowing only the Prometheus pod
* **nginx:** `location /metrics { allow 10.0.0.0/8; deny all; }`
* **fly.io:** the internal `*.flycast` network is already private

Available metrics include `http_requests_total`, `http_request_duration_seconds`, `audit_runs_total`, `indexing_runs_total`, plus live `audit_running` / `indexing_running` / `sse_subscribers` gauges. See `ARCHITECTURE.md` for the full list.
