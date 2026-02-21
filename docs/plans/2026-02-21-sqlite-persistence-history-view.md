# SQLite 持久化 + 历史查看功能 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用 SQLite 替代内存 Dict 实现任务持久化，支持通过 URL 参数 `?job_id=xxx` 查看历史任务的输入输出并下载结果文件。

**Architecture:** JobManager 底层存储从 `Dict[str, dict]` 切换为 SQLite 单表。新建 `db.py` 封装所有数据库操作，JobManager 调用 db 层读写。前端解析 URL 参数，复用现有输入/输出面板展示历史任务，历史表格 job_id 变为可点击链接。

**Tech Stack:** Python sqlite3 (标准库，零依赖) / FastAPI / Vanilla JS

---

## 设计决策记录

### 为什么用 SQLite 而不是 JSON 文件？
- 单用户桌面应用，SQLite 是最佳选择：零配置、ACID、单文件
- 比每个 job 写一个 meta.json 更可靠（原子写入 vs 文件损坏风险）
- 查询能力：按时间排序、按状态过滤，SQL 天然支持

### 为什么不用 aiosqlite？
- 单用户场景，SQLite 操作都是亚毫秒级
- 同步调用不会阻塞事件循环（数据量极小）
- 少一个依赖，少一层复杂度

### 数据库表设计
```sql
CREATE TABLE IF NOT EXISTS jobs (
    job_id     TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'pending',
    calc_type  TEXT NOT NULL,
    request    TEXT NOT NULL,   -- JobRequest.model_dump_json()
    created_at TEXT NOT NULL,
    result     TEXT,            -- CalculationResult.model_dump_json() | NULL
    error      TEXT             -- 错误信息 | NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
```

### 前端历史查看方案
- 复用现有输入面板 + 结果面板，不新建页面
- URL: `/?job_id=abc12345` → 自动加载该任务
- 历史表格 job_id 列变为 `<a href="?job_id=xxx">` 链接
- 查看历史时输入面板加"历史查看"视觉提示，表单只读

---

## Task 1: 新建 SQLite 数据库层 `db.py`

**Files:**
- Create: `backend/app/services/db.py`
- Test: `backend/tests/test_db.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_db.py
# -*- coding: utf-8 -*-
"""SQLite 数据库层测试"""
import json
import pytest
from pathlib import Path
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
```

**Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.db'`

**Step 3: 实现 db.py**

```python
# backend/app/services/db.py
# -*- coding: utf-8 -*-
"""SQLite 持久化层 —— 任务元数据存储"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id     TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'pending',
    calc_type  TEXT NOT NULL,
    request    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    result     TEXT,
    error      TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
"""


class JobDB:
    """轻量 SQLite 封装，同步操作，单连接"""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def insert(self, job_id: str, status: str, calc_type: str,
               request: str, created_at: str) -> None:
        self._conn.execute(
            "INSERT INTO jobs (job_id, status, calc_type, request, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, status, calc_type, request, created_at),
        )
        self._conn.commit()

    def update_status(self, job_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id)
        )
        self._conn.commit()

    def update_result(self, job_id: str, status: str, result: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET status = ?, result = ? WHERE job_id = ?",
            (status, result, job_id),
        )
        self._conn.commit()

    def update_error(self, job_id: str, status: str, error: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET status = ?, error = ? WHERE job_id = ?",
            (status, error, job_id),
        )
        self._conn.commit()

    def get(self, job_id: str) -> Optional[Dict]:
        cur = self._conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_all(self, limit: int = 100) -> List[Dict]:
        cur = self._conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cur.fetchall()]
```

**Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_db.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/app/services/db.py backend/tests/test_db.py
git commit -m "feat: add SQLite persistence layer (db.py)"
```

---

## Task 2: 改造 JobManager 使用 SQLite 后端

**Files:**
- Modify: `backend/app/services/job_manager.py` (全文重写)
- Modify: `backend/app/config.py:21-35` (新增 db_path 配置)
- Test: `backend/tests/test_job_manager.py`

**Step 1: 在 config.py 中添加 db_path 配置**

在 `_DEFAULT_CONFIG["paths"]` 中添加：
```python
"db_path": "./data/factsage.db",
```

在 `Settings` 类中添加属性：
```python
@property
def db_path(self) -> Path:
    return self._resolve(
        os.getenv("DB_PATH") or self._cfg["paths"]["db_path"]
    )
