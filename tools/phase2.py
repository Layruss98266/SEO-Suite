"""
Phase 2 SEO Tools — Free Google APIs
16. Page Speed / Core Web Vitals (PageSpeed Insights API)
17. Mobile Friendliness (same API)
18. Crawlability Check (GSC API)
"""

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from core.security import safe_requests_get

PAGESPEED_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SEOAuditBot/1.0)"}

# Thresholds — overridable via config.json "thresholds" block
def _thresholds():
    try:
        from core.checker import load_config
        t = load_config().get("thresholds", {})
    except Exception:
        t = {}
    return t

def _ps_pass():  return _thresholds().get("pagespeed_pass", 90)
def _ps_warn():  return _thresholds().get("pagespeed_warn", 50)
def _mob_pass(): return _thresholds().get("mobile_pass", 70)
def _mob_warn(): return _thresholds().get("mobile_warn", 50)


def result(url, tool, status, value, message, details=None):
    return {"url": url, "tool": tool, "status": status,
            "value": value, "message": message, "details": details or {}}


# ══════════════════════════════════════════════════════════════════════════════
# 16 + 17. PageSpeed + Core Web Vitals + Mobile Friendliness
# ══════════════════════════════════════════════════════════════════════════════
def pagespeed_check(url: str, api_key: str, strategy: str = "mobile") -> dict:
    """
    strategy: 'mobile' or 'desktop'
    Returns performance score + Core Web Vitals (LCP, CLS, FID/INP, TTFB).
    API key from: console.cloud.google.com → PageSpeed Insights API (free).
    """
    params = {"url": url, "strategy": strategy, "key": api_key}
    try:
        resp = safe_requests_get(PAGESPEED_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return result(url, f"pagespeed_{strategy}", "error", None, str(e))

    cats       = data.get("lighthouseResult", {}).get("categories", {})
    perf       = cats.get("performance", {}).get("score", 0)
    perf_score = round(perf * 100) if perf else 0

    audits = data.get("lighthouseResult", {}).get("audits", {})

    def metric(key):
        m = audits.get(key, {})
        return {"value": m.get("displayValue",""), "score": m.get("score", 0)}

    lcp   = metric("largest-contentful-paint")
    cls   = metric("cumulative-layout-shift")
    fid   = metric("max-potential-fid")
    inp   = metric("interaction-to-next-paint")
    tbt   = metric("total-blocking-time")
    fcp   = metric("first-contentful-paint")
    si    = metric("speed-index")

    # Mobile usability from field data
    field = data.get("loadingExperience", {}).get("metrics", {})
    inp_field = field.get("INTERACTION_TO_NEXT_PAINT", {})

    if perf_score >= _ps_pass():   s, msg = "pass",    f"Excellent performance: {perf_score}/100"
    elif perf_score >= _ps_warn(): s, msg = "warning", f"Needs improvement: {perf_score}/100"
    else:                          s, msg = "fail",    f"Poor performance: {perf_score}/100"

    return result(url, f"pagespeed_{strategy}", s, perf_score, msg, {
        "performance_score": perf_score,
        "lcp":  lcp,  "cls": cls, "fid": fid,
        "inp":  inp,  "tbt": tbt, "fcp": fcp,
        "speed_index": si,
        "strategy": strategy,
        "inp_field": inp_field.get("category",""),
    })


def mobile_check(url: str, api_key: str, mob=None, desk=None) -> dict:
    """Check mobile friendliness via PageSpeed API mobile strategy."""
    if mob is None or desk is None:
        with ThreadPoolExecutor(max_workers=2) as ex:
            mob_f  = ex.submit(pagespeed_check, url, api_key, "mobile")
            desk_f = ex.submit(pagespeed_check, url, api_key, "desktop")
            mob    = mob_f.result()
            desk   = desk_f.result()

    if mob.get("status") == "error":
        return result(url, "mobile", "error", None, mob["message"])

    mob_score  = mob["details"].get("performance_score", 0)
    desk_score = desk["details"].get("performance_score", 0)
    diff       = desk_score - mob_score

    s   = "pass" if mob_score >= _mob_pass() else "warning" if mob_score >= _mob_warn() else "fail"
    msg = f"Mobile: {mob_score} | Desktop: {desk_score} | Gap: {diff}"

    return result(url, "mobile", s, {"mobile": mob_score, "desktop": desk_score}, msg, {
        "mobile_details":  mob["details"],
        "desktop_details": desk["details"],
        "score_gap":       diff,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 18. Crawlability Check (GSC URL Inspection API)
# ══════════════════════════════════════════════════════════════════════════════
def crawlability_check(url: str, gsc_service, site_url: str = None) -> dict:
    """Uses GSC URL Inspection API to check if Google can crawl the page."""
    try:
        if not site_url:
            parsed = urlparse(url)
            site_url = f"{parsed.scheme}://{parsed.netloc}/"
        resp = gsc_service.urlInspectionResult().inspect(
            body={"inspectionUrl": url, "siteUrl": site_url}
        ).execute()

        insp   = resp.get("urlInspectionResult", {})
        index  = insp.get("indexStatusResult", {})
        mobile = insp.get("mobileUsabilityResult", {})

        verdict       = index.get("verdict", "")
        crawled_as    = index.get("crawledAs", "")
        last_crawl    = index.get("lastCrawlTime", "")
        crawl_allowed = index.get("robotsTxtState", "") != "BLOCKED"
        page_fetch    = index.get("pageFetchState", "")
        indexing_state = index.get("indexingState", "")
        coverage       = index.get("coverageState", "")

        mobile_verdict = mobile.get("verdict", "")
        mobile_issues  = mobile.get("issues", [])

        s = "pass" if verdict == "PASS" else "warning" if verdict == "NEUTRAL" else "fail"
        msg = f"GSC: {verdict} | Crawled as: {crawled_as} | Fetch: {page_fetch}"

        return result(url, "crawlability", s, verdict, msg, {
            "verdict":         verdict,
            "crawled_as":      crawled_as,
            "last_crawl":      last_crawl,
            "crawl_allowed":   crawl_allowed,
            "page_fetch":      page_fetch,
            "indexing_state":  indexing_state,
            "coverage":        coverage,
            "mobile_verdict":  mobile_verdict,
            "mobile_issues":   mobile_issues,
        })

    except Exception as e:
        return result(url, "crawlability", "error", None, f"GSC error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Core Web Vitals extractor — pulls LCP / CLS / FCP / INP from pagespeed result
# ══════════════════════════════════════════════════════════════════════════════
def extract_cwv(ps_result: dict) -> list[dict]:
    """Return 4 CWV result dicts from an existing pagespeed_check output dict.
    No extra API call — reuses already-fetched LH data stored in details.
    """
    url     = ps_result.get("url", "")
    details = ps_result.get("details", {})
    out     = []

    CWV = [
        ("lcp", "LCP — Largest Contentful Paint", "< 2.5 s"),
        ("cls", "CLS — Cumulative Layout Shift",  "< 0.1"),
        ("fcp", "FCP — First Contentful Paint",   "< 1.8 s"),
        ("inp", "INP — Interaction to Next Paint", "< 200 ms"),
    ]
    for tid, label, target in CWV:
        metric = details.get(tid)
        if not metric:
            continue
        val   = metric.get("value", "N/A")
        score = metric.get("score")
        s     = ("pass"    if score is not None and score >= 0.9 else
                 "warning" if score is not None and score >= 0.5 else
                 "fail"    if score is not None else "warning")
        out.append(result(url, tid, s, val, f"{label}: {val} (target {target})",
                          {"score": score, "target": target}))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Run all Phase 2 tools
# ══════════════════════════════════════════════════════════════════════════════
def audit_url(url: str, api_key: str = "", gsc_service=None, site_url: str = "") -> list[dict]:
    results = []
    if api_key:
        with ThreadPoolExecutor(max_workers=2) as ex:
            mob_f  = ex.submit(pagespeed_check, url, api_key, "mobile")
            desk_f = ex.submit(pagespeed_check, url, api_key, "desktop")
            mob    = mob_f.result()
            desk   = desk_f.result()
        results += [mob, desk, mobile_check(url, api_key, mob=mob, desk=desk)]
    if gsc_service:
        results.append(crawlability_check(url, gsc_service, site_url or None))
    return results


# ══════════════════════════════════════════════════════════════════════════════
# Stage 3-C: Performance Opportunity Layer
# ══════════════════════════════════════════════════════════════════════════════

# CWV thresholds (Google's official values)
_CWV = {
    "largest-contentful-paint": {
        "good": 2.5, "needs_improvement": 4.0, "unit": "s",
        "label": "LCP", "impact": "high",
        "fix": "Optimise server response time, eliminate render-blocking resources, preload hero image",
    },
    "cumulative-layout-shift": {
        "good": 0.1, "needs_improvement": 0.25, "unit": "",
        "label": "CLS", "impact": "medium",
        "fix": "Set explicit width/height on images, avoid inserting DOM above existing content",
    },
    "interaction-to-next-paint": {
        "good": 200, "needs_improvement": 500, "unit": "ms",
        "label": "INP", "impact": "medium",
        "fix": "Break up long tasks, reduce JS execution time, defer non-critical scripts",
    },
    "total-blocking-time": {
        "good": 200, "needs_improvement": 600, "unit": "ms",
        "label": "TBT", "impact": "medium",
        "fix": "Split large JS bundles, use code splitting, move third-party scripts off critical path",
    },
    "first-contentful-paint": {
        "good": 1.8, "needs_improvement": 3.0, "unit": "s",
        "label": "FCP", "impact": "low",
        "fix": "Eliminate render-blocking resources, reduce server response time, use CDN",
    },
    "speed-index": {
        "good": 3.4, "needs_improvement": 5.8, "unit": "s",
        "label": "Speed Index", "impact": "low",
        "fix": "Minimise render-blocking resources, optimise critical rendering path",
    },
}


def _parse_metric_value(display_value: str) -> float:
    """Extract numeric seconds/ms from Lighthouse displayValue like '2.4 s' or '540 ms'."""
    if not display_value:
        return 0.0
    import re
    m = re.search(r"[\d.]+", display_value)
    if not m:
        return 0.0
    num = float(m.group())
    if "ms" in display_value.lower():
        return num / 1000  # convert ms → s for uniform comparison
    return num


def _cwv_grade(metric_key: str, display_value: str) -> str:
    cfg     = _CWV.get(metric_key, {})
    val     = _parse_metric_value(display_value)
    good    = cfg.get("good", 0)
    ni      = cfg.get("needs_improvement", 0)
    # Thresholds are already normalised to the metric's unit (s for time
    # metrics, dimensionless for CLS), so no unit conversion is needed here.
    if val == 0.0:
        return "unknown"
    if val <= good:
        return "good"
    if val <= ni:
        return "needs_improvement"
    return "poor"


def performance_opportunities(url: str, api_key: str) -> dict:
    """
    Run PageSpeed for mobile + desktop, analyse Core Web Vitals, and produce
    a prioritised fix plan grouped into three buckets:

      critical — poor CWV that directly hurt ranking (LCP, CLS, INP/TBT)
      quick_wins — issues with high impact and low effort
      nice_to_have — smaller gains (FCP, speed-index)

    Returns a structured dict ready to render in the dashboard.
    """
    if not api_key:
        return {"ok": False, "error": "PageSpeed API key required (set in Settings → pagespeed_key)"}

    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            mob_f  = ex.submit(pagespeed_check, url, api_key, "mobile")
            desk_f = ex.submit(pagespeed_check, url, api_key, "desktop")
            mob    = mob_f.result()
            desk   = desk_f.result()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if mob.get("status") == "error":
        return {"ok": False, "error": mob["message"]}

    mob_det  = mob.get("details",  {})
    desk_det = desk.get("details", {})

    # Build metric rows
    metric_keys = [
        "largest-contentful-paint", "cumulative-layout-shift",
        "interaction-to-next-paint", "total-blocking-time",
        "first-contentful-paint",   "speed-index",
    ]

    metrics = []
    for key in metric_keys:
        cfg        = _CWV.get(key, {})
        mob_val    = (mob_det.get(key.replace("-", "_")) or mob_det.get(key) or {})
        desk_val   = (desk_det.get(key.replace("-", "_")) or desk_det.get(key) or {})
        mob_disp   = mob_val.get("value",  "") if isinstance(mob_val, dict) else ""
        desk_disp  = desk_val.get("value", "") if isinstance(desk_val, dict) else ""
        mob_grade  = _cwv_grade(key, mob_disp)
        desk_grade = _cwv_grade(key, desk_disp)
        worst      = "poor" if "poor" in (mob_grade, desk_grade) else \
                     "needs_improvement" if "needs_improvement" in (mob_grade, desk_grade) else \
                     "good"
        metrics.append({
            "key":         key,
            "label":       cfg.get("label", key),
            "impact":      cfg.get("impact", "low"),
            "fix":         cfg.get("fix", ""),
            "mobile":      {"value": mob_disp,  "grade": mob_grade},
            "desktop":     {"value": desk_disp, "grade": desk_grade},
            "worst_grade": worst,
        })

    # Bucket into priority groups
    critical     = [m for m in metrics if m["worst_grade"] == "poor"    and m["impact"] == "high"]
    quick_wins   = [m for m in metrics if m["worst_grade"] in ("poor", "needs_improvement")
                    and m["impact"] == "medium"]
    nice_to_have = [m for m in metrics if m["worst_grade"] == "needs_improvement"
                    and m["impact"] == "low"]

    mob_score  = mob_det.get("performance_score",  0)
    desk_score = desk_det.get("performance_score", 0)
    gap        = desk_score - mob_score

    overall_grade = (
        "critical"    if critical else
        "needs_work"  if quick_wins else
        "good"        if mob_score >= 90 else
        "fair"
    )

    return {
        "ok":      True,
        "url":     url,
        "scores":  {"mobile": mob_score, "desktop": desk_score, "gap": gap},
        "overall": overall_grade,
        "metrics": metrics,
        "buckets": {
            "critical":     critical,
            "quick_wins":   quick_wins,
            "nice_to_have": nice_to_have,
        },
        "summary": (
            f"Mobile {mob_score}/100 | Desktop {desk_score}/100 | "
            f"{len(critical)} critical, {len(quick_wins)} quick wins"
        ),
    }
