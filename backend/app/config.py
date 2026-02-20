# -*- coding: utf-8 -*-
"""应用配置 —— 从 config.json 加载，支持环境变量覆盖"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# ── 基准目录 ──────────────────────────────────────────
# 打包模式 (PyInstaller): exe 所在目录
# 开发模式: backend/ 目录
_IS_FROZEN = getattr(sys, "frozen", False)
_BASE_DIR = (
    Path(sys.executable).resolve().parent
    if _IS_FROZEN
    else Path(__file__).resolve().parent.parent
)

_DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 8000},
    "factsage": {
        "dir": r"C:\FactSage",
        "exe_name": "EquiSage.exe",
        "timeout_seconds": 300,
    },
    "paths": {
        "work_root": "./work",
        "templates_dir": "templates" if _IS_FROZEN else "./templates",
        "presets_dir": "presets" if _IS_FROZEN else "./presets",
        "frontend_dir": "frontend" if _IS_FROZEN else "../frontend",
    },
    "mock": {"enabled": "auto", "delay_seconds": 1.5},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并，override 中的值覆盖 base"""
    merged = base.copy()
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


class Settings:
    """全局配置：config.json → 环境变量 → 自动检测"""

    def __init__(self, config_path: Path | None = None) -> None:
        cfg_path = config_path or _BASE_DIR / "config.json"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
        else:
            user_cfg = {}
        self._cfg = _deep_merge(_DEFAULT_CONFIG, user_cfg)

    # ── 路径解析 ──────────────────────────────────────────

    def _resolve(self, raw: str) -> Path:
        """相对路径基于 _BASE_DIR 解析，绝对路径原样返回"""
        p = Path(os.path.expandvars(raw))
        return p if p.is_absolute() else (_BASE_DIR / p).resolve()

    # ── FactSage ──────────────────────────────────────────

    @property
    def factsage_dir(self) -> Path:
        return Path(os.getenv("FACTSAGE_DIR") or self._cfg["factsage"]["dir"])

    @property
    def factsage_exe(self) -> Path:
        return self.factsage_dir / self._cfg["factsage"]["exe_name"]

    @property
    def factsage_timeout(self) -> int:
        return int(self._cfg["factsage"]["timeout_seconds"])

    # ── 路径 ──────────────────────────────────────────────

    @property
    def work_root(self) -> Path:
        return self._resolve(
            os.getenv("WORK_ROOT") or self._cfg["paths"]["work_root"]
        )

    @property
    def templates_dir(self) -> Path:
        return self._resolve(
            os.getenv("TEMPLATES_DIR") or self._cfg["paths"]["templates_dir"]
        )

    @property
    def presets_dir(self) -> Path:
        return self._resolve(
            os.getenv("PRESETS_DIR") or self._cfg["paths"]["presets_dir"]
        )

    @property
    def frontend_dir(self) -> Path:
        return self._resolve(
            os.getenv("FRONTEND_DIR") or self._cfg["paths"]["frontend_dir"]
        )

    # ── 服务器 ────────────────────────────────────────────

    @property
    def server_host(self) -> str:
        return os.getenv("HOST") or self._cfg["server"]["host"]

    @property
    def server_port(self) -> int:
        return int(os.getenv("PORT") or self._cfg["server"]["port"])

    # ── Mock ──────────────────────────────────────────────

    @property
    def mock_mode(self) -> bool:
        val = os.getenv("MOCK_MODE") or self._cfg["mock"]["enabled"]
        if isinstance(val, bool):
            return val
        val = str(val).lower()
        if val == "auto":
            return not self.factsage_exe.exists()
        return val in ("1", "true", "yes")

    @property
    def mock_delay(self) -> float:
        return float(self._cfg["mock"]["delay_seconds"])


settings = Settings()
