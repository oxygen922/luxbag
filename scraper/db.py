"""SQLite 状态库：条目去重、阶段进度、Pinterest 发布记录。

status 流转：
  discovered -> fetched -> transferred -> rewritten -> published
任一文章只要 published 即视为完成；可断点续跑。
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime

from models import EntrySummary


SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    entry_id        TEXT PRIMARY KEY,
    source          TEXT,
    source_url      TEXT,
    title           TEXT,
    status          TEXT DEFAULT 'discovered',
    cover_cdn       TEXT,
    first_seen      TEXT,
    last_updated    TEXT,
    detail_fetched  INTEGER DEFAULT 0,
    images_transferred INTEGER DEFAULT 0,
    rewritten       INTEGER DEFAULT 0,
    pinterest_published INTEGER DEFAULT 0,
    pinterest_pins  TEXT DEFAULT '[]',
    error           TEXT
);
"""


class DB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as c:
            c.executescript(SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    # ---------- 写 ----------
    def upsert_discovered(self, e: EntrySummary):
        with self._lock, self._connect() as c:
            c.execute(
                """INSERT INTO entries(entry_id, source, source_url, title, first_seen, last_updated)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(entry_id) DO UPDATE SET
                     source=excluded.source,
                     source_url=excluded.source_url,
                     title=excluded.title,
                     last_updated=excluded.last_updated""",
                (e.entry_id, e.source, e.source_url, e.title, self._now(), self._now()),
            )

    def set_status(self, entry_id: str, status: str, **fields):
        cols = ["status=?", "last_updated=?"]
        vals = [status, self._now()]
        for k, v in fields.items():
            cols.append(f"{k}=?")
            vals.append(v)
        vals.append(entry_id)
        with self._lock, self._connect() as c:
            c.execute(f"UPDATE entries SET {', '.join(cols)} WHERE entry_id=?", vals)

    def add_pin(self, entry_id: str, pin_id: str, image_url: str):
        with self._lock, self._connect() as c:
            row = c.execute("SELECT pinterest_pins FROM entries WHERE entry_id=?", (entry_id,)).fetchone()
            pins = json.loads(row["pinterest_pins"]) if row and row["pinterest_pins"] else []
            pins.append({"pin_id": pin_id, "image": image_url})
            c.execute(
                "UPDATE entries SET pinterest_pins=?, pinterest_published=1, last_updated=? WHERE entry_id=?",
                (json.dumps(pins, ensure_ascii=False), self._now(), entry_id),
            )

    # ---------- 读 ----------
    def is_seen(self, entry_id: str) -> bool:
        with self._connect() as c:
            row = c.execute("SELECT 1 FROM entries WHERE entry_id=?", (entry_id,)).fetchone()
            return row is not None

    def is_published(self, entry_id: str) -> bool:
        with self._connect() as c:
            row = c.execute("SELECT pinterest_published FROM entries WHERE entry_id=?", (entry_id,)).fetchone()
            return bool(row and row["pinterest_published"])

    def pending_for_stage(self, stage: str, limit: int = 50) -> list[dict]:
        """返回未达到某阶段的条目。stage: fetched/transferred/rewritten/published。"""
        cond = {
            "fetched": "detail_fetched=0",
            "transferred": "detail_fetched=1 AND images_transferred=0",
            "rewritten": "images_transferred=1 AND rewritten=0",
            "published": "rewritten=1 AND pinterest_published=0",
        }[stage]
        with self._connect() as c:
            rows = c.execute(
                f"SELECT * FROM entries WHERE {cond} ORDER BY first_seen DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get(self, entry_id: str) -> dict | None:
        with self._connect() as c:
            row = c.execute("SELECT * FROM entries WHERE entry_id=?", (entry_id,)).fetchone()
            return dict(row) if row else None
