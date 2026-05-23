from unittest.mock import patch, MagicMock

from tools.ai_assist import draft_meta, _chat


def _resp(status=200, payload=None, headers=None):
    m = MagicMock()
    m.status_code = status
    m.headers = headers or {}
    m.json.return_value = payload or {"choices": [{"message": {"content": "ok"}}]}
    def _raise():
        import requests
        if status >= 400:
            raise requests.HTTPError(f"{status}")
    m.raise_for_status.side_effect = _raise
    return m


class TestChatRetry:
    def test_retries_on_429_then_succeeds(self):
        seq = [_resp(status=429, headers={"Retry-After": "0"}), _resp(status=200)]
        with patch("tools.ai_assist.safe_requests_post", side_effect=seq), \
             patch("tools.ai_assist.time.sleep"):
            out = _chat([{"role": "user", "content": "hi"}], "key")
        assert out == "ok"


class TestDraftMeta:
    def test_rejects_private_url(self):
        r = draft_meta("http://127.0.0.1/", "t", "d", [], "key")
        assert r["ok"] is False

    def test_missing_api_key(self):
        r = draft_meta("https://e.com/", "t", "d", [], "")
        assert r["ok"] is False
