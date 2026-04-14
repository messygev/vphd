from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DumpRequest(BaseModel):
    type: str
    layer: str
    content: str
    source: str | None = None
    trust: float = Field(default=1.0, ge=0.0, le=1.0)


class DumpResponse(BaseModel):
    id: str
    status: str


class RetrieveRequest(BaseModel):
    query: str
    k: int = Field(default=10, ge=1, le=50)


class MemoryResult(BaseModel):
    id: str
    content: str
    ts: int
    trust: float


class RetrieveResponse(BaseModel):
    results: list[MemoryResult]


class ChatRequest(BaseModel):
    model_profile: str = Field(default="mid")
    prompt: str
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)


class ChatResponse(BaseModel):
    model: str
    content: str
    usage: dict[str, Any] | None = None


class DecisionRequest(BaseModel):
    context: str
    action: str
    outcome: str | None = None
    reward: float = 0.0
    propensity: float = Field(default=1.0, gt=0.0, le=1.0)
    counterfactual_regret: float = 0.0


class DecisionResponse(BaseModel):
    id: str
    status: str
