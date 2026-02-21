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
        """查询单个任务，返回包含反序列化对象的 dict"""
        row = self._db.get(job_id)
        if not row:
            return None
        return self._hydrate(row)

    def list_all(self, limit: int = 100) -> List[Dict]:
        """列出所有任务（按创建时间倒序）"""
        return [self._hydrate(r) for r in self._db.list_all(limit=limit)]

    # ── 内部方法 ─────────────────────────────────────────

    @staticmethod
    def _hydrate(row: Dict) -> Dict:
        """将 DB 行转换为业务 dict（反序列化 JSON 字段）"""
        result = None
        if row.get("result"):
            result = CalculationResult.model_validate_json(row["result"])
        request = JobRequest.model_validate_json(row["request"])
        return {
            "job_id": row["job_id"],
            "status": JobStatus(row["status"]),
            "calc_type": CalcType(row["calc_type"]),
            "request": request,
            "created_at": row["created_at"],
            "result": result,
            "error": row.get("error"),
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
