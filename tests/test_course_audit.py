"""Tests for tools.course_audit — pure-HTML, no network."""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from tools.course_audit import (
    _score,
    audit_course_page,
    check_cta,
    check_faq,
    check_instructor,
    check_mobile_friendly,
    check_outcomes,
    check_overview,
    check_pricing,
    check_schedule,
    check_schema,
    check_syllabus,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ── A "fully optimised" course page ──────────────────────────────────────────
FULL_PAGE = """<!doctype html>
<html><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Advanced Python — 8-week cohort</title>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Course",
    "name": "Advanced Python",
    "description": "A deep-dive course into modern Python for working engineers.",
    "provider": {"@type": "Organization", "name": "Acme Academy"}
  }
  </script>
</head><body>
  <h1>Advanced Python — 8-week cohort</h1>
  <p>This intensive program gets working engineers fluent in modern Python idioms,
     async, typing and packaging. Built for teams shipping production code.</p>

  <h2>What you'll learn</h2>
  <ul><li>Async patterns</li><li>Type-driven design</li></ul>

  <h2>Curriculum</h2>
  <ol><li>Week 1 — Foundations</li><li>Week 2 — Concurrency</li></ol>

  <h2>Your instructor</h2>
  <p>Taught by Jane Doe, senior engineer at BigCo.</p>

  <h2>Schedule</h2>
  <p>Duration: 8 weeks. Live sessions on Tuesdays 7:00pm. Next cohort starts March 4.</p>

  <h2>Pricing</h2>
  <div class="price"><span itemprop="price" content="499">$499</span></div>

  <h2>FAQ</h2>
  <p>Frequently asked questions about enrollment, refunds, and certificates.</p>

  <a href="/enroll" class="cta">Enroll now</a>
</body></html>
"""

# ── Bare-bones page — should fail every section-based check ──────────────────
BARE_PAGE = "<html><head><title>x</title></head><body><div>hello</div></body></html>"


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────────────

class TestOverview:
    def test_pass(self):
        html = "<html><body><h1>Course</h1><p>" + "x" * 50 + "</p></body></html>"
        assert check_overview(_soup(html))["status"] == "pass"

    def test_fail_when_both_missing(self):
        assert check_overview(_soup("<html><body></body></html>"))["status"] == "fail"

    def test_warning_when_only_h1(self):
        assert check_overview(_soup("<h1>Course</h1>"))["status"] == "warning"


class TestOutcomes:
    def test_pass_on_heading(self):
        assert check_outcomes(_soup("<h2>What you'll learn</h2>"))["status"] == "pass"

    def test_pass_objectives(self):
        assert check_outcomes(_soup("<h3>Course Objectives</h3>"))["status"] == "pass"

    def test_fail(self):
        assert check_outcomes(_soup("<h2>About</h2>"))["status"] == "fail"


class TestSyllabus:
    def test_pass_curriculum(self):
        assert check_syllabus(_soup("<h2>Curriculum</h2>"))["status"] == "pass"

    def test_pass_modules(self):
        assert check_syllabus(_soup("<h3>Course Modules</h3>"))["status"] == "pass"

    def test_fail(self):
        assert check_syllabus(_soup("<h2>About</h2>"))["status"] == "fail"


class TestInstructor:
    def test_pass_heading(self):
        assert check_instructor(_soup("<h2>Your instructor</h2>"))["status"] == "pass"

    def test_pass_rel_author(self):
        assert check_instructor(_soup('<a rel="author" href="/jane">Jane</a>'))["status"] == "pass"

    def test_fail(self):
        assert check_instructor(_soup("<h2>About</h2>"))["status"] == "fail"


class TestSchedule:
    def test_pass_duration(self):
        assert check_schedule(_soup("<p>Duration: 8 weeks</p>"))["status"] == "pass"

    def test_pass_start_date(self):
        assert check_schedule(_soup("<p>Next cohort starts soon.</p>"))["status"] == "pass"

    def test_fail(self):
        assert check_schedule(_soup("<p>Some text.</p>"))["status"] == "fail"


class TestPricing:
    def test_pass_itemprop(self):
        assert check_pricing(_soup('<span itemprop="price" content="99">$99</span>'))["status"] == "pass"

    def test_pass_currency(self):
        assert check_pricing(_soup("<p>Cost: $199 today.</p>"))["status"] == "pass"

    def test_pass_free(self):
        assert check_pricing(_soup("<p>This is a free course.</p>"))["status"] == "pass"

    def test_fail(self):
        assert check_pricing(_soup("<p>Sign up today.</p>"))["status"] == "fail"


class TestFAQ:
    def test_pass(self):
        assert check_faq(_soup("<h2>FAQ</h2>"))["status"] == "pass"

    def test_pass_long(self):
        assert check_faq(_soup("<h3>Frequently Asked Questions</h3>"))["status"] == "pass"

    def test_fail(self):
        assert check_faq(_soup("<h2>About</h2>"))["status"] == "fail"


class TestCTA:
    def test_pass_button(self):
        assert check_cta(_soup("<button>Enroll Now</button>"))["status"] == "pass"

    def test_pass_link(self):
        assert check_cta(_soup('<a href="/buy">Buy now</a>'))["status"] == "pass"

    def test_fail(self):
        assert check_cta(_soup('<a href="/about">Learn more</a>'))["status"] == "fail"


class TestSchema:
    def test_pass(self):
        block = {"@context": "https://schema.org", "@type": "Course",
                 "name": "X", "description": "Y", "provider": {"@type": "Organization", "name": "Z"}}
        html = f'<script type="application/ld+json">{json.dumps(block)}</script>'
        assert check_schema(_soup(html))["status"] == "pass"

    def test_warning_missing_fields(self):
        block = {"@type": "Course", "name": "X"}
        html = f'<script type="application/ld+json">{json.dumps(block)}</script>'
        assert check_schema(_soup(html))["status"] == "warning"

    def test_fail_no_schema(self):
        assert check_schema(_soup("<html></html>"))["status"] == "fail"

    def test_pass_in_graph(self):
        block = {"@graph": [{"@type": "Course", "name": "X",
                              "description": "Y", "provider": "Z"}]}
        html = f'<script type="application/ld+json">{json.dumps(block)}</script>'
        assert check_schema(_soup(html))["status"] == "pass"


class TestMobile:
    def test_pass(self):
        assert check_mobile_friendly(_soup(
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
        ))["status"] == "pass"

    def test_warning_no_width(self):
        assert check_mobile_friendly(_soup(
            '<meta name="viewport" content="initial-scale=1">'
        ))["status"] == "warning"

    def test_fail(self):
        assert check_mobile_friendly(_soup("<html></html>"))["status"] == "fail"


# ─────────────────────────────────────────────────────────────────────────────
# Score helper
# ─────────────────────────────────────────────────────────────────────────────

class TestScore:
    def test_all_pass_is_100(self):
        results = [{"status": "pass"}] * 10
        assert _score(results) == 100

    def test_all_fail_is_zero(self):
        assert _score([{"status": "fail"}] * 10) == 0

    def test_warning_is_half(self):
        assert _score([{"status": "warning"}] * 10) == 50

    def test_empty(self):
        assert _score([]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Full-page integration (offline — patches fetch_html)
# ─────────────────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, html: str, url: str = "https://example.com/course", status: int = 200):
        self.text = html
        self.url = url
        self.status_code = status


def test_full_page_scores_high(monkeypatch):
    monkeypatch.setattr("tools.course_audit.validate_public_url", lambda u: u)
    monkeypatch.setattr("tools.course_audit.fetch_html",
                        lambda url, **kw: _FakeResp(FULL_PAGE, url=url))
    out = audit_course_page("https://example.com/course")
    assert out["ok"] is True
    assert out["score"] >= 90, f"Expected >=90, got {out['score']}: {out}"
    assert out["passes"] >= 9


def test_bare_page_fails_section_checks(monkeypatch):
    monkeypatch.setattr("tools.course_audit.validate_public_url", lambda u: u)
    monkeypatch.setattr("tools.course_audit.fetch_html",
                        lambda url, **kw: _FakeResp(BARE_PAGE, url=url))
    out = audit_course_page("https://example.com/bare")
    assert out["ok"] is True
    # All eight section-based checks plus schema + mobile should fail
    fail_tools = {r["tool"] for r in out["results"] if r["status"] == "fail"}
    expected_failures = {
        "course_overview", "course_outcomes", "course_syllabus",
        "course_instructor", "course_schedule", "course_pricing",
        "course_faq", "course_cta", "course_schema", "mobile_friendly",
    }
    assert expected_failures.issubset(fail_tools), \
        f"Missing failures: {expected_failures - fail_tools}"
    assert out["score"] == 0


def test_fetch_error_returns_ok_false(monkeypatch):
    def _boom(url, **kw):
        from tools._common import ToolFetchError
        raise ToolFetchError("nope")
    monkeypatch.setattr("tools.course_audit.validate_public_url", lambda u: u)
    monkeypatch.setattr("tools.course_audit.fetch_html", _boom)
    out = audit_course_page("https://example.com/x")
    assert out["ok"] is False
    assert "error" in out


def test_invalid_url(monkeypatch):
    def _reject(u):
        raise ValueError("private host")
    monkeypatch.setattr("tools.course_audit.validate_public_url", _reject)
    out = audit_course_page("http://localhost/")
    assert out["ok"] is False
    assert "private host" in out["error"]
