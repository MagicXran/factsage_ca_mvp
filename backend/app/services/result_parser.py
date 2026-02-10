# -*- coding: utf-8 -*-
"""解析 FactSage Equilib XML 结果（适配 FactSage 8.3 / 8.4）"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..models import CalculationResult, SlagResult, SteelResult


def parse_result_xml(xml_path: Path) -> CalculationResult:
    """解析 Equilib XML 并返回结构化结果"""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    header = root.find("header")
    page = root.find("page")
    if header is None or page is None:
        raise ValueError("XML 结构异常：缺少 <header> 或 <page>")

    alpha = float(page.attrib.get("alpha", "nan") or "nan")
    T = float(page.attrib.get("T", "nan") or "nan")
    P = float(page.attrib.get("P", "nan") or "nan")

    # 检测 FactSage 是否产出了有效计算结果
    if T == 0.0 and P == 0.0 and alpha == 0.0:
        raise ValueError(
            "FactSage 计算未产出有效结果（alpha/T/P 全为 0），"
            "请检查 .equi 输入文件格式是否正确"
        )

    spec_def = header.find("species_definition")
    if spec_def is None:
        raise ValueError("XML 缺少 <species_definition>")

    # 物种 → 相映射
    species_to_phase: dict[str, str] = {}
    phaseid_to_state: dict[str, str] = {}
    for sol in spec_def.findall("solution"):
        pid = sol.attrib.get("phase_id")
        st = sol.attrib.get("state", "")
        if pid:
            phaseid_to_state[pid] = st
        for sp in sol.iter("species"):
            sid = sp.attrib.get("id")
            if sid and pid:
                species_to_phase[sid] = pid

    # 物种名称映射
    species_name: dict[str, str] = {}
    for sp in header.iter("species"):
        sid = sp.attrib.get("id")
        if sid and sid not in species_name:
            species_name[sid] = sp.attrib.get("name", sid)

    # 识别钢液和渣液相
    steel_pid = _find_phase(phaseid_to_state, "Fe-liq")
    slag_pid = _find_phase(phaseid_to_state, "Slag-liq#1") or _find_phase(
        phaseid_to_state, "Slag-liq"
    )
    if steel_pid is None:
        raise ValueError("找不到钢液相 (Fe-liq)")

    # 检查是否有有效的 result 数据
    results = page.findall("result")
    valid_results = [r for r in results if r.attrib.get("id", "")]
    if not valid_results:
        raise ValueError(
            "FactSage 结果 XML 中无有效物种数据（所有 result id 为空），"
            "计算可能未收敛或输入参数异常"
        )

    # 收集各相质量
    phase_total_g: dict[str, float] = {}
    phase_species_g: dict[str, dict[str, float]] = {}
    for r in page.findall("result"):
        sid = r.attrib.get("id")
        if not sid:
            continue
        pid = species_to_phase.get(sid)
        if not pid:
            continue
        g = float(r.attrib.get("g", "0") or 0)
        phase_total_g[pid] = phase_total_g.get(pid, 0.0) + g
        sname = species_name.get(sid, sid)
        bucket = phase_species_g.setdefault(pid, {})
        bucket[sname] = bucket.get(sname, 0.0) + g

    def _wt(phase_id: str | None, species: str) -> float:
        if not phase_id:
            return 0.0
        tot = phase_total_g.get(phase_id, 0.0)
        if tot <= 0:
            return 0.0
        return 100.0 * phase_species_g.get(phase_id, {}).get(species, 0.0) / tot

    o_wt = _wt(steel_pid, "O")
    steel = SteelResult(
        Fe_wtpct=round(_wt(steel_pid, "Fe"), 4),
        Mn_wtpct=round(_wt(steel_pid, "Mn"), 4),
        Si_wtpct=round(_wt(steel_pid, "Si"), 4),
        Al_wtpct=round(_wt(steel_pid, "Al"), 6),
        O_wtpct=round(o_wt, 5),
        O_ppm=round(o_wt * 1e4, 1),
        S_wtpct=round(_wt(steel_pid, "S"), 5),
        total_g=round(phase_total_g.get(steel_pid, 0.0), 2),
    )

    slag = SlagResult(
        CaO_wtpct=round(_wt(slag_pid, "CaO"), 2),
        Al2O3_wtpct=round(_wt(slag_pid, "Al2O3"), 2),
        SiO2_wtpct=round(_wt(slag_pid, "SiO2"), 2),
        MnO_wtpct=round(_wt(slag_pid, "MnO"), 2),
        FeO_wtpct=round(_wt(slag_pid, "FeO"), 2),
        CaS_wtpct=round(_wt(slag_pid, "CaS"), 2),
        total_g=round(phase_total_g.get(slag_pid, 0.0), 2) if slag_pid else 0.0,
    )

    return CalculationResult(
        alpha_Ca_g=round(alpha, 4), T_K=T, P_atm=P, steel=steel, slag=slag
    )


def _find_phase(mapping: dict[str, str], keyword: str) -> str | None:
    for pid, state in mapping.items():
        if keyword in state:
            return pid
    return None
