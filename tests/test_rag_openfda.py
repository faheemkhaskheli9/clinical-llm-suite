import pytest
import requests

from clinical_core.rag.fetchers import openfda
from clinical_core.rag.fetchers.openfda import _parse_record, _record_id, fetch

SAMPLE_RECORD = {
    "id": "abc123",
    "set_id": "set-abc123",
    "openfda": {"brand_name": ["Examplitol"], "generic_name": ["exampline"]},
    "indications_and_usage": ["Examplitol is indicated for the treatment of examplitis."],
    "dosage_and_administration": ["Take one tablet daily."],
    "warnings": ["May cause drowsiness."],
    # contraindications / drug_interactions intentionally omitted
}


def test_parse_record_yields_one_document_per_present_section():
    docs = list(_parse_record(SAMPLE_RECORD))

    sections = {doc.section for doc in docs}
    assert sections == {"indications", "dosage", "warnings"}
    assert all(doc.doc_type == "medication" for doc in docs)
    assert all(doc.title == "Examplitol" for doc in docs)
    assert all(doc.url == "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=set-abc123" for doc in docs)


def test_parse_record_ids_are_unique_per_section():
    docs = list(_parse_record(SAMPLE_RECORD))
    ids = [doc.id for doc in docs]
    assert len(ids) == len(set(ids))


def test_parse_record_falls_back_to_generic_name_when_no_brand_name():
    record = {**SAMPLE_RECORD, "openfda": {"generic_name": ["exampline"]}}
    docs = list(_parse_record(record))
    assert all(doc.title == "exampline" for doc in docs)


def test_parse_record_skips_record_with_no_known_sections():
    docs = list(_parse_record({"id": "x", "openfda": {"brand_name": ["X"]}}))
    assert docs == []


def test_record_id_does_not_collide_for_two_distinct_unnamed_records():
    a = {"warnings": ["Warning A"]}
    b = {"warnings": ["Warning B"]}
    assert _record_id(a) != _record_id(b)
    # ...and it does not silently degrade to a slug of "Unknown drug".
    assert "unknown" not in _record_id(a).lower()


def test_record_id_prefers_explicit_id_then_set_id():
    assert _record_id({"id": "abc"}) == "abc"
    assert _record_id({"set_id": "set-abc"}) == "set-abc"


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code}")
            err.response = self
            raise err

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return self._responses.pop(0)


def test_fetch_stops_cleanly_on_404_past_end_of_result_set(monkeypatch):
    monkeypatch.setattr(openfda, "polite_delay", lambda *a, **k: None)
    page = {"results": [{"id": f"r{i}", "warnings": ["w"]} for i in range(100)]}
    session = _FakeSession([_FakeResponse(page), _FakeResponse({"error": {"code": "NOT_FOUND"}}, 404)])

    docs = list(fetch(limit=500, page_size=100, session=session))

    assert len(docs) == 100  # one page, then a graceful stop rather than a crash
    assert session.calls == 2


def test_fetch_reraises_non_404_http_errors(monkeypatch):
    monkeypatch.setattr(openfda, "polite_delay", lambda *a, **k: None)
    session = _FakeSession([_FakeResponse({"error": "boom"}, 500)])
    with pytest.raises(requests.HTTPError):
        list(fetch(limit=100, page_size=100, session=session))
