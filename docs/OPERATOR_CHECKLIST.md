# Operator Checklist — what you need to do on your side

Everything in this document is **manual setup or operations work that
SEO Suite can't do for itself**. Codebase changes from recent sessions
have shipped a lot of new capabilities, but several of them require
out-of-band action by you (the operator) before they're useful in
production.

Items are grouped by priority and tagged with effort estimates.

---

## 🔴 Before going to production (must-do)

### 1. Set `SEO_SUITE_SECRET` to a stable value
**Why:** Session cookies are signed with this. If it's missing, the app
generates an ephemeral key on each restart and every login is invalidated.

**How:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Copy the 64-char hex string into your hosting dashboard's env vars
# Render: Dashboard → service → Environment → Add Variable
# Fly:    fly secrets set SEO_SUITE_SECRET=<value>
```

**Time:** 1 minute.

---

### 2. Stop using the env admin (`SEO_SUITE_PASSWORD_HASH`)
**Why:** That hash sits in environment variables — accessible via `ps aux`,
`/proc/$pid/environ`, container logs, and any `.env` file that gets
committed to git by accident. Every new release of SEO Suite forces this
user to set a per-user password on their next login (the
`must_rotate_password` flag in `/api/auth_status`).

**How:**
1. Log in as the env admin one last time.
2. Create a real user account via `POST /api/users` (admin endpoint) or
   `/signup` if signups are enabled. Use a **strong** password (zxcvbn
   will reject weak ones automatically).
3. Verify the new user can log in and is admin.
4. **Remove `SEO_SUITE_PASSWORD_HASH` from your env vars** on the host.
5. Restart the app.

**Time:** 5 minutes.

---

### 3. Run the data directory on a persistent volume
**Why:** Free Render and similar tiers have ephemeral disk. Reports,
SQLite, uploads, and login history all disappear on each redeploy.

**How:**
- **Render:** uncomment the `disk:` block in `render.yaml`, upgrade to
  `plan: starter`.
- **Fly.io:** `fly volumes create seo_suite_data --size 1` then ensure
  `fly.toml` has the mount mapping (it already does in the shipped config).
- **Docker on a VPS:** `-v seo_suite_data:/app/data`.

**Time:** 10 minutes.

---

### 4. Generate a GSC service account
Only if you actually want Search Console data in audits. See full guide:
[`docs/SETUP_GUIDES.md`](SETUP_GUIDES.md) → "Google Search Console".

**Steps 1–6 are all on Google's side** — no code changes here.

**Time:** ~15 minutes (including Step 5: granting the service account
access to your Search Console property — this is the step nobody can
skip).

---

### 5. Configure SMTP for the auth emails to work
The following features **silently no-op without SMTP**:
- Password reset (`POST /api/auth/request_password_reset`)
- Email verification (`POST /api/auth/send_verification`)
- New-device login notifications (sent on novel IP + UA combinations)

**How:**
Set these in `config.json` (via the Settings UI, which is initialized from `config.json.example` on setup) or `.env`:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=<app-specific password — Gmail requires this>
EMAIL_FROM=you@gmail.com
```

For Gmail you need an "App password" from your Google account security
settings. SendGrid, Postmark, AWS SES all work too.

**Time:** 10 minutes.

---

## 🟠 Recommended (production-ready)

### 6. Configure HTTPS-only cookies + HSTS
**Why:** On a real domain over HTTPS the session cookie should never
flow over plain HTTP.

**How:**
```
SEO_SUITE_COOKIE_SECURE=1
```
This also activates the HSTS response header.

Render serves HTTPS by default, so set this there. Fly likewise.

**Time:** 30 seconds.

---

### 7. Restrict the `/metrics` and `/openapi.yaml` endpoints
**Why:** They're intentionally unauthenticated — Prometheus scrapers
can't send a session cookie. Network-layer access control is required
in production.

