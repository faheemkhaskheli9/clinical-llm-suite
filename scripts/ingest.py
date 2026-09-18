"""CLI: fetch public medical reference data online, then chunk/embed/upsert
it into the local vector store.

Usage:
    python scripts/ingest.py
    python scripts/ingest.py --sources medlineplus,openfda
    python scripts/ingest.py --config configs/rag_ingest.yaml

Raw responses are cached under data/raw/, normalized documents as JSONL
under data/processed/<source>.jsonl, and chunked+embedded records in
data/processed/vector_store.json (all gitignored — local cache, not tracked
data). Re-running is idempotent: MedlinePlus/MedQuAD raw responses are
cached to disk and skipped on a second run; openFDA is re-queried since its
result set changes over time; vector store upserts never duplicate a chunk
that was already ingested.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))  # allow running as `python scripts/ingest.py`

from clinical_core.rag.embeddings import HashingEmbedder  # noqa: E402
from clinical_core.rag.ingest import FETCHERS, run  # noqa: E402
from clinical_core.rag.vector_store import JSONVectorStore  # noqa: E402

DEFAULT_CONFIG = REPO_ROOT / "configs" / "rag_ingest.yaml"
DEFAULT_STORE_PATH = REPO_ROOT / "data" / "processed" / "vector_store.json"


def load_config(path: Path, *, required: bool) -> dict:
    """Load a per-source YAML config.

    ``required`` is True when the user passed ``--config`` explicitly: a
    missing/typo'd path is then a hard error rather than a silent fall-through
    to built-in defaults (which would run with the wrong limits and no
    warning). The built-in default path is allowed to be absent.
    """
    if not path.exists():
        if required:
            raise SystemExit(f"--config: no such file: {path}")
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--sources",
        default=",".join(FETCHERS),
        help=f"Comma-separated source names to ingest (default: all — {', '.join(FETCHERS)})",
    )
    parser.add_argument(
        "--config",
        default=None,
        type=Path,
        help=f"YAML file of per-source keyword arguments (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--store",
        default=DEFAULT_STORE_PATH,
        type=Path,
        help=f"Vector store JSON path (default: {DEFAULT_STORE_PATH})",
    )
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    config = load_config(
        args.config if args.config is not None else DEFAULT_CONFIG,
        required=args.config is not None,
    )

    store = JSONVectorStore(args.store)
    counts = run(sources, config, HashingEmbedder(), store)

    for source, count in counts.items():
        print(f"[{source}] upserted {count} chunk(s)")
    print(f"\nDone. {sum(counts.values())} chunk(s) written across {len(counts)} source(s). "
          f"Vector store now holds {len(store)} chunk(s) total.")


if __name__ == "__main__":
    main()
