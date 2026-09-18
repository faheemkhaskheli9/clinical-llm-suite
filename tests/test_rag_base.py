import pytest

from clinical_core.rag.fetchers.base import ResponseValidationError, fetch_text, get_text


class _Resp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("unexpected HTTP error in test")


class _Session:
    def __init__(self, *bodies):
        self._bodies = list(bodies)
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return _Resp(self._bodies.pop(0))


def _valid_xml(text: str) -> bool:
    return text.strip().startswith("<ok>")


def test_fetch_text_reports_cache_hit_vs_miss(tmp_path):
    cache = tmp_path / "resp.xml"
    session = _Session("<ok>fresh</ok>")

    text, from_cache = fetch_text(session, "http://x", cache_path=cache, validate=_valid_xml)
    assert (text, from_cache) == ("<ok>fresh</ok>", False)

    text, from_cache = fetch_text(session, "http://x", cache_path=cache, validate=_valid_xml)
    assert (text, from_cache) == ("<ok>fresh</ok>", True)
    assert session.calls == 1  # second call served from disk


def test_bad_http_200_body_is_not_cached_and_raises(tmp_path):
    cache = tmp_path / "resp.xml"
    session = _Session("<html>maintenance</html>")

    with pytest.raises(ResponseValidationError):
        get_text(session, "http://x", cache_path=cache, validate=_valid_xml)

    assert not cache.exists()  # poisoned body must not persist


def test_poisoned_cache_file_is_discarded_and_refetched(tmp_path):
    cache = tmp_path / "resp.xml"
    cache.write_text("<html>stale error page</html>", encoding="utf-8")
    session = _Session("<ok>recovered</ok>")

    text, from_cache = fetch_text(session, "http://x", cache_path=cache, validate=_valid_xml)

    assert (text, from_cache) == ("<ok>recovered</ok>", False)
    assert cache.read_text(encoding="utf-8") == "<ok>recovered</ok>"
    assert session.calls == 1
