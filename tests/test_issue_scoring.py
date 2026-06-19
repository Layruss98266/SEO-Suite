"""Tests for ``tools.issue_scoring`` — impact/effort prioritisation."""

from __future__ import annotations

from tools.issue_scoring import score_issues


def _mk(tool: str, status: str, message: str = "") -> dict:
    return {"tool": tool, "status": status, "message": message or f"{tool} {status}"}


def test_known_tools_sorted_by_priority() -> None:
    """SSL fail (impact 10, medium) should outrank og_tags warning (impact 5, low)."""
    audit = {
        "url": "https://example.com",
        "results": [
            _mk("og_tags", "warning"),
            _mk("ssl", "fail"),
            _mk("title", "pass"),
            _mk("meta_description", "warning"),
        ],
    }
    out = score_issues(audit)
    tools_in_order = [s["tool"] for s in out["scored_issues"]]
    # ssl/fail (priority 5.0) > meta_description/warning (3.5) > og_tags/warning (2.5)
    assert tools_in_order[0] == "ssl"
    assert tools_in_order[-1] == "og_tags"
    # Priorities are monotonically non-increasing.
    priorities = [s["priority"] for s in out["scored_issues"]]
    assert priorities == sorted(priorities, reverse=True)


def test_unknown_tool_uses_default() -> None:
    audit = {"results": [_mk("totally_made_up_tool", "fail")]}
    out = score_issues(audit)
    assert len(out["scored_issues"]) == 1
    issue = out["scored_issues"][0]
    assert issue["impact"] == 5
    assert issue["effort"] == "medium"
    # priority = 5 * 1.0 / 2 = 2.5
    assert issue["priority"] == 2.5


def test_pass_status_excluded() -> None:
    audit = {
        "results": [
            _mk("title", "pass"),
            _mk("ssl", "pass"),
            _mk("h1", "fail"),
        ],
    }
    out = score_issues(audit)
    tools = [s["tool"] for s in out["scored_issues"]]
    assert tools == ["h1"]
    assert all(s["status"] != "pass" for s in out["scored_issues"])


def test_summary_quick_wins_count() -> None:
    audit = {
        "results": [
            # quick wins: impact>=7 AND effort==low AND not pass
            _mk("title", "fail"),               # 9/low — quick win, high impact
            _mk("meta_description", "warning"), # 7/low — quick win
            _mk("robots", "fail"),              # 10/low — quick win, high impact
            # not quick wins:
            _mk("og_tags", "fail"),             # 5/low — low impact
            _mk("lcp", "fail"),                 # 9/high — not low effort
            _mk("title", "pass"),               # excluded entirely
        ],
    }
    out = score_issues(audit)
    assert out["summary"]["quick_wins_count"] == 3
    # high_impact_count = impact >= 8: title(9), robots(10), lcp(9) = 3
    assert out["summary"]["high_impact_count"] == 3


def test_original_results_left_intact() -> None:
    original_results = [
        _mk("title", "fail"),
        _mk("ssl", "warning"),
    ]
    audit = {"url": "https://example.com", "results": original_results}
    out = score_issues(audit)
    # Input dict untouched.
    assert audit["results"] is original_results
    assert "scored_issues" not in audit
    assert "summary" not in audit
    # Inner check dicts also untouched (no impact/effort/priority leakage).
    for r in original_results:
        assert "impact" not in r
        assert "effort" not in r
        assert "priority" not in r
    # Output is a separate object with preserved fields plus annotations.
    assert out["url"] == "https://example.com"
    assert len(out["results"]) == 2
    assert "scored_issues" in out
    assert "summary" in out


def test_non_dict_input_safe() -> None:
    out = score_issues([])  # type: ignore[arg-type]
    assert out["scored_issues"] == []
    assert out["summary"] == {"high_impact_count": 0, "quick_wins_count": 0}


def test_error_status_weighted() -> None:
    audit = {"results": [_mk("ssl", "error")]}
    out = score_issues(audit)
    # ssl: impact 10, effort medium(2), error weight 0.7 → 10*0.7/2 = 3.5
    assert out["scored_issues"][0]["priority"] == 3.5
