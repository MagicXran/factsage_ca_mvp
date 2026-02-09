# -*- coding: utf-8 -*-
"""Jinja2 模板渲染：生成 .equi 和 .mac 文件"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Template

from ..config import settings
from ..models import JobRequest


def _read_text(path: Path) -> str:
    """读取模板文件，统一行尾为 \\n（防止 \\r\\r\\n 等异常行尾）"""
    raw = path.read_bytes().decode("utf-8")
    # 先处理 \r\r\n（损坏的双 CR），再处理正常 \r\n，最后处理孤立 \r
    raw = raw.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    return raw


def _write_text(path: Path, text: str) -> None:
    """写出文件，统一使用 Windows CRLF 行尾"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 先归一化为 \n，再统一转 \r\n
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8", newline="")


def render_job_templates(job_id: str, request: JobRequest) -> Dict[str, Any]:
    """渲染 .equi 和 .mac 模板，返回各路径信息"""
    job_dir = settings.work_root / job_id
    in_dir = job_dir / "input"
    out_dir = job_dir / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    prefix = "case"

    # 渲染 .equi
    equi_tpl = Template(_read_text(settings.templates_dir / "ca_equilib_estimate.equi.j2"))
    equi_text = equi_tpl.render(
        alpha_guess=request.alpha_guess,
        Fe_g=request.steel.Fe_g,
        Mn_field=request.steel.Mn_field,
        Si_g=request.steel.Si_g,
        Al_g=request.steel.Al_g,
        O_g=request.steel.O_g,
        S_g=request.steel.S_g,
        CaO_g=request.slag.CaO_g,
        Al2O3_g=request.slag.Al2O3_g,
        SiO2_g=request.slag.SiO2_g,
        T_C=request.conditions.T_C,
        P_atm=request.conditions.P_atm,
        target_elem=request.target.element,
        target_value=request.target.value,
    )
    equi_path = in_dir / f"{prefix}.equi"
    _write_text(equi_path, equi_text)

    # 渲染 .mac
    mac_tpl = Template(_read_text(settings.templates_dir / "run_equilib.mac.j2"))
    mac_text = mac_tpl.render(
        equi_file=str(equi_path),
        out_dir=str(out_dir) + "\\",
        prefix=prefix,
        T_C=request.conditions.T_C,
        P_atm=request.conditions.P_atm,
    )
    mac_path = in_dir / f"{prefix}.mac"
    _write_text(mac_path, mac_text)

    return {
        "job_dir": job_dir,
        "in_dir": in_dir,
        "out_dir": out_dir,
        "equi_path": equi_path,
        "mac_path": mac_path,
        "prefix": prefix,
    }
