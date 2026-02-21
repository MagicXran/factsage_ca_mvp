# -*- coding: utf-8 -*-
"""任务管理：SQLite 持久化 + 内存队列 + 后台 worker"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..models import (
    CalcType,
    CalculationResult,
    JobRequest,
    JobStatus,
)
from .db import JobDB
from .factsage_runner import run_calculation
from .template_renderer import render_job_templates

logger = logging.getLogger(__name__)


class JobManager:
    """单例任务管理器：SQLite 持久化，FIFO 队列，单 worker"""

    def __init__(self, db_path: Path | None = None) -> None:
        from ..config import settings
        self._db = JobDB(db_path or settings.db_path)
        self._db.cleanup_orphans()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    # ── 生命周期 ────────────────────────────────────────────

    async def start(self) -> None:
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("JobManager worker 已启动")

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._db.close()
        logger.info("JobManager worker 已停止")

    # ── 公开接口 ────────────────────────────────────────────

    async def submit(self, request: JobRequest) -> str:
        """提交任务，返回 job_id"""
        job_id = uuid.uuid4().hex[:8]
        created_at = datetime.now().isoformat(timespec="microseconds")
        self._db.insert(
            job_id=job_id,
            status=JobStatus.pending.value,
            calc_type=request.calc_type.value,
            request=request.model_dump_json(),
            created_at=created_at,
        )
        await self._queue.put(job_id)
        logger.info("任务 %s 已入队 (%s)", job_id, request.calc_type.value)
        return job_id

    def get(self, job_id: str) -> Optional[Dict]:
        """查询单个任务；result.xml 存在时优先从 XML 解析，结果回写 DB"""
        row = self._db.get(job_id)
        if not row:
            return self._recover_from_disk(job_id, request=None, created_at=None, calc_type=None)

        job = self._hydrate(row)

        if job["status"] != JobStatus.completed:
            return job

        # result.xml 优先策略：存在时解析并与 DB 比较，不同则更新
        solve_species = job["request"].solve_species if job["request"] else "Ca"
        xml_result = self._parse_result_from_disk(job_id, solve_species)
        if xml_result is not None and xml_result != job["result"]:
            self._db.update_result(
                job_id, JobStatus.completed.value, xml_result.model_dump_json()
            )
            job["result"] = xml_result
            logger.info("任务 %s 已从 result.xml 刷新结果", job_id)
        return job

    def list_all(self, limit: int = 100) -> List[Dict]:
        """列出所有任务（按创建时间倒序）"""
        jobs: List[Dict] = []
        for row in self._db.list_all(limit=limit):
            job = self._hydrate(row)
            # 历史列表要求 calc_type 可识别；异常数据仅跳过，不阻断接口
            if job["calc_type"] is None:
                logger.warning("任务 %s 的 calc_type 无效，已跳过列表输出", job.get("job_id"))
                continue
            jobs.append(job)
        return jobs

    # ── 内部方法 ─────────────────────────────────────────

    @staticmethod
    def _hydrate(row: Dict) -> Dict:
        """将 DB 行转换为业务 dict（反序列化 JSON 字段）"""
        result = None
        if row.get("result"):
            try:
                result = CalculationResult.model_validate_json(row["result"])
            except Exception as exc:
                logger.warning("任务 %s 的 result 字段反序列化失败: %s", row.get("job_id"), exc)
                result = None

        request = None
        if row.get("request"):
            try:
                request = JobRequest.model_validate_json(row["request"])
            except Exception as exc:
                logger.warning("任务 %s 的 request 字段反序列化失败: %s", row.get("job_id"), exc)
                request = None

        status = JobStatus.failed
        if row.get("status"):
            try:
                status = JobStatus(row["status"])
            except Exception as exc:
                logger.warning("任务 %s 的 status 字段无效: %s", row.get("job_id"), exc)

        calc_type = None
        if row.get("calc_type"):
            try:
                calc_type = CalcType(row["calc_type"])
            except Exception as exc:
                logger.warning("任务 %s 的 calc_type 字段无效: %s", row.get("job_id"), exc)

        return {
            "job_id": row["job_id"],
            "status": status,
            "calc_type": calc_type,
            "request": request,
            "created_at": row["created_at"],
            "result": result,
            "error": row.get("error"),
        }

    @staticmethod
    def _parse_result_from_disk(
        job_id: str, solve_species: str = "Ca"
    ) -> Optional[CalculationResult]:
        """从 work/<job_id>/out/result.xml 解析结果"""
        from ..config import settings
        from .result_parser import parse_result_xml

        xml_path = settings.work_root / job_id / "out" / "result.xml"
        if not xml_path.exists():
            return None
        try:
            return parse_result_xml(xml_path, solve_species=solve_species or "Ca")
        except Exception as exc:
            logger.warning("任务 %s 从 XML 恢复失败: %s", job_id, exc)
            return None

    @classmethod
    def _recover_from_disk(
        cls,
        job_id: str,
        request: JobRequest | None,
        created_at: str | None,
        calc_type: CalcType | None,
    ) -> Optional[Dict]:
        """DB 无记录时，允许通过磁盘中的 result.xml 直接查看历史"""
        from ..config import settings

        solve_species = request.solve_species if request else "Ca"
        result = cls._parse_result_from_disk(job_id, solve_species=solve_species)
        if result is None:
            return None

        xml_path = settings.work_root / job_id / "out" / "result.xml"
        recovered_created_at = created_at
        if recovered_created_at is None:
            recovered_created_at = datetime.fromtimestamp(
                xml_path.stat().st_mtime
            ).isoformat(timespec="seconds")

        return {
            "job_id": job_id,
            "status": JobStatus.completed,
            "calc_type": calc_type,
            "request": request,
            "created_at": recovered_created_at,
            "result": result,
            "error": None,
        }

    # ── 后台 worker ─────────────────────────────────────────

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            row = self._db.get(job_id)
            if not row:
                self._queue.task_done()
                continue

            self._db.update_status(job_id, JobStatus.running.value)
            logger.info("任务 %s 开始执行", job_id)

            try:
                request = JobRequest.model_validate_json(row["request"])
                paths = render_job_templates(job_id, request)
                result: CalculationResult = await run_calculation(
                    job_id, request, paths
                )
                self._db.update_result(
                    job_id, JobStatus.completed.value, result.model_dump_json()
                )
                logger.info("任务 %s 完成, %s=%.4f g", job_id, result.solve_species, result.alpha_g)
            except Exception as exc:
                self._db.update_error(job_id, JobStatus.failed.value, str(exc))
                logger.error("任务 %s 失败: %s", job_id, exc, exc_info=True)
            finally:
                self._queue.task_done()


# 全局单例
job_manager = JobManager()
