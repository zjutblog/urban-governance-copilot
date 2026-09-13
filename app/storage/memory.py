"""用户记忆：长期偏好/纠正/事实，检索式注入 planner。"""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "memory.db",
)


class MemoryStore:
    def __init__(self, db_path: str = _DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        cur = self.conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS memories(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT, kind TEXT, content TEXT,
                importance REAL, created_at REAL, last_access REAL)"""
        )
        self.conn.commit()

    def add_memory(self, user_id: str, kind: str, content: str, importance: float = 0.5):
        now = time.time()
        self.conn.execute(
            "INSERT INTO memories(user_id, kind, content, importance, created_at, last_access) VALUES(?,?,?,?,?,?)",
            (user_id, kind, content, importance, now, now),
        )
        self.conn.commit()

    def get_memories(self, user_id: str, top_k: int = 5) -> list[str]:
        rows = self.conn.execute(
            "SELECT content FROM memories WHERE user_id=? ORDER BY importance DESC, last_access DESC LIMIT ?",
            (user_id, top_k),
        ).fetchall()
        now = time.time()
        self.conn.execute(
            "UPDATE memories SET last_access=? WHERE user_id=?",
            (now, user_id),
        )
        self.conn.commit()
        return [r["content"] for r in rows]

    def close(self):
        self.conn.close()
