import pytest

from clinical_core.rag.chunking import chunk_text


def test_short_text_returns_single_chunk():
    assert chunk_text("hello world", chunk_size=800, chunk_overlap=100) == ["hello world"]


def test_empty_text_returns_no_chunks():
    assert chunk_text("   ", chunk_size=800, chunk_overlap=100) == []


def test_long_text_splits_at_whitespace_not_mid_word():
    text = "word " * 50  # 250 chars, well over a small chunk_size
    chunks = chunk_text(text, chunk_size=40, chunk_overlap=10)

    assert len(chunks) > 1
    assert all(chunk == chunk.strip() for chunk in chunks)
    # Every chunk is made up of whole "word" tokens -- no mid-token split.
    for chunk in chunks:
        assert all(token == "word" for token in chunk.split())


def test_overlap_guarantees_forward_progress_even_near_chunk_size():
    # chunk_overlap close to chunk_size must not stall/move start backward.
    text = "a" * 500
    chunks = chunk_text(text, chunk_size=50, chunk_overlap=49)
    assert len(chunks) > 1
    assert sum(len(c) for c in chunks) >= len(text)  # made real progress, didn't loop forever


@pytest.mark.parametrize("chunk_size,chunk_overlap", [(0, 0), (-1, 0), (50, 50), (50, 60)])
def test_invalid_chunk_size_or_overlap_raises(chunk_size, chunk_overlap):
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size, chunk_overlap)
