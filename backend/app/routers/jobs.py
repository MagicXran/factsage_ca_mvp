# -*- coding: utf-8 -*-
"""API 路由：任务提交 / 查询 / 预设"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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


@router.get("/validate-combination")
async def validate_combination_api(
    solve_species: str, target_elem: str
):
    """验证 solve_species + target_elem 组合是否可行"""
    from ..services.template_renderer import validate_combination
    level, message = validate_combination(solve_species, target_elem)
    return {"level": level, "message": message}


@router.post("/calculate")
async def calculate(request: JobRequest) -> JobResponse:
    """提交一次计算任务"""
    # 组合预检
    from ..services.template_renderer import validate_combination
    level, msg = validate_combination(
        request.solve_species, request.target.element
    )
    if level == "reject":
        raise HTTPException(status_code=400, detail=msg)

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


@router.get("/jobs/{job_id}/download")
async def download_result(job_id: str):
    """下载计算结果文件（result.xml + result.res 的 zip 包）"""
    out_dir = settings.work_root / job_id / "out"
    if not out_dir.exists():
        raise HTTPException(status_code=404, detail="任务输出目录不存在")

    files_to_zip = []
    for name in ("result.xml", "result.res"):
        p = out_dir / name
        if p.exists():
            files_to_zip.append(p)
    if not files_to_zip:
        raise HTTPException(status_code=404, detail="结果文件不存在")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files_to_zip:
            zf.write(p, p.name)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{job_id}_result.zip"'
        },
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


@router.get("/whitelist")
async def get_whitelist():
    """返回可选求解物质白名单"""
    from ..services.template_renderer import get_whitelist as _get_wl
    return _get_wl()


@router.get("/calc-options")
async def calc_options():
    """返回计算类型→目标元素→求解物质的完整选项配置"""
    from ..services.template_renderer import get_calc_options
    return get_calc_options()


@router.get("/config/info")
async def config_info():
    """返回当前运行模式信息"""
    return {
        "mock_mode": settings.mock_mode,
        "factsage_dir": str(settings.factsage_dir),
        "templates_dir": str(settings.templates_dir),
        "presets_dir": str(settings.presets_dir),
    }
