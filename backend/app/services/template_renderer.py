# -*- coding: utf-8 -*-
"""模板渲染：简单 {{KEY}} 占位符替换，生成 .equi 和 .mac 文件"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Tuple

from ..config import settings
from ..models import JobRequest


# ── 组合验证矩阵 ────────────────────────────────────────
# 每个 target_elem 对应: recommended(推荐), allowed(可用但警告), blocked(禁止)

COMBINATION_MATRIX: Dict[str, Dict[str, list]] = {
    "Al": {
        "recommended": ["Ca"],
        "allowed": ["CaO", "Mg", "Mn"],
        "blocked": ["Al", "Al2O3", "Si", "SiO2", "Ti", "MgO", "CaF2", "CaC2"],
    },
    "O": {
        "recommended": ["Al", "Si", "Mg", "Ca", "Ti"],
        "allowed": ["CaO", "Mn"],
        "blocked": ["MgO", "Al2O3", "SiO2", "CaF2", "CaC2"],
    },
    "S": {
        "recommended": ["CaO", "CaC2", "Ca", "Mg"],
        "allowed": ["CaF2", "Al"],
        "blocked": ["Si", "SiO2", "Mn", "Ti", "MgO", "Al2O3"],
    },
}


def validate_combination(
    solve_species: str, target_elem: str
) -> Tuple[str, str]:
    """验证 solve_species + target_elem 组合。

    Returns:
        (level, message) — level 为 "ok" / "warn" / "reject"
    """
    matrix = COMBINATION_MATRIX.get(target_elem)
    if matrix is None:
        return "reject", f"不支持的目标元素 '{target_elem}'，可选: Al, O, S"

    if solve_species in matrix["recommended"]:
        return "ok", ""

    if solve_species in matrix["allowed"]:
        rec = ", ".join(matrix["recommended"])
        return "warn", (
            f"组合 {solve_species}+{target_elem} 可能有效但非最优，"
            f"推荐使用: {rec}"
        )

    # blocked 或 未列出 → reject
    rec = ", ".join(matrix["recommended"])
    return "reject", (
        f"组合 {solve_species}+{target_elem} 物理意义不合理，"
        f"FactSage 极大概率无解。"
        f"建议将求解物质改为: {rec}"
    )


# ── 计算类型→目标元素映射 ──────────────────────────────
# 每个目标元素对应固定单位和默认值（冶金行业惯例）

CALC_TYPE_TARGETS: Dict[str, list] = {
    "deoxidation": [
        {"element": "Al", "unit": "wtpct", "label": "Al (脱氧PPT)", "default_value": 0.01},
        {"element": "O",  "unit": "ppm",   "label": "O (脱氧直控)", "default_value": 10},
    ],
    "desulfurization": [
        {"element": "S",  "unit": "ppm",   "label": "S (脱硫)",     "default_value": 50},
    ],
}


def get_calc_options() -> dict:
    """返回前端所需的全部计算选项配置"""
    species_by_target = {}
    for elem, matrix in COMBINATION_MATRIX.items():
        species_by_target[elem] = {
            "recommended": matrix["recommended"],
            "allowed": matrix["allowed"],
            "default": matrix["recommended"][0] if matrix["recommended"] else "",
        }
    return {
        "calc_types": CALC_TYPE_TARGETS,
        "species_by_target": species_by_target,
    }


# ── 白名单 ──────────────────────────────────────────────

_WHITELIST: Dict[str, Dict[str, str]] | None = None


def _load_whitelist() -> Dict[str, Dict[str, str]]:
    """加载并缓存 materials_whitelist.json"""
    global _WHITELIST
    if _WHITELIST is None:
        wl_path = Path(__file__).resolve().parent.parent.parent / "materials_whitelist.json"
        with open(wl_path, "r", encoding="utf-8") as f:
            _WHITELIST = json.load(f)
    return _WHITELIST


def get_whitelist() -> Dict[str, Dict[str, str]]:
    """公开接口，供 API 路由调用"""
    return _load_whitelist()


# ── 文件 I/O ────────────────────────────────────────────

def _read_text(path: Path) -> str:
    """读取模板文件，统一行尾为 \\n"""
    raw = path.read_bytes().decode("utf-8")
    raw = raw.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    return raw


def _write_text(path: Path, text: str) -> None:
    """写出文件，统一使用 Windows CRLF 行尾"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8", newline="")