```

**Step 2: 写失败测试**

```python
# backend/tests/test_job_manager.py
# -*- coding: utf-8 -*-
"""JobManager 集成测试（使用 SQLite 后端）"""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

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
    assert job["status"] == "pending"


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
```

**Step 3: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_job_manager.py -v`
Expected: FAIL

**Step 4: 重写 job_manager.py**

```python
# backend/app/services/job_manager.py
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
        created_at = datetime.now().isoformat(timespec="seconds")
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
```

**Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_job_manager.py tests/test_db.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/app/config.py backend/app/services/job_manager.py backend/tests/test_job_manager.py
git commit -m "feat: migrate JobManager from in-memory Dict to SQLite"
```

---

## Task 3: API 层适配 —— JobResponse 增加 request 字段

**Files:**
- Modify: `backend/app/models.py:98-111` (JobResponse 增加 request 字段，JobListItem 增加 solve_species)
- Modify: `backend/app/routers/jobs.py:87-144` (适配新的 JobManager 返回格式)

**Step 1: 修改 models.py**

在 `JobResponse` 中增加 `request` 字段，用于历史查看时返回输入参数：

```python
class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    calc_type: Optional[CalcType] = None
    created_at: Optional[str] = None
    request: Optional[JobRequest] = None      # 新增：输入参数
    result: Optional[CalculationResult] = None
    error: Optional[str] = None
```

在 `JobListItem` 中增加 `solve_species` 字段，避免历史列表为了拿 solve_species 而逐个请求详情：

```python
class JobListItem(BaseModel):
    job_id: str
    status: JobStatus
    calc_type: CalcType
    created_at: str
    solve_species: str = "Ca"                 # 新增
```

**Step 2: 修改 routers/jobs.py**

`get_job` 端点现在返回 request：

```python
@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JobResponse:
    """查询任务状态与结果（含输入参数）"""
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        calc_type=job["calc_type"],
        created_at=job["created_at"],
        request=job["request"],
        result=job["result"],
        error=job["error"],
    )
```

`list_jobs` 端点增加 solve_species：

```python
@router.get("/jobs")
async def list_jobs() -> List[JobListItem]:
    """列出所有任务"""
    return [
        JobListItem(
            job_id=j["job_id"],
            status=j["status"],
            calc_type=j["calc_type"],
            created_at=j["created_at"],
            solve_species=j["request"].solve_species if j.get("request") else "Ca",
        )
        for j in job_manager.list_all()
    ]
```

`calculate` 端点适配（job_manager.get 返回格式不变，无需改动）。

**Step 3: 运行全部测试确认通过**

Run: `cd backend && python -m pytest -v`
Expected: ALL PASS

**Step 4: 手动验证 API**

启动服务后：
- `GET /api/jobs/xxx` 应返回包含 `request` 字段的完整 JSON
- `GET /api/jobs` 应返回包含 `solve_species` 的列表

**Step 5: Commit**

```bash
git add backend/app/models.py backend/app/routers/jobs.py
git commit -m "feat: add request field to JobResponse for history viewing"
```

---

## Task 4: 前端 —— URL 参数解析 + 历史任务加载 + 表格可点击

**Files:**
- Modify: `frontend/js/app.js` (增加 URL 参数解析、历史加载函数、表格链接化)
- Modify: `frontend/index.html` (增加历史查看模式的视觉提示)
- Modify: `frontend/css/style.css` (历史查看模式样式)

**Step 1: 修改 app.js —— init() 中增加 URL 参数检测**

在 `init()` 函数末尾（`await loadPreset()` 之后）添加：

```javascript
// 检查 URL 参数，加载历史任务
const params = new URLSearchParams(window.location.search);
const viewJobId = params.get("job_id");
if (viewJobId) {
    await loadHistoryJob(viewJobId);
}
```

**Step 2: 新增 loadHistoryJob() 函数**

在 `pollJob` 函数之后添加：

```javascript
// ── 历史任务加载 ──────────────────────────────────────

async function loadHistoryJob(jobId) {
    showLoading();
    try {
        const job = await api("GET", `/jobs/${jobId}`);
        if (!job) {
            showError("任务不存在: " + jobId);
            return;
        }

        // 填充输入参数（如果有 request 数据）
        if (job.request) {
            fillForm({
                calc_type: job.calc_type,
                steel: job.request.steel,
                slag: job.request.slag,
                conditions: job.request.conditions,
                target: job.request.target,
                solve_species: job.request.solve_species,
                alpha_guess: job.request.alpha_guess,
                alpha_max: job.request.alpha_max,
            });
            enterHistoryMode(jobId);
        }

        // 展示结果
        if (job.status === "completed" && job.result) {
            currentJobId = jobId;
            showResult(job.result, jobId);
        } else if (job.status === "failed") {
            showError(job.error || "计算失败");
        } else {
            showError("任务状态: " + job.status);
        }

        refreshHistory();
    } catch (e) {
        showError("加载历史任务失败: " + e.message);
    }
}

