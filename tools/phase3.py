"""
Phase 3 SEO Tools — Google Search Console API
19. Clicks & Impressions per URL
20. Average Position Tracker
21. CTR Analyzer
22. Coverage Errors
23. Top Queries per Page
24. Sitemaps Status
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def result(url, tool, status, value, message, details=None):
    return {"url": url, "tool": tool, "status": status,
            "value": value, "message": message, "details": details or {}}


def date_range(days: int = 90):
    end   = datetime.utcnow().date()
    start = end - timedelta(days=days)
    return str(start), str(end)


# ══════════════════════════════════════════════════════════════════════════════
# 19. Clicks & Impressions per URL
# ══════════════════════════════════════════════════════════════════════════════
def clicks_impressions(url: str, service, site_url: str, days: int = 90) -> dict:
    start, end = date_range(days)
    try:
        resp = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start, "endDate": end,
                "dimensions": ["page"],
                "dimensionFilterGroups": [{"filters": [{"dimension": "page", "operator": "equals", "expression": url}]}],
                "rowLimit": 1,
            }
        ).execute()

        rows = resp.get("rows", [])
        if not rows:
            return result(url, "clicks_impressions", "warning", {}, "No GSC data found for this URL")

        row = rows[0]
        clicks      = row.get("clicks", 0)
        impressions = row.get("impressions", 0)
        ctr         = round(row.get("ctr", 0) * 100, 2)
        position    = round(row.get("position", 0), 1)

        s   = "pass" if clicks > 0 else "warning"
        msg = f"Clicks: {clicks} | Impressions: {impressions} | CTR: {ctr}% | Pos: {position}"

        return result(url, "clicks_impressions", s, {
            "clicks": clicks, "impressions": impressions, "ctr": ctr, "position": position
        }, msg, {"date_range": f"{start} to {end}", "days": days})

    except Exception as e:
        logger.warning("clicks_impressions GSC error for %s: %s", url, e)
        return result(url, "clicks_impressions", "error", None, f"GSC error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 20. Average Position Tracker (trend over time)
# ══════════════════════════════════════════════════════════════════════════════
def position_tracker(url: str, service, site_url: str) -> dict:
    start, end = date_range(90)
    try:
        resp = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start, "endDate": end,
                "dimensions": ["page", "date"],
                "dimensionFilterGroups": [{"filters": [{"dimension": "page", "operator": "equals", "expression": url}]}],
                "rowLimit": 90,
            }
        ).execute()

        rows = resp.get("rows", [])
        if not rows:
            return result(url, "position_tracker", "warning", [], "No position data")

        trend = [{"date": r["keys"][1], "position": round(r.get("position", 0), 1),
                  "clicks": r.get("clicks", 0)} for r in rows]
        trend.sort(key=lambda x: x["date"])

        avg_pos   = round(sum(t["position"] for t in trend) / len(trend), 1)
        first_pos = trend[0]["position"]
        last_pos  = trend[-1]["position"]
        improving = last_pos < first_pos

        s   = "pass" if avg_pos <= 10 else "warning" if avg_pos <= 30 else "fail"
        msg = f"Avg position: {avg_pos} | {'📈 Improving' if improving else '📉 Declining'}"

        return result(url, "position_tracker", s, trend, msg, {
            "avg_position": avg_pos, "first_position": first_pos,
            "last_position": last_pos, "improving": improving,
        })

    except Exception as e:
        logger.warning("position_tracker GSC error for %s: %s", url, e)
        return result(url, "position_tracker", "error", None, f"GSC error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 21. CTR Analyzer — low CTR pages that rank but don't get clicks
# ══════════════════════════════════════════════════════════════════════════════
def ctr_analyzer(service, site_url: str, min_impressions: int = 100) -> dict:
    start, end = date_range(90)
    try:
        resp = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start, "endDate": end,
                "dimensions": ["page"],
                "rowLimit": 500,
            }
        ).execute()

        rows = resp.get("rows", [])
        low_ctr = []

        for row in rows:
            impressions = row.get("impressions", 0)
            ctr         = row.get("ctr", 0) * 100
            position    = row.get("position", 0)
            if impressions >= min_impressions and ctr < 2.0 and position <= 20:
                low_ctr.append({
                    "url":         row["keys"][0],
                    "impressions": impressions,
                    "clicks":      row.get("clicks", 0),
                    "ctr":         round(ctr, 2),
                    "position":    round(position, 1),
                    "opportunity": "Improve title/description to boost CTR",
                })

        low_ctr.sort(key=lambda x: x["impressions"], reverse=True)

        s   = "warning" if low_ctr else "pass"
        msg = f"{len(low_ctr)} pages with low CTR despite ranking in top 20"

        return result(site_url, "ctr_analyzer", s, low_ctr[:50], msg, {
            "total_pages_analyzed": len(rows),
            "low_ctr_count": len(low_ctr),
            "min_impressions_threshold": min_impressions,
        })

    except Exception as e:
        logger.warning("ctr_analyzer GSC error for %s: %s", site_url, e)
        return result(site_url, "ctr_analyzer", "error", None, f"GSC error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 22. Coverage Errors
# ══════════════════════════════════════════════════════════════════════════════
def coverage_errors(service, site_url: str) -> dict:
    try:
        # Coverage gaps are derived from sitemap submitted-vs-indexed counts.
        sitemaps_resp = service.sitemaps().list(siteUrl=site_url).execute()
        sitemap_list  = sitemaps_resp.get("sitemap", [])

        errors   = []
        warnings = []

        for sm in sitemap_list:
            contents = sm.get("contents", [])
            for c in contents:
                t = c.get("type", "")
                if t == "WEB":
                    submitted = c.get("submitted", 0)
                    indexed   = c.get("indexed", 0)
                    if submitted and indexed:
                        gap = submitted - indexed
                        if gap > 0:
                            warnings.append({
                                "sitemap": sm.get("path",""),
                                "submitted": submitted,
                                "indexed": indexed,
                                "not_indexed": gap,
                            })

        s   = "fail" if errors else "warning" if warnings else "pass"
        msg = f"{len(errors)} errors | {len(warnings)} coverage gaps found"

        return result(site_url, "coverage_errors", s, {"errors": errors, "warnings": warnings}, msg, {
            "sitemap_count": len(sitemap_list),
        })

    except Exception as e:
        logger.warning("coverage_errors GSC error for %s: %s", site_url, e)
        return result(site_url, "coverage_errors", "error", None, f"GSC error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 23. Top Queries per Page
# ══════════════════════════════════════════════════════════════════════════════
def top_queries(url: str, service, site_url: str, top_n: int = 10) -> dict:
    start, end = date_range(90)
    try:
        resp = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start, "endDate": end,
                "dimensions": ["page", "query"],
                "dimensionFilterGroups": [{"filters": [{"dimension": "page", "operator": "equals", "expression": url}]}],
                "rowLimit": top_n,
                "orderBy": [{"fieldName": "clicks", "sortOrder": "DESCENDING"}],
            }
        ).execute()

        rows = resp.get("rows", [])
        if not rows:
            return result(url, "top_queries", "warning", [], "No query data found")

        queries = [{
            "query":       r["keys"][1],
            "clicks":      r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr":         round(r.get("ctr", 0) * 100, 2),
            "position":    round(r.get("position", 0), 1),
        } for r in rows]

        top_q = queries[0]["query"] if queries else ""
        msg   = f"Top query: '{top_q}' | {len(queries)} queries found"

        return result(url, "top_queries", "pass", queries, msg, {
            "total_queries": len(queries),
            "date_range": f"{start} to {end}",
        })

    except Exception as e:
        logger.warning("top_queries GSC error for %s: %s", url, e)
        return result(url, "top_queries", "error", None, f"GSC error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 24. Sitemaps Status
# ══════════════════════════════════════════════════════════════════════════════
def sitemaps_status(service, site_url: str) -> dict:
    try:
        resp     = service.sitemaps().list(siteUrl=site_url).execute()
        sitemaps = resp.get("sitemap", [])

        if not sitemaps:
            return result(site_url, "sitemaps_status", "warning", [], "No sitemaps submitted in GSC")

        details  = []
        issues   = []

        for sm in sitemaps:
            last_submitted = sm.get("lastSubmitted", "")
            last_downloaded = sm.get("lastDownloaded", "")
            errors_count   = len(sm.get("errors", []))
            warnings_count = len(sm.get("warnings", []))
            is_pending     = sm.get("isPending", False)
            is_processing  = sm.get("isProcessing", False)

            contents   = sm.get("contents", [])
            submitted  = sum(c.get("submitted", 0) for c in contents)
            indexed    = sum(c.get("indexed",   0) for c in contents)

            if errors_count:   issues.append(f"{sm['path']}: {errors_count} error(s)")
            if submitted > 0 and indexed < submitted * 0.5:
                issues.append(f"{sm['path']}: Only {indexed}/{submitted} URLs indexed")

            details.append({
                "path":            sm.get("path",""),
                "last_submitted":  last_submitted,
                "last_downloaded": last_downloaded,
                "submitted":       submitted,
                "indexed":         indexed,
                "index_rate":      round(indexed/submitted*100,1) if submitted else 0,
                "errors":          errors_count,
                "warnings":        warnings_count,
                "pending":         is_pending,
                "processing":      is_processing,
            })

        total_submitted = sum(d["submitted"] for d in details)
        total_indexed   = sum(d["indexed"]   for d in details)
        overall_rate    = round(total_indexed / total_submitted * 100, 1) if total_submitted else 0

        s   = "fail" if issues else "pass"
        msg = f"{len(sitemaps)} sitemaps | {total_indexed}/{total_submitted} URLs indexed ({overall_rate}%)"

        return result(site_url, "sitemaps_status", s, details, msg, {
            "sitemap_count":   len(sitemaps),
            "total_submitted": total_submitted,
            "total_indexed":   total_indexed,
            "index_rate":      overall_rate,
            "issues":          issues,
        })

    except Exception as e:
        logger.warning("sitemaps_status GSC error for %s: %s", site_url, e)
        return result(site_url, "sitemaps_status", "error", None, f"GSC error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Run all Phase 3 tools for a site
# ══════════════════════════════════════════════════════════════════════════════
def audit_site(service, site_url: str, sample_urls: list[str] = None) -> list[dict]:
    results = []
    results.append(ctr_analyzer(service, site_url))
    results.append(coverage_errors(service, site_url))
    results.append(sitemaps_status(service, site_url))
    if sample_urls:
        for url in sample_urls[:5]:
            results.append(clicks_impressions(url, service, site_url))
            results.append(position_tracker(url, service, site_url))
            results.append(top_queries(url, service, site_url))
    return results


# ══════════════════════════════════════════════════════════════════════════════
# Stage 3-B: GSC Opportunity Layer
# ══════════════════════════════════════════════════════════════════════════════

def opportunity_pages(service, site_url: str, min_impressions: int = 200,
                      max_ctr: float = 3.0, max_position: float = 20.0) -> dict:
    """
    Find pages with high impressions but low CTR — the biggest quick wins.
    These pages already have visibility; improving title/description = more clicks.

    Returns pages sorted by impressions descending, each with:
      - estimated extra clicks if CTR reaches the position's benchmark
      - specific action recommendation
    """
    # Typical CTR benchmarks by avg position (industry averages)
    _CTR_BENCHMARKS = {
        1: 28.5, 2: 15.7, 3: 11.0, 4: 8.0, 5: 7.2,
        6: 5.1,  7: 4.0,  8: 3.2,  9: 2.8, 10: 2.5,
    }

    start, end = date_range(90)
    try:
        resp = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start, "endDate": end,
                "dimensions": ["page"],
                "rowLimit": 1000,
            }
        ).execute()
        rows = resp.get("rows", [])

        opps = []
        for row in rows:
            impressions = row.get("impressions", 0)
            ctr         = row.get("ctr", 0) * 100
            position    = row.get("position", 0)
            clicks      = row.get("clicks", 0)

            if impressions < min_impressions or ctr >= max_ctr or position > max_position:
                continue

            pos_int   = min(10, max(1, round(position)))
            benchmark = _CTR_BENCHMARKS.get(pos_int, 2.5)
            est_extra = round((benchmark / 100 - ctr / 100) * impressions)

            if position <= 3:
                action = "Title/description likely low-relevance — run A/B test on title"
            elif position <= 10:
                action = "Add power words, numbers, or brackets to title; enrich description"
            else:
                action = "Improve content depth to climb to top 10, then optimise CTR"

            opps.append({
                "url":            row["keys"][0],
                "impressions":    impressions,
                "clicks":         clicks,
                "ctr":            round(ctr, 2),
                "position":       round(position, 1),
                "benchmark_ctr":  benchmark,
                "est_extra_clicks": max(0, est_extra),
                "action":         action,
            })

        opps.sort(key=lambda x: x["impressions"], reverse=True)
        total_est = sum(o["est_extra_clicks"] for o in opps)

        s   = "warning" if opps else "pass"
        msg = (f"{len(opps)} opportunity page(s) | "
               f"~{total_est:,} extra clicks/90d if CTR improved")

        return result(site_url, "opportunity_pages", s, opps[:100], msg, {
            "total_opportunities": len(opps),
            "total_pages_analyzed": len(rows),
            "estimated_extra_clicks": total_est,
            "thresholds": {
                "min_impressions": min_impressions,
                "max_ctr": max_ctr,
                "max_position": max_position,
            },
        })
    except Exception as e:
        logger.warning("opportunity_pages GSC error for %s: %s", site_url, e)
        return result(site_url, "opportunity_pages", "error", None, f"GSC error: {e}")


def position_decay(service, site_url: str, days: int = 90,
                   decay_threshold: float = 3.0) -> dict:
    """
    Detect pages that have declined in average position over the analysis window.
    Compares first-half vs second-half of the date range.
    Pages that dropped > decay_threshold positions are flagged.
    """
    start, end = date_range(days)
    try:
        resp = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start, "endDate": end,
                "dimensions": ["page", "date"],
                "rowLimit": 25000,
            }
        ).execute()
        rows = resp.get("rows", [])

        # Group by page, split into first-half / second-half
        from collections import defaultdict
        page_dates: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
        for row in rows:
            page = row["keys"][0]
            date = row["keys"][1]
            page_dates[page].append((date, row.get("position", 0), row.get("clicks", 0)))

        decayed = []
        for page, entries in page_dates.items():
            entries.sort(key=lambda x: x[0])
            half = len(entries) // 2
            if half < 5:
                continue   # too few data points
            first_positions = [e[1] for e in entries[:half]]
            last_positions  = [e[1] for e in entries[half:]]
            avg_first = sum(first_positions) / len(first_positions)
            avg_last  = sum(last_positions)  / len(last_positions)
            delta     = avg_last - avg_first   # positive = dropped (higher number = worse)

            if delta >= decay_threshold:
                total_clicks = sum(e[2] for e in entries)
                decayed.append({
                    "url":         page,
                    "pos_start":   round(avg_first, 1),
                    "pos_end":     round(avg_last,  1),
                    "delta":       round(delta, 1),
                    "total_clicks": total_clicks,
                    "severity":    "high" if delta >= 10 else "medium" if delta >= 5 else "low",
                })

        decayed.sort(key=lambda x: x["delta"], reverse=True)

        s   = "fail" if any(d["severity"] == "high" for d in decayed) else \
              "warning" if decayed else "pass"
        msg = f"{len(decayed)} page(s) show position decay (>{decay_threshold} pos drop)"

        return result(site_url, "position_decay", s, decayed[:50], msg, {
            "total_decayed": len(decayed),
            "days_analyzed": days,
            "decay_threshold": decay_threshold,
        })
    except Exception as e:
        logger.warning("position_decay GSC error for %s: %s", site_url, e)
        return result(site_url, "position_decay", "error", None, f"GSC error: {e}")


def keyword_cannibalization(service, site_url: str, min_impressions: int = 50,
                            top_queries: int = 500) -> dict:
    """
    Find queries where multiple pages compete for the same keyword.
    Cannibalization dilutes ranking signals — consolidate or differentiate.
    Returns query groups with 2+ competing pages.
    """
    start, end = date_range(90)
    try:
        resp = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start, "endDate": end,
                "dimensions": ["query", "page"],
                "rowLimit": min(top_queries, 25000),
                "orderBy": [{"fieldName": "impressions", "sortOrder": "DESCENDING"}],
            }
        ).execute()
        rows = resp.get("rows", [])

        from collections import defaultdict
        query_pages: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            query       = row["keys"][0]
            page        = row["keys"][1]
            impressions = row.get("impressions", 0)
            if impressions < min_impressions:
                continue
            query_pages[query].append({
                "page":        page,
                "impressions": impressions,
                "clicks":      row.get("clicks", 0),
                "ctr":         round(row.get("ctr", 0) * 100, 2),
                "position":    round(row.get("position", 0), 1),
            })

        cannibal = []
        for query, pages in query_pages.items():
            if len(pages) < 2:
                continue
            pages.sort(key=lambda x: x["position"])
            cannibal.append({
                "query":         query,
                "competing_pages": len(pages),
                "pages":         pages,
                "winner":        pages[0]["page"],
                "total_impressions": sum(p["impressions"] for p in pages),
                "recommendation": (
                    "Consolidate into one page" if len(pages) >= 3
                    else "Add internal link from weaker page to winner, or differentiate content"
                ),
            })

        cannibal.sort(key=lambda x: x["total_impressions"], reverse=True)

        s   = "warning" if cannibal else "pass"
        msg = f"{len(cannibal)} cannibalized keyword(s) found across {len(rows)} query-page pairs"

        return result(site_url, "keyword_cannibalization", s, cannibal[:50], msg, {
            "total_cannibal_queries":   len(cannibal),
            "total_query_pages_scanned": len(rows),
            "min_impressions_threshold": min_impressions,
        })
    except Exception as e:
        logger.warning("keyword_cannibalization GSC error for %s: %s", site_url, e)
        return result(site_url, "keyword_cannibalization", "error", None, f"GSC error: {e}")


def manual_actions(url: str, service, site_url: str) -> dict:
    """Check for Google manual actions via GSC URL Inspection API."""
    try:
        resp   = service.urlInspectionResult().inspect(
            body={"inspectionUrl": url, "siteUrl": site_url}
        ).execute()
        ma     = resp.get("urlInspectionResult", {}).get("manualActionsResult", {})
        verdict = ma.get("verdict", "")
        issues  = ma.get("manualActionInfo", [])
        if verdict == "NO_MANUAL_ACTIONS" or not issues:
            return result(url, "manual_actions", "pass", [], "No manual actions detected")
        types = [a.get("action", "Unknown action") for a in issues]
        msg   = f"Manual action(s): {', '.join(types[:2])}"
        return result(url, "manual_actions", "fail", types, msg,
                      {"verdict": verdict, "actions": issues})
    except Exception as e:
        logger.warning("manual_actions GSC error for %s: %s", url, e)
        return result(url, "manual_actions", "error", None, f"GSC error: {e}")


def gsc_opportunities(service, site_url: str) -> dict:
    """Run all three opportunity analyses and return a combined report."""
    return {
        "ok":               True,
        "site_url":         site_url,
        "opportunity_pages":         opportunity_pages(service, site_url),
        "position_decay":            position_decay(service, site_url),
        "keyword_cannibalization":   keyword_cannibalization(service, site_url),
    }
