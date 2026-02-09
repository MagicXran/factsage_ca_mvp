# -*- coding: utf-8 -*-
"""任务管理：内存队列 + 后台 worker + 状态追踪"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from ..models import (
    CalcType,
    CalculationResult,
    JobRequest,
    JobStatus,
)
from .factsage_runner import run_calculation
from .template_renderer import render_job_templates

logger = logging.getLogger(__name__)


class JobManager:
    """单例任务管理器：FIFO 队列，每次只跑一个 FactSage 进程"""

    def __init__(self) -> None:
        self._jobs: Dict[str, dict] = {}
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
        logger.info("JobManager worker 已停止")

    # ── 公开接口 ────────────────────────────────────────────

    async def submit(self, request: JobRequest) -> str:
        """提交任务，返回 job_id"""
        job_id = uuid.uuid4().hex[:8]
        self._jobs[job_id] = {
            "job_id": job_id,
            "status": JobStatus.pending,
            "calc_type": request.calc_type,
            "request": request,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "result": None,
            "error": None,
        }
        await self._queue.put(job_id)
        logger.info("任务 %s 已入队 (%s)", job_id, request.calc_type.value)
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        return self._jobs.get(job_id)

    def list_all(self) -> List[dict]:
        return sorted(
            self._jobs.values(), key=lambda x: x["created_at"], reverse=True
        )

    # ── 后台 worker ─────────────────────────────────────────

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            job = self._jobs.get(job_id)
            if not job:
                self._queue.task_done()
                continue

            job["status"] = JobStatus.running
            logger.info("任务 %s 开始执行", job_id)

            try:
                request: JobRequest = job["request"]
                paths = render_job_templates(job_id, request)
                result: CalculationResult = await run_calculation(
                    job_id, request, paths
                )
                job["result"] = result
                job["status"] = JobStatus.completed
                logger.info("任务 %s 完成, alpha_Ca=%.4f g", job_id, result.alpha_Ca_g)
            except Exception as exc:
                job["error"] = str(exc)
                job["status"] = JobStatus.failed
                logger.error("任务 %s 失败: %s", job_id, exc, exc_info=True)
            finally:
                self._queue.task_done()


# 全局单例
job_manager = JobManager()
