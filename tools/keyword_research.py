"""
Keyword research tool adapted from OpenSEO's DataForSEO Labs workflow.

Supports the same research modes:
- auto: try related keywords, then suggestions, then ideas until coverage is useful
- related: DataForSEO related_keywords endpoint
- suggestions: DataForSEO keyword_suggestions endpoint
- ideas: DataForSEO keyword_ideas endpoint
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import requests

KeywordIntent = Literal[
    "informational",
    "commercial",
    "transactional",
    "navigational",
    "unknown",
]
KeywordSource = Literal["related", "suggestions", "ideas"]
KeywordMode = Literal["auto", "related", "suggestions", "ideas"]

logger = logging.getLogger(__name__)

DATAFORSEO_LABS_BASE = "https://api.dataforseo.com/v3/dataforseo_labs/google"
AUTO_SOURCES: tuple[KeywordSource, ...] = ("related", "suggestions", "ideas")
MIN_NON_SEED_FOR_AUTO = 5


def normalize_keyword(input_text: str) -> str:
    return " ".join(input_text.strip().lower().split())


def normalize_intent(raw: str | None) -> KeywordIntent:
    if not raw:
        return "unknown"
    value = raw.lower()
    if "inform" in value:
        return "informational"
    if "commerc" in value:
        return "commercial"
    if "transact" in value:
        return "transactional"
    if "navig" in value:
        return "navigational"
    return "unknown"


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _monthly_searches(keyword_info: dict[str, Any]) -> list[dict[str, int]]:
    rows = []
    for entry in keyword_info.get("monthly_searches") or []:
        if not isinstance(entry, dict):
            continue
        year = _coerce_int(entry.get("year"))
        month = _coerce_int(entry.get("month"))
        search_volume = _coerce_int(entry.get("search_volume")) or 0
        if year and month:
            rows.append(
                {
                    "year": year,
                    "month": month,
                    "searchVolume": search_volume,
                }
            )
    return rows


def _best_keyword_info(keyword_data: dict[str, Any]) -> dict[str, Any]:
    clickstream = keyword_data.get("keyword_info_normalized_with_clickstream")
    if isinstance(clickstream, dict) and clickstream.get("search_volume"):
        return clickstream
    info = keyword_data.get("keyword_info")
    return info if isinstance(info, dict) else {}


def _map_keyword_data(keyword_data: dict[str, Any]) -> dict[str, Any] | None:
    raw_keyword = keyword_data.get("keyword")
    if not isinstance(raw_keyword, str) or not raw_keyword.strip():
        return None

    keyword = normalize_keyword(raw_keyword)
    keyword_info = _best_keyword_info(keyword_data)
    plain_info = keyword_data.get("keyword_info")
    if not isinstance(plain_info, dict):
        plain_info = {}
    properties = keyword_data.get("keyword_properties")
    if not isinstance(properties, dict):
        properties = {}
    intent_info = keyword_data.get("search_intent_info")
    if not isinstance(intent_info, dict):
        intent_info = {}

    return {
        "keyword": keyword,
        "searchVolume": _coerce_int(keyword_info.get("search_volume")),
        "trend": _monthly_searches(keyword_info),
        "cpc": _coerce_float(plain_info.get("cpc")),
        "competition": _coerce_float(plain_info.get("competition")),
        "keywordDifficulty": _coerce_int(properties.get("keyword_difficulty")),
        "intent": normalize_intent(intent_info.get("main_intent")),
    }


def _extract_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return []
    result = tasks[0].get("result") if isinstance(tasks[0], dict) else None
    if not isinstance(result, list) or not result:
        return []
    items = result[0].get("items") if isinstance(result[0], dict) else None
    return items if isinstance(items, list) else []


def _map_items(items: list[dict[str, Any]], source: KeywordSource) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        keyword_data = item.get("keyword_data") if source == "related" else item
        if not isinstance(keyword_data, dict):
            continue
        row = _map_keyword_data(keyword_data)
        if not row or row["keyword"] in seen:
            continue
        seen.add(row["keyword"])
        rows.append(row)
    return rows


def _endpoint_for(source: KeywordSource) -> str:
    endpoint = {
        "related": "related_keywords",
        "suggestions": "keyword_suggestions",
        "ideas": "keyword_ideas",
    }[source]
    return f"{DATAFORSEO_LABS_BASE}/{endpoint}/live"


def _payload_for(
    source: KeywordSource,
    seed_keyword: str,
    location_code: int,
    language_code: str,
    limit: int,
    depth: int,
) -> list[dict[str, Any]]:
    common: dict[str, Any] = {
        "location_code": location_code,
        "language_code": language_code,
        "limit": limit,
        "include_clickstream_data": True,
        "include_serp_info": False,
    }
    if source == "related":
        return [{**common, "keyword": seed_keyword, "depth": depth}]
    if source == "suggestions":
        return [
            {
                **common,
                "keyword": seed_keyword,
                "include_seed_keyword": True,
                "ignore_synonyms": False,
                "exact_match": False,
            }
        ]
    return [
        {
            **common,
            "keywords": [seed_keyword],
            "ignore_synonyms": False,
            "closely_variants": False,
        }
    ]


def fetch_research_rows_by_source(
    source: KeywordSource,
    seed_keyword: str,
    dataforseo_login: str,
    dataforseo_password: str,
    location_code: int = 2840,
    language_code: str = "en",
    limit: int = 150,
    depth: int = 3,
) -> list[dict[str, Any]]:
    resp = requests.post(
        _endpoint_for(source),
        json=_payload_for(source, seed_keyword, location_code, language_code, limit, depth),
        auth=(dataforseo_login, dataforseo_password),
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"DataForSEO returned HTTP {resp.status_code}")
    data = resp.json()
    if data.get("status_code") not in (None, 20000):
        message = data.get("status_message") or "DataForSEO request failed"
        raise RuntimeError(str(message))
    return _map_items(_extract_items(data), source)


def _non_seed_count(rows: list[dict[str, Any]], seed_keyword: str) -> int:
    return sum(1 for row in rows if row.get("keyword") != seed_keyword)


def _dedupe_append(
    target: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    seen: set[str],
    limit: int,
) -> None:
    for row in rows:
        if len(target) >= limit:
            return
        keyword = row.get("keyword")
        if not isinstance(keyword, str) or keyword in seen:
            continue
        seen.add(keyword)
        target.append(row)


def research_keywords(
    keywords: list[str],
    dataforseo_login: str,
    dataforseo_password: str,
    location_code: int = 2840,
    language_code: str = "en",
    limit: int = 150,
    mode: KeywordMode = "auto",
) -> dict[str, Any]:
    unique_keywords = []
    seen_inputs = set()
    for keyword in keywords:
        normalized = normalize_keyword(keyword)
        if normalized and normalized not in seen_inputs:
            seen_inputs.add(normalized)
            unique_keywords.append(normalized)

    if not unique_keywords:
        return {"ok": False, "error": "Enter at least one keyword."}
    if mode not in ("auto", "related", "suggestions", "ideas"):
        return {"ok": False, "error": "Invalid research mode."}
    if limit not in (50, 100, 150, 300, 500):
        return {"ok": False, "error": "Limit must be 50, 100, 150, 300, or 500."}
    if not dataforseo_login or not dataforseo_password:
        return {
            "ok": False,
            "error": "DataForSEO credentials are required for keyword research.",
            "setup": "Add DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD to .env or Settings.",
        }

    seed_keyword = unique_keywords[0]
    source_attempts = []

    try:
        if mode == "auto":
            accumulated: list[dict[str, Any]] = []
            seen_rows: set[str] = set()
            last_source: KeywordSource = "related"
            used_fallback = False

            for source in AUTO_SOURCES:
                rows = fetch_research_rows_by_source(
                    source,
                    seed_keyword,
                    dataforseo_login,
                    dataforseo_password,
                    location_code,
                    language_code,
                    limit,
                )
                _dedupe_append(accumulated, rows, seen_rows, limit)
                source_attempts.append(
                    {
                        "source": source,
                        "rowCount": len(rows),
                        "nonSeedCount": _non_seed_count(rows, seed_keyword),
                    }
                )
                last_source = source
                if source != AUTO_SOURCES[0]:
                    used_fallback = True
                if _non_seed_count(accumulated, seed_keyword) >= MIN_NON_SEED_FOR_AUTO:
                    return {
                        "ok": True,
                        "seedKeyword": seed_keyword,
                        "rows": accumulated,
                        "source": source,
                        "usedFallback": used_fallback,
                        "diagnostics": {
                            "requestedMode": mode,
                            "threshold": MIN_NON_SEED_FOR_AUTO,
                            "sourceAttempts": source_attempts,
                        },
                    }

            return {
                "ok": True,
                "seedKeyword": seed_keyword,
                "rows": accumulated,
                "source": last_source,
                "usedFallback": True,
                "diagnostics": {
                    "requestedMode": mode,
                    "threshold": MIN_NON_SEED_FOR_AUTO,
                    "sourceAttempts": source_attempts,
                },
            }

        rows = fetch_research_rows_by_source(
            mode,
            seed_keyword,
            dataforseo_login,
            dataforseo_password,
            location_code,
            language_code,
            limit,
        )
        return {
            "ok": True,
            "seedKeyword": seed_keyword,
            "rows": rows,
            "source": mode,
            "usedFallback": False,
            "diagnostics": {
                "requestedMode": mode,
                "threshold": MIN_NON_SEED_FOR_AUTO,
                "sourceAttempts": [
                    {
                        "source": mode,
                        "rowCount": len(rows),
                        "nonSeedCount": _non_seed_count(rows, seed_keyword),
                    }
                ],
            },
        }
    except (requests.RequestException, OSError, ValueError, KeyError, RuntimeError) as exc:
        logger.exception("Keyword research failed for %s", seed_keyword)
        return {"ok": False, "error": str(exc)}
