"""
Guard tests for the use-case / task registry in core.seo_audit.

The dashboard and the audit executor both rely on USE_CASES + TASKS being
internally consistent. These tests catch drift between the registry, the
scoring weights, and the executor without needing live network calls.
"""

from core.seo_audit import TASKS, USE_CASES, WEIGHTS, _SCORE_EXCLUDED, calc_seo_score


class TestRegistryConsistency:
    def test_every_usecase_has_tasks(self):
        for uc in USE_CASES:
            assert uc in TASKS, f"USE_CASES has '{uc}' with no TASKS entry"

    def test_every_task_block_maps_to_a_usecase(self):
        for uc in TASKS:
            assert uc in USE_CASES, f"TASKS has '{uc}' with no USE_CASES entry"

    def test_tasks_have_id_and_label(self):
        for uc, tasks in TASKS.items():
            for t in tasks:
                assert t.get("id"), f"{uc} has a task missing 'id'"
                assert t.get("label"), f"{uc} task '{t.get('id')}' missing 'label'"

    def test_no_duplicate_task_ids_within_a_usecase(self):
        for uc, tasks in TASKS.items():
            ids = [t["id"] for t in tasks]
            assert len(ids) == len(set(ids)), f"{uc} has duplicate task ids: {ids}"

    def test_requires_keys_are_known(self):
        # `requires` must reference a real config key the app understands.
        allowed = {None, "pagespeed_api_key", "gsc", "serpapi_key"}
        for uc, meta in USE_CASES.items():
            assert meta.get("requires") in allowed, \
                f"{uc} declares unknown requires={meta.get('requires')!r}"


class TestScoringWeights:
    def test_weighted_or_excluded_tasks_are_partitioned(self):
        # Every task id should either carry an explicit weight or be explicitly
        # excluded from scoring — nothing should silently fall through to the
        # default weight of 2 unnoticed. (Diagnostic-only tools go in _SCORE_EXCLUDED.)
        unaccounted = []
        for uc, tasks in TASKS.items():
            for t in tasks:
                tid = t["id"]
                if tid not in WEIGHTS and tid not in _SCORE_EXCLUDED:
                    unaccounted.append(f"{uc}:{tid}")
        assert not unaccounted, (
            "Task ids neither weighted nor excluded (would score at default 2): "
            + ", ".join(unaccounted)
        )

    def test_error_results_do_not_affect_score(self):
        results = [
            {"tool": "title", "status": "pass"},
            {"tool": "performance_setup", "status": "error"},
        ]
        # The error entry must be ignored: a single passing weighted check = 100.
        assert calc_seo_score(results) == 100

    def test_excluded_tools_do_not_affect_score(self):
        results = [
            {"tool": "title", "status": "pass"},
            {"tool": "top_queries", "status": "fail"},  # diagnostic, excluded
        ]
        assert calc_seo_score(results) == 100

    def test_empty_results_score_zero(self):
        assert calc_seo_score([]) == 0
