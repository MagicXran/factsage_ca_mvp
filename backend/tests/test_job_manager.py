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


def _write_result_xml(work_root: Path, job_id: str) -> None:
    out_dir = work_root / job_id / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<equilib>
  <header>
    <species_definition>
      <solution phase_id="p_fe" state="Fe-liq">
        <species id="sp_fe" name="Fe"/>
        <species id="sp_o" name="O"/>
        <species id="sp_s" name="S"/>
      </solution>
      <solution phase_id="p_slag" state="Slag-liq#1">
        <species id="sp_cao" name="CaO"/>
        <species id="sp_al2o3" name="Al2O3"/>
      </solution>
    </species_definition>
    <species id="sp_fe" name="Fe"/>
    <species id="sp_o" name="O"/>
    <species id="sp_s" name="S"/>
    <species id="sp_cao" name="CaO"/>
    <species id="sp_al2o3" name="Al2O3"/>
  </header>
  <page alpha="0.1234" T="1873.15" P="1">
    <result id="sp_fe" g="99.0"/>
    <result id="sp_o" g="0.01"/>
    <result id="sp_s" g="0.02"/>
    <result id="sp_cao" g="10.0"/>
    <result id="sp_al2o3" g="5.0"/>
  </page>
</equilib>
"""
    (out_dir / "result.xml").write_text(xml, encoding="utf-8")


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


def test_get_recovers_completed_result_from_xml(manager, tmp_path, monkeypatch):
    """DB 中 completed 但 result 为空时，自动从 result.xml 修复"""
    work_root = tmp_path / "work"
    monkeypatch.setenv("WORK_ROOT", str(work_root))

    req = _make_request()
    job_id = "legacy01"
    _write_result_xml(work_root, job_id)

    manager._db.insert(
        job_id=job_id,
        status=JobStatus.pending.value,
        calc_type=CalcType.deoxidation.value,
        request=req.model_dump_json(),
        created_at="2026-02-21T18:22:57.000000",
    )
    manager._db.update_status(job_id, JobStatus.completed.value)

    job = manager.get(job_id)
    assert job is not None
    assert job["status"] == JobStatus.completed
    assert job["result"] is not None
    assert job["result"].alpha_g == pytest.approx(0.1234)

    row = manager._db.get(job_id)
    assert row is not None
    assert row["result"] is not None


def test_get_supports_disk_only_history_when_db_missing(manager, tmp_path, monkeypatch):
    """DB 无记录时，允许直接从磁盘 XML 加载历史结果"""
    work_root = tmp_path / "work"
    monkeypatch.setenv("WORK_ROOT", str(work_root))

    job_id = "legacy02"
    _write_result_xml(work_root, job_id)

    job = manager.get(job_id)
    assert job is not None
    assert job["job_id"] == job_id
    assert job["status"] == JobStatus.completed
    assert job["request"] is None
    assert job["result"] is not None
    assert job["result"].alpha_g == pytest.approx(0.1234)


def test_get_refreshes_stale_db_result_from_xml(manager, tmp_path, monkeypatch):
    """DB 有旧 result（如 Mock 数据）但 result.xml 更新时，优先使用 XML 结果并回写 DB"""
    work_root = tmp_path / "work"
    monkeypatch.setenv("WORK_ROOT", str(work_root))

    req = _make_request()
    job_id = "refresh1"

    # 先在 DB 中写入旧 result（模拟 Mock 结果）
    old_result = CalculationResult(alpha_g=0.9999, solve_species="Ca", T_K=1873.15, P_atm=1.0)
    manager._db.insert(
        job_id=job_id,
        status=JobStatus.pending.value,
        calc_type=CalcType.deoxidation.value,
        request=req.model_dump_json(),
        created_at="2026-02-21T18:00:00.000000",
    )
    manager._db.update_result(job_id, JobStatus.completed.value, old_result.model_dump_json())

    # 确认 DB 中是旧数据
    job = manager.get(job_id)
    assert job["result"].alpha_g == pytest.approx(0.9999)

    # 写入 result.xml（真实结果，alpha=0.1234）
    _write_result_xml(work_root, job_id)

    # 再次 get → 应从 XML 刷新
    job = manager.get(job_id)
    assert job["result"] is not None
    assert job["result"].alpha_g == pytest.approx(0.1234)

    # DB 也应已更新
    row = manager._db.get(job_id)
    import json
    db_result = json.loads(row["result"])
    assert db_result["alpha_g"] == pytest.approx(0.1234)
