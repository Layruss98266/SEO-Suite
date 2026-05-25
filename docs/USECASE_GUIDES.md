# SEO Suite — Use Case Setup & Usage Guides

SEO Suite ships **7 built-in audit use cases**, grouped into **Technical** and **Visibility** categories. Each use case bundles a focused set of checks so you can run targeted audits (e.g. just "Crawl Access" vs. a full audit).

This guide explains what each use case checks, what API keys it needs, how to configure it, and how to interpret the results.

---

## Table of Contents

**Technical use cases (no API keys required for most):**
1. [Crawl Access](#1-crawl-access-crawlability)
2. [On-Page SEO](#2-on-page-seo-on_page)
3. [Site Health](#3-site-health-site_health)
4. [Performance](#4-performance-performance)

**Visibility use cases (API keys required):**
5. [Search Console](#5-search-console-search_console)
6. [Authority](#6-authority-authority)
7. [Rankings](#7-rankings-rankings)

**Bonus:**
8. [Running Combined Audits](#8-running-combined-audits)
9. [Saving Reusable Profiles](#9-saving-reusable-profiles)

---

## 1. Crawl Access (`crawlability`)

🕷️ **Group:** Technical · **API Keys:** None required

### What it checks

| Check | What it verifies |
|-------|------------------|
| `robots.txt` | File exists, syntax is valid, key pages aren't blocked |
| HTTP status | URL returns 200 OK (not 4xx/5xx) |
| Redirects | Redirect chains are clean (≤2 hops, no loops) |
| Broken links | No internal links pointing to 404s |
| Sitemaps | `sitemap.xml` exists and is reachable from `robots.txt` |
| Crawlability flags | No accidental `noindex`, `nofollow`, or canonical issues |

### Step 1: No setup needed

This use case works out of the box — no API keys, no extra config.

### Step 2: Run the audit

**Dashboard:** Open the dashboard → **Audit** tab → check **Crawl Access** → enter URL(s) → **Run**

**API:**
```bash
curl -X POST http://localhost:8080/api/audit/run \
  -H "Content-Type: application/json" \
  -d '{"input":"https://example.com","input_type":"url","use_cases":["crawlability"]}'
```

### Step 3: Interpret results

- **Pass** — URL is fully crawlable, no blockers
- **Warning** — Minor issues (e.g. one redirect hop, soft 404)
- **Fail** — Blockers present (e.g. `noindex`, 5xx, robots.txt blocking)

### Common fixes

| Issue | Fix |
|-------|-----|
| `robots.txt blocks /page` | Remove the `Disallow:` line for that path |
| `Redirect chain too long` | Update internal links to point directly to the final URL |
| `Missing sitemap.xml` | Generate one (Tools → Sitemap Generator) and reference it in `robots.txt` |

---

## 2. On-Page SEO (`on_page`)

📝 **Group:** Technical · **API Keys:** None required

### What it checks

| Check | What it verifies |
|-------|------------------|
| Title tag | Present, 30-60 chars, unique per page |
| Meta description | Present, 120-160 chars |
| Heading structure | Single H1, logical H2-H6 nesting |
| Word count | Sufficient content depth (>300 words for content pages) |
| Image alt text | All images have descriptive `alt` attributes |
| Open Graph tags | OG title, description, image for social sharing |
| Schema markup | Valid JSON-LD or microdata present |
| Favicon | Present and reachable |
| Readability | Flesch-Kincaid score appropriate for audience |

### Step 1: No setup needed

Pure HTML parsing — works on any public URL.

### Step 2: Run the audit

**Dashboard:** Check **On-Page SEO** → enter URL → **Run**

**API:**
```json
{"input":"https://example.com","input_type":"url","use_cases":["on_page"]}
```

### Step 3: Interpret results

The audit returns a per-check status. Common output:

```
✅ Title (52 chars): "Best SEO Tools 2024 — Complete Guide"
⚠️ Meta description (89 chars): "Too short, recommend 120-160 chars"
✅ H1: "Best SEO Tools 2024" (1 found)
❌ Image alt: 12 of 47 images missing alt attribute
```

### Common fixes

| Issue | Fix |
|-------|-----|
| Multiple H1s | Use H2 for secondary headings; one H1 per page |
| Missing meta description | Add `<meta name="description" content="...">` to `<head>` |
| Image alt missing | Add descriptive `alt=""` to every `<img>` |
| Schema missing | Use Tools → Schema Generator to scaffold JSON-LD |

---

## 3. Site Health (`site_health`)

🛡️ **Group:** Technical · **API Keys:** None required

### What it checks

| Check | What it verifies |
|-------|------------------|
| SSL certificate | Valid, not expired, full chain present |
| HTTPS enforcement | HTTP redirects to HTTPS |
| Domain age | WHOIS-based registration date |
| DNS health | A/AAAA/MX/SPF/DMARC records present and valid |
| Mixed content | No `http://` resources on HTTPS pages |
| Archive history | Wayback Machine snapshots exist |
| Security headers | CSP, X-Frame-Options, X-Content-Type-Options |

### Step 1: No setup needed

Uses public WHOIS, DNS, and Archive.org APIs — no auth required.

### Step 2: Run the audit

**Dashboard:** Check **Site Health** → enter URL → **Run**

### Step 3: Interpret results

```
✅ SSL: Valid until 2026-12-15 (Let's Encrypt)
✅ HTTPS redirect: http://example.com → https://example.com
⚠️ Domain age: 2 months (new domains have less trust)
❌ Mixed content: 3 http:// images on https:// page
❌ DMARC: No DMARC record found
```

### Common fixes

| Issue | Fix |
|-------|-----|
| Mixed content | Replace `http://` URLs with `https://` or protocol-relative `//` |
| Missing DMARC | Add a TXT record at `_dmarc.example.com` with policy |
| Missing security headers | Add them in your web server config (nginx/Apache/CDN) |
| SSL expiring soon | Renew via Let's Encrypt, Certbot, or your CA |

---

## 4. Performance (`performance`)

⚡ **Group:** Technical · **API Keys:** **PageSpeed Insights required**

### What it checks

| Check | What it measures |
|-------|------------------|
| PageSpeed score (mobile) | Lighthouse mobile performance score 0-100 |
| PageSpeed score (desktop) | Lighthouse desktop performance score 0-100 |
| LCP (Largest Contentful Paint) | Loading speed of main content |
| CLS (Cumulative Layout Shift) | Visual stability during load |
| INP (Interaction to Next Paint) | Responsiveness |
| FCP (First Contentful Paint) | Time until first visible content |
| TTFB (Time to First Byte) | Server response speed |
| Mobile-friendliness | Viewport, tap targets, font sizes |

### Step 1: Set up PageSpeed API key

Follow [SETUP_GUIDES.md → PageSpeed Insights](SETUP_GUIDES.md#2-google-pagespeed-insights):

1. Create a Google Cloud project
2. Enable PageSpeed Insights API
3. Create an API key
4. Add to `.env`:
   ```
   PAGESPEED_API_KEY=AIzaSy...
   ```

### Step 2: Run the audit

**Dashboard:** Check **Performance** → enter URL → **Run**

> **Note:** Performance audits are slow (~30s per URL) because PageSpeed runs a full Lighthouse audit. Use fewer parallel workers (1-2) for large batches.

### Step 3: Interpret results

```
✅ PageSpeed mobile: 87
⚠️ PageSpeed desktop: 72 (target: 90+)
✅ LCP: 2.1s (good)
❌ CLS: 0.18 (poor — target <0.1)
✅ INP: 145ms (good)
```

### Performance Opportunities tool

For specific optimization suggestions, use **Tools → Performance Opportunities** which exposes Lighthouse's "Opportunities" panel (e.g. "Eliminate render-blocking resources", "Properly size images").

### Common fixes

| Issue | Fix |
|-------|-----|
| Low PageSpeed score | Compress images, defer JS, enable caching |
| Poor LCP | Optimize hero image, use CDN, reduce server response time |
| High CLS | Add explicit width/height to images and ads |
| Poor INP | Reduce JS execution time, split long tasks |

---

## 5. Search Console (`search_console`)

📊 **Group:** Visibility · **API Keys:** **Google Search Console required**

### What it checks

| Check | What it returns |
|-------|----------------|
| Clicks & impressions | Last 28-day totals from GSC |
| Position tracker | Average position per URL |
| CTR analyzer | Click-through rate vs. position benchmark |
| Top queries | Top 10 search terms driving traffic |
| Coverage errors | Indexing errors (4xx, 5xx, soft 404) |
| Sitemaps status | Submitted sitemaps and discovery counts |
| Manual actions | Any Google manual penalties |

### Step 1: Set up GSC service account

Follow [SETUP_GUIDES.md → Google Search Console](SETUP_GUIDES.md#1-google-search-console-gsc):

1. Create a Google Cloud project
2. Enable Search Console API
3. Create a service account + download JSON key
4. Place `gsc_credentials.json` in project root
5. **Add the service account email as a user in Search Console** (required)
6. Enable in `config.json`:
   ```json
   {"gsc": {"enabled": true, "credentials_file": "gsc_credentials.json"}}
   ```

### Step 2: Run the audit

**Dashboard:** Check **Search Console** → enter URL → **Run**

> **Note:** URLs must belong to a property the service account has access to. URLs outside owned properties return `GSC Error`.

### Step 3: Interpret results

```
📊 Last 28 days:
   Clicks: 1,247
   Impressions: 24,891
   Avg position: 8.3
   CTR: 5.0%

🔍 Top queries:
   "seo audit tool" — 312 clicks, pos 5
   "free seo checker" — 198 clicks, pos 8

⚠️ Coverage: 3 URLs with errors
   - /old-page (404)
   - /redirect-loop (redirect chain)
```

### Dedicated GSC Tools

Beyond the audit, dedicated tools exist for deeper analysis:

- **GSC Opportunities** — find pages ranking 8-20 (low-hanging fruit)
- **Position Tracker** — historical position changes per URL
- **CTR Analyzer** — pages with below-average CTR for their position
- **Coverage Errors** — full list of indexing errors
- **Sitemaps Status** — sitemap submission and discovery counts

### Common issues

| Issue | Fix |
|-------|-----|
| `GSC Error: 403` | Service account not added to that property (re-do Step 5 above) |
| Empty data | URL is too new (GSC has 2-3 day lag) or has zero impressions |
| `Quota exceeded` | GSC allows 1,200 queries/minute. Reduce concurrency |

---

## 6. Authority (`authority`)

🔗 **Group:** Visibility · **API Keys:** Moz or DataForSEO required

### What it checks

| Check | What it returns |
|-------|----------------|
| Backlink count | Total inbound links |
| Domain Authority (DA) | Moz's DA score 0-100 |
| Page Authority (PA) | Moz's PA score 0-100 |
| Referring domains | Number of unique linking domains |
| Spam score | Moz's spam score 0-17 |
| Broken backlinks | Inbound links to dead pages |
| NoFollow ratio | % of backlinks marked nofollow |

### Step 1: Set up Moz or DataForSEO

**Option A — Moz (cheap, basic):** [SETUP_GUIDES.md → Moz](SETUP_GUIDES.md#5-moz-domain-authority)
```
MOZ_ACCESS_ID=mozscape-abc
MOZ_SECRET_KEY=...
```

**Option B — DataForSEO (more depth):** [SETUP_GUIDES.md → DataForSEO](SETUP_GUIDES.md#6-dataforseo-backlinks-rankings-keywords)
```
DATAFORSEO_LOGIN=you@example.com
DATAFORSEO_PASSWORD=...
```

You can configure either or both. DataForSEO is preferred when available; Moz is the fallback.

### Step 2: Run the audit

**Dashboard:** Check **Authority** → enter URL → **Run**

### Step 3: Interpret results

```
🔗 Authority for example.com:
   Domain Authority: 42 / 100
   Page Authority: 38 / 100
   Backlinks: 1,247
   Referring domains: 89
   Spam score: 2 / 17 (low)
```

### Common fixes

| Issue | Fix |
|-------|-----|
| Low DA | Acquire backlinks from higher-DA sites (guest posts, PR, partnerships) |
| High spam score | Disavow toxic links via Google Search Console |
| Many broken backlinks | Set up 301 redirects to preserve link equity |

---

## 7. Rankings (`rankings`)

🏆 **Group:** Visibility · **API Keys:** SerpAPI or DataForSEO required

### What it checks

| Check | What it returns |
|-------|----------------|
| Keyword rank tracker | Position for each tracked keyword |
| SERP rank | Top 10 results for the keyword |
| Competitor comparison | Where competitors rank for the same terms |
| SERP features | Featured snippets, People Also Ask, etc. |
| Rank change | Position delta vs. last audit |
| Traffic share | Estimated traffic capture vs. competitors |

### Step 1: Configure keywords

Rankings need keywords to track. Add them in two ways:

**Dashboard:** Audit form → **Keywords** field → comma-separated list

**Profile:** Save keywords to a profile so they reload automatically:
```json
{
  "keywords": "best seo tool, free seo audit, indexing checker",
  "limit": 10
}
```

### Step 2: Set up SerpAPI or DataForSEO

**Option A — SerpAPI (simpler):** [SETUP_GUIDES.md → SerpAPI](SETUP_GUIDES.md#4-serpapi-rankings)
```
SERPAPI_KEY=...
```

**Option B — DataForSEO:** [SETUP_GUIDES.md → DataForSEO](SETUP_GUIDES.md#6-dataforseo-backlinks-rankings-keywords)

> **Note:** Free SerpAPI tier is only 100 searches/month. If you track 10 keywords across 5 URLs, that's 50 queries per audit run — be mindful.

### Step 3: Run the audit

**Dashboard:** Check **Rankings** → enter URL + keywords → **Run**

### Step 4: Interpret results

```
🏆 Rankings for example.com:
   "best seo tool"         — pos 7  (↑ from 12)
   "free seo audit"        — pos 14 (no change)
   "indexing checker"      — pos 3  (↑ from 8)
   "site audit tool"       — pos 23 (↓ from 19)

🔥 SERP features:
   "best seo tool" — Featured snippet captured by competitor.com
```

### Common fixes

| Issue | Fix |
|-------|-----|
| Keyword not ranking in top 100 | Improve on-page targeting for that keyword |
| Competitor outranking you | Use Competitor Comparison tool to find content gaps |
| Featured snippet lost | Audit the page that lost it; rewrite for snippet format |

---

## 8. Running Combined Audits

You can run any combination of use cases in a single audit.

### Via Dashboard

In the **Audit** tab, check multiple boxes:
- ☑ Crawl Access
- ☑ On-Page SEO
- ☐ Site Health
- ☑ Performance
- ☑ Search Console

Then click **Run**.

### Via API

```bash
curl -X POST http://localhost:8080/api/audit/run \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://example.com",
    "input_type": "url",
    "use_cases": ["crawlability", "on_page", "performance", "search_console"],
    "keywords": "seo tool, audit tool"
  }'
```

### Use case quick reference

| Code | Use case | Group | Requires |
|------|----------|-------|----------|
| `crawlability` | Crawl Access | Technical | None |
| `on_page` | On-Page SEO | Technical | None |
| `site_health` | Site Health | Technical | None |
| `performance` | Performance | Technical | PageSpeed API key |
| `search_console` | Search Console | Visibility | GSC credentials |
| `authority` | Authority | Visibility | Moz or DataForSEO |
| `rankings` | Rankings | Visibility | SerpAPI or DataForSEO + keywords |

### Full audit (all 7)

Leave `use_cases` empty in the API or check all boxes — SEO Suite runs every available use case for which credentials exist. Use cases without credentials are skipped gracefully (they neither pass nor fail).

---

## 9. Saving Reusable Profiles

For audits you run repeatedly (e.g. monthly site checks), save the configuration as a profile.

### Step 1: Configure the audit

In the **Audit** tab, set:
- URL(s) or input file
- Use cases (check all relevant boxes)
- Keywords (if running Rankings)
- Worker count, retry settings, etc.

### Step 2: Save the profile

Click **Save Profile** → name it (e.g. `monthly-blog-audit`)

### Step 3: Reload later

Click **Profile** dropdown → select the saved profile → all settings restore instantly → click **Run**

### Profile file location

Profiles are stored in `data/profiles.json`:
```json
{
  "monthly-blog-audit": {
    "use_cases": ["crawlability", "on_page", "performance", "search_console"],
    "tasks": [],
    "keywords": "seo tool, audit tool, indexing",
    "limit": 10,
    "saved_at": "2026-05-25T10:30:00"
  }
}
```

You can edit this file directly to bulk-create profiles.

---

## See Also

- **[SETUP_GUIDES.md](SETUP_GUIDES.md)** — detailed API key setup for all 11 integrations
- **[DEPLOYMENT.md](../DEPLOYMENT.md)** — production deployment guides
- **[NEW_TOOLS_USECASES.md](../NEW_TOOLS_USECASES.md)** — roadmap of planned use cases
