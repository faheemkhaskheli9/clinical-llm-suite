"""openFDA Drug Label fetcher.

Ported from clinical-ai-assistant's src/rag/fetchers/openfda.py (issue #13).
Paginates https://api.fda.gov/drug/label.json and normalizes each label's
free-text sections (indications, dosage, contraindications, warnings, drug
interactions) into one SourceDocument per section. Public domain (US FDA) —
no API key required, though setting OPENFDA_API_KEY raises the rate limit
(240 req/min vs 40 req/min unauthenticated).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator

import requests

from clinical_core.rag.fetchers.base import build_session, get_json, polite_delay
from clinical_core.rag.schema import DocType, SourceDocument

BASE_URL = "https://api.fda.gov/drug/label.json"

# record field -> our section label
SECTION_FIELDS = {
    "indications_and_usage": "indications",
    "dosage_and_administration": "dosage",
    "contraindications": "contraindications",
    "warnings": "warnings",
    "drug_interactions": "interactions",
}


def _drug_name(record: dict) -> str:
    openfda = record.get("openfda", {})
    for key in ("brand_name", "generic_name", "substance_name"):
        values = openfda.get(key)
        if values:
            return values[0]
    return "Unknown drug"


def _record_url(record: dict) -> str:
    set_id = record.get("set_id") or record.get("id", "")
    if not set_id:
        return ""
    return f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}"


def _record_id(record: dict) -> str:
    """A stable id for a label record.

    Prefer openFDA's own ``id`` / ``set_id``. Only if both are missing fall
    back to a content hash — NOT to a slug of the drug name, since multiple
    unnamed records would all collapse to the same "unknown-drug" id and
    silently overwrite each other once loaded into the vector store.
    """
    explicit = record.get("id") or record.get("set_id")
    if explicit:
        return str(explicit)
    digest = hashlib.sha1(json.dumps(record, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return f"sha1-{digest[:16]}"


def _parse_record(record: dict) -> Iterator[SourceDocument]:
    name = _drug_name(record)
    url = _record_url(record)
    record_id = _record_id(record)

    for field, section in SECTION_FIELDS.items():
        values = record.get(field)
        if not values:
            continue
        text = " ".join(values).strip()
        if not text:
            continue
        yield SourceDocument(
            id=f"openfda:{record_id}:{section}",
            doc_type=DocType.MEDICATION,
            source="openfda",
            title=name,
            section=section,
            text=text,
            url=url,
            metadata={"openfda_id": record_id},
        )


def fetch(
    limit: int = 200,
    page_size: int = 100,
    *,
    session: requests.Session | None = None,
) -> Iterator[SourceDocument]:
    """Fetch and normalize up to `limit` drug label records (newest first).

    Not cached to disk raw — paginated listings churn as new labels are
    added, so each run re-queries; the normalized JSONL output is what gets
    reused downstream.
    """
    session = session or build_session()
    api_key = os.environ.get("OPENFDA_API_KEY")
    fetched = 0
    skip = 0

    while fetched < limit:
        page_limit = min(page_size, limit - fetched)
        params: dict[str, str | int] = {"limit": page_limit, "skip": skip}
        if api_key:
            params["api_key"] = api_key

        try:
            payload = get_json(session, BASE_URL, params=params)
        except requests.HTTPError as exc:
            # openFDA signals "no more records" with HTTP 404 (NOT_FOUND),
            # not an empty results list, once `skip` passes the last match.
            if exc.response is not None and exc.response.status_code == 404:
                break
            raise
        results = payload.get("results", [])
        if not results:
            break

        for record in results:
            yield from _parse_record(record)

        fetched += len(results)
        skip += len(results)
        if len(results) < page_limit:
            break
        polite_delay()
