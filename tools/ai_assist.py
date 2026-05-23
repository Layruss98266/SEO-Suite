"""
Groq AI Assistance Layer — Stage 3-D
Provides: audit explanation, meta tag drafting via Groq's free LLM API.

Groq is OpenAI-compatible, fast (100 tokens/s), and has a generous free tier.
API key: https://console.groq.com → API Keys
Docs:    https://console.groq.com/docs/openai

Environment variable: GROQ_API_KEY
Config key:           groq_api_key
"""

import time

from core.security import safe_requests_post, validate_public_url
from tools._common import safe_error

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
    last_status = None
    for attempt in range(3):
        resp = safe_requests_post(_GROQ_CHAT_URL, headers=headers, json=body, timeout=30)
        last_status = resp.status_code
        if resp.status_code in (429,) or resp.status_code >= 500:
            if attempt < 2:
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
        lines_out = [l.strip() for l in reply.split("\n") if l.strip()]
        # Heuristic: lines starting with 1. 2. 3. are action items
        import re
        action_pattern = re.compile(r"^[\d]+[\.\)]\s+")
        explanation_lines = [l for l in lines_out if not action_pattern.match(l)]
        action_lines      = [re.sub(r"^[\d]+[\.\)]\s+", "", l)
                              for l in lines_out if action_pattern.match(l)]

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
        return {"ok": False, "error": safe_error(exc)}
