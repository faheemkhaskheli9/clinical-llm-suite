"""MedlinePlus Health Topics fetcher.

Ported from clinical-ai-assistant's src/rag/fetchers/medlineplus.py (issue
#13). Queries the public wsearch API (https://wsearch.nlm.nih.gov/ws/query,
db=healthTopics) for a curated seed list of common conditions and normalizes
each hit's full summary into a SourceDocument. Public domain (US National
Library of Medicine) — no API key required.

MedlinePlus has ~1000 health topics total; this seed list is a "broad but
shallow" starting slice, not the full catalog. Extend DEFAULT_SEED_TERMS (or
pass your own via configs/rag_ingest.yaml) to widen coverage.
"""

from __future__ import annotations

import html
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator

import requests

from clinical_core.rag.fetchers.base import build_session, fetch_text, polite_delay
from clinical_core.rag.schema import DocType, SourceDocument
from clinical_core.rag.storage import raw_cache_path

BASE_URL = "https://wsearch.nlm.nih.gov/ws/query"

DEFAULT_SEED_TERMS = [
    "diabetes", "hypertension", "asthma", "influenza", "covid-19",
    "depression", "anxiety", "migraine", "stroke", "heart disease",
    "obesity", "arthritis", "osteoporosis", "chronic kidney disease",
    "copd", "pneumonia", "tuberculosis", "hepatitis", "hiv aids",
    "anemia", "epilepsy", "alzheimer disease", "parkinson disease",
    "thyroid disease", "psoriasis", "eczema", "allergies", "gerd",
    "irritable bowel syndrome", "gallstones", "kidney stones",
    "urinary tract infection", "sepsis", "anaphylaxis", "shingles",
    "measles", "malaria", "lyme disease", "sickle cell disease",
    "cystic fibrosis", "multiple sclerosis", "lupus", "gout",
    "high cholesterol", "atrial fibrillation", "heart failure",
    "peripheral artery disease", "deep vein thrombosis",
    "postpartum depression", "adhd",
]  # fmt: skip

# Only match real HTML/XML tags: '<' followed by an optional '/' and then a
# letter (tag name). This deliberately does NOT match clinical threshold
# notation such as "<60 mL/min" or "<120/80 mmHg", where '<' is an operator.
_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


def _clean(raw: str) -> str:
    """Strip MedlinePlus's <span class="qt0"> highlight markup and decode entities."""
    return html.unescape(_TAG_RE.sub("", raw)).strip()


def _is_valid_wsearch_xml(text: str) -> bool:
    """True if ``text`` parses as XML and looks like a wsearch result envelope.

    Guards against wsearch returning HTTP 200 with an HTML maintenance page or
    a truncated body — those must not be parsed or cached.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return False
    return root.tag in {"nlmSearchResult", "result"}


def _parse_response(xml_text: str, term: str) -> Iterator[SourceDocument]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"[medlineplus] skipping {term!r}: malformed XML response ({exc})", file=sys.stderr)
        return
    for document in root.findall(".//document"):
        url = document.get("url", "")
        fields: dict[str, str] = {}
        for content in document.findall("content"):
            name = content.get("name")
            if name and name not in fields:  # first value wins; altTitle repeats
                fields[name] = "".join(content.itertext())

        title = _clean(fields.get("title", term))
        summary = _clean(fields.get("FullSummary", ""))
        if not summary:
            continue

        slug = url.rsplit("/", 1)[-1].removesuffix(".html") if url else ""
        doc_id = slug or title.lower().replace(" ", "-")
        yield SourceDocument(
            id=f"medlineplus:{doc_id}",
            doc_type=DocType.DISEASE,
            source="medlineplus",
            title=title,
            section="overview",
            text=summary,
            url=url,
            metadata={"query_term": term},
        )


def fetch(
    seed_terms: list[str] | None = None,
    retmax: int = 1,
    *,
    session: requests.Session | None = None,
) -> Iterator[SourceDocument]:
    """Fetch and normalize the top MedlinePlus health topic per seed term.

    One wsearch call per term (results are cached to data/raw/medlineplus/,
    so re-running is free). Duplicate topics matched by more than one term
    are yielded once.
    """
    terms = seed_terms or DEFAULT_SEED_TERMS
    session = session or build_session()
    seen_ids: set[str] = set()

    for term in terms:
        cache_path = raw_cache_path("medlineplus", f"{term.replace(' ', '_')}.xml")
        xml_text, from_cache = fetch_text(
            session,
            BASE_URL,
            params={"db": "healthTopics", "term": term, "retmax": retmax},
            cache_path=cache_path,
            validate=_is_valid_wsearch_xml,
        )
        for doc in _parse_response(xml_text, term):
            if doc.id not in seen_ids:
                seen_ids.add(doc.id)
                yield doc
        if not from_cache:
            polite_delay()  # only pause when we actually hit the network
