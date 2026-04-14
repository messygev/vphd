from app.core.scoring import compute_memory_score


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
