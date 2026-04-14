from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import MODEL_PROFILES, get_settings
from app.core.llm_client import OpenAICompatibleClient
from app.core.storage import SQLiteStore
from app.schemas import (
    ChatRequest,
    ChatResponse,
    DecisionRequest,
    DecisionResponse,
    DumpRequest,
    DumpResponse,
    RetrieveRequest,
    RetrieveResponse,
)

settings = get_settings()
store = SQLiteStore(settings.db_path)
llm = OpenAICompatibleClient(settings)

app = FastAPI(title="BrainDump API", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup() -> None:
    store.init_schema()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"models": [profile.__dict__ for profile in MODEL_PROFILES.values()]},
    )


@app.get("/api/models")
def list_models():
    return {"models": [profile.__dict__ for profile in MODEL_PROFILES.values()]}


@app.post("/api/dump", response_model=DumpResponse)
def dump_memory(payload: DumpRequest):
    event_id = store.insert_event(payload.type, payload.layer, payload.content, payload.source, payload.trust)
    return DumpResponse(id=event_id, status="stored")


@app.post("/api/retrieve", response_model=RetrieveResponse)
def retrieve(payload: RetrieveRequest):
    try:
        rows = store.search_events(payload.query, payload.k)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Retrieve failed: {exc}") from exc
    return RetrieveResponse(results=rows)


@app.post("/api/decisions", response_model=DecisionResponse)
def record_decision(payload: DecisionRequest):
    decision_id = store.insert_decision(
        context=payload.context,
        action=payload.action,
        outcome=payload.outcome,
        reward=payload.reward,
        propensity=payload.propensity,
        counterfactual_regret=payload.counterfactual_regret,
    )
    return DecisionResponse(id=decision_id, status="recorded")


@app.post("/api/chat", response_model=ChatResponse)
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
