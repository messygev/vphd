from app.core.scoring import compute_memory_score, reciprocal_rank_fusion


def test_score_increases_with_confidence():
    low = compute_memory_score(
        relevance=0.8,
        recency_days=1,
        usage=2,
        confidence=0.3,
        trust=1.0,
    )
    high = compute_memory_score(
        relevance=0.8,
        recency_days=1,
        usage=2,
        confidence=0.9,
        trust=1.0,
    )
    assert high > low


def test_score_decreases_with_age():
    recent = compute_memory_score(
        relevance=0.8,
        recency_days=1,
        usage=2,
        confidence=0.8,
        trust=1.0,
    )
    old = compute_memory_score(
        relevance=0.8,
        recency_days=90,
        usage=2,
        confidence=0.8,
        trust=1.0,
    )
    assert recent > old


def test_rrf_prefers_items_appearing_in_multiple_lists():
    fused = reciprocal_rank_fusion(
        [
            ["a", "b", "c"],
            ["b", "d", "a"],
        ],
        k=60,
    )
    assert fused["b"] > fused["c"]
