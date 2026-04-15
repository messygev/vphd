from __future__ import annotations

import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import MODEL_PROFILES, get_settings
from app.core.llm_client import OpenAICompatibleClient
from app.core.rate_limit import InMemoryRateLimiter
from app.core.scoring import compute_memory_score, reciprocal_rank_fusion
from app.core.storage import SQLiteStore
from app.schemas import (
    BeliefRequest,
    BeliefResponse,
    ChatRequest,
    ChatResponse,
    DecisionRequest,
    DecisionResponse,
    DumpRequest,
    DumpResponse,
    PolicyResponse,
    RetrieveRequest,
    RetrieveResponse,
)

settings = get_settings()
store = SQLiteStore(settings.db_path)
llm = OpenAICompatibleClient(settings)
rate_limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)

app = FastAPI(title="BrainDump API", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Tenant-Id", "X-API-Key"],
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup() -> None:
    store.init_schema()


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if x_api_key != settings.app_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def enforce_rate_limit(
    request: Request,
    x_tenant_id: str = Header(default="default"),
) -> None:
    key = f"{x_tenant_id}:{request.client.host if request.client else 'unknown'}"
    rate_limiter.check(key)


@app.get("/healthz")
def healthcheck():
    return {"status": "ok", "ts": int(time.time())}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "models": [profile.__dict__ for profile in MODEL_PROFILES.values()],
            "default_api_key": settings.app_api_key,
        },
    )


@app.get("/api/models", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
def list_models():
    return {"models": [profile.__dict__ for profile in MODEL_PROFILES.values()]}


@app.post("/api/dump", response_model=DumpResponse, dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
def dump_memory(payload: DumpRequest, x_tenant_id: str = Header(default="default")):
    event_id = store.insert_event(
        tenant_id=x_tenant_id,
        event_type=payload.type,
        layer=payload.layer,
        content=payload.content,
        source=payload.source,
        trust=payload.trust,
        confidence=payload.confidence,
        metadata=payload.metadata,
    )
    return DumpResponse(id=event_id, status="stored")


@app.post(
    "/api/retrieve",
    response_model=RetrieveResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def retrieve(payload: RetrieveRequest, x_tenant_id: str = Header(default="default")):
    try:
        lexical_rows = store.search_events(tenant_id=x_tenant_id, query=payload.query, limit=payload.k * 3)
        graph_rows = store.search_graph_events(tenant_id=x_tenant_id, query=payload.query, limit=payload.k * 3)

        lexical_ids = [row["id"] for row in lexical_rows]
        graph_ids = [row["id"] for row in graph_rows]
        rrf_scores = reciprocal_rank_fusion([lexical_ids, graph_ids], k=60)

        merged = {row["id"]: row for row in graph_rows}
        merged.update({row["id"]: row for row in lexical_rows})

        decision_signal = store.decision_signal(tenant_id=x_tenant_id, query=payload.query)
        now = int(time.time())
        scored = []
        for row_id, row in merged.items():
            age_days = max((now - row["ts"]) / 86400.0, 0.0)
            lexical_relevance = 1.0 / (abs(row.get("lexical_rank", 0.0)) + 1.0)
            base_score = compute_memory_score(
                relevance=lexical_relevance,
                recency_days=age_days,
                usage=row["usage_count"] + 1,
                confidence=row["confidence"],
                trust=row["trust"],
            )
            rrf_boost = 1 + rrf_scores.get(row_id, 0.0) * 5.0
            decision_boost = 1 + max(decision_signal, 0.0) * 0.15
            row["score"] = base_score * rrf_boost * decision_boost
            scored.append(row)
        ranked = sorted(scored, key=lambda item: item["score"], reverse=True)[: payload.k]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Retrieve failed: {exc}") from exc
    return RetrieveResponse(results=ranked)


@app.post(
    "/api/decisions",
    response_model=DecisionResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def record_decision(payload: DecisionRequest, x_tenant_id: str = Header(default="default")):
    decision_id = store.insert_decision(
        tenant_id=x_tenant_id,
        context=payload.context,
        action=payload.action,
        outcome=payload.outcome,
        reward=payload.reward,
        propensity=payload.propensity,
        counterfactual_regret=payload.counterfactual_regret,
        policy_name=payload.policy_name,
    )
    return DecisionResponse(id=decision_id, status="recorded")


@app.post(
    "/api/beliefs",
    response_model=BeliefResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def upsert_belief(payload: BeliefRequest, x_tenant_id: str = Header(default="default")):
    belief = store.upsert_belief(
        tenant_id=x_tenant_id,
        statement=payload.statement,
        reinforce=payload.reinforce,
        contradict=payload.contradict,
    )
    return BeliefResponse(**belief)


@app.get(
    "/api/policies",
    response_model=PolicyResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def list_policy_stats(x_tenant_id: str = Header(default="default")):
    rows = store.list_policies(tenant_id=x_tenant_id)
    return PolicyResponse(policies=rows)


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
async def chat(payload: ChatRequest):
    try:
        result = await llm.chat(payload.model_profile, payload.prompt, payload.temperature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    return ChatResponse(**result)
