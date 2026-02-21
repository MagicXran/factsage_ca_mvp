# -*- coding: utf-8 -*-
"""SQLite 持久化层 —— 任务元数据存储"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id     TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'pending',
    calc_type  TEXT NOT NULL,
    request    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    result     TEXT,
    error      TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
"""


class JobDB:
    """轻量 SQLite 封装，同步操作，单连接"""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def insert(self, job_id: str, status: str, calc_type: str,
               request: str, created_at: str) -> None:
        self._conn.execute(
            "INSERT INTO jobs (job_id, status, calc_type, request, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, status, calc_type, request, created_at),
        )
        self._conn.commit()

    def update_status(self, job_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id)
        )
        self._conn.commit()

    def update_result(self, job_id: str, status: str, result: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET status = ?, result = ? WHERE job_id = ?",
            (status, result, job_id),
        )
        self._conn.commit()

    def update_error(self, job_id: str, status: str, error: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET status = ?, error = ? WHERE job_id = ?",
            (status, error, job_id),
        )
        self._conn.commit()

    def get(self, job_id: str) -> Optional[Dict]:
        cur = self._conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_all(self, limit: int = 100) -> List[Dict]:
        cur = self._conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cur.fetchall()]

    def cleanup_orphans(self) -> int:
        """将 pending/running 状态的孤儿任务标记为 failed"""
        cur = self._conn.execute(
            "UPDATE jobs SET status = 'failed', error = '服务重启，任务中断' "
            "WHERE status IN ('pending', 'running')"
        )
        self._conn.commit()
        return cur.rowcount
