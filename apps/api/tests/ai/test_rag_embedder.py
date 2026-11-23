import math

import pytest

from app.ai.rag.embedder.fake import FakeEmbedder


def test_fake_embedder_dimension_and_normalization() -> None:
    embedder = FakeEmbedder(dimension=768)
    vec = embedder.embed_passage("This is a regulatory guideline chunk.")

    assert len(vec) == 768
    # L2 norm check
    l2_norm = math.sqrt(sum(x * x for x in vec))
    assert abs(l2_norm - 1.0) < 1e-3


def test_fake_embedder_determinism() -> None:
    embedder1 = FakeEmbedder()
    embedder2 = FakeEmbedder()

    text = "Section 503 BNSS property return guidelines"
    vec1 = embedder1.embed_passage(text)
    vec2 = embedder2.embed_passage(text)

    assert vec1 == vec2


def test_fake_embedder_prefix_asymmetry() -> None:
    embedder = FakeEmbedder()
    text = "What is the sustainable indebtedness limit?"

    passage_vec = embedder.embed_passage(text)
    query_vec = embedder.embed_query(text)

    # Per ADR-001, passage: prefix and query: prefix must result in distinct vectors
    assert passage_vec != query_vec


def test_fake_embedder_transient_failure_simulation() -> None:
    embedder = FakeEmbedder(fail_next_n=2)

    with pytest.raises(RuntimeError, match="Simulated transient embedder failure"):
        embedder.embed_passage("Attempt 1")

    with pytest.raises(RuntimeError, match="Simulated transient embedder failure"):
        embedder.embed_passage("Attempt 2")

    # 3rd attempt succeeds
    vec = embedder.embed_passage("Attempt 3")
    assert len(vec) == 768
