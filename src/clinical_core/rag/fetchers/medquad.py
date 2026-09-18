"""MedQuAD fetcher.

Ported from clinical-ai-assistant's src/rag/fetchers/medquad.py (issue #13).
Downloads the MedQuAD dataset — medical Q&A pairs aggregated from
MedlinePlus/NIH/CDC/cancer.gov/GARD/etc. by Abacha & Demner-Fushman
(https://github.com/abachaa/MedQuAD) — as a GitHub archive, extracts it
locally, and normalizes each QA pair into a SourceDocument. Doubles as a
ready-made gold-answer set for retrieval/answer-quality evaluation, since
it's already question/answer shaped.
"""

from __future__ import annotations

import os
import shutil
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from pathlib import Path

import requests

from clinical_core.rag.fetchers.base import build_session, get_bytes
from clinical_core.rag.schema import DocType, SourceDocument
from clinical_core.rag.storage import RAW_DIR, raw_cache_path

ARCHIVE_URL = "https://codeload.github.com/abachaa/MedQuAD/zip/refs/heads/master"
EXTRACT_ROOT = RAW_DIR / "medquad"
EXTRACTED_DIR = EXTRACT_ROOT / "MedQuAD-master"

# Per the dataset's own readme.txt, these 3 of 12 source folders ship with
# every <Answer> stripped to comply with the MedlinePlus copyright (URLs are
# kept in case you want to crawl the answers yourself — out of scope here).
# "10_..." also sorts before "1_..." as a string, so left unfiltered these
# can silently eat an entire max_files budget on unusable records.
EXCLUDED_DIR_NAMES = {
    "10_MPlus_ADAM_QA",              # A.D.A.M. Medical Encyclopedia
    "11_MPlusDrugs_QA",              # MedlinePlus Drug information
    "12_MPlusHerbsSupplements_QA",   # MedlinePlus Herbal/supplement information
}


def _ensure_extracted(session: requests.Session) -> Path:
    """Download (once, cached) and extract the MedQuAD repo archive.

    Extraction goes to a scratch directory that is atomically renamed onto
    ``EXTRACTED_DIR`` only after it completes. So ``EXTRACTED_DIR.exists()`` is
    a reliable "fully extracted" signal — an interrupted prior run (Ctrl-C,
    crash, disk full) leaves only the scratch dir, which is discarded and
    redone rather than walked as if complete. A corrupt cached zip is deleted
    so the next run re-downloads it instead of failing forever.
    """
    if EXTRACTED_DIR.exists():
        return EXTRACTED_DIR

    zip_path = raw_cache_path("medquad", "medquad.zip")
    get_bytes(session, ARCHIVE_URL, cache_path=zip_path)

    staging = EXTRACT_ROOT / ".extract-tmp"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging)
        extracted = staging / EXTRACTED_DIR.name
        if not extracted.is_dir():
            raise RuntimeError(f"archive did not contain expected top-level dir {EXTRACTED_DIR.name!r}")
        os.replace(extracted, EXTRACTED_DIR)
    except zipfile.BadZipFile:
        zip_path.unlink(missing_ok=True)  # corrupt/truncated download — don't cache it
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return EXTRACTED_DIR


def _parse_file(path: Path) -> Iterator[SourceDocument]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return

    focus = (root.findtext("Focus") or path.stem).strip()
    original_source = root.get("source", "unknown")
    doc_url = root.get("url", "")
    doc_id = root.get("id", path.stem)

    for qa_pair in root.findall(".//QAPair"):
        question = (qa_pair.findtext("Question") or "").strip()
        answer = (qa_pair.findtext("Answer") or "").strip()
        if not question or not answer:
            continue
        pid = qa_pair.get("pid", "0")
        yield SourceDocument(
            id=f"medquad:{doc_id}:{pid}",
            doc_type=DocType.QA,
            source="medquad",
            title=f"{focus}: {question}",
            section="qa_pair",
            text=f"Q: {question}\nA: {answer}",
            url=doc_url,
            metadata={"focus": focus, "original_source": original_source},
        )


def fetch(max_files: int = 500, *, session: requests.Session | None = None) -> Iterator[SourceDocument]:
    """Download (if not cached) and normalize up to `max_files` MedQuAD XML documents.

    The full dataset is ~47k QA pairs across ~15k files; `max_files` caps a
    first "broad but shallow" pull. Raise it (or drop it) once storage/embed
    costs are accounted for.
    """
    session = session or build_session()
    root_dir = _ensure_extracted(session)
    xml_files = sorted(
        path
        for path in root_dir.rglob("*.xml")
        if path.relative_to(root_dir).parts[0] not in EXCLUDED_DIR_NAMES
    )[:max_files]
    for path in xml_files:
        yield from _parse_file(path)
