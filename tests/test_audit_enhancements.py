import pytest
from core.seo_audit import compare_audits, find_previous_audit
from tools.phase1 import sitemap_validate

def test_compare_audits_regression_and_improvement():
    prev_audits = [
        {
            "url": "https://example.com/page1",
            "score": 85,
            "results": [
                {"tool": "title_tag", "status": "pass", "message": "Good title"},
                {"tool": "meta_description", "status": "fail", "message": "Missing meta description"}
            ]
        },
        {
            "url": "https://example.com/page2",
            "score": 90,
            "results": [
                {"tool": "ssl_certificate", "status": "pass", "message": "Secure"}
            ]
        }
    ]
    
    current_audits = [
        {
            "url": "https://example.com/page1",
            "score": 90, # Improved
            "results": [
                {"tool": "title_tag", "status": "pass", "message": "Good title"},
                {"tool": "meta_description", "status": "pass", "message": "Good meta description"} # Resolved!
            ]
        },
        {
            "url": "https://example.com/page2",
            "score": 75, # Regressed
            "results": [
                {"tool": "ssl_certificate", "status": "fail", "message": "Expired"} # New Issue!
            ]
        }
    ]
    
    res = compare_audits(current_audits, prev_audits)
    
    assert len(res["improved_urls"]) == 1
    assert res["improved_urls"][0]["url"] == "https://example.com/page1"
    assert res["improved_urls"][0]["delta"] == 5
    
    assert len(res["regressed_urls"]) == 1
    assert res["regressed_urls"][0]["url"] == "https://example.com/page2"
    assert res["regressed_urls"][0]["delta"] == -15
    
    assert len(res["resolved_issues"]) == 1
    assert res["resolved_issues"][0]["tool"] == "meta_description"
    assert res["resolved_issues"][0]["url"] == "https://example.com/page1"
    
    assert len(res["new_issues"]) == 1
    assert res["new_issues"][0]["tool"] == "ssl_certificate"
    assert res["new_issues"][0]["url"] == "https://example.com/page2"

def test_sitemap_validate_ssrf_blocking():
    # Private / localhost URLs must be blocked immediately
    res = sitemap_validate("http://127.0.0.1/sitemap.xml")
    assert res["status"] == "error"
    assert "SSRF guard blocked sitemap URL" in res["message"]