/** 进入历史查看模式：输入面板加提示，表单只读 */
function enterHistoryMode(jobId) {
    const panel = document.querySelector(".input-panel");
    // 添加历史模式提示条
    let banner = document.getElementById("historyBanner");
    if (!banner) {
        banner = document.createElement("div");
        banner.id = "historyBanner";
        banner.className = "history-banner";
        panel.insertBefore(banner, panel.querySelector("h2").nextSibling);
    }
    banner.innerHTML = `📋 正在查看历史任务 <code>${jobId}</code> <a href="/" class="btn-back">返回新建计算</a>`;
    banner.classList.remove("hidden");

    // 禁用所有输入
    panel.querySelectorAll("input, select").forEach(el => el.disabled = true);
    btnCalc.classList.add("hidden");
    btnPreset.classList.add("hidden");
}

/** 退出历史查看模式 */
function exitHistoryMode() {
    const banner = document.getElementById("historyBanner");
    if (banner) banner.classList.add("hidden");
    const panel = document.querySelector(".input-panel");
    panel.querySelectorAll("input, select").forEach(el => el.disabled = false);
    btnCalc.classList.remove("hidden");
    btnPreset.classList.remove("hidden");
}
```

**Step 3: 修改 refreshHistory() —— job_id 列变为可点击链接**

将历史表格渲染中的 `<td>${j.job_id}</td>` 改为：

```javascript
`<td><a href="?job_id=${j.job_id}" class="job-link">${j.job_id}</a></td>`
```

同时，solve_species 直接从 list 接口获取（不再逐个请求详情）：

```javascript
async function refreshHistory() {
    try {
        const jobs = await api("GET", "/jobs");
        if (!jobs.length) {
            historyEmpty.classList.remove("hidden");
            historyTbody.innerHTML = "";
            return;
        }
        historyEmpty.classList.add("hidden");

        const rows = jobs.slice(0, 50).map((j) => {
            const typeLabel = j.calc_type === "deoxidation" ? "脱氧" : "脱硫";
            const statusLabel = {
                pending: "等待中",
                running: "计算中",
                completed: "✓ 完成",
                failed: "✗ 失败",
            }[j.status] || j.status;
            return `<tr>
                <td><a href="?job_id=${j.job_id}" class="job-link">${j.job_id}</a></td>
                <td>${typeLabel}</td>
                <td>${j.solve_species || "Ca"}</td>
                <td>—</td>
                <td class="status-${j.status}">${statusLabel}</td>
                <td>${j.created_at}</td>
            </tr>`;
        });
        historyTbody.innerHTML = rows.join("");
    } catch (_) { /* ignore */ }
}
```

> **注意**：这里去掉了原来对每个 completed 任务逐个 GET 详情拿 alpha_g 的逻辑。
> 那个 N+1 查询本来就是性能隐患。如果需要在列表中显示 alpha_g，
> 应该在 JobListItem 中增加该字段，而不是前端逐个请求。
> 当前先简化为 "—"，点击进入详情页再看具体数值。

**Step 4: 修改 index.html —— 无需大改**

历史查看的 banner 是 JS 动态创建的，不需要改 HTML 结构。

**Step 5: 修改 style.css —— 添加历史模式样式**

在 CSS 文件末尾（`@media` 之前）添加：

```css
/* ── 历史查看模式 ────────────────────────────────── */
.history-banner {
    background: #fff3e0;
    border: 1px solid #ffb74d;
    border-radius: var(--radius);
    padding: 10px 16px;
    margin-bottom: 14px;
    font-size: .88rem;
    color: #e65100;
    display: flex;
    align-items: center;
    gap: 12px;
}
.history-banner code {
    background: #ffe0b2;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
}
.btn-back {
    margin-left: auto;
    color: var(--primary);
    text-decoration: none;
    font-weight: 600;
    font-size: .85rem;
}
.btn-back:hover { text-decoration: underline; }

