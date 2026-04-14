from __future__ import annotations

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
                    ts INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    trust REAL DEFAULT 1.0,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                );
                CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(content, content='events', content_rowid='rowid');

                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    ts INTEGER NOT NULL,
                    context TEXT NOT NULL,
                    action TEXT NOT NULL,
                    outcome TEXT,
                    reward REAL,
                    propensity REAL NOT NULL,
                    counterfactual_regret REAL DEFAULT 0.0
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts DESC);
                """
            )

    def insert_event(self, event_type: str, layer: str, content: str, source: str | None, trust: float) -> str:
        event_id = str(uuid.uuid4())
        ts = int(time.time())
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO events(id, ts, type, layer, content, source, trust) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (event_id, ts, event_type, layer, content, source, trust),
            )
            conn.execute("INSERT INTO events_fts(rowid, content) SELECT rowid, content FROM events WHERE id = ?", (event_id,))
        return event_id

    def search_events(self, query: str, limit: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.content, e.ts, e.trust
                FROM events_fts f
                JOIN events e ON e.rowid = f.rowid
                WHERE f.content MATCH ?
                ORDER BY e.ts DESC
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_decision(
        self,
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
                INSERT INTO decisions(id, ts, context, action, outcome, reward, propensity, counterfactual_regret)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (decision_id, ts, context, action, outcome, reward, propensity, counterfactual_regret),
            )
        return decision_id
