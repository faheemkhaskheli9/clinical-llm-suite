"""Fixed-size character chunking with overlap.

Same shape as hybrid-research-agent's kb/chunking.py (chunking-and-embedding-
ingestion knowledge-base pattern) — reused here as-is since chunk boundary
logic doesn't need to know it's chunking medical text specifically.
"""

from __future__ import annotations

from typing import List


def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> List[str]:
    """Splits `text` into overlapping chunks of at most `chunk_size` chars.

    Boundaries snap to the nearest preceding whitespace when one exists
    within the chunk, so words aren't split mid-token.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")

    text = text.strip()
    if not text:
        return []

    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        next_start = end - chunk_overlap
        # Guard against the whitespace-snapped `end` landing so close to
        # `start` that overlap would produce zero forward progress (infinite loop).
        start = next_start if next_start > start else end
    return chunks