.job-link {
    color: var(--primary);
    text-decoration: none;
    font-family: monospace;
}
.job-link:hover {
    text-decoration: underline;
    color: var(--primary-dark);
}
```

**Step 6: 手动验证**

1. 启动服务，提交一次计算
2. 在历史表格中确认 job_id 是可点击链接
3. 点击链接 → 页面刷新，URL 变为 `/?job_id=xxx`
4. 输入面板显示历史参数（只读），结果面板显示计算结果
5. 下载按钮可用
6. 点击"返回新建计算"→ 回到正常模式
7. 重启服务 → 历史记录仍在，点击仍可查看

**Step 7: Commit**

```bash
git add frontend/js/app.js frontend/css/style.css
git commit -m "feat: URL-based history viewing with clickable job links"
```

---

## Task 5: 端到端集成验证 + 边界情况处理

**Files:**
- Modify: `backend/app/services/job_manager.py` (处理启动时 pending/running 状态的孤儿任务)
- Test: `backend/tests/test_integration.py`

**Step 1: 处理孤儿任务**

服务重启时，SQLite 中可能有 `pending` 或 `running` 状态的任务（上次进程被杀时正在执行的）。
这些任务不会被重新入队，需要标记为 `failed`。

在 `JobManager.__init__` 末尾添加：

```python
# 启动时清理孤儿任务（上次进程异常退出遗留的 pending/running）
self._db.cleanup_orphans()
```

在 `db.py` 中添加：

```python
def cleanup_orphans(self) -> int:
    """将 pending/running 状态的孤儿任务标记为 failed"""
    cur = self._conn.execute(
        "UPDATE jobs SET status = 'failed', error = '服务重启，任务中断' "
        "WHERE status IN ('pending', 'running')"
    )
    self._conn.commit()
    return cur.rowcount
```

**Step 2: 写集成测试**

```python
# backend/tests/test_integration.py
# -*- coding: utf-8 -*-
"""端到端集成测试"""
import pytest
from pathlib import Path

from app.services.db import JobDB
from app.services.job_manager import JobManager
from app.models import JobRequest


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
    db.insert("orphan1", "running", "deoxidation", '{}', "2026-01-01T00:00:00")
    db.insert("orphan2", "pending", "deoxidation", '{}', "2026-01-01T00:00:01")
    db.insert("done1", "completed", "deoxidation", '{}', "2026-01-01T00:00:02")
    db.close()

    # 新实例启动 → 自动清理
    mgr = JobManager(db_path=db_path)
    assert mgr.get("orphan1")["status"].value == "failed"
    assert mgr.get("orphan2")["status"].value == "failed"
    assert mgr.get("done1")["status"].value == "completed"


@pytest.mark.asyncio
async def test_full_lifecycle(tmp_path):
    """完整生命周期：提交 → 查询 → 列表 → 重启后仍可查"""
    db_path = tmp_path / "lifecycle.db"
    mgr = JobManager(db_path=db_path)
    req = _make_request()

    # 提交
    job_id = await mgr.submit(req)
    job = mgr.get(job_id)
    assert job["status"].value == "pending"
    assert job["request"].solve_species == "Ca"

    # 列表
    jobs = mgr.list_all()
    assert len(jobs) == 1

    # 重启后仍可查
    mgr2 = JobManager(db_path=db_path)
    job2 = mgr2.get(job_id)
    assert job2 is not None
    # 注意：重启后 pending 会被清理为 failed
    assert job2["status"].value == "failed"
```

**Step 3: 运行全部测试**

Run: `cd backend && python -m pytest -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: orphan job cleanup on restart + integration tests"
```

---

## 变更文件汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/db.py` | 新建 | SQLite 数据库层 |
| `backend/app/services/job_manager.py` | 重写 | 从内存 Dict 迁移到 SQLite |
| `backend/app/config.py` | 修改 | 新增 `db_path` 配置项 |
| `backend/app/models.py` | 修改 | JobResponse 增加 request 字段 |
| `backend/app/routers/jobs.py` | 修改 | 适配新 JobManager + 返回 request |
| `frontend/js/app.js` | 修改 | URL 参数解析 + 历史加载 + 表格链接化 |
| `frontend/css/style.css` | 修改 | 历史查看模式样式 |
| `backend/tests/test_db.py` | 新建 | db 层单元测试 |
| `backend/tests/test_job_manager.py` | 新建 | JobManager 集成测试 |
| `backend/tests/test_integration.py` | 新建 | 端到端集成测试 |

## 不变的文件

- `frontend/index.html` — 无需修改，banner 由 JS 动态创建
- `backend/app/services/factsage_runner.py` — 不涉及
- `backend/app/services/result_parser.py` — 不涉及
- `backend/app/services/template_renderer.py` — 不涉及
- `backend/requirements.txt` — 无新依赖（sqlite3 是标准库）
