# -*- coding: utf-8 -*-
"""FastAPI 应用入口"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import jobs
from .services.job_manager import job_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "启动 FactSage 钢渣反应计算服务  mock=%s", settings.mock_mode
    )
    await job_manager.start()
    yield
    await job_manager.stop()


app = FastAPI(
    title="FactSage 钢渣反应计算",
    description="钢渣反应脱氧/脱硫 添加剂用量估算 API",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS（开发时前端可能从不同端口访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 验证异常处理：记录详细错误信息
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error("422 验证失败  url=%s  body=%s  errors=%s",
                 request.url, await request.body(), exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# 注册 API 路由
app.include_router(jobs.router)

# 挂载前端静态资源
_FE = settings.frontend_dir
if _FE.exists():
    app.mount("/css", StaticFiles(directory=_FE / "css"), name="css")
    app.mount("/js", StaticFiles(directory=_FE / "js"), name="js")

    @app.get("/")
    async def index():
        return FileResponse(_FE / "index.html")
else:
    logger.warning("前端目录不存在: %s，仅提供 API 服务", _FE)
