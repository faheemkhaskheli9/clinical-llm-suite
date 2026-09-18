"""Local persistence for fetched/normalized medical reference documents.

Ported from clinical-ai-assistant's src/rag/storage.py (issue #13). Raw
responses are cached under ``data/raw/<source>/`` so re-running ingestion
doesn't re-hit the source API for data it already has; normalized documents
are written as JSONL under ``data/processed/<source>.jsonl``, one
``SourceDocument`` per line. Both directories are gitignored — this is a
local cache, not a dataset the repo ships with.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from clinical_core.rag.schema import SourceDocument

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"


def raw_cache_path(source: str, name: str) -> Path:
    """Path for caching one raw response file under data/raw/<source>/<name>."""
    path = RAW_DIR / source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def processed_path(source: str) -> Path:
    """Path to the normalized JSONL output file for a given source."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    return PROCESSED_DIR / f"{source}.jsonl"


@contextmanager
def atomic_write(path: Path, encoding: str = "utf-8"):
    """Yield a file handle for a temp file that is renamed onto ``path`` on success.

    If the body raises, the temp file is removed and ``path`` is left exactly as
    it was — callers never see a half-written file. The rename is atomic because
    the temp file is created in the same directory (same filesystem).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            yield fh
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def write_documents(source: str, documents: Iterable[SourceDocument]) -> int:
    """Overwrite ``data/processed/<source>.jsonl`` with the given documents.

    Full overwrite (not append) so re-running ingestion never accumulates
    stale/duplicate records. The write is atomic: if ``documents`` (a live
    fetch generator) raises partway through, the previous file is kept intact
    rather than being replaced by a truncated one. Returns the number written.
    """
    path = processed_path(source)
    count = 0
    with atomic_write(path) as fh:
        for doc in documents:
            fh.write(doc.model_dump_json())
            fh.write("\n")
            count += 1
    return count


def read_documents(source: str) -> Iterator[SourceDocument]:
    """Read back the normalized documents previously written for a source."""
    path = processed_path(source)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield SourceDocument.model_validate_json(line)