def _render_tpl(template_text: str, variables: Dict[str, str]) -> str:
    """简单 {{KEY}} → value 替换"""
    result = template_text
    for key, value in variables.items():
        result = result.replace("{{" + key + "}}", str(value))
    # 检查未替换的占位符
    remaining = re.findall(r"\{\{(\w+)\}\}", result)
    if remaining:
        raise ValueError(f"模板中存在未替换的占位符: {remaining}")
    return result


# ── 单位换算 ────────────────────────────────────────────

def _target_to_mass_fraction(value: float, unit: str) -> float:
    """将目标值转换为质量分数"""
    unit = unit.lower().strip()
    if unit == "ppm":
        return value / 1e6
    # wtpct / wt% 等
    return value / 100.0


# ── 主渲染函数 ──────────────────────────────────────────

def render_job_templates(job_id: str, request: JobRequest) -> Dict[str, Any]:
    """渲染 .equi 和 .mac 模板，返回各路径信息"""
    job_dir = settings.work_root / job_id
    in_dir = job_dir / "input"
    out_dir = job_dir / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    prefix = "case"

    # 白名单校验
    whitelist = _load_whitelist()
    species = request.solve_species
    if species not in whitelist:
        raise ValueError(
            f"求解物质 '{species}' 不在白名单中。"
            f"可选: {', '.join(whitelist.keys())}"
        )
    state_token = whitelist[species]["default_state_token"]

    # 组合验证
    level, msg = validate_combination(species, request.target.element)
    if level == "reject":
        raise ValueError(msg)

    # 目标值 → 质量分数
    target_frac = _target_to_mass_fraction(
        request.target.value, request.target.unit
    )

    # Mn 字段处理
    mn_field = request.steel.Mn_field.strip()
    mn_value = mn_field if mn_field else " "

    # 构建替换变量
    equi_vars = {
        "A_GUESS": str(request.alpha_guess),
        "A_MAX": str(request.alpha_max),
        "STEEL_FE": str(request.steel.Fe_g),
        "STEEL_MN": mn_value,
        "STEEL_SI": str(request.steel.Si_g),
        "STEEL_AL": str(request.steel.Al_g),
        "STEEL_O": str(request.steel.O_g),
        "STEEL_S": str(request.steel.S_g),
        "SLAG_CAO": str(request.slag.CaO_g),
        "SLAG_AL2O3": str(request.slag.Al2O3_g),
        "SLAG_SIO2": str(request.slag.SiO2_g),
        "SOLVE_SPECIES": species,
        "SOLVE_STATE_TOKEN": state_token,
        "TEMP_C": str(request.conditions.T_C),
        "PRESS_ATM": str(request.conditions.P_atm),
        "TARGET_ELEM": request.target.element,
        "TARGET_VALUE_FRAC": str(target_frac),
    }

    # 渲染 .equi
    equi_tpl_text = _read_text(settings.templates_dir / "equilib_estimate.equi.tpl")
    equi_text = _render_tpl(equi_tpl_text, equi_vars)
    equi_path = in_dir / f"{prefix}.equi"
    _write_text(equi_path, equi_text)

    # 渲染 .mac
    mac_vars = {
        "EQUI_FILE": str(equi_path),
        "OUT_DIR": str(out_dir) + "\\",
        "TEMP_C": str(request.conditions.T_C),
        "PRESS_ATM": str(request.conditions.P_atm),
    }
    mac_tpl_text = _read_text(settings.templates_dir / "run_equilib.mac.tpl")
    mac_text = _render_tpl(mac_tpl_text, mac_vars)
    mac_path = in_dir / f"{prefix}.mac"
    _write_text(mac_path, mac_text)

    return {
        "job_dir": job_dir,
        "in_dir": in_dir,
        "out_dir": out_dir,
        "equi_path": equi_path,
        "mac_path": mac_path,
    }


def re_render_equi_alpha_max(equi_path: Path, new_a_max: float) -> None:
    """就地替换 .equi 文件中 ESTA 行的 A_MAX 值（供重试调用）"""
    text = _read_text(equi_path)
    # ESTA 行格式: 'ESTA' 'guess' 'max' '0'
    text = re.sub(
        r"('ESTA'\s+'[^']*'\s+')([^']*)('\s+'0')",
        lambda m: m.group(1) + str(new_a_max) + m.group(3),
        text,
    )
    _write_text(equi_path, text)
