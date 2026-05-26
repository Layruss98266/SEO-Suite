"""
Groq AI Assistance Layer — Stage 3-D
Provides: audit explanation, meta tag drafting via Groq's free LLM API.

Groq is OpenAI-compatible, fast (100 tokens/s), and has a generous free tier.
API key: https://console.groq.com → API Keys
Docs:    https://console.groq.com/docs/openai

Environment variable: GROQ_API_KEY
Config key:           groq_api_key
"""

import logging
import time

from core.security import safe_requests_post, validate_public_url
from tools._common import safe_error

logger = logging.getLogger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL  = "llama-3.1-8b-instant"   # fast + free tier friendly

# Hard cap on characters sent to the LLM to stay within context limits
_MAX_AUDIT_CHARS = 8000


def _chat(messages: list[dict], api_key: str, model: str = _DEFAULT_MODEL,
          temperature: float = 0.4, max_tokens: int = 800) -> str:
    """Send a chat completion request to Groq. Retries on 429/5xx. Returns reply text."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":       model,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
    }
    # Groq's free tier rate-limits aggressively (429) and occasionally 5xxs.
    # Retry up to 3 times so a transient throttle doesn't surface as a hard
    # failure to the user mid-audit.
    last_status = None
    for attempt in range(3):
        resp = safe_requests_post(_GROQ_CHAT_URL, headers=headers, json=body, timeout=30)
        last_status = resp.status_code
        if resp.status_code in (429,) or resp.status_code >= 500:
            if attempt < 2:
                # Honour the server's Retry-After when it gives a numeric value;
                # otherwise back off exponentially (0.5s, 1s).
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if (retry_after and retry_after.replace(".", "", 1).isdigit()) else 0.5 * (2 ** attempt)
                time.sleep(delay)
                continue
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    raise RuntimeError(f"Groq API unavailable (HTTP {last_status})")


# ══════════════════════════════════════════════════════════════════════════════
# Explain Audit
# ══════════════════════════════════════════════════════════════════════════════
def explain_audit(audit_results: list[dict] | dict, api_key: str,
                  url: str = "", model: str = _DEFAULT_MODEL) -> dict:
    """
    Summarise SEO audit findings in plain English.
    audit_results: list of tool-result dicts (tool, status, message, value, details)
                   OR the full audit JSON dict (with a "results" key).
    Returns: {ok, explanation, top_actions, model}
    """
    if not api_key:
        return {"ok": False, "error": "Groq API key not configured (Settings → groq_api_key)"}

    # Normalise input
    if isinstance(audit_results, dict) and "results" in audit_results:
        results_list = audit_results["results"]
    elif isinstance(audit_results, list):
        results_list = audit_results
    else:
        results_list = [audit_results]

    # Build a compact text summary to stay inside context limits
    lines = []
    fails    = []
    warnings = []
    passes   = []
    for r in results_list:
        tool   = r.get("tool", "unknown")
        status = r.get("status", "")
        msg    = r.get("message", "")
        entry  = f"[{status.upper()}] {tool}: {msg}"
        lines.append(entry)
        if status == "fail":         fails.append(entry)
        elif status == "warning":    warnings.append(entry)
        else:                        passes.append(entry)

    summary_text = "\n".join(lines)
    if len(summary_text) > _MAX_AUDIT_CHARS:
        # Keep fails + warnings only if too long
        summary_text = "\n".join(fails + warnings)[:_MAX_AUDIT_CHARS]

    site_context = f"for {url}" if url else ""

    system_msg = (
        "You are an expert SEO consultant. "
        "Given a list of SEO audit results, explain the findings clearly to a non-technical website owner. "
        "Use plain English. Be direct and specific. "
        "Focus on what matters most and skip anything that passed."
    )
    user_msg = (
        f"Here are the SEO audit results {site_context}:\n\n"
        f"{summary_text}\n\n"
        f"Please:\n"
        f"1. Give a 2-3 sentence plain-English summary of the overall SEO health.\n"
        f"2. List the top 3-5 most important actions to fix, ordered by priority.\n"
        f"3. Keep each action to one line with a verb (e.g. 'Fix X because Y').\n"
        f"Do NOT repeat the raw audit data back to me."
    )

    try:
        reply = _chat(
            [{"role": "system", "content": system_msg},
             {"role": "user",   "content": user_msg}],
            api_key, model=model, max_tokens=700,
        )

        # Split explanation vs actions list
        lines_out = [ln.strip() for ln in reply.split("\n") if ln.strip()]
        # Heuristic: lines starting with 1. 2. 3. are action items
        import re
        action_pattern = re.compile(r"^[\d]+[\.\)]\s+")
        explanation_lines = [ln for ln in lines_out if not action_pattern.match(ln)]
        action_lines      = [re.sub(r"^[\d]+[\.\)]\s+", "", ln)
                              for ln in lines_out if action_pattern.match(ln)]

        return {
            "ok":          True,
            "explanation": " ".join(explanation_lines[:4]),
            "top_actions": action_lines[:5],
            "model":       model,
            "stats": {
                "fails":    len(fails),
                "warnings": len(warnings),
                "passes":   len(passes),
            },
        }
    except Exception as exc:
        logger.warning("explain_audit failed: %s", exc)
        return {"ok": False, "error": safe_error(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# Draft Meta Tags
# ══════════════════════════════════════════════════════════════════════════════
def draft_meta(url: str, current_title: str, current_desc: str,
               top_queries: list[str] | None, api_key: str,
               model: str = _DEFAULT_MODEL) -> dict:
    """
    Suggest improved title and meta description variants using the page's
    current meta and top GSC queries.

    Returns: {ok, variants: [{title, description, rationale}], model}
    """
    if not api_key:
        return {"ok": False, "error": "Groq API key not configured (Settings → groq_api_key)"}

    try:
        url = validate_public_url(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    queries_text = ""
    if top_queries:
        queries_text = "Top search queries for this page:\n" + "\n".join(f"  - {q}" for q in top_queries[:10])

    system_msg = (
        "You are an expert SEO copywriter. "
        "Write compelling, click-worthy title tags and meta descriptions that:\n"
        "- Include the primary keyword naturally\n"
        "- Title: 50-60 characters, no brand suffix needed\n"
        "- Description: 140-155 characters, contains a call to action\n"
        "- Sound human, not keyword-stuffed\n"
        "- Are factually consistent with the existing content"
    )
    user_msg = (
        f"URL: {url}\n"
        f"Current title: {current_title or '(none)'}\n"
        f"Current description: {current_desc or '(none)'}\n"
        f"{queries_text}\n\n"
        f"Write exactly 3 alternative title + description variants.\n"
        f"Format each as:\n"
        f"VARIANT N\n"
        f"Title: ...\n"
        f"Description: ...\n"
        f"Rationale: one sentence why this is better\n"
    )

    try:
        reply = _chat(
            [{"role": "system", "content": system_msg},
             {"role": "user",   "content": user_msg}],
            api_key, model=model, temperature=0.7, max_tokens=600,
        )

        # Parse VARIANT blocks
        import re
        blocks = re.split(r"VARIANT\s+\d+", reply, flags=re.IGNORECASE)
        variants = []
        for block in blocks:
            if not block.strip():
                continue
            title_m = re.search(r"Title:\s*(.+)", block, re.IGNORECASE)
            desc_m  = re.search(r"Description:\s*(.+)", block, re.IGNORECASE)
            rat_m   = re.search(r"Rationale:\s*(.+)", block, re.IGNORECASE)
            if title_m and desc_m:
                variants.append({
                    "title":       title_m.group(1).strip(),
                    "description": desc_m.group(1).strip(),
                    "rationale":   rat_m.group(1).strip() if rat_m else "",
                })

        if not variants:
            # Fallback: return raw reply
            return {"ok": True, "variants": [{"title": "", "description": reply, "rationale": ""}],
                    "model": model}

        return {"ok": True, "variants": variants[:3], "model": model}
    except Exception as exc:
        logger.warning("draft_meta failed for %s: %s", url, exc)
        return {"ok": False, "error": safe_error(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# Explain Site Audit
# ══════════════════════════════════════════════════════════════════════════════
def explain_site_audit(audits: list[dict], api_key: str, model: str = _DEFAULT_MODEL) -> dict:
    """
    Generate a plain-English site audit executive summary using Groq.
    audits: list of audit dictionaries, each containing: url, score, results, counts, etc.
    """
    if not api_key:
        return {"ok": False, "error": "Groq API key not configured"}

    # Aggregate core findings
    total_urls = len(audits)
    avg_score = round(sum(a["score"] for a in audits) / total_urls) if total_urls else 0

    fails = []
    warnings = []
    for a in audits:
        url = a.get("url", "")
        # Parse results list
        results_list = a.get("results", []) or []
        for r in results_list:
            status = r.get("status", "")
            tool = r.get("tool", "")
            msg = r.get("message", "")
            entry = f"- URL: {url} | Issue: {tool} | Details: {msg}"
            if status == "fail":
                fails.append(entry)
            elif status == "warning":
                warnings.append(entry)

    # Limit summary data to stay within token/context caps
    summary_text = ""
    if fails:
        summary_text += "FAILED CHECKS:\n" + "\n".join(fails[:15]) + "\n\n"
    if warnings:
        summary_text += "WARNING CHECKS:\n" + "\n".join(warnings[:10]) + "\n\n"

    system_msg = (
        "You are an elite enterprise SEO Director. "
        "You are writing a concise executive briefing and a prioritized 4-step remediation roadmap "
        "for a website owner after a comprehensive multi-page technical SEO audit. "
        "Do NOT repeat raw counts or code formats back; write for human stakeholders."
    )
    user_msg = (
        f"Here are the aggregated technical SEO audit results across {total_urls} pages.\n"
        f"Average SEO Health Score: {avg_score}/100\n\n"
        f"{summary_text}\n"
        f"Please write:\n"
        f"1. A high-level Executive Summary (2-3 sentences max) outlining the most prominent site-wide technical threats in plain English.\n"
        f"2. A prioritized 4-step Remediation Roadmap (one short, action-oriented sentence per step starting with a verb).\n"
        f"Format EXACTLY as:\n"
        f"EXECUTIVE SUMMARY: ...\n"
        f"ROADMAP:\n"
        f"1. ...\n"
        f"2. ...\n"
        f"3. ...\n"
        f"4. ...\n"
    )

    try:
        reply = _chat(
            [{"role": "system", "content": system_msg},
             {"role": "user",   "content": user_msg}],
            api_key, model=model, max_tokens=600, temperature=0.3
        )

        # Parse reply
        import re
        summary_m = re.search(r"EXECUTIVE SUMMARY:\s*(.*?)(?=ROADMAP:|$)", reply, re.DOTALL | re.IGNORECASE)
        roadmap_m = re.search(r"ROADMAP:\s*(.*)", reply, re.DOTALL | re.IGNORECASE)

        summary = summary_m.group(1).strip() if summary_m else "Technical audit complete. See details below."
        roadmap_raw = roadmap_m.group(1).strip() if roadmap_m else ""
        roadmap = [re.sub(r"^[\d]+[\.\)]\s*", "", line).strip() for line in roadmap_raw.splitlines() if line.strip()][:4]

        # Pad roadmap if needed
        while len(roadmap) < 4:
            roadmap.append("Review remaining page-level audits in detail.")

        return {
            "ok": True,
            "summary": summary,
            "roadmap": roadmap[:4],
            "model": model
        }
    except Exception as e:
        logger.warning("explain_site_audit failed: %s", e)
        return {"ok": False, "error": safe_error(e)}

