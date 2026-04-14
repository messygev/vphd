# BrainDump Web MVP (FastAPI + Vanilla JS)

Dieses Repository enthält einen produktiven Startpunkt für **BrainDump v3.1** mit:

- **FastAPI REST API** (Dump, Retrieve, Decision, Chat)
- **SQLite (WAL) als performanter Core Store**
- **Vanilla HTML/CSS/JS UI** für schnelle Bedienung ohne Framework-Overhead
- **OpenAI-kompatible Chat-Integration** mit 4 Modellprofilen

## Modellprofile

Die UI und API unterstützen vier Profile:

1. `small`
2. `fast` (3B)
3. `mid` (z. B. `gpt-oss-120b`)
4. `enterprise` (z. B. `gpt-5.4`)

Die realen Modell-IDs sind per Env konfigurierbar.

## Schnellstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

Dann im Browser öffnen:

- http://127.0.0.1:8000
- API Docs: http://127.0.0.1:8000/docs

## Konfiguration

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export MODEL_SMALL="small-3b"
export MODEL_FAST="fast-3b"
export MODEL_MID="gpt-oss-120b"
export MODEL_ENTERPRISE="gpt-5.4"
export BRAIN_DB_PATH="braindump.db"
```

## REST API Übersicht

- `GET /api/models` – verfügbare Modellprofile
- `POST /api/dump` – rohen Event speichern
- `POST /api/retrieve` – FTS5-basierte Suche
- `POST /api/decisions` – Decision Event speichern
- `POST /api/chat` – Chat Completion via OpenAI-kompatibler API

## Qualitäts-/Performance-Basics im MVP

- SQLite im **WAL-Modus** + `busy_timeout`
- FTS5 für schnelle Lexical Retrievals
- klare Schema-/Service-Trennung (`config`, `storage`, `llm_client`, `schemas`)
- API Contract via Pydantic
- Smoke-Tests für Kernfluss
