# -*- coding: utf-8 -*-
"""FactSage 执行服务：真实调用 EquiSage.exe / mock 模拟"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from ..config import settings
from ..models import CalculationResult, JobRequest, SlagResult, SteelResult


async def run_calculation(
    job_id: str, request: JobRequest, paths: Dict[str, Any]
) -> CalculationResult:
    """根据配置选择真实执行或 mock"""
    if settings.mock_mode:
        return await _mock_calculation(request)
    return await _real_calculation(request, paths)


# ── 真实执行 ──────────────────────────────────────────────


def _run_factsage_blocking(mac_path: Path) -> int:
    """同步调用 EquiSage.exe（在线程池中执行）"""
    exe = settings.factsage_exe
    if not exe.exists():
        raise FileNotFoundError(f"找不到 EquiSage.exe: {exe}")

    cmd = [str(exe), "/EQUILIB", "/MACRO", str(mac_path)]

    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE

    p = subprocess.Popen(
        cmd, cwd=str(settings.factsage_dir), startupinfo=startupinfo
    )
    return p.wait(timeout=settings.factsage_timeout)


async def _real_calculation(
    request: JobRequest, paths: Dict[str, Any]
) -> CalculationResult:
    loop = asyncio.get_event_loop()
    rc = await loop.run_in_executor(None, _run_factsage_blocking, paths["mac_path"])
    if rc != 0:
        raise RuntimeError(f"FactSage 退出码: {rc}")

    xml_path: Path = paths["out_dir"] / f"{paths['prefix']}.xml"
    if not xml_path.exists():
        raise FileNotFoundError(f"FactSage 输出未找到: {xml_path}")

    from .result_parser import parse_result_xml

    return parse_result_xml(xml_path)


# ── Mock 模拟 ─────────────────────────────────────────────


async def _mock_calculation(request: JobRequest) -> CalculationResult:
    """基于输入参数生成合理的模拟结果（确定性，同输入=同输出）"""
    await asyncio.sleep(settings.mock_delay)

    total_steel_g = (
        request.steel.Fe_g
        + request.steel.Si_g
        + request.steel.Al_g
        + request.steel.O_g
        + request.steel.S_g
    )
    slag_total_g = request.slag.CaO_g + request.slag.Al2O3_g + request.slag.SiO2_g
    T_K = request.conditions.T_C + 273.15

    if request.target.element == "Al":
        return _mock_deoxidation(request, total_steel_g, slag_total_g, T_K)
    return _mock_desulfurization(request, total_steel_g, slag_total_g, T_K)


def _mock_deoxidation(
    req: JobRequest, steel_g: float, slag_g: float, T_K: float
) -> CalculationResult:
    alpha = round(req.steel.O_g * 62.5 + 0.002, 4)
    o_ppm = round(max(1, req.steel.O_g * 1e4 * 0.28), 1)
    return CalculationResult(
        alpha_Ca_g=alpha,
        T_K=T_K,
        P_atm=req.conditions.P_atm,
        steel=SteelResult(
            Fe_wtpct=round(req.steel.Fe_g / steel_g * 100, 3),
            Mn_wtpct=0.0,
            Si_wtpct=round(req.steel.Si_g / steel_g * 100 * 0.94, 4),
            Al_wtpct=round(req.target.value, 6),
            O_wtpct=round(o_ppm / 1e4, 5),
            O_ppm=o_ppm,
            S_wtpct=round(req.steel.S_g / steel_g * 100 * 0.82, 5),
            total_g=round(steel_g, 2),
        ),
        slag=SlagResult(
            CaO_wtpct=round(req.slag.CaO_g / slag_g * 100 * 1.05, 2),
            Al2O3_wtpct=round(req.slag.Al2O3_g / slag_g * 100 * 0.95, 2),
            SiO2_wtpct=round(req.slag.SiO2_g / slag_g * 100 * 0.88, 2),
            MnO_wtpct=0.52,
            FeO_wtpct=0.78,
            CaS_wtpct=2.14,
            total_g=round(slag_g + alpha * 0.6, 2),
        ),
    )


def _mock_desulfurization(
    req: JobRequest, steel_g: float, slag_g: float, T_K: float
) -> CalculationResult:
    alpha = round(req.steel.S_g * 35 + 0.005, 4)
    o_ppm = round(max(3, req.steel.O_g * 1e4 * 0.73), 1)
    return CalculationResult(
        alpha_Ca_g=alpha,
        T_K=T_K,
        P_atm=req.conditions.P_atm,
        steel=SteelResult(
            Fe_wtpct=round(req.steel.Fe_g / steel_g * 100, 3),
            Mn_wtpct=0.0,
            Si_wtpct=round(req.steel.Si_g / steel_g * 100 * 0.92, 4),
            Al_wtpct=round(req.steel.Al_g / steel_g * 100 * 0.86, 5),
            O_wtpct=round(o_ppm / 1e4, 5),
            O_ppm=o_ppm,
            S_wtpct=round(req.target.value, 6),
            total_g=round(steel_g, 2),
        ),
        slag=SlagResult(
            CaO_wtpct=round(req.slag.CaO_g / slag_g * 100 * 0.96, 2),
            Al2O3_wtpct=round(req.slag.Al2O3_g / slag_g * 100 * 0.93, 2),
            SiO2_wtpct=round(req.slag.SiO2_g / slag_g * 100 * 0.85, 2),
            MnO_wtpct=0.41,
            FeO_wtpct=0.58,
            CaS_wtpct=5.83,
            total_g=round(slag_g + alpha * 0.8, 2),
        ),
    )
