from __future__ import annotations

import math


def logit(probability: float, epsilon: float = 1e-6) -> float:
    probability = min(max(probability, epsilon), 1.0 - epsilon)
    return math.log(probability / (1.0 - probability))


def compute_memory_score(
    *,
    relevance: float,
    recency_days: float,
    usage: int,
    confidence: float,
    trust: float,
    w_relevance: float = 1.0,
    w_recency: float = 0.7,
    w_usage: float = 0.4,
    w_confidence: float = 0.8,
    w_trust: float = 0.5,
    epsilon: float = 1e-3,
) -> float:
    recency_decay = math.exp(-max(recency_days, 0.0) / 30.0)
    log_score = (
        w_relevance * math.log(max(relevance, 0.0) + epsilon)
        + w_recency * math.log(recency_decay + epsilon)
        + w_usage * math.log(max(usage, 0) + 1)
        + w_confidence * logit(confidence)
        + w_trust * math.log(max(trust, 0.0) + epsilon)
    )
    return math.exp(log_score)
