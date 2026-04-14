# BrainDump Web MVP (FastAPI + Vanilla JS)

Dieses Repository enthält einen produktiven Startpunkt für **BrainDump v3.1** mit:

- **FastAPI REST API** (Dump, Retrieve, Decision, Chat)
- **SQLite (WAL) als performanter Core Store**
- **Vanilla HTML/CSS/JS UI** im modernen Glassmorphism-Look ohne Framework-Overhead
- **OpenAI-kompatible Chat-Integration** mit 4 Modellprofilen

## Modellprofile

Die UI und API unterstützen vier Profile:

1. `small`
2. `fast` (3B)
3. `mid` (z. B. `gpt-oss-120b`)
4. `enterprise` (z. B. `gpt-5.4`)

Die realen Modell-IDs sind per Env konfigurierbar.

## Verbesserungen gegenüber initialem Slice


## UI Design

- modernes, responsives Dashboard-Layout mit Sidebar + Workspace
- CI-Farbtokens als CSS-Variablen aus dem bereitgestellten Variablenkatalog
- Toast-Feedback statt Browser-Alerts für bessere UX

- Tenant-Isolation über `X-Tenant-Id` Header bei Memory- und Decision-Endpunkten
- Retrieval-Re-Ranking mit log-linearem Memory Score (Relevanz, Recency, Usage, Confidence, Trust)
- Nutzungstracking (`usage_count`) direkt im Event-Store
- Healthcheck Endpoint `/healthz`

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

## Docker Auslieferung

### Build & Run (Docker)

```bash
docker build -t braindump-web:latest .
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="<dein-key>" \
  -e BRAIN_DB_PATH="/data/braindump.db" \
  -v $(pwd)/.data:/data \
  braindump-web:latest
```

### Compose (empfohlen)

```bash
docker compose -f docker-compose.yaml up --build
```

Damit läuft die App auf `http://localhost:8000` und die SQLite-Datei wird im Volume `braindump_data` persistiert.

## REST API Übersicht

- `GET /healthz` – Service Health
- `GET /api/models` – verfügbare Modellprofile
- `POST /api/dump` – rohen Event speichern (`X-Tenant-Id`)
- `POST /api/retrieve` – FTS5 + Score Ranking (`X-Tenant-Id`)
- `POST /api/decisions` – Decision Event speichern (`X-Tenant-Id`)
- `POST /api/chat` – Chat Completion via OpenAI-kompatibler API

## Qualitäts-/Performance-Basics im MVP

- SQLite im **WAL-Modus** + `busy_timeout`
- FTS5 für schnelle Lexical Retrievals
- Ranking mit Score-Heuristik (`app/core/scoring.py`)
- klare Schema-/Service-Trennung (`config`, `storage`, `llm_client`, `schemas`)
- API Contract via Pydantic
- Smoke-Tests für Kernfluss
