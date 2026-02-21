# -*- coding: utf-8 -*-
"""JobManager 集成测试（使用 SQLite 后端）"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import JobRequest, JobStatus, CalcType, CalculationResult
from app.services.job_manager import JobManager


def _make_request(**overrides) -> JobRequest:
    defaults = {
        "calc_type": "deoxidation",
        "steel": {"Fe_g": 1000, "Mn_field": "", "Si_g": 0.5, "Al_g": 0.3, "O_g": 0.05, "S_g": 0.02},
        "slag": {"CaO_g": 10, "Al2O3_g": 5, "SiO2_g": 3},
        "conditions": {"T_C": 1600},
        "target": {"element": "Al", "value": 0.03, "unit": "wtpct"},
        "solve_species": "Ca",
    }
    defaults.update(overrides)
    return JobRequest(**defaults)


@pytest.fixture
def manager(tmp_path):
    """使用临时数据库的 JobManager"""
    db_path = tmp_path / "test.db"
    mgr = JobManager(db_path=db_path)
    return mgr


@pytest.mark.asyncio
async def test_submit_creates_job(manager):
    req = _make_request()
    job_id = await manager.submit(req)
    assert len(job_id) == 8
    job = manager.get(job_id)
    assert job is not None
    assert job["status"] == JobStatus.pending


@pytest.mark.asyncio
async def test_get_nonexistent(manager):
    assert manager.get("nope") is None


@pytest.mark.asyncio
async def test_list_all_returns_submitted(manager):
    req = _make_request()
    await manager.submit(req)
    await manager.submit(req)
    jobs = manager.list_all()
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_persistence_across_instances(tmp_path):
    """验证重启后数据仍在"""
    db_path = tmp_path / "persist.db"
    mgr1 = JobManager(db_path=db_path)
    req = _make_request()
    job_id = await mgr1.submit(req)

    # 新实例，同一个数据库文件
    mgr2 = JobManager(db_path=db_path)
    job = mgr2.get(job_id)
    assert job is not None
    assert job["job_id"] == job_id
    # 重启后 pending 被清理为 failed
    assert job["status"] == JobStatus.failed


@pytest.mark.asyncio
async def test_hydrate_returns_request_object(manager):
    """验证 get() 返回的 request 是 JobRequest 对象"""
    req = _make_request()
    job_id = await manager.submit(req)
    job = manager.get(job_id)
    assert isinstance(job["request"], JobRequest)
    assert job["request"].solve_species == "Ca"
    assert job["request"].steel.Fe_g == 1000
