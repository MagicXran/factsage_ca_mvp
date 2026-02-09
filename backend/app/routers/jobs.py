# -*- coding: utf-8 -*-
"""API 路由：任务提交 / 查询 / 预设"""
from __future__ import annotations

import json
import logging
from typing import List

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..models import (
    JobListItem,
    JobRequest,
    JobResponse,
    JobStatus,
)
from ..services.job_manager import job_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["jobs"])


# ── 预设管理（从文件加载） ───────────────────────────────────


def _load_presets() -> dict:
    """扫描 presets_dir 下所有 .json 文件，按 job_id 或文件名索引"""
    presets: dict = {}
    d = settings.presets_dir
    if not d.exists():
        logger.warning("预设目录不存在: %s", d)
        return presets
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            key = data.get("job_id") or f.stem
            # 自动补充 calc_type（根据 target.element 推断）
            elem = data.get("target", {}).get("element", "")
            if "calc_type" not in data:
                data["calc_type"] = (
                    "deoxidation" if elem == "Al" else "desulfurization"
                )
            presets[key] = data
        except Exception as exc:
            logger.warning("加载预设 %s 失败: %s", f.name, exc)
    return presets


# ── 接口 ─────────────────────────────────────────────────


@router.post("/calculate")
async def calculate(request: JobRequest) -> JobResponse:
    """提交一次计算任务"""
    job_id = await job_manager.submit(request)
    job = job_manager.get(job_id)
    return JobResponse(
        job_id=job_id,
        status=job["status"],
        calc_type=job["calc_type"],
        created_at=job["created_at"],
    )


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JobResponse:
    """查询任务状态与结果"""
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        calc_type=job["calc_type"],
        created_at=job["created_at"],
        result=job["result"],
        error=job["error"],
    )


@router.get("/jobs")
async def list_jobs() -> List[JobListItem]:
    """列出所有任务"""
    return [
        JobListItem(
            job_id=j["job_id"],
            status=j["status"],
            calc_type=j["calc_type"],
            created_at=j["created_at"],
        )
        for j in job_manager.list_all()
    ]


@router.get("/presets")
async def list_presets():
    """列出可用预设名称"""
    return list(_load_presets().keys())


@router.get("/presets/{name}")
async def get_preset(name: str):
    """获取指定预设参数"""
    presets = _load_presets()
    if name not in presets:
        raise HTTPException(status_code=404, detail=f"预设 '{name}' 不存在")
    return presets[name]


@router.get("/config/info")
async def config_info():
    """返回当前运行模式信息"""
    return {
        "mock_mode": settings.mock_mode,
        "factsage_dir": str(settings.factsage_dir),
        "templates_dir": str(settings.templates_dir),
        "presets_dir": str(settings.presets_dir),
    }