**How (nginx):**
```nginx
location /metrics {
    allow 10.0.0.0/8;       # only internal scrapers
    deny all;
    proxy_pass http://seo-suite:8080;
}
```

**How (Kubernetes):**
NetworkPolicy that allows only the Prometheus pod to hit port 8080's
`/metrics` path.

**How (Fly.io):**
The internal `*.flycast` network is private by default — point Prometheus
at the `.flycast` address rather than the public one. Done.

**Time:** 15 minutes.

---

### 8. Set up a Prometheus scrape job
Once `/metrics` is reachable, configure your monitoring stack:

```yaml
scrape_configs:
  - job_name: seo-suite
    scrape_interval: 15s
    static_configs:
      - targets: ['seo-suite.internal:8080']
```

Then alert on:
- `audit_runs_total{status="error"}` rate > 0.1/min
- `indexing_running == 1 for 1h`  (stuck run)
- `http_requests_total{status=~"5.."}` rate > 0
- `sse_subscribers{stream="audit"}` consistently > 0 with no audit running

**Time:** 30 minutes.

---

### 9. Set up Sentry for error tracking
**Why:** Tracebacks in stdout are useless without aggregation.

**How:**
1. Sign up at [sentry.io](https://sentry.io) (free tier covers small teams).
2. Create a Python project, copy the DSN.
3. Set `SENTRY_DSN=<your-dsn>` in env.
4. Optionally set `SEO_SUITE_ENV=production` so events are tagged.

**Time:** 10 minutes.

---

### 10. Enable structured JSON logs (if you use ELK / Datadog / Loki)
**Why:** Lets your log pipeline query by field rather than regex.

**How:**
```
SEO_SUITE_LOG_JSON=1
```
The library `python-json-logger` is already in `requirements.txt`.

**Time:** 30 seconds.

---

## 🟡 Per-user setup (each end-user does this themselves)

These are NOT operator tasks — users do them via the dashboard. Listed
here so you can document them in your onboarding flow.

### 11. Enable 2FA
**User flow:**
1. Settings → Security → "Enable two-factor authentication"
2. Scan QR (rendered client-side from the `provisioning_uri` returned
   by `POST /api/auth/totp/enroll`)
3. Enter the 6-digit code from their authenticator app
4. **Save the 10 backup codes** — shown once, never again

After this every login asks for a TOTP code on a second screen
(`/login/totp`) after the password.

---

### 12. Verify email
**User flow:**
1. After signup, click the link in the verification email
   (or hit `POST /api/auth/send_verification` to re-send)
2. Visit `/verify_email?token=<token>` (or the dashboard handles this)

`POST /api/auth/verify_email` consumes the token and flips
`users.email_verified = 1`.

---

### 13. Change password / use forgot-password
**User flow:**
- **Logged in:** Settings → Change password (`POST /api/auth/change_password`)
- **Locked out:** `/login` → "Forgot password?" link →
  `POST /api/auth/request_password_reset` → click email link → submit new password.

---

## 🟢 Optional / future improvements

### 14. Set up CI signing for releases
GitHub Actions already runs tests + lint + security scan. Add:
- Release tag triggers a Docker image build + push to ghcr.io
- Image scanning via Trivy
- SBOM generation via Syft

**Time:** 1-2 hours.

---

### 15. Configure log retention
The `data/app.log` file grows without bound. Either:
- Use `logrotate` (Linux): drop a config in `/etc/logrotate.d/seo-suite`
- Use Docker's `--log-opt max-size=10m --log-opt max-file=3`
- Pipe to your central log system and don't write the file at all

**Time:** 15 minutes.

---

### 16. Schedule SQLite backups
The `data/seo_suite.db` is the new source of truth for users, sessions,
login history, TOTP secrets, and auth tokens. A backup strategy:

```bash
# Cron entry — runs nightly at 3am
0 3 * * * sqlite3 /app/data/seo_suite.db ".backup /app/data/backups/seo_suite_$(date +\%Y\%m\%d).db" \
          && find /app/data/backups -name 'seo_suite_*.db' -mtime +14 -delete
```

`.backup` is online — doesn't lock the DB or interrupt the app.

**Time:** 30 minutes.

---

### 17. Audit the broad `except Exception` clauses still in `tools/`
The recent session-of-five-sprints added `logger.exception()` to most
silent ones, but the next pass should narrow them to specific exception
types (`requests.Timeout`, `ValueError`, etc.). See ARCHITECTURE.md →
"Open Architecture Questions".

**Time:** 2 hours.

---

### 18. Frontend modernization
`app/static/js/dashboard.js` is ~3,000 lines of vanilla JS. Consider:
- Adding TypeScript (works alongside vanilla JS via JSDoc or full rewrite)
- Splitting per-tab files
- Building with Vite for tree-shaking and minification

**Time:** 1-2 days.

---

### 19. Job queue (Celery / RQ)
Currently audits run in in-process threads. If the server restarts
mid-audit, work is lost. A job queue with Redis would give you:
- Survive restarts
- Multi-instance deployments
- Retry semantics for free

**Time:** 1-2 days. Adds Redis as a deployment dependency.

---

### 20. WebAuthn / passkeys
Standard browser API, no password to lose. Library: `webauthn` on PyPI.

**Time:** 2 days. Best done after #11 (TOTP) is widely adopted.

---

### 21. OAuth / SSO (Google / GitHub / Microsoft)
Table stakes for SaaS. Library: `authlib` on PyPI.

**Time:** 1 day per provider.

---

## Quick reference: critical env vars

These must be set in production for the corresponding feature to work:

| Env var | Required for | Default |
|---------|--------------|---------|
| `SEO_SUITE_SECRET` | Session cookies surviving restart | random ephemeral (warns loudly) |
| `SEO_SUITE_DATA_DIR` | Where SQLite + reports + uploads live | `./data` (relative to project) |
| `SEO_SUITE_COOKIE_SECURE` | HTTPS-only cookies + HSTS | off |
| `SENTRY_DSN` | Error aggregation | off |
| `SEO_SUITE_LOG_JSON` | JSON-formatted logs | text format |
| `SEO_SUITE_USERS_BACKEND` | `sqlite` (default) or `json` (rollback) | `sqlite` |
| `SEO_SUITE_SKIP_ENV_ADMIN_ROTATION` | Suppress the "rotate me!" banner | off |
| `SEO_SUITE_DISABLE_ZXCVBN` | Skip password-strength check | off (zxcvbn active) |
| `SEO_SUITE_DISABLE_HIBP` | Skip breach lookup at signup | off (HIBP active) |
| `SEO_SUITE_FORCE_AUTH` | Require auth even with zero users | auto-on for Render |

Everything else (API keys for PageSpeed, SerpAPI, Moz, DataForSEO, Bing,
Groq) is optional — the features degrade gracefully when absent.

---

## What the codebase does for you automatically

You **do not** need to do any of these manually — they're hooked into
the code path:

- argon2id hashing of new passwords (legacy scrypt still verifies)
- zxcvbn + HIBP rejection of weak/breached passwords at signup + change
- account lockout after 10 failed logins in 15 minutes
- SQLite auto-migration from `users.json` on first read
- login history pruning (90-day retention, sweeps on each write)
- expired session cleanup (sweeps on list)
- `/health/ready` probes the writable data dir
- Prometheus metric refresh on each scrape (`audit_running`, etc.)
- argon2 opportunistic upgrade for legacy scrypt users on next password change
- session creation on login + revocation on logout / password change
- new-device login notification email (best-effort, when SMTP configured)
- env admin "must rotate" banner on first login

---

## When this doc is out of date

Last updated to match commit `9e7e524`. If the codebase has moved on:

```bash
git log --since="last operator checklist update" --oneline
```

…and update the relevant sections. CI never enforces this doc, so it
relies on human attention to stay accurate.
