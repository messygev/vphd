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
                    counterfactual_regret REAL DEFAULT 0.0,
                    policy_name TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_tenant_ts ON decisions(tenant_id, ts DESC);

                CREATE TABLE IF NOT EXISTS beliefs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    alpha INTEGER NOT NULL DEFAULT 1,
                    beta INTEGER NOT NULL DEFAULT 1,
                    last_reinforced INTEGER,
                    UNIQUE(tenant_id, statement)
                );

                CREATE TABLE IF NOT EXISTS policies (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    alpha INTEGER NOT NULL DEFAULT 1,
                    beta INTEGER NOT NULL DEFAULT 1,
                    success_rate REAL NOT NULL DEFAULT 0.5,
                    updated_at INTEGER,
                    UNIQUE(tenant_id, name)
                );

                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT,
                    aliases TEXT,
                    first_seen INTEGER,
                    last_seen INTEGER,
                    UNIQUE(tenant_id, name)
                );

                CREATE TABLE IF NOT EXISTS relations (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    src_entity TEXT NOT NULL,
                    dst_entity TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    evidence_count INTEGER DEFAULT 1,
                    last_seen INTEGER
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    ref_id TEXT,
                    data TEXT NOT NULL,
                    hash TEXT NOT NULL
                );
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

    def decision_signal(self, *, tenant_id: str, query: str) -> float:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(AVG(reward), 0.0) AS avg_reward, COUNT(*) AS cnt
                FROM decisions
                WHERE tenant_id = ?
                  AND context LIKE '%' || ? || '%'
                """,
                (tenant_id, query),
            ).fetchone()
        avg_reward = float(row["avg_reward"] or 0.0)
        count_boost = min(int(row["cnt"]), 10) / 10.0
        return avg_reward * 0.7 + count_boost * 0.3

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
        policy_name: str | None,
    ) -> str:
        decision_id = str(uuid.uuid4())
        ts = int(time.time())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions(id, tenant_id, ts, context, action, outcome, reward, propensity, counterfactual_regret, policy_name)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (decision_id, tenant_id, ts, context, action, outcome, reward, propensity, counterfactual_regret, policy_name),
            )
            if policy_name:
                self._update_policy(conn, tenant_id=tenant_id, policy_name=policy_name, reward=reward, ts=ts)
        return decision_id

    def _update_policy(self, conn: sqlite3.Connection, *, tenant_id: str, policy_name: str, reward: float, ts: int) -> None:
        row = conn.execute(
            "SELECT id, alpha, beta FROM policies WHERE tenant_id = ? AND name = ?",
            (tenant_id, policy_name),
        ).fetchone()

        reward_positive = reward > 0
        if row is None:
            alpha = 2 if reward_positive else 1
            beta = 1 if reward_positive else 2
            success_rate = alpha / (alpha + beta)
            conn.execute(
                """
                INSERT INTO policies(id, tenant_id, name, alpha, beta, success_rate, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), tenant_id, policy_name, alpha, beta, success_rate, ts),
            )
            return

        alpha = int(row["alpha"]) + (1 if reward_positive else 0)
        beta = int(row["beta"]) + (0 if reward_positive else 1)
        success_rate = alpha / (alpha + beta)
        conn.execute(
            """
            UPDATE policies
            SET alpha = ?, beta = ?, success_rate = ?, updated_at = ?
            WHERE id = ?
            """,
            (alpha, beta, success_rate, ts, row["id"]),
        )

    def upsert_belief(self, *, tenant_id: str, statement: str, reinforce: bool, contradict: bool) -> dict:
        ts = int(time.time())
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, alpha, beta FROM beliefs WHERE tenant_id = ? AND statement = ?",
                (tenant_id, statement),
            ).fetchone()

            if row is None:
                alpha = 2 if reinforce else 1
                beta = 2 if contradict else 1
                belief_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO beliefs(id, tenant_id, statement, alpha, beta, last_reinforced)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (belief_id, tenant_id, statement, alpha, beta, ts),
                )
            else:
                alpha = int(row["alpha"]) + (1 if reinforce else 0)
                beta = int(row["beta"]) + (1 if contradict else 0)
                conn.execute(
                    "UPDATE beliefs SET alpha = ?, beta = ?, last_reinforced = ? WHERE id = ?",
                    (alpha, beta, ts, row["id"]),
                )

        confidence = alpha / (alpha + beta)
        return {"statement": statement, "alpha": alpha, "beta": beta, "confidence": confidence}

    def list_policies(self, *, tenant_id: str, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT name, success_rate, alpha, beta
                FROM policies
                WHERE tenant_id = ?
                ORDER BY success_rate DESC, updated_at DESC
                LIMIT ?
                """,
                (tenant_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
