from unittest.mock import MagicMock

from tools.keyword_research import (
    fetch_research_rows_by_source,
    normalize_intent,
    normalize_keyword,
    research_keywords,
)


class TestKeywordResearchHelpers:
    def test_normalize_keyword_collapses_spaces_and_case(self):
        assert normalize_keyword("  SEO   Audit Tool ") == "seo audit tool"

    def test_normalize_intent_maps_dataforseo_values(self):
        assert normalize_intent("Informational") == "informational"
        assert normalize_intent("commercial investigation") == "commercial"
        assert normalize_intent(None) == "unknown"


class TestDataforseoMapping:
    def test_fetch_suggestions_maps_keyword_metrics(self, monkeypatch):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "status_code": 20000,
            "tasks": [
                {
                    "result": [
                        {
                            "items": [
                                {
                                    "keyword": "SEO Tools",
                                    "keyword_info": {
                                        "search_volume": 1200,
                                        "cpc": 1.25,
                                        "competition": 0.42,
                                        "monthly_searches": [
                                            {
                                                "year": 2026,
                                                "month": 4,
                                                "search_volume": 1000,
                                            }
                                        ],
                                    },
                                    "keyword_properties": {"keyword_difficulty": 37},
                                    "search_intent_info": {"main_intent": "informational"},
                                }
                            ]
                        }
                    ]
                }
            ],
        }
        monkeypatch.setattr(
            "tools.keyword_research.requests.post",
            MagicMock(return_value=response),
        )

        rows = fetch_research_rows_by_source(
            "suggestions",
            "seo",
            "login",
            "password",
            limit=50,
        )

        assert rows == [
            {
                "keyword": "seo tools",
                "searchVolume": 1200,
                "trend": [{"year": 2026, "month": 4, "searchVolume": 1000}],
                "cpc": 1.25,
                "competition": 0.42,
                "keywordDifficulty": 37,
                "intent": "informational",
            }
        ]

    def test_fetch_related_reads_nested_keyword_data(self, monkeypatch):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "status_code": 20000,
            "tasks": [
                {
                    "result": [
                        {
                            "items": [
                                {
                                    "keyword_data": {
                                        "keyword": "Technical SEO",
                                        "keyword_info": {"search_volume": 500},
                                        "keyword_properties": {"keyword_difficulty": 21},
                                    }
                                }
                            ]
                        }
                    ]
                }
            ],
        }
        monkeypatch.setattr(
            "tools.keyword_research.requests.post",
            MagicMock(return_value=response),
        )

        rows = fetch_research_rows_by_source(
            "related",
            "seo",
            "login",
            "password",
            limit=50,
        )

        assert rows[0]["keyword"] == "technical seo"
        assert rows[0]["searchVolume"] == 500
        assert rows[0]["keywordDifficulty"] == 21


class TestResearchKeywords:
    def test_requires_dataforseo_credentials(self):
        result = research_keywords(["seo"], "", "")

        assert result["ok"] is False
        assert "DataForSEO" in result["error"]

    def test_auto_falls_back_until_enough_non_seed_rows(self, monkeypatch):
        calls = []

        def fake_fetch(source, *args, **kwargs):
            calls.append(source)
            if source == "related":
                return [{"keyword": "seo", "searchVolume": 10}]
            return [
                {"keyword": "seo tools", "searchVolume": 100},
                {"keyword": "seo audit", "searchVolume": 90},
                {"keyword": "technical seo", "searchVolume": 80},
                {"keyword": "on page seo", "searchVolume": 70},
                {"keyword": "seo checklist", "searchVolume": 60},
            ]

        monkeypatch.setattr(
            "tools.keyword_research.fetch_research_rows_by_source",
            fake_fetch,
        )

        result = research_keywords(["seo"], "login", "password", limit=50)

        assert result["ok"] is True
        assert result["source"] == "suggestions"
        assert result["usedFallback"] is True
        assert calls == ["related", "suggestions"]
