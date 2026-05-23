"""
Bing Webmaster API integration — Stage 3-A
Provides: URL inspection, search performance, crawl stats, sitemap status.

API key: Bing Webmaster Tools → Settings → API Access → Generate key
Docs:    https://learn.microsoft.com/en-us/bingwebmaster/getting-access
"""

from urllib.parse import quote_plus, urlencode

from core.security import safe_requests_get, safe_requests_post

# Base URL for all Bing Webmaster API calls
_BASE = "https://ssl.bing.com/webmaster/api.svc/json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOSuiteBot/1.0)",
    "Content-Type": "application/json; charset=utf-8",
}


def _get(path: str, api_key: str, params: dict = None, timeout: int = 20) -> dict:
    """GET request to Bing Webmaster API. Returns parsed JSON dict."""
    p = dict(params or {})
    p["apikey"] = api_key
    url = f"{_BASE}/{path}?{urlencode(p)}"
    resp = safe_requests_get(url, timeout=timeout, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, api_key: str, body: dict, timeout: int = 20) -> dict:
    """POST request to Bing Webmaster API. Returns parsed JSON dict."""
    url = f"{_BASE}/{path}?apikey={quote_plus(api_key)}"
    resp = safe_requests_post(url, timeout=timeout, headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()


# ══════════════════════════════════════════════════════════════════════════════
# URL Traffic / Performance
# ══════════════════════════════════════════════════════════════════════════════
def url_traffic(site_url: str, api_key: str, period: int = 1) -> dict:
    """
    Get search performance data for an entire site.
    period: 1=last week, 2=last month, 3=last 6 months
    Returns clicks, impressions, CTR, avg position.
    """
    try:
        data = _get("GetUrlTrafficInfo", api_key, {"siteUrl": site_url, "period": period})
        d = data.get("d") or {}
        total_clicks      = d.get("TotalClicks",      0)
        total_impressions = d.get("TotalImpressions",  0)
        avg_ctr           = round(d.get("AvgCTR", 0) * 100, 2)
        avg_position      = round(d.get("AvgPosition", 0), 1)

        period_label = {1: "last week", 2: "last month", 3: "last 6 months"}.get(period, "")
        s   = "pass" if total_clicks > 0 else "warning"
        msg = (f"Clicks: {total_clicks} | Impressions: {total_impressions} "
               f"| CTR: {avg_ctr}% | Avg Pos: {avg_position} ({period_label})")

        return {"ok": True, "status": s, "message": msg, "data": {
            "clicks":      total_clicks,
            "impressions": total_impressions,
            "avg_ctr":     avg_ctr,
            "avg_position": avg_position,
            "period":      period_label,
        }}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# Crawl Stats
# ══════════════════════════════════════════════════════════════════════════════
def crawl_stats(site_url: str, api_key: str) -> dict:
    """
    Fetch Bing's crawl statistics for the site:
    pages crawled, DNS failures, connection errors, robots blocked, etc.
    """
    try:
        data = _get("GetCrawlStats", api_key, {"siteUrl": site_url})
        rows = data.get("d") or []
        if not rows:
            return {"ok": True, "status": "warning", "message": "No crawl data available", "data": []}

        # Summarise the last 30 days (most recent rows first, each row = one day)
        recent  = rows[:30]
        crawled = sum(r.get("CrawledPages",     0) for r in recent)
        errors  = sum(r.get("CrawlErrors",      0) for r in recent)
        dns_err = sum(r.get("DnsFailures",      0) for r in recent)
        robots  = sum(r.get("RobotsBlocked",    0) for r in recent)
        conn    = sum(r.get("ConnectionErrors",  0) for r in recent)

        issues = []
        if errors  > crawled * 0.05: issues.append(f"High crawl error rate ({errors}/{crawled})")
        if dns_err > 5:              issues.append(f"DNS failures: {dns_err}")
        if robots  > 0:              issues.append(f"Robots-blocked requests: {robots}")
        if conn    > 5:              issues.append(f"Connection errors: {conn}")

        s   = "fail" if any("High crawl error" in i for i in issues) else "warning" if issues else "pass"
        msg = f"Crawled {crawled} pages in last 30 days | {errors} errors | {robots} robots-blocked"

        timeline = [{
            "date":     r.get("Date", ""),
            "crawled":  r.get("CrawledPages",    0),
            "errors":   r.get("CrawlErrors",     0),
            "dns":      r.get("DnsFailures",     0),
            "robots":   r.get("RobotsBlocked",   0),
            "conn_err": r.get("ConnectionErrors", 0),
        } for r in recent]

        return {"ok": True, "status": s, "message": msg, "issues": issues, "data": {
            "summary": {
                "crawled_30d": crawled, "errors_30d": errors,
                "dns_failures": dns_err, "robots_blocked": robots,
                "connection_errors": conn,
            },
            "timeline": timeline,
        }}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# Sitemap Status
# ══════════════════════════════════════════════════════════════════════════════
def sitemap_status(site_url: str, api_key: str) -> dict:
    """
    List sitemaps submitted to Bing Webmaster and their indexation status.
    """
    try:
        data     = _get("GetSitemap", api_key, {"siteUrl": site_url})
        sitemaps = data.get("d") or []
        if not sitemaps:
            return {"ok": True, "status": "warning",
                    "message": "No sitemaps submitted to Bing Webmaster", "data": []}

        parsed   = []
        issues   = []
        for sm in sitemaps:
            url_count   = sm.get("UrlCount",    0)
            indexed     = sm.get("IndexedCount", 0)
            warnings    = sm.get("WarningsCount", 0)
            errors      = sm.get("ErrorsCount",   0)
            sm_type     = sm.get("Type",  "")
            status_val  = sm.get("Status", "")

            if errors:   issues.append(f"{sm.get('SitemapUrl','')}: {errors} error(s)")
            if url_count and indexed < url_count * 0.5:
                issues.append(f"{sm.get('SitemapUrl','')}: only {indexed}/{url_count} URLs indexed")

            parsed.append({
                "url":          sm.get("SitemapUrl", ""),
                "type":         sm_type,
                "status":       status_val,
                "url_count":    url_count,
                "indexed":      indexed,
                "index_rate":   round(indexed / url_count * 100, 1) if url_count else 0,
                "warnings":     warnings,
                "errors":       errors,
                "last_updated": sm.get("LastUpdated", ""),
            })

        total_urls    = sum(p["url_count"] for p in parsed)
        total_indexed = sum(p["indexed"]   for p in parsed)
        overall_rate  = round(total_indexed / total_urls * 100, 1) if total_urls else 0

        s   = "fail" if issues else "pass"
        msg = (f"{len(sitemaps)} sitemap(s) | "
               f"{total_indexed}/{total_urls} URLs indexed ({overall_rate}%)")

        return {"ok": True, "status": s, "message": msg, "issues": issues, "data": parsed}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# URL Inspection
# ══════════════════════════════════════════════════════════════════════════════
def inspect_url(page_url: str, site_url: str, api_key: str) -> dict:
    """
    Use Bing URL Inspection API to fetch indexation status, crawl verdict,
    last crawl time, and canonical URL for a specific page.
    """
    try:
        data = _get("GetUrlInfo", api_key, {"siteUrl": site_url, "url": page_url})
        d    = data.get("d") or {}

        is_indexed   = d.get("IsIndexed",    False)
        last_crawled = d.get("LastCrawled",   "")
        canonical    = d.get("CanonicalUrl",  "")
        crawl_state  = d.get("CrawlState",    "")
        index_state  = d.get("IndexState",    "")

        s   = "pass" if is_indexed else "warning"
        msg = (f"Indexed: {'Yes' if is_indexed else 'No'} | "
               f"Crawl: {crawl_state} | Index: {index_state}")
        if last_crawled:
            msg += f" | Last crawled: {last_crawled}"

        return {"ok": True, "status": s, "message": msg, "data": {
            "is_indexed":   is_indexed,
            "last_crawled": last_crawled,
            "canonical":    canonical,
            "crawl_state":  crawl_state,
            "index_state":  index_state,
        }}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# Submit URL to Bing
# ══════════════════════════════════════════════════════════════════════════════
def submit_url(page_url: str, site_url: str, api_key: str) -> dict:
    """Submit a single URL to Bing for crawling."""
    try:
        _post("SubmitUrl", api_key, {"siteUrl": site_url, "url": page_url})
        return {"ok": True, "message": f"Submitted to Bing: {page_url}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# Full site overview (combines all checks)
# ══════════════════════════════════════════════════════════════════════════════
def site_overview(site_url: str, api_key: str, period: int = 2) -> dict:
    """Run traffic, crawl stats, and sitemap status in sequence."""
    traffic  = url_traffic(site_url, api_key, period)
    crawl    = crawl_stats(site_url, api_key)
    sitemaps = sitemap_status(site_url, api_key)
    return {
        "ok":       True,
        "site_url": site_url,
        "traffic":  traffic,
        "crawl":    crawl,
        "sitemaps": sitemaps,
    }
