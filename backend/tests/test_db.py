# -*- coding: utf-8 -*-
"""SQLite 数据库层测试"""
import pytest
import sys
from pathlib import Path

# 确保 backend/app 可以被导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.db import JobDB


@pytest.fixture
def db(tmp_path):
    """每个测试用独立的临时数据库"""
    return JobDB(tmp_path / "test.db")


def test_insert_and_get(db):
    db.insert("abc123", "pending", "deoxidation", '{"fake":"request"}', "2026-01-01T00:00:00")
    row = db.get("abc123")
    assert row is not None
    assert row["job_id"] == "abc123"
    assert row["status"] == "pending"
    assert row["calc_type"] == "deoxidation"
    assert row["request"] == '{"fake":"request"}'
    assert row["result"] is None
    assert row["error"] is None


def test_get_nonexistent(db):
    assert db.get("nope") is None


def test_update_status(db):
    db.insert("j1", "pending", "deoxidation", '{}', "2026-01-01T00:00:00")
    db.update_status("j1", "running")
    assert db.get("j1")["status"] == "running"


def test_update_result(db):
    db.insert("j1", "pending", "deoxidation", '{}', "2026-01-01T00:00:00")
    db.update_result("j1", "completed", '{"alpha_g": 1.23}')
    row = db.get("j1")
    assert row["status"] == "completed"
    assert row["result"] == '{"alpha_g": 1.23}'


def test_update_error(db):
    db.insert("j1", "pending", "deoxidation", '{}', "2026-01-01T00:00:00")
    db.update_error("j1", "failed", "boom")
    row = db.get("j1")
    assert row["status"] == "failed"
    assert row["error"] == "boom"


def test_list_all_ordered_by_created_at_desc(db):
    db.insert("a", "completed", "deoxidation", '{}', "2026-01-01T00:00:00")
    db.insert("b", "completed", "deoxidation", '{}', "2026-01-02T00:00:00")
    db.insert("c", "completed", "deoxidation", '{}', "2026-01-03T00:00:00")
    rows = db.list_all()
    assert [r["job_id"] for r in rows] == ["c", "b", "a"]


def test_list_all_with_limit(db):
    for i in range(5):
        db.insert(f"j{i}", "completed", "deoxidation", '{}', f"2026-01-0{i+1}T00:00:00")
    rows = db.list_all(limit=3)
    assert len(rows) == 3


def test_cleanup_orphans(db):
    db.insert("r1", "running", "deoxidation", '{}', "2026-01-01T00:00:00")
    db.insert("p1", "pending", "deoxidation", '{}', "2026-01-01T00:00:01")
    db.insert("c1", "completed", "deoxidation", '{}', "2026-01-01T00:00:02")
    count = db.cleanup_orphans()
    assert count == 2
    assert db.get("r1")["status"] == "failed"
    assert db.get("p1")["status"] == "failed"
    assert db.get("c1")["status"] == "completed"
