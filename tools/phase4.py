"""
Phase 4 SEO Tools — Third-Party APIs (free tiers available)
25. Backlink Checker       — OpenLinkProfiler API (free) / Ahrefs
26. Domain Authority       — Moz API (free tier) / OpenPageRank
27. Keyword Rank Tracker   — SerpAPI (free 100/month) / DataForSEO
28. Competitor Comparison  — SerpAPI SERP scraping

All tools gracefully degrade if API keys are not configured.
"""

import logging
import time
from collections.abc import Callable

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

from core.security import safe_requests_get, safe_requests_post

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SEOAuditBot/1.0)"}


def _fetch_with_backoff(method: Callable, *args: Any, max_retries: int = 3, **kwargs: Any) -> Any | None:
    """safe_requests_get/post with fast-fail on 429, short backoff on 5xx."""
    for attempt in range(max_retries):
        try:
            resp = method(*args, **kwargs)
            if resp.status_code == 429:
                return None  # fail fast — don't block the audit thread
            if resp.status_code >= 500:
                if attempt < max_retries - 1:
                    time.sleep(min(2 ** attempt, 4))  # max 4s between retries
                continue
            return resp
        except (requests.RequestException, OSError) as exc:
            logger.warning("_fetch_with_backoff attempt %d failed: %s", attempt + 1, exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(min(2 ** attempt, 4))
    return None


def result(url: str, tool: str, status: str, value: Any, message: str, details: dict | None = None) -> dict:
    return {"url": url, "tool": tool, "status": status,
            "value": value, "message": message, "details": details or {}}


# ══════════════════════════════════════════════════════════════════════════════
# 25. Backlink Checker
# Uses: OpenPageRank API (free, no key needed for basic data)
#       or Ahrefs API (paid)
# ══════════════════════════════════════════════════════════════════════════════
def backlink_check(url: str, ahrefs_key: str = "", dataforseo_login: str = "",
                   dataforseo_password: str = "") -> dict[str, Any]:
    domain = urlparse(url).netloc.removeprefix("www.")

    # Option A: DataForSEO (most accurate, paid but affordable)
    if dataforseo_login and dataforseo_password:
        try:
            endpoint = "https://api.dataforseo.com/v3/backlinks/summary/live"
            payload  = [{"target": domain, "include_subdomains": True}]
            resp = _fetch_with_backoff(safe_requests_post, endpoint, json=payload, timeout=10,
                                       auth=(dataforseo_login, dataforseo_password))
            data = resp.json()
            task = data.get("tasks", [{}])[0].get("result", [{}])[0]
            backlinks   = task.get("backlinks", 0)
            ref_domains = task.get("referring_domains", 0)
            rank        = task.get("rank", 0)

            s   = "pass" if backlinks > 100 else "warning" if backlinks > 10 else "fail"
            msg = f"Backlinks: {backlinks:,} | Referring domains: {ref_domains:,}"
            return result(url, "backlinks", s, {"backlinks": backlinks, "ref_domains": ref_domains}, msg,
                          {"source": "DataForSEO", "domain_rank": rank})
        except (requests.RequestException, OSError, ValueError, KeyError) as e:
            logger.warning("backlink_check DataForSEO error for %s: %s", url, e)

    # No paid API configured
    return result(url, "backlinks", "warning", None,
                  "No backlink API configured — add DataForSEO credentials in Settings",
                  {"setup": "Add dataforseo_login / dataforseo_password to config.json"})


# ══════════════════════════════════════════════════════════════════════════════
# 26. Domain Authority
# Uses: Moz API (free 10 req/month) or OpenPageRank
# ══════════════════════════════════════════════════════════════════════════════
def domain_authority(url: str, moz_access_id: str = "", moz_secret_key: str = "") -> dict:
    domain = urlparse(url).netloc.removeprefix("www.")

    # Option A: Moz API
    if moz_access_id and moz_secret_key:
        try:
            import base64
            import hashlib
            import hmac
            import time
            expires    = str(int(time.time()) + 300)
            str_to_sign = moz_access_id + "\n" + expires
            sig        = base64.b64encode(
                hmac.new(moz_secret_key.encode(), str_to_sign.encode(), hashlib.sha1).digest()
            ).decode()

            resp = safe_requests_get(
                "https://lsapi.seomoz.com/v2/url_metrics",
                params={
                    "AccessID": moz_access_id, "Expires": expires,
                    "Signature": sig, "Cols": "68719476736",
                    "Site": domain,
                },
                timeout=10
            )
            data = resp.json()
            da   = data.get("pda", 0)
            pa   = data.get("upa", 0)

            s   = "pass" if da >= 40 else "warning" if da >= 20 else "fail"
            msg = f"Domain Authority: {da}/100 | Page Authority: {pa}/100"
            return result(url, "domain_authority", s, {"da": da, "pa": pa}, msg,
                          {"source": "Moz", "domain": domain})
        except (requests.RequestException, OSError, ValueError, KeyError) as e:
            logger.warning("domain_authority Moz error for %s: %s", url, e)

    return result(url, "domain_authority", "warning", None,
                  "No DA API configured — add Moz API keys in Settings",
                  {"setup": "Add moz_access_id / moz_secret_key to config.json"})


# ══════════════════════════════════════════════════════════════════════════════
# 27. Keyword Rank Tracker
# Uses: SerpAPI (free 100/month) or DataForSEO
# ══════════════════════════════════════════════════════════════════════════════
def keyword_rank_tracker(url: str, keywords: list[str], serpapi_key: str = "",
                         dataforseo_login: str = "", dataforseo_password: str = "") -> dict:
    domain  = urlparse(url).netloc
    results_list = []

    if not keywords:
        return result(url, "rank_tracker", "warning", [], "No keywords provided")

    # Option A: SerpAPI
    if serpapi_key:
        def _serp_lookup(kw):
            try:
                resp = safe_requests_get("https://serpapi.com/search", params={
                    "api_key": serpapi_key, "q": kw, "num": 100,
                    "gl": "us", "hl": "en",
                }, timeout=10)
                items = resp.json().get("organic_results", [])
                rank = next((i for i, item in enumerate(items, 1) if domain in item.get("link","")), None)
                return {"keyword": kw, "rank": rank,
                        "in_top_10": rank is not None and rank <= 10,
                        "in_top_3":  rank is not None and rank <= 3}
            except (requests.RequestException, OSError, ValueError, KeyError) as e:
                logger.warning("SerpAPI lookup failed for keyword %r: %s", kw, e)
                return {"keyword": kw, "rank": None, "error": str(e)}

        with ThreadPoolExecutor(max_workers=5) as ex:
            for res in as_completed([ex.submit(_serp_lookup, kw) for kw in keywords[:10]]):
                results_list.append(res.result())

    # Option B: DataForSEO
    elif dataforseo_login and dataforseo_password:
        try:
            tasks = [{"keyword": kw, "location_code": 2840, "language_code": "en"} for kw in keywords[:10]]
            resp  = safe_requests_post(
                "https://api.dataforseo.com/v3/serp/google/organic/live/advanced",
                json=tasks, auth=(dataforseo_login, dataforseo_password), timeout=15
            )
            data  = resp.json()
            for task in data.get("tasks", []):
                kw   = task.get("data", {}).get("keyword","")
                items = (task.get("result") or [{}])[0].get("items", [])
                rank = None
                for item in items:
                    if domain in (item.get("url") or ""):
                        rank = item.get("rank_absolute"); break
                results_list.append({"keyword": kw, "rank": rank,
                                     "in_top_10": rank is not None and rank <= 10})
        except (requests.RequestException, OSError, ValueError, KeyError) as e:
            logger.warning("DataForSEO rank_tracker failed for %s: %s", url, e)
            return result(url, "rank_tracker", "error", None, str(e))
    else:
        return result(url, "rank_tracker", "warning", [],
                      "No rank tracking API configured — add SerpAPI or DataForSEO key",
                      {"setup": "Add serpapi_key or dataforseo credentials to config.json"})

    ranked   = [r for r in results_list if r.get("rank")]
    top10    = [r for r in ranked if r.get("in_top_10")]
    top3     = [r for r in results_list if r.get("in_top_3")]

    s   = "pass" if top10 else "warning" if ranked else "fail"
    msg = f"{len(top10)}/{len(keywords)} keywords in top 10 | {len(top3)} in top 3"

    return result(url, "rank_tracker", s, results_list, msg, {
        "total_keywords": len(keywords),
        "ranked_count":   len(ranked),
        "top_10_count":   len(top10),
        "top_3_count":    len(top3),
    })


# ══════════════════════════════════════════════════════════════════════════════
# 28. Competitor Comparison
# Compares your page vs competitors for the same keyword
# ══════════════════════════════════════════════════════════════════════════════
def competitor_comparison(target_url: str, keyword: str, serpapi_key: str = "",
                          dataforseo_login: str = "", dataforseo_password: str = "") -> dict:
    target_domain = urlparse(target_url).netloc

    if not serpapi_key and not (dataforseo_login and dataforseo_password):
        return result(target_url, "competitor", "warning", [],
                      "No API configured for competitor analysis",
                      {"setup": "Add serpapi_key to config.json"})

    try:
        if serpapi_key:
            resp = safe_requests_get("https://serpapi.com/search", params={
                "api_key": serpapi_key, "q": keyword, "num": 10,
                "gl": "us", "hl": "en",
            }, timeout=10)
            items = resp.json().get("organic_results", [])
        else:
            task_resp = safe_requests_post(
                "https://api.dataforseo.com/v3/serp/google/organic/live/regular",
                json=[{"keyword": keyword, "location_code": 2840, "language_code": "en"}],
                auth=(dataforseo_login, dataforseo_password), timeout=15
            )
            items = (task_resp.json().get("tasks",[{}])[0].get("result",[{}])[0].get("items",[]))

        competitors = []
        target_rank = None

        for i, item in enumerate(items[:10], 1):
            link  = item.get("link","") or item.get("url","")
            title = item.get("title","")
            snip  = item.get("snippet","") or item.get("description","")
            dom   = urlparse(link).netloc

            entry = {
                "rank":    i,
                "domain":  dom,
                "url":     link,
                "title":   title,
                "snippet": snip[:200],
                "is_you":  dom == target_domain,
            }
            competitors.append(entry)
            if dom == target_domain:
                target_rank = i

        s   = "pass" if target_rank and target_rank <= 3 else "warning" if target_rank and target_rank <= 10 else "fail"
        msg = f"You rank #{target_rank} for '{keyword}'" if target_rank else f"Not in top 10 for '{keyword}'"

        return result(target_url, "competitor", s, competitors, msg, {
            "keyword":     keyword,
            "your_rank":   target_rank,
            "top_competitor": competitors[0]["domain"] if competitors else "",
        })

    except (requests.RequestException, OSError, ValueError, KeyError) as e:
        logger.warning("competitor_comparison failed for %s: %s", target_url, e)
        return result(target_url, "competitor", "error", None, f"API error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 29. Page Authority (Moz PA — split from domain_authority)
# ══════════════════════════════════════════════════════════════════════════════
def page_authority(url: str, moz_access_id: str = "", moz_secret_key: str = "") -> dict:
    if not moz_access_id or not moz_secret_key:
        return result(url, "page_authority", "warning", None,
                      "No Moz API configured — add moz_access_id / moz_secret_key in Settings")
    da_r = domain_authority(url, moz_access_id, moz_secret_key)
    pa   = (da_r.get("value") or {}).get("pa", 0)
    s    = "pass" if pa >= 30 else "warning" if pa >= 15 else "fail"
    return result(url, "page_authority", s, pa, f"Page Authority: {pa}/100",
                  {"source": "Moz", "pa": pa})


# ══════════════════════════════════════════════════════════════════════════════
# 30. Referring Domains (DataForSEO — split from backlinks)
# ══════════════════════════════════════════════════════════════════════════════
def referring_domains(url: str, dataforseo_login: str = "",
                      dataforseo_password: str = "") -> dict:
    if not dataforseo_login or not dataforseo_password:
        return result(url, "referring_domains", "warning", None,
                      "No DataForSEO credentials — add dataforseo_login / dataforseo_password in Settings")
    bl  = backlink_check(url, dataforseo_login=dataforseo_login,
                         dataforseo_password=dataforseo_password)
    ref = (bl.get("value") or {}).get("ref_domains", 0) or 0
    s   = "pass" if ref >= 50 else "warning" if ref >= 10 else "fail"
    return result(url, "referring_domains", s, ref, f"Referring domains: {ref:,}",
                  {"source": "DataForSEO"})


# ══════════════════════════════════════════════════════════════════════════════
# 31. Domain Rank (DataForSEO rank from backlinks summary)
# ══════════════════════════════════════════════════════════════════════════════
def domain_rank(url: str, dataforseo_login: str = "",
                dataforseo_password: str = "") -> dict:
    if not dataforseo_login or not dataforseo_password:
        return result(url, "domain_rank", "warning", None,
                      "No DataForSEO credentials — add dataforseo_login / dataforseo_password in Settings")
    bl   = backlink_check(url, dataforseo_login=dataforseo_login,
                          dataforseo_password=dataforseo_password)
    rank = bl.get("details", {}).get("domain_rank", 0) or 0
    s    = "pass" if rank >= 50 else "warning" if rank >= 20 else "fail"
    return result(url, "domain_rank", s, rank, f"Domain rank: {rank}/100 (DataForSEO)",
                  {"source": "DataForSEO"})


# ══════════════════════════════════════════════════════════════════════════════
# 32. Broken Backlinks (DataForSEO)
# ══════════════════════════════════════════════════════════════════════════════
def broken_backlinks(url: str, dataforseo_login: str = "",
                     dataforseo_password: str = "") -> dict:
    if not dataforseo_login or not dataforseo_password:
        return result(url, "broken_backlinks", "warning", None,
                      "No DataForSEO credentials — add dataforseo_login / dataforseo_password in Settings")
    domain = urlparse(url).netloc.removeprefix("www.")
    try:
        endpoint = "https://api.dataforseo.com/v3/backlinks/backlinks/live"
        payload  = [{"target": domain, "broken_backlinks": True, "limit": 1}]
        resp     = _fetch_with_backoff(safe_requests_post, endpoint, json=payload, timeout=12,
                                       auth=(dataforseo_login, dataforseo_password))
        task     = resp.json().get("tasks", [{}])[0].get("result", [{}])[0]
        broken   = task.get("total_count", 0) or 0
        s        = "pass" if broken == 0 else "warning" if broken <= 10 else "fail"
        return result(url, "broken_backlinks", s, broken, f"Broken backlinks: {broken:,}")
    except (requests.RequestException, OSError, ValueError, KeyError) as e:
        logger.warning("broken_backlinks failed for %s: %s", url, e)
        return result(url, "broken_backlinks", "error", None, f"DataForSEO error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 33. Nofollow / Dofollow Ratio (DataForSEO)
# ══════════════════════════════════════════════════════════════════════════════
def nofollow_ratio(url: str, dataforseo_login: str = "",
                   dataforseo_password: str = "") -> dict:
    if not dataforseo_login or not dataforseo_password:
        return result(url, "nofollow_ratio", "warning", None,
                      "No DataForSEO credentials — add dataforseo_login / dataforseo_password in Settings")
    domain = urlparse(url).netloc.removeprefix("www.")
    try:
        endpoint = "https://api.dataforseo.com/v3/backlinks/summary/live"
        payload  = [{"target": domain, "include_subdomains": True}]
        resp     = _fetch_with_backoff(safe_requests_post, endpoint, json=payload, timeout=12,
                                       auth=(dataforseo_login, dataforseo_password))
        task     = resp.json().get("tasks", [{}])[0].get("result", [{}])[0]
        nofollow = task.get("nofollow", 0) or 0
        dofollow = task.get("dofollow", 0) or 0
        total    = nofollow + dofollow or 1
        pct_do   = round(dofollow / total * 100, 1)
        s        = "pass" if pct_do >= 70 else "warning" if pct_do >= 50 else "fail"
        msg      = f"Dofollow: {pct_do}% | Nofollow: {round(100 - pct_do, 1)}%"
        return result(url, "nofollow_ratio", s,
                      {"dofollow": dofollow, "nofollow": nofollow}, msg)
    except (requests.RequestException, OSError, ValueError, KeyError) as e:
        logger.warning("nofollow_ratio failed for %s: %s", url, e)
        return result(url, "nofollow_ratio", "error", None, f"DataForSEO error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 34. Spam Score (Moz)
# ══════════════════════════════════════════════════════════════════════════════
def spam_score(url: str, moz_access_id: str = "", moz_secret_key: str = "") -> dict:
    if not moz_access_id or not moz_secret_key:
        return result(url, "spam_score", "warning", None,
                      "No Moz API configured — add moz_access_id / moz_secret_key in Settings")
    domain = urlparse(url).netloc.removeprefix("www.")
    try:
        import base64
        import hashlib
        import hmac as _hmac
        import time as _time
        expires     = str(int(_time.time()) + 300)
        sig         = base64.b64encode(
            _hmac.new(moz_secret_key.encode(),
                      (moz_access_id + "\n" + expires).encode(),
                      hashlib.sha1).digest()
        ).decode()
        resp = safe_requests_get(
            "https://lsapi.seomoz.com/v2/url_metrics",
            params={"AccessID": moz_access_id, "Expires": expires,
                    "Signature": sig, "Cols": "68719476736", "Site": domain},
            timeout=10
        )
        data  = resp.json()
        spam  = data.get("spam_score", 0)
        s     = "pass" if spam <= 3 else "warning" if spam <= 7 else "fail"
        return result(url, "spam_score", s, spam, f"Spam score: {spam}/17 (Moz)",
                      {"source": "Moz"})
    except (requests.RequestException, OSError, ValueError, KeyError) as e:
        logger.warning("spam_score failed for %s: %s", url, e)
        return result(url, "spam_score", "error", None, f"Moz error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 35. SERP Features (featured snippets, PAA, rich results)
# ══════════════════════════════════════════════════════════════════════════════
def serp_features(url: str, keywords: list, serpapi_key: str = "",
                  dataforseo_login: str = "", dataforseo_password: str = "") -> dict:
    if not keywords:
        return result(url, "serp_features", "warning", [], "No keywords provided")
    if not serpapi_key and not (dataforseo_login and dataforseo_password):
        return result(url, "serp_features", "warning", [],
                      "No API configured — add SerpAPI or DataForSEO key in Settings")
    kw = keywords[0]
    try:
        features = []
        if serpapi_key:
            resp = safe_requests_get("https://serpapi.com/search", params={
                "api_key": serpapi_key, "q": kw, "num": 10, "gl": "us", "hl": "en",
            }, timeout=10)
            data = resp.json()
            if "answer_box"        in data: features.append("Featured Snippet")
            if "related_questions" in data: features.append("People Also Ask")
            if "knowledge_graph"   in data: features.append("Knowledge Graph")
            if "local_results"     in data: features.append("Local Pack")
            if "shopping_results"  in data: features.append("Shopping")
        s   = "pass" if features else "warning"
        msg = f"SERP features for '{kw}': {', '.join(features) or 'none detected'}"
        return result(url, "serp_features", s, features, msg, {"keyword": kw})
    except (requests.RequestException, OSError, ValueError, KeyError) as e:
        logger.warning("serp_features failed for %s: %s", url, e)
        return result(url, "serp_features", "error", None, f"SERP error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 36. Rank Change — compare vs previous run stored in data/rank_history.json
# ══════════════════════════════════════════════════════════════════════════════
def rank_change(url: str, keywords: list, serpapi_key: str = "",
                dataforseo_login: str = "", dataforseo_password: str = "") -> dict:
    import json
    import time as _time
    from pathlib import Path
    _RANK_FILE = Path(__file__).parent.parent / "data" / "rank_history.json"

    if not keywords:
        return result(url, "rank_change", "warning", [], "No keywords provided")

    history = {}
    if _RANK_FILE.exists():
        try:
            history = json.loads(_RANK_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.debug("rank_history.json unreadable, starting fresh: %s", e)

    domain   = urlparse(url).netloc
    prev_run = history.get(domain, {})

    current   = keyword_rank_tracker(url, keywords, serpapi_key=serpapi_key,
                                     dataforseo_login=dataforseo_login,
                                     dataforseo_password=dataforseo_password)
    curr_data = current.get("value", []) or []

    changes = []
    new_hist = {}
    for kd in curr_data:
        kw   = kd.get("keyword", "")
        rank = kd.get("rank")
        if rank:
            new_hist[kw] = rank
        prev = prev_run.get(kw)
        if rank and prev:
            changes.append({"keyword": kw, "current": rank, "previous": prev,
                            "delta": prev - rank})

    history[domain] = {**new_hist, "_ts": int(_time.time())}
    try:
        _RANK_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RANK_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except OSError as e:
        logger.debug("rank_history.json write failed: %s", e)

    if not changes:
        return result(url, "rank_change", "warning", [],
                      "No previous run data — run again next time to see changes")
    improved = sum(1 for c in changes if c["delta"] > 0)
    declined = sum(1 for c in changes if c["delta"] < 0)
    s   = "pass" if improved >= declined else "warning"
    msg = f"↑ {improved} improved · ↓ {declined} declined vs last run"
    return result(url, "rank_change", s, changes, msg, {"total_compared": len(changes)})


# ══════════════════════════════════════════════════════════════════════════════
# 37. Traffic Share — CTR estimate from position data
# ══════════════════════════════════════════════════════════════════════════════
def traffic_share(url: str, keywords: list, serpapi_key: str = "",
                  dataforseo_login: str = "", dataforseo_password: str = "") -> dict:
    if not keywords:
        return result(url, "traffic_share", "warning", [], "No keywords provided")
    CTR = {1:28.5, 2:15.7, 3:11.0, 4:8.0, 5:7.2,
           6:5.1,  7:4.0,  8:3.2,  9:2.8, 10:2.5}
    current   = keyword_rank_tracker(url, keywords, serpapi_key=serpapi_key,
                                     dataforseo_login=dataforseo_login,
                                     dataforseo_password=dataforseo_password)
    curr_data = current.get("value", []) or []
    shares    = [{"keyword": d["keyword"], "rank": d["rank"],
                  "estimated_ctr": CTR.get(d["rank"], 2.0)}
                 for d in curr_data if d.get("rank") and d["rank"] <= 10]
    if not shares:
        return result(url, "traffic_share", "warning", [],
                      "No top-10 rankings found — no traffic share to estimate")
    avg_ctr = round(sum(s["estimated_ctr"] for s in shares) / len(shares), 1)
    s   = "pass" if avg_ctr >= 10 else "warning" if avg_ctr >= 5 else "fail"
    msg = f"Avg estimated CTR: {avg_ctr}% across {len(shares)} top-10 keyword(s)"
    return result(url, "traffic_share", s, shares, msg, {"model": "Sistrix CTR model"})


# ══════════════════════════════════════════════════════════════════════════════
# Run all Phase 4 tools — parallel to minimise total latency
# ══════════════════════════════════════════════════════════════════════════════
def audit_url(url: str, cfg: dict, keywords: list[str] = None, keyword: str = "") -> list[dict]:
    serpapi_key  = cfg.get("serpapi_key", "")
    moz_id       = cfg.get("moz_access_id", "")
    moz_secret   = cfg.get("moz_secret_key", "")
    dfs_login    = cfg.get("dataforseo_login", "")
    dfs_password = cfg.get("dataforseo_password", "")

    tasks = {
        "backlinks": lambda: backlink_check(url, dataforseo_login=dfs_login, dataforseo_password=dfs_password),
        "domain_authority": lambda: domain_authority(url, moz_id, moz_secret),
    }
    if keywords:
        tasks["rank_tracker"] = lambda: keyword_rank_tracker(url, keywords, serpapi_key, dfs_login, dfs_password)
    if keyword:
        tasks["competitor"] = lambda: competitor_comparison(url, keyword, serpapi_key, dfs_login, dfs_password)

    results = [None] * len(tasks)
    task_names = list(tasks.keys())

    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as ex:
        futures = {ex.submit(fn): i for i, (_, fn) in enumerate(tasks.items())}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:
                logger.exception("phase4 task %s failed for %s: %s", task_names[idx], url, e)

    return [r for r in results if r is not None]
