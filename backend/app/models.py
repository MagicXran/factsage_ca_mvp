# -*- coding: utf-8 -*-
"""Pydantic 数据模型"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── 枚举 ────────────────────────────────────────────────

class CalcType(str, Enum):
    deoxidation = "deoxidation"
    desulfurization = "desulfurization"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


# ─── 请求模型 ────────────────────────────────────────────

class SteelInput(BaseModel):
    Fe_g: float = Field(..., gt=0, description="Fe (g)")
    Mn_field: str = Field("", description="Mn 字段（留空=不加入Mn）")
    Si_g: float = Field(..., ge=0, description="Si (g)")
    Al_g: float = Field(..., ge=0, description="Al (g)")
    O_g: float = Field(..., ge=0, description="O (g)")
    S_g: float = Field(..., ge=0, description="S (g)")


class SlagInput(BaseModel):
    CaO_g: float = Field(..., ge=0, description="CaO (g)")
    Al2O3_g: float = Field(..., ge=0, description="Al₂O₃ (g)")
    SiO2_g: float = Field(..., ge=0, description="SiO₂ (g)")


class ConditionsInput(BaseModel):
    T_C: float = Field(..., description="温度 (°C)")
    P_atm: float = Field(1.0, gt=0, description="压力 (atm)")


class TargetInput(BaseModel):
    element: str = Field(..., description="目标元素 (Al / O / S)")
    value: float = Field(..., gt=0, description="目标含量值")
    unit: str = Field("wtpct", description="单位: ppm | wtpct")


class JobRequest(BaseModel):
    calc_type: CalcType
    steel: SteelInput
    slag: SlagInput
    conditions: ConditionsInput
    target: TargetInput
    solve_species: str = Field("Ca", description="求解物质（白名单校验）")
    alpha_guess: float = Field(0.5, gt=0, description="Alpha 初始猜测值")
    alpha_max: float = Field(10.0, gt=0, description="ESTA 搜索上限 (g)")


# ─── 结果模型 ────────────────────────────────────────────

class SteelResult(BaseModel):
    Fe_wtpct: float = 0.0
    Mn_wtpct: float = 0.0
    Si_wtpct: float = 0.0
    Al_wtpct: float = 0.0
    O_wtpct: float = 0.0
    O_ppm: float = 0.0
    S_wtpct: float = 0.0
    total_g: float = 0.0


class SlagResult(BaseModel):
    CaO_wtpct: float = 0.0
    Al2O3_wtpct: float = 0.0
    SiO2_wtpct: float = 0.0
    MnO_wtpct: float = 0.0
    FeO_wtpct: float = 0.0
    CaS_wtpct: float = 0.0
    total_g: float = 0.0


class CalculationResult(BaseModel):
    alpha_g: float = Field(..., description="求解物质需要量 (g)")
    solve_species: str = Field("Ca", description="求解物质名称")
    T_K: float = 0.0
    P_atm: float = 1.0
    steel: SteelResult = Field(default_factory=SteelResult)
    slag: SlagResult = Field(default_factory=SlagResult)


# ─── 响应模型 ────────────────────────────────────────────

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    calc_type: Optional[CalcType] = None
    created_at: Optional[str] = None
    result: Optional[CalculationResult] = None
    error: Optional[str] = None


class JobListItem(BaseModel):
    job_id: str
    status: JobStatus
    calc_type: CalcType
    created_at: str
