from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    trust REAL DEFAULT 1.0,
                    confidence REAL DEFAULT 0.5,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                );
                CREATE INDEX IF NOT EXISTS idx_events_tenant_ts ON events(tenant_id, ts DESC);

                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
                    content,
                    tenant_id UNINDEXED,
                    content=''
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    context TEXT NOT NULL,
                    action TEXT NOT NULL,
                    outcome TEXT,
                    reward REAL,
                    propensity REAL NOT NULL,
                    counterfactual_regret REAL DEFAULT 0.0
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_tenant_ts ON decisions(tenant_id, ts DESC);
                """
            )

    def insert_event(
        self,
        *,
        tenant_id: str,
        event_type: str,
        layer: str,
        content: str,
        source: str | None,
        trust: float,
        confidence: float,
        metadata: dict | None,
    ) -> str:
        event_id = str(uuid.uuid4())
        ts = int(time.time())
        metadata_json = json.dumps(metadata or {})
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO events(id, tenant_id, ts, type, layer, content, source, trust, confidence, metadata)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, tenant_id, ts, event_type, layer, content, source, trust, confidence, metadata_json),
            )
            conn.execute(
                "INSERT INTO events_fts(rowid, content, tenant_id) VALUES(last_insert_rowid(), ?, ?)",
                (content, tenant_id),
            )
        return event_id

    def search_events(self, *, tenant_id: str, query: str, limit: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.content, e.ts, e.trust, e.confidence, e.usage_count, bm25(f) AS lexical_rank
                FROM events_fts f
                JOIN events e ON e.rowid = f.rowid
                WHERE f.content MATCH ?
                  AND e.tenant_id = ?
                ORDER BY lexical_rank ASC, e.ts DESC
                LIMIT ?
                """,
                (query, tenant_id, limit),
            ).fetchall()

            event_ids = [row["id"] for row in rows]
            if event_ids:
                conn.executemany(
                    "UPDATE events SET usage_count = usage_count + 1 WHERE id = ? AND tenant_id = ?",
                    [(event_id, tenant_id) for event_id in event_ids],
                )

        return [dict(row) for row in rows]

    def insert_decision(
        self,
        *,
        tenant_id: str,
        context: str,
        action: str,
        outcome: str | None,
        reward: float,
        propensity: float,
        counterfactual_regret: float,
    ) -> str:
        decision_id = str(uuid.uuid4())
        ts = int(time.time())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions(id, tenant_id, ts, context, action, outcome, reward, propensity, counterfactual_regret)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (decision_id, tenant_id, ts, context, action, outcome, reward, propensity, counterfactual_regret),
            )
        return decision_id
