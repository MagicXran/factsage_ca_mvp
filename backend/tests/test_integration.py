# -*- coding: utf-8 -*-
"""端到端集成测试"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.db import JobDB
from app.services.job_manager import JobManager
from app.models import JobRequest, JobStatus


def _make_request() -> JobRequest:
    return JobRequest(
        calc_type="deoxidation",
        steel={"Fe_g": 1000, "Mn_field": "", "Si_g": 0.5, "Al_g": 0.3, "O_g": 0.05, "S_g": 0.02},
        slag={"CaO_g": 10, "Al2O3_g": 5, "SiO2_g": 3},
        conditions={"T_C": 1600},
        target={"element": "Al", "value": 0.03, "unit": "wtpct"},
        solve_species="Ca",
    )


def test_orphan_cleanup(tmp_path):
    """模拟服务崩溃后重启，孤儿任务应被标记为 failed"""
    db_path = tmp_path / "orphan.db"
    db = JobDB(db_path)
    req = _make_request()
    db.insert("orphan1", "running", "deoxidation", req.model_dump_json(), "2026-01-01T00:00:00")
    db.insert("orphan2", "pending", "deoxidation", req.model_dump_json(), "2026-01-01T00:00:01")
    db.insert("done1", "completed", "deoxidation", req.model_dump_json(), "2026-01-01T00:00:02")
    db.close()

    # 新实例启动 → 自动清理
    mgr = JobManager(db_path=db_path)
    assert mgr.get("orphan1")["status"] == JobStatus.failed
    assert mgr.get("orphan2")["status"] == JobStatus.failed
    assert mgr.get("done1")["status"] == JobStatus.completed
    assert mgr.get("orphan1")["error"] == "服务重启，任务中断"


@pytest.mark.asyncio
async def test_full_lifecycle(tmp_path):
    """完整生命周期：提交 → 查询 → 列表 → 重启后仍可查"""
    db_path = tmp_path / "lifecycle.db"
    mgr = JobManager(db_path=db_path)
    req = _make_request()

    # 提交
    job_id = await mgr.submit(req)
    job = mgr.get(job_id)
    assert job["status"] == JobStatus.pending
    assert job["request"].solve_species == "Ca"
    assert job["request"].steel.Fe_g == 1000

    # 列表
    jobs = mgr.list_all()
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == job_id

    # 重启后仍可查
    mgr2 = JobManager(db_path=db_path)
    job2 = mgr2.get(job_id)
    assert job2 is not None
    # 重启后 pending 被清理为 failed
    assert job2["status"] == JobStatus.failed
    assert job2["request"].solve_species == "Ca"


@pytest.mark.asyncio
async def test_multiple_jobs_ordering(tmp_path):
    """多个任务按创建时间倒序排列"""
    db_path = tmp_path / "order.db"
    mgr = JobManager(db_path=db_path)
    req = _make_request()

    ids = []
    for _ in range(5):
        ids.append(await mgr.submit(req))

    jobs = mgr.list_all()
    assert len(jobs) == 5
    # 最后提交的排在最前面
    assert jobs[0]["job_id"] == ids[-1]
