"""Trace 存储：结构化事件流落库（先落库，后接 UI）。"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Optional

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "trace.db",
)


class TraceStore:
    def __init__(self, db_path: str = _DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        cur = self.conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS runs(
                run_id TEXT PRIMARY KEY, complaint_id TEXT, plan_json TEXT,
                status TEXT, steps_used INTEGER, consistency REAL, route TEXT,
                created_at TEXT)"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS steps(
                run_id TEXT, node TEXT, action_type TEXT,
                input_json TEXT, output_json TEXT, latency_ms REAL, error TEXT)"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS gate_results(
                run_id TEXT, consistency REAL, votes_json TEXT, route TEXT,
                decision_json TEXT, reasoning_json TEXT)"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS complaint_updates(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT, content TEXT, created_at REAL)"""
        )
        # 轻量迁移：老库补列（已存在则忽略）
        for col_sql in (
            "ALTER TABLE runs ADD COLUMN complaint_text TEXT",
            "ALTER TABLE runs ADD COLUMN refreshed_at REAL",
        ):
            try:
                cur.execute(col_sql)
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    def log_run(
        self,
        run_id: str,
        complaint_id: str,
        plan_json: str,
        status: str = "running",
        steps_used: int = 0,
        complaint_text: str = "",
    ):
        self.conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, complaint_id, plan_json, status, steps_used, created_at, complaint_text) VALUES(?,?,?,?,?,?,?)",
            (run_id, complaint_id, plan_json, status, steps_used, time.time(), complaint_text),
        )
        self.conn.commit()

    def update_run(self, run_id: str, status: str, steps_used: int, consistency: float, route: str):
        self.conn.execute(
            "UPDATE runs SET status=?, steps_used=?, consistency=?, route=? WHERE run_id=?",
            (status, steps_used, consistency, route, run_id),
        )
        self.conn.commit()

    def log_step(
        self,
        run_id: str,
        node: str,
        action_type: str,
        input_json: str,
        output_json: str,
        latency_ms: float,
        error: str = "",
    ):
        self.conn.execute(
            "INSERT INTO steps(run_id, node, action_type, input_json, output_json, latency_ms, error) VALUES(?,?,?,?,?,?,?)",
            (run_id, node, action_type, input_json, output_json, latency_ms, error),
        )
        self.conn.commit()

    def log_gate(
        self,
        run_id: str,
        consistency: float,
        votes_json: str,
        route: str,
        decision_json: str,
        reasoning_json: str,
    ):
        self.conn.execute(
            "INSERT INTO gate_results(run_id, consistency, votes_json, route, decision_json, reasoning_json) VALUES(?,?,?,?,?,?)",
            (run_id, consistency, votes_json, route, decision_json, reasoning_json),
        )
        self.conn.commit()

    # ---- 留言更新（留言板推送 → 历史 run 打标 → 按需重答）----

    def add_update(self, run_id: str, content: str) -> int:
        """记录一条留言更新，返回该 run 的累计更新数。"""
        self.conn.execute(
            "INSERT INTO complaint_updates(run_id, content, created_at) VALUES(?,?,?)",
            (run_id, content, time.time()),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM complaint_updates WHERE run_id=?", (run_id,)
        ).fetchone()
        return int(row["n"])

    def list_updates(self, run_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, content, created_at FROM complaint_updates WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT run_id, COUNT(*) AS n FROM complaint_updates GROUP BY run_id"
        ).fetchall()
        return {r["run_id"]: int(r["n"]) for r in rows}

    def get_run(self, run_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def latest_decision(self, run_id: str) -> Optional[str]:
        """取最近一次门控落库的决策 JSON（refresh 时作为"过去生成的"拼 prompt）。"""
        row = self.conn.execute(
            "SELECT decision_json FROM gate_results WHERE run_id=? ORDER BY rowid DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        return row["decision_json"] if row else None

    def set_refreshed(self, run_id: str):
        self.conn.execute(
            "UPDATE runs SET refreshed_at=? WHERE run_id=?", (time.time(), run_id)
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
