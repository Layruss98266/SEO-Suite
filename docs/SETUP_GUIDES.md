# SEO Suite — API & Integration Setup Guides

All API keys are **optional**. Phases that lack a key are skipped gracefully.
Keys can be set in two ways:

1. **`.env` file** — environment variables loaded at startup
2. **Dashboard Settings** — saved to `config.json` (persists across restarts)

---

## Table of Contents

1. [Google Search Console (GSC)](#1-google-search-console-gsc)
2. [Google PageSpeed Insights](#2-google-pagespeed-insights)
3. [Groq AI Assistant](#3-groq-ai-assistant)
4. [SerpAPI (Rankings)](#4-serpapi-rankings)
5. [Moz (Domain Authority)](#5-moz-domain-authority)
6. [DataForSEO (Backlinks, Rankings, Keywords)](#6-dataforseo-backlinks-rankings-keywords)
7. [Bing Webmaster Tools](#7-bing-webmaster-tools)
8. [Email Notifications (SMTP)](#8-email-notifications-smtp)
9. [Slack Notifications](#9-slack-notifications)
10. [Microsoft Teams Notifications](#10-microsoft-teams-notifications)
11. [Sentry Error Tracking](#11-sentry-error-tracking)

---

## 1. Google Search Console (GSC)

**What it unlocks:** Authoritative URL indexation status, click/impression data, search queries, sitemaps status, coverage errors, CTR analysis, and position tracking.

**Why it matters:** GSC is the only official source of truth for whether Google has indexed a URL. Browser-based checks are a fallback — GSC is primary.

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click the project dropdown (top-left) → **New Project**
3. Name it (e.g. `SEO Suite`) → **Create**
4. Make sure the new project is selected in the dropdown

### Step 2: Enable the Search Console API

1. Go to **APIs & Services → Library** (left sidebar)
2. Search for **Google Search Console API**
3. Click it → **Enable**

### Step 3: Create a Service Account

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → Service Account**
3. Name it (e.g. `seo-suite-gsc`) → **Create and Continue**
4. Skip the optional role/access steps → **Done**
5. Click the newly created service account email
6. Go to the **Keys** tab → **Add Key → Create New Key**
7. Select **JSON** → **Create**
8. A `.json` file downloads — this is your credentials file

### Step 4: Place the Credentials File

Rename the downloaded file to `gsc_credentials.json` and place it in the project root:

```
SEO Suite/
├── gsc_credentials.json   ← here
├── main.py
└── ...
```

### Step 5: Add the Service Account to Search Console

> **This step is required.** GSC is property-based, not API-key-based. The service account is just an identity — it has zero access until you grant it permission on each property.

1. Open the downloaded JSON file, copy the `"client_email"` value
   (looks like `seo-suite-gsc@your-project.iam.gserviceaccount.com`)
2. Go to [Google Search Console](https://search.google.com/search-console)
3. Select your property (website)
4. Go to **Settings → Users and permissions**
5. Click **Add User**
6. Paste the service account email
7. Set permission to **Full** (recommended) or **Restricted** (read-only)
8. Click **Add**

Repeat for each property you want SEO Suite to access.

### Step 6: Enable GSC in SEO Suite

**Option A — Dashboard:** Settings tab → set `gsc.enabled` to `true`

**Option B — config.json:**
```json
{
  "gsc": {
    "enabled": true,
    "credentials_file": "gsc_credentials.json"
  }
}
```

### Step 7: Verify

Restart the server and run an indexing check. The logs should show:
```
Using Google Search Console API (primary)…
```

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `GSC setup failed` in logs | Ensure `gsc_credentials.json` exists and is valid JSON |
| `GSC Error` on all URLs | Service account not added to the Search Console property (Step 5) |
| Only some URLs work | Add the service account to all relevant SC properties |
| `credentials_file not found` | Check the path in `config.json` matches the actual filename |

---

## 2. Google PageSpeed Insights

**What it unlocks:** Core Web Vitals (LCP, FID, CLS, INP), Performance/Accessibility/SEO scores, mobile vs desktop comparison, and specific optimization opportunities.

**Free tier:** 25,000 queries/day (very generous).

### Step 1: Get an API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Select or create a project (you can reuse the same project as GSC)
3. Go to **APIs & Services → Library**
4. Search for **PageSpeed Insights API** → **Enable**
5. Go to **APIs & Services → Credentials**
6. Click **+ Create Credentials → API Key**
7. Copy the generated key

**Optional but recommended:** Click **Restrict Key** → under API restrictions, select **PageSpeed Insights API** only. This prevents misuse if the key leaks.

### Step 2: Add to SEO Suite

**Option A — `.env` file:**
```
PAGESPEED_API_KEY=AIzaSy...your-key-here
```

**Option B — Dashboard:** Settings tab → paste into `pagespeed_api_key`

### Step 3: Verify

Run **Settings → Test Connection → PageSpeed** from the dashboard (or run a Phase 2 audit). You should see performance scores appear.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `403 Forbidden` | API not enabled in Google Cloud, or key is restricted to wrong API |
| `429 Too Many Requests` | You hit the daily quota (25k). Wait 24h or create a second project |
| Scores show but are slow | Normal — PageSpeed runs a full Lighthouse audit per URL. Use fewer concurrent workers |

---

## 3. Groq AI Assistant

**What it unlocks:** "Explain with AI" button on audit results, AI-drafted meta titles/descriptions, executive AI summary on site audits.

**Free tier:** Very generous — 30 requests/minute, 14,400 requests/day on free models.

### Step 1: Create a Groq Account

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up with Google, GitHub, or email

### Step 2: Generate an API Key

1. In the Groq Console, go to **API Keys** (left sidebar)
2. Click **Create API Key**
3. Name it (e.g. `seo-suite`) → **Create**
4. Copy the key (starts with `gsk_...`) — you won't see it again

### Step 3: Add to SEO Suite

**Option A — `.env` file:**
```
GROQ_API_KEY=gsk_...your-key-here
```

**Option B — Dashboard:** Settings tab → paste into `groq_api_key`

### Step 4: Verify

Run **Settings → Test Connection → Groq** from the dashboard. Or run any audit and click the "Explain with AI" button on a result.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `401 Unauthorized` | Key is invalid or expired — generate a new one |
| `429 Rate limit` | Free tier limit hit. Wait a minute, or upgrade to a paid plan |
| Responses are generic | The model (`llama-3.1-8b-instant`) is fast but small. Results improve with more audit data as context |

---

## 4. SerpAPI (Rankings)

**What it unlocks:** Keyword rank tracking, competitor comparison, SERP feature detection, traffic share estimation.

**Free tier:** 100 searches/month.

### Step 1: Create a SerpAPI Account

1. Go to [serpapi.com](https://serpapi.com)
2. Sign up for a free account
3. After signing in, your API key is shown on the [dashboard](https://serpapi.com/manage-api-key)
4. Copy the key

### Step 2: Add to SEO Suite

**Option A — `.env` file:**
```
SERPAPI_KEY=your-key-here
```

**Option B — Dashboard:** Settings tab → paste into `serpapi_key`

### Step 3: Verify

Run **Settings → Test Connection → SerpAPI** from the dashboard, or run a Phase 4 audit with keywords configured.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `401 Invalid API key` | Double-check the key at [serpapi.com/manage-api-key](https://serpapi.com/manage-api-key) |
| `You have exceeded your plan` | Free tier is 100/month. Upgrade or wait for next billing cycle |
| No ranking data | Make sure you've added keywords in the audit profile — rankings need keywords to track |

---

## 5. Moz (Domain Authority)

**What it unlocks:** Domain Authority (DA), Page Authority (PA), spam score, linking domains count.

**Free tier:** 10 requests/month on the free Moz API. Paid plans start at ~$99/month.

### Step 1: Create a Moz Account

1. Go to [moz.com](https://moz.com)
2. Sign up for a free Moz account
3. Go to [moz.com/products/api](https://moz.com/products/api)
4. Generate your **Access ID** and **Secret Key**

### Step 2: Add to SEO Suite

**Option A — `.env` file:**
```
MOZ_ACCESS_ID=mozscape-abc123
MOZ_SECRET_KEY=your-secret-key-here
```

**Option B — Dashboard:** Settings tab → paste into `moz_access_id` and `moz_secret_key`

### Step 3: Verify

Run a Phase 4 audit — DA/PA scores should appear in the Authority section of results.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `403 Forbidden` | Access ID or Secret Key is wrong. Regenerate at moz.com |
| `402 Payment Required` | Free tier exhausted (10/month). Upgrade or wait for next cycle |
| DA shows 0 for all URLs | The domain may be too new or too small for Moz's index |

---

## 6. DataForSEO (Backlinks, Rankings, Keywords)

**What it unlocks:** Backlink analysis, keyword research (volume, difficulty, CPC, trends), SERP rankings, keyword suggestions, related keywords, competitor keywords.

**Free tier:** $1.00 credit on signup (enough for ~500-1000 API calls depending on endpoint).

### Step 1: Create a DataForSEO Account

1. Go to [dataforseo.com](https://dataforseo.com)
2. Sign up for an account
3. Go to [app.dataforseo.com/api-access](https://app.dataforseo.com/api-access)
4. Your **Login** (account email) and **API Password** are shown there

> **Note:** The API password is NOT your account password. It's a separate credential on the API Access page.

### Step 2: Add to SEO Suite

**Option A — `.env` file:**
```
DATAFORSEO_LOGIN=your-email@example.com
DATAFORSEO_PASSWORD=your-api-password-here
```

**Option B — Dashboard:** Settings tab → paste into `dataforseo_login` and `dataforseo_password`

### Step 3: Verify

Run **Settings → Test Connection → DataForSEO** from the dashboard, or use the Keyword Research tool.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `401 Unauthorized` | Using account password instead of API password. Check [app.dataforseo.com/api-access](https://app.dataforseo.com/api-access) |
| `402 Insufficient credits` | Top up your balance at dataforseo.com |
| Keyword research returns empty | Check that the keyword isn't too niche — DataForSEO may not have data for very low-volume terms |

---

## 7. Bing Webmaster Tools

**What it unlocks:** Bing URL inspection, URL submission, crawl stats, sitemap status, and traffic overview for Bing search.

**Free:** Unlimited, no paid tier.

### Step 1: Add Your Site to Bing Webmaster

1. Go to [bing.com/webmasters](https://www.bing.com/webmasters)
2. Sign in with a Microsoft account
3. Add your site (you can import from Google Search Console for instant verification)

### Step 2: Get Your API Key

1. In Bing Webmaster Tools, click the **gear icon** (Settings) in the top-right
2. Go to **API Access**
3. Click **Generate** to create an API key
4. Copy the key

### Step 3: Add to SEO Suite

**Option A — `.env` file:**
```
BING_WEBMASTER_API_KEY=your-key-here
```

**Option B — Dashboard:** Settings tab → paste into `bing_api_key`

### Step 4: Verify

Run **Settings → Test Connection → Bing** from the dashboard, or use the Bing tools (Overview, Inspect, Submit) from the Tools panel.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `401 Unauthorized` | API key is invalid. Regenerate at Bing Webmaster → Settings → API Access |
| `No data found for this site` | The site hasn't been added to your Bing Webmaster account |
| URL submission fails | Bing has a daily submission limit. Try again tomorrow |

---

## 8. Email Notifications (SMTP)

**What it unlocks:** Email alerts when indexing checks or audits complete.

### Step 1: Get SMTP Credentials

**Gmail (recommended for testing):**
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. You need 2-Factor Authentication enabled first
3. Generate an **App Password** for "Mail"
4. Copy the 16-character password

**Other providers:** Use your SMTP host, port, username, and password from your email provider's settings.

### Step 2: Add to SEO Suite

Add to `.env`:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
EMAIL_FROM=you@gmail.com
EMAIL_TO=recipient@example.com
```

### Step 3: Enable in Dashboard

Go to **Settings** → set `email.enabled` to `true`

### Step 4: Verify

Run **Settings → Test Connection → Email** from the dashboard, or click "Send Test" in the notification settings.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `Authentication failed` | For Gmail, use an App Password, not your regular password |
| `Connection refused` | Check SMTP_HOST and SMTP_PORT. Gmail is `smtp.gmail.com:587` |
| `Less secure apps` error | Google deprecated this. Use App Passwords instead |
| Email sent but not received | Check spam folder. Also verify `EMAIL_TO` is correct |

---

## 9. Slack Notifications

**What it unlocks:** Slack channel alerts when indexing checks or audits complete.

### Step 1: Create a Slack Webhook

1. Go to [api.slack.com/messaging/webhooks](https://api.slack.com/messaging/webhooks)
2. Click **Create your Slack app** (or use an existing app)
3. Select your workspace
4. Go to **Incoming Webhooks** → toggle **Activate**
5. Click **Add New Webhook to Workspace**
6. Pick the channel to post to → **Allow**
7. Copy the webhook URL (starts with `https://hooks.slack.com/services/...`)

### Step 2: Add to SEO Suite

**Option A — `.env` file:**
```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

**Option B — Dashboard:** Settings tab → paste into `slack.webhook_url`

### Step 3: Enable and Verify

1. Go to **Settings** → set `slack.enabled` to `true`
2. Run **Settings → Test Connection → Slack** or click "Send Test"
3. Check the Slack channel for a test message

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `404 Not Found` | Webhook URL is wrong or the Slack app was deleted |
| `403 Forbidden` | The webhook was revoked. Create a new one |
| Messages don't appear | Check you selected the right channel when creating the webhook |

---

## 10. Microsoft Teams Notifications

**What it unlocks:** Teams channel alerts when indexing checks or audits complete.

### Step 1: Create a Teams Webhook

1. Open Microsoft Teams
2. Go to the channel you want notifications in
3. Click the **...** menu on the channel → **Connectors** (or **Manage channel** → **Connectors**)
4. Find **Incoming Webhook** → **Configure**
5. Name it (e.g. `SEO Suite`) and optionally upload an icon
6. Click **Create**
7. Copy the webhook URL

> **Note:** If you don't see Connectors, your Teams admin may have disabled them. Ask your IT admin to enable Incoming Webhooks.

### Step 2: Add to SEO Suite

**Option A — `.env` file:**
```
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
```

**Option B — Dashboard:** Settings tab → paste into `teams.webhook_url`

### Step 3: Enable and Verify

1. Go to **Settings** → set `teams.enabled` to `true`
2. Run **Settings → Test Connection → Teams** or click "Send Test"
3. Check the Teams channel for a test message

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `404 Not Found` | Webhook URL is expired or was deleted. Create a new one |
| Connectors option missing | Your Teams admin has disabled connectors. Contact IT |
| Message appears but looks broken | Teams webhooks use Adaptive Cards — this is normal formatting |

---

## 11. Sentry Error Tracking

**What it unlocks:** Automatic error reporting, performance monitoring, and crash alerts for your SEO Suite instance.

**Free tier:** 5,000 errors/month, 10,000 performance transactions/month.

### Step 1: Create a Sentry Account

1. Go to [sentry.io](https://sentry.io) → **Start for Free**
2. Create an organization

### Step 2: Create a Project

1. Click **Projects → Create Project**
2. Select **Flask** as the platform
3. Name it (e.g. `seo-suite`)
4. Click **Create Project**
5. Copy the **DSN** from the setup page (looks like `https://abc123@o456.ingest.sentry.io/789`)

### Step 3: Add to SEO Suite

Add to `.env`:
```
SENTRY_DSN=https://abc123@o456.ingest.sentry.io/789
SEO_SUITE_ENV=production
```

`SEO_SUITE_ENV` tags errors so you can filter by environment (development/staging/production).

### Step 4: Verify

Restart the server. The logs should show:
```
Sentry error tracking enabled (env=production)
```

Sentry captures 5% of requests for performance monitoring by default.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| No errors appearing | Sentry only captures unhandled exceptions. Check the DSN is correct |
| `sentry_sdk not installed` | Run `pip install sentry-sdk` (already in requirements.txt) |
| Too many events | Adjust `traces_sample_rate` in `app/server.py` (default is 0.05 = 5%) |

---

## Quick Reference

| Integration | Env Variable | Config Key | Free Tier |
|-------------|-------------|------------|-----------|
| PageSpeed | `PAGESPEED_API_KEY` | `pagespeed_api_key` | 25,000/day |
| GSC | — (JSON file) | `gsc.enabled` + `gsc.credentials_file` | Unlimited |
| Groq AI | `GROQ_API_KEY` | `groq_api_key` | 14,400/day |
| SerpAPI | `SERPAPI_KEY` | `serpapi_key` | 100/month |
| Moz | `MOZ_ACCESS_ID` + `MOZ_SECRET_KEY` | `moz_access_id` + `moz_secret_key` | 10/month |
| DataForSEO | `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD` | `dataforseo_login` + `dataforseo_password` | $1 credit |
| Bing Webmaster | `BING_WEBMASTER_API_KEY` | `bing_api_key` | Unlimited |
| Email (SMTP) | `SMTP_HOST`, `SMTP_PORT`, etc. | `email.*` | Depends on provider |
| Slack | `SLACK_WEBHOOK_URL` | `slack.webhook_url` | Unlimited |
| Teams | `TEAMS_WEBHOOK_URL` | `teams.webhook_url` | Unlimited |
| Sentry | `SENTRY_DSN` | — | 5,000 errors/month |
