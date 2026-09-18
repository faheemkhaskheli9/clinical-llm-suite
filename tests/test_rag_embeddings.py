import math

from clinical_core.rag.embeddings import HashingEmbedder


def test_embed_is_deterministic_for_the_same_text():
    embedder = HashingEmbedder(dimensions=64)

    a = embedder.embed(["diabetes causes high blood glucose"])[0]
    b = embedder.embed(["diabetes causes high blood glucose"])[0]

    assert (a == b).all()


def test_embed_is_l2_normalized():
    embedder = HashingEmbedder(dimensions=64)

    vector = embedder.embed(["some clinical text about hypertension"])[0]
    norm = math.sqrt(float((vector * vector).sum()))

    assert math.isclose(norm, 1.0, abs_tol=1e-9)


def test_embed_differs_for_different_text():
    embedder = HashingEmbedder(dimensions=64)

    a, b = embedder.embed(["hypertension", "asthma"])

    assert not (a == b).all()


def test_dimensions_property_matches_constructor():
    assert HashingEmbedder(dimensions=128).dimensions == 128
