# FactSage 钢渣反应计算系统 — 技术设计文档

> 版本: 1.0 | 更新日期: 2026-03-06
> 适用范围: factsage_ca_mvp 项目

---

## 目录

1. [系统概览](#1-系统概览)
2. [冶金原理](#2-冶金原理)
3. [FactSage Equilib 计算原理](#3-factsage-equilib-计算原理)
4. [质量归一化规则](#4-质量归一化规则)
5. [系统架构](#5-系统架构)
6. [数据模型](#6-数据模型)
7. [完整计算流程](#7-完整计算流程)
8. [模板系统](#8-模板系统)
9. [工业物料与纯度换算](#9-工业物料与纯度换算)
10. [预设系统](#10-预设系统)
11. [重试与诊断机制](#11-重试与诊断机制)
12. [Mock 模式](#12-mock-模式)
13. [配置管理](#13-配置管理)
14. [文件清单](#14-文件清单)

---

## 1. 系统概览

本系统是一个**钢渣反应热力学计算平台**，封装 FactSage 8.3/8.4 的 Equilib 模块，为炼钢车间提供：

- **脱氧计算**：给定钢液成分和目标 Al/Si 含量，求解需要添加多少脱氧剂（铝锭、铝线、碳化硅等）
- **脱硫计算**：给定钢液成分和目标 S 含量，求解需要添加多少脱硫剂（白灰等）

核心价值：将 FactSage 的专业热力学计算能力，通过 Web 界面交付给不熟悉 FactSage 操作的工艺工程师。

### 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| 前端 | 原生 HTML/CSS/JS | 单页应用，零框架依赖 |
| 后端 | Python + FastAPI | 异步 API 服务 |
| 计算引擎 | FactSage EquiSage.exe | 热力学平衡计算 |
| 持久化 | SQLite | 任务状态与历史记录 |
| 部署 | PyInstaller 单文件 | 打包为 Windows EXE |

---

## 2. 冶金原理

### 2.1 脱氧（Deoxidation）

**工序位置**：转炉出钢后、LF 精炼前。

转炉吹炼结束时，钢液中溶解氧含量很高（300-600 ppm）。必须通过添加脱氧剂（Al、Si、SiC 等）与溶解氧反应，降低氧含量。

核心反应（以铝脱氧为例）：

```
2[Al] + 3[O] → (Al₂O₃)
```

- 方括号 `[ ]` 表示溶解在钢液中的元素
- 圆括号 `( )` 表示渣相中的氧化物
- 反应产物 Al₂O₃ 上浮进入渣层

**转炉出钢后的钢液特征**：
- Si ≈ 0.01%（吹炼几乎烧损殆尽）
- Mn ≈ 0.1%（大部分氧化进入渣中）
- Al ≈ 0.002%（极低）
- O ≈ 400 ppm（高氧状态）
- S ≈ 150 ppm（未变化）

### 2.2 脱硫（Desulfurization）

**工序位置**：LF 精炼初期，已完成脱氧。

脱氧完成后，钢液中氧含量已降至 ~20 ppm，此时具备脱硫的热力学条件。通过添加碱性渣料（CaO）实现脱硫。

核心反应：

```
[S] + (CaO) → (CaS) + [O]
```

脱硫的热力学驱动力取决于：
- 渣的碱度（CaO/SiO₂ 比）越高，脱硫能力越强
- 钢液中 [O] 越低，脱硫越有利（Le Chatelier 原理）
- 温度越高，脱硫越有利

**LF 精炼初期的钢液特征**：
- Si ≈ 0.25%（已通过硅铁合金化）
- Mn ≈ 0.5%（已合金化）
- Al ≈ 0.03%（脱氧后残余）
- O ≈ 20 ppm（已脱氧）
- S ≈ 150 ppm（待脱硫）

### 2.3 两个工序阶段的差异

| 参数 | 脱氧（转炉出钢后） | 脱硫（LF精炼初期） |
|------|:---:|:---:|
| O 含量 | ~400 ppm（高） | ~20 ppm（低） |
| Si 含量 | ~0.01%（极低） | ~0.25%（已合金化） |
| Mn 含量 | ~0.1%（低） | ~0.5%（已合金化） |
| Al 含量 | ~0.002%（极低） | ~0.03%（脱氧残余） |
| 渣量 | 少（转炉下渣） | 较多（LF 造渣） |

这就是为什么**脱氧和脱硫的预设必须使用不同的钢液成分**。

---

## 3. FactSage Equilib 计算原理

### 3.1 Equilib 模块简介

FactSage 的 Equilib 模块基于**吉布斯自由能最小化**原理，计算多组分、多相体系的热力学平衡态。

给定：
- 系统组成（各元素/化合物的初始量）
- 温度和压力
- 热力学数据库（FactPS、FTmisc、FToxid）

Equilib 求解使所有相的总吉布斯自由能 G_total 最小的平衡态。

### 3.2 ESTA 目标求解

本系统使用 Equilib 的 **ESTA（Estimate Alpha）** 功能进行**逆向求解**：

**正向问题**：给定添加量 α，求平衡态各组分含量 → Equilib 直接计算
**逆向问题**：给定目标含量，求需要的添加量 α → 需要 ESTA

ESTA 的工作方式：

```
在 [0, A_MAX] 区间内搜索 α 值，
使得平衡态中目标元素的含量 = 用户指定的目标值
```

在 `.equi` 文件中的配置：

```
'ESTA' '{{A_GUESS}}' '{{A_MAX}}' '0'
```

- `A_GUESS`：初始猜测值（帮助收敛）
- `A_MAX`：搜索上限（α 的最大值）
- `0`：搜索下限（固定为 0）

### 3.3 `<A>` 标记

在 `.equi` 模板的反应物列表中：

```
<A> {{SOLVE_SPECIES}}  =
```

`<A>` 是 FactSage 的特殊标记，表示该物质的量是**待求解的未知量**（即 alpha）。FactSage 会在 ESTA 区间内搜索这个量，使得目标约束得到满足。

### 3.4 目标约束

在 `.equi` 模板末尾：

```
277    C      0  1 SOLN-FELQ Fe {{TARGET_ELEM}} -1 {{TARGET_VALUE_FRAC}}
```

这一行告诉 FactSage：
- `C`：这是一个约束条件
- `SOLN-FELQ`：约束作用于钢液相（Fe-liquid）
- `{{TARGET_ELEM}}`：目标元素（Al、Si 或 S）
- `-1`：约束类型（质量分数约束）
- `{{TARGET_VALUE_FRAC}}`：目标质量分数值

### 3.5 计算输出

FactSage 计算完成后输出 `result.xml`，包含：
- `alpha`：求解得到的添加量（g）
- 各相（钢液、渣液、固相等）的组成
- 温度、压力等状态信息

---

## 4. 质量归一化规则

### 4.1 100g 基准

FactSage 以 **100g 钢液**为基准进行归一化计算。所有输入量都是基于这个基准的克数。

**铁律：钢液各组分之和必须精确等于 100.0g**

```
Fe_g + Mn_field + Si_g + Al_g + O_g + S_g = 100.000 g
```

### 4.2 验证示例

**脱氧预设**：
```
99.833 + 0.1 + 0.01 + 0.002 + 0.04 + 0.015 = 100.000 ✓
```

**脱硫预设**：
```
99.203 + 0.5 + 0.25 + 0.03 + 0.002 + 0.015 = 100.000 ✓
```

### 4.3 渣的处理

渣的各组分单独输入（CaO、Al₂O₃、SiO₂），不参与 100g 钢液约束。

**渣钢比** = 渣总量 / 100g 钢液

| 工序 | 渣总量 | 渣钢比 | 说明 |
|------|--------|--------|------|
| 脱氧 | 3.0g | 3% | 转炉下渣量少 |
| 脱硫 | 5.0g | 5% | LF 造渣量较多 |

### 4.4 实际换算

100g 基准计算出的结果，需按实际钢水量换算：

```
实际用量 = alpha_g × (实际钢水量 / 100g)
```

例如：alpha_g = 2.5g，钢水量 130 吨（130,000 kg）：

```
实际用量 = 2.5 × (130,000,000 / 100) = 3,250,000 g = 3,250 kg
```

---

## 5. 系统架构

### 5.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (index.html + app.js)            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ 输入面板  │  │ 结果面板  │  │ 历史面板  │  │ Tab栏  │ │
│  └─────┬────┘  └────▲─────┘  └────▲─────┘  └───┬────┘ │
└────────┼────────────┼────────────┼──────────────┼──────┘
         │ POST       │ GET        │ GET          │ GET
         ↓            │            │              ↓
┌────────────────────────────────────────────────────────┐
│                   FastAPI 后端                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │              routers/jobs.py                     │   │
│  │  POST /api/calculate     GET /api/jobs/{id}     │   │
│  │  GET  /api/presets/{name} GET /api/calc-options  │   │
│  └──────────────┬──────────────────────────────────┘   │
│                 │                                       │
│  ┌──────────────▼──────────────────────────────────┐   │
│  │           services/job_manager.py                │   │
│  │  SQLite 持久化 + asyncio Queue + Worker         │   │
│  └──────┬────────────────────────────────────┬─────┘   │
│         │                                    │          │
│  ┌──────▼───────────┐  ┌────────────────────▼──────┐  │
│  │ template_renderer │  │    factsage_runner        │  │
│  │ .equi + .mac 生成 │  │ EquiSage.exe 调用 + 重试 │  │
│  └──────────────────┘  └────────────┬──────────────┘  │
│                                      │                  │
│                         ┌────────────▼──────────────┐  │
│                         │     result_parser          │  │
│                         │ XML 解析 → CalculationResult│ │
│                         └───────────────────────────┘  │
└────────────────────────────────────────────────────────┘
         │
         ↓ subprocess
┌────────────────────┐
│  FactSage 8.3/8.4  │
│  EquiSage.exe      │
│  /EQUILIB /MACRO   │
└────────────────────┘
```

### 5.2 请求生命周期

```
用户点击"开始计算"
  │
  ↓ 前端构建 JSON body
POST /api/calculate
  │
  ├── 1. Pydantic 模型验证 (JobRequest)
  ├── 2. 工业物料校验（material_id → solve_species 自动设定）
  ├── 3. 组合验证（solve_species + target_element 合理性）
  ├── 4. 生成 job_id，写入 SQLite（status=pending）
  └── 5. 入队 asyncio.Queue
          │
          ↓ Worker 取出任务
  ├── 6. 更新状态为 running
  ├── 7. 渲染模板（.equi + .mac 文件）
  ├── 8. 调用 EquiSage.exe（子进程）
  ├── 9. 解析 result.xml
  ├──10. 工业物料用量换算（purity）
  └──11. 写入 SQLite（status=completed + result JSON）
          │
          ↓ 前端轮询
GET /api/jobs/{job_id}
  │
  └── 返回 JobResponse（含 CalculationResult）
          │
          ↓ 前端渲染结果
  显示 alpha_g、物料用量、钢液/渣组成
```

---

## 6. 数据模型

### 6.1 请求模型 (JobRequest)

```
JobRequest
├── calc_type: "deoxidation" | "desulfurization"
├── steel: SteelInput
│   ├── Fe_g: float          # 铁 (g)，必须 > 0
│   ├── Mn_field: str        # 锰 (g)，空字符串 = 不加入
│   ├── Si_g: float          # 硅 (g)，≥ 0
│   ├── Al_g: float          # 铝 (g)，≥ 0
│   ├── O_g: float           # 氧 (g)，≥ 0
│   └── S_g: float           # 硫 (g)，≥ 0
├── slag: SlagInput
│   ├── CaO_g: float         # 氧化钙 (g)
│   ├── Al2O3_g: float       # 氧化铝 (g)
│   └── SiO2_g: float        # 二氧化硅 (g)
├── conditions: ConditionsInput
│   ├── T_C: float           # 温度 (°C)
│   └── P_atm: float         # 压力 (atm)，默认 1.0
├── target: TargetInput
│   ├── element: str          # 目标元素 (Al / Si / S)
│   ├── value: float          # 目标含量值
│   └── unit: str             # 单位 (ppm / wtpct)
├── solve_species: str        # 求解物质（白名单校验）
├── alpha_guess: float        # ESTA 初始猜测值
├── alpha_max: float          # ESTA 搜索上限
├── material_id: str?         # 工业物料 ID（可选）
└── purity: float?            # 纯度百分比（可选，0-100）
```

### 6.2 结果模型 (CalculationResult)

```
CalculationResult
├── alpha_g: float            # 求解物质需要量 (g / 100g钢)
├── solve_species: str        # 求解物质名称
├── T_K: float                # 平衡温度 (K)
├── P_atm: float              # 平衡压力 (atm)
├── steel: SteelResult
│   ├── Fe_wtpct: float       # 平衡态 Fe (wt%)
│   ├── Mn_wtpct: float       # 平衡态 Mn (wt%)
│   ├── Si_wtpct: float       # 平衡态 Si (wt%)
│   ├── Al_wtpct: float       # 平衡态 Al (wt%)
│   ├── O_wtpct: float        # 平衡态 O (wt%)
│   ├── O_ppm: float          # 平衡态 O (ppm)
│   ├── S_wtpct: float        # 平衡态 S (wt%)
│   └── total_g: float        # 钢液总质量 (g)
├── slag: SlagResult
│   ├── CaO_wtpct: float      # 渣中 CaO (wt%)
│   ├── Al2O3_wtpct: float    # 渣中 Al₂O₃ (wt%)
│   ├── SiO2_wtpct: float     # 渣中 SiO₂ (wt%)
│   ├── MnO_wtpct: float      # 渣中 MnO (wt%)
│   ├── FeO_wtpct: float      # 渣中 FeO (wt%)
│   ├── CaS_wtpct: float      # 渣中 CaS (wt%)
│   └── total_g: float        # 渣总质量 (g)
├── material_id: str?         # 工业物料 ID
├── material_name: str?       # 工业物料名称
├── purity: float?            # 纯度百分比
└── material_amount_g: float? # 工业物料用量 (g)
```

### 6.3 Mn 字段的特殊处理

`Mn_field` 是一个**字符串**而非浮点数，因为 FactSage 模板中 Mn 的位置需要支持"不加入"场景：

- `Mn_field = "0.5"` → 模板中渲染为 `0.5 Mn`
- `Mn_field = ""` → 模板中渲染为空格 ` Mn`（FactSage 忽略该行）

这意味着 Mn 的值**不参与 Pydantic 的数值校验**，但必须纳入 100g 总量手动验证。

---

## 7. 完整计算流程

### 7.1 步骤详解

#### Step 1: 前端表单提交

```javascript
// app.js: submitCalc()
const body = {
    calc_type: "deoxidation",
    steel: { Fe_g: 99.833, Mn_field: "0.1", Si_g: 0.01, ... },
    slag: { CaO_g: 1.5, Al2O3_g: 0.5, SiO2_g: 1.0 },
    conditions: { T_C: 1600.0, P_atm: 1.0 },
    target: { element: "Al", value: 0.03, unit: "wtpct" },
    solve_species: "Al",
    alpha_guess: 0.05,
    alpha_max: 10,
    material_id: "al_ingot",
    purity: 99.9
};
```

#### Step 2: API 校验 (routers/jobs.py)

1. **Pydantic 自动校验**：字段类型、范围约束
2. **物料校验**：`material_id` 存在时，自动设定 `solve_species`，校验 `target_element` 一致性
3. **组合验证**：`validate_combination(solve_species, target_element)` 判断组合是否物理合理

组合验证矩阵（`COMBINATION_MATRIX`）：

| 目标元素 | 推荐求解物质 | 允许 | 禁止 |
|---------|:---:|:---:|:---:|
| Al | Al | — | Ca, Mg, Si, SiO₂, ... |
| Si | SiC | — | Ca, Mg, Al, ... |
| S | CaO | CaF₂ | Ca, Mg, Al, Si, ... |

#### Step 3: 任务入队 (job_manager.py)

```python
job_id = uuid.uuid4().hex[:8]    # 8 位随机 ID
self._db.insert(job_id, "pending", request_json)
await self._queue.put(job_id)    # 入队等待 worker 处理
```

#### Step 4: 模板渲染 (template_renderer.py)

将用户输入填入 `.equi` 和 `.mac` 模板。

关键变量替换：

| 占位符 | 来源 | 示例 |
|--------|------|------|
| `{{STEEL_FE}}` | request.steel.Fe_g | 99.833 |
| `{{STEEL_MN}}` | request.steel.Mn_field | 0.1 |
| `{{STEEL_SI}}` | request.steel.Si_g | 0.01 |
| `{{STEEL_AL}}` | request.steel.Al_g | 0.002 |
| `{{STEEL_O}}` | request.steel.O_g | 0.04 |
| `{{STEEL_S}}` | request.steel.S_g | 0.015 |
| `{{SLAG_CAO}}` | request.slag.CaO_g | 1.5 |
| `{{SLAG_AL2O3}}` | request.slag.Al2O3_g | 0.5 |
| `{{SLAG_SIO2}}` | request.slag.SiO2_g | 1.0 |
| `{{SOLVE_SPECIES}}` | request.solve_species | Al |
| `{{SOLVE_STATE_TOKEN}}` | 白名单查询 | (25,1,s-FactPS,#1) |
| `{{A_GUESS}}` | request.alpha_guess | 0.05 |
| `{{A_MAX}}` | request.alpha_max | 10 |
| `{{TEMP_C}}` | request.conditions.T_C | 1600 |
| `{{PRESS_ATM}}` | request.conditions.P_atm | 1 |
| `{{TARGET_ELEM}}` | request.target.element | Al |
| `{{TARGET_VALUE_FRAC}}` | value → 质量分数 | 0.0003 |

**单位换算**（`_target_to_mass_fraction`）：
- `ppm` → 除以 1,000,000
- `wtpct` → 除以 100

#### Step 5: FactSage 调用 (factsage_runner.py)

```python
cmd = [str(exe), "/EQUILIB", "/MACRO", str(mac_path)]
p = subprocess.Popen(cmd, cwd=factsage_dir)
p.wait(timeout=300)
```

- 以子进程方式调用 `EquiSage.exe`
- 在 Windows 上隐藏窗口（`STARTF_USESHOWWINDOW`）
- 超时 300 秒
- 在 asyncio 线程池中执行，不阻塞主事件循环

#### Step 6: 结果解析 (result_parser.py)

解析 `result.xml` 的 XML 结构：

```xml
<page alpha="2.5" T="1873.15" P="1.0">
  <result id="species_id" g="质量(g)" />
  ...
</page>
```

解析步骤：
1. 提取 `alpha`（求解结果）、`T`、`P`
2. 检测 "no solution"（alpha=0 且 T>0 且 P>0，或 .out 文件包含关键词）
3. 构建物种→相的映射（哪个物种属于钢液相、哪个属于渣液相）
4. 计算各相的质量百分比：`wt% = 100 × species_g / phase_total_g`
5. 返回 `CalculationResult`

#### Step 7: 工业物料换算 (factsage_runner.py)

```python
def _apply_material_amount(result, request):
    if request.material_id and request.purity:
        result.material_amount_g = alpha_g / (purity / 100.0)
```

**Purity 不参与 FactSage 计算本身**——它只在计算完成后，将纯物质需要量转换为工业物料用量。

---

## 8. 模板系统

### 8.1 .equi 文件（Equilib 输入）

`.equi` 文件定义了 FactSage Equilib 的完整计算配置，包括：

**控制参数区**：
```
'O' '13'      ← 输出格式控制
'O' '10'      ← 数值精度控制
'O' '7'       ← 迭代限制
'O' '4'       ← ESTA 求解配置
  'ESTA' '0.05' '10' '0'
```

**反应物定义区**（三行，分段输入）：

```
# 第一行：钢液主要元素
Fe + Mn + Si + Al +

# 第二行：微量元素 + 渣组分
O + S + CaO + Al2O3 +

# 第三行：渣 + 待求解物质
SiO2 + <A> Al =
```

每种物质后面跟随**状态标记**（相和数据库信息）：
```
(25,1,s-FactPS,#1)    ← 25°C 参考态，纯固体，FactPS 数据库
(25,1,g-FactPS,#1)    ← 25°C 参考态，气体，FactPS 数据库
(25,1,s1-FactPS,#1)   ← 25°C 参考态，固体相1，FactPS 数据库
```

**溶液相/固溶体定义区**（`'SS'` 区段）：
定义了 292 种可能生成的物种和溶液相模型，包括：
- `SOLN-FELQ`：Fe-液相（钢液）
- `SOLN-SLAGA`：渣液相
- `SOLN-SPINB`：尖晶石固溶体
- `SOLN-OLIVA`：橄榄石固溶体
- 等...

**约束条件**（最后一行）：
```
277    C      0  1 SOLN-FELQ Fe Al -1 0.0003
```
含义：在钢液相（FELQ）中，Al 的质量分数 = 0.0003（即 0.03 wt%）。

### 8.2 .mac 文件（Macro 脚本）

`.mac` 文件控制 FactSage 的执行流程：

```
OPEN %EquiFile          ← 打开 .equi 文件
SET FINAL T 1600        ← 设置温度
SET FINAL P 1           ← 设置压力
CALC                    ← 执行计算
SAVE "result.xml"       ← 保存 XML 结果
SAVE "result.res"       ← 保存二进制结果
END
```

### 8.3 模板渲染安全

模板使用简单的 `{{KEY}} → value` 字符串替换。渲染完成后会检查是否有未替换的占位符，如果有则抛出异常。

所有值来自 Pydantic 校验后的数据，类型安全由模型约束保证。

---

## 9. 工业物料与纯度换算

### 9.1 设计理念

FactSage 计算的是**纯物质**的热力学平衡。但实际生产中使用的是**工业物料**（含有杂质）。

```
纯物质需要量（alpha_g）──[纯度换算]──→ 工业物料用量（material_amount_g）
```

### 9.2 核心公式

```
material_amount_g = alpha_g / (purity / 100)
```

| 场景 | alpha_g | purity | material_amount_g | 说明 |
|------|---------|--------|-------------------|------|
| 铝锭脱氧 | 2.50g | 99.9% | 2.503g | 铝锭杂质极少 |
| 70碳化硅脱氧 | 1.80g | 70% | 2.571g | SiC 含量只有 70% |
| 白灰脱硫 | 0.53g | 85% | 0.624g | 白灰含 CaO 约 85% |

### 9.3 工业物料配置

`backend/industrial_materials.json` 定义了所有可用物料：

```json
{
  "al_ingot": {
    "name": "铝锭",
    "solve_species": "Al",        // FactSage 求解物质
    "target_element": "Al",       // 对应目标元素
    "target_unit": "wtpct",       // 单位
    "calc_type": "deoxidation",   // 所属计算类型
    "default_purity": 99.9,       // 默认纯度 (%)
    "purity_min": 95.0,           // 纯度下限
    "purity_max": 100.0           // 纯度上限
  }
}
```

**物料→求解物质的自动映射**：选择物料后，`solve_species` 和 `target_element` 自动确定，用户无需手动设置。

### 9.4 Purity 在系统中的流转

```
前端: 物料选择 → 自动填入 default_purity → 用户可修改
  ↓
API: JobRequest.purity（Pydantic 校验：0 < purity ≤ 100）
  ↓
FactSage: ❌ 不参与（只计算纯物质平衡）
  ↓
后处理: _apply_material_amount() ← 唯一使用位置
  ↓
前端: 显示 "铝锭用量 2.503g (纯度 99.9%)"
```

---

## 10. 预设系统

### 10.1 预设文件

预设存放在 `backend/presets/` 目录下，每个 JSON 文件对应一个预设方案。

当前预设：

| 文件 | 用途 | 工序阶段 |
|------|------|---------|
| `deox_Al_target.json` | 铝脱氧预设 | 转炉出钢后 |
| `desul_S_target.json` | 白灰脱硫预设 | LF 精炼初期 |

### 10.2 前端加载逻辑

```javascript
const TYPE_TO_PRESET = {
    deoxidation: "deox_Al_target",
    desulfurization: "desul_S_target",
};
```

切换 Tab（脱氧/脱硫）时，自动加载对应预设并填充表单。

### 10.3 预设内容结构

预设文件的结构与 `JobRequest` 完全一致（加上 `material_id` 和 `purity`），前端通过 `fillForm()` 直接映射到表单字段。

---

## 11. 重试与诊断机制

### 11.1 ESTA 搜索失败

当 FactSage 在给定的 `[0, A_MAX]` 区间内找不到满足目标约束的 alpha 值时，会输出 "no solution"。

### 11.2 自动重试梯度

```python
_RETRY_STEPS = [1, 10, 100]

def _build_retry_steps(user_max):
    larger = sorted(s for s in _RETRY_STEPS if s > user_max)
    return [user_max] + larger
```

重试策略：
1. 首先使用用户指定的 `alpha_max`
2. 如果无解，**只向上扩展**（物理依据：更小的区间是子集，不可能有解）
3. 依次尝试更大的梯度（10, 100）

示例：用户 `alpha_max = 5`
→ 重试序列: `[5, 10, 100]`

### 11.3 重试时的 .equi 修改

```python
def re_render_equi_alpha_max(equi_path, new_a_max):
    # 用正则替换 ESTA 行中的 A_MAX 值
    text = re.sub(
        r"('ESTA'\s+'[^']*'\s+')([^']*)('\s+'0')",
        lambda m: m.group(1) + str(new_a_max) + m.group(3),
        text,
    )
```

直接就地修改已渲染的 `.equi` 文件，只改 `A_MAX` 值，其他参数不变。

### 11.4 诊断消息

所有梯度都失败后，生成用户可读的诊断信息：

```
FactSage 在所有尝试的 ESTA 区间内均未找到解。
当前组合: 求解物质=Al, 目标元素=Al
已尝试的 A_MAX 梯度: [10, 100]

建议:
  1. 放宽目标值（当前 0.03 wtpct）
  2. 增大 alpha_max（当前 10）
```

---

## 12. Mock 模式

### 12.1 自动检测

```python
@property
def mock_mode(self) -> bool:
    val = self._cfg["mock"]["enabled"]
    if val == "auto":
        return not self.factsage_exe.exists()  # 没有 FactSage → 自动 Mock
```

如果 EquiSage.exe 不存在（开发环境），自动启用 Mock 模式。

### 12.2 Mock 计算逻辑

Mock 不调用 FactSage，而是基于输入参数用简单公式生成"合理的"模拟结果：

**脱氧 Mock**：
```python
alpha = O_g * 62.5 + 0.002    # alpha 与氧含量正相关
o_ppm = max(1, O_g * 1e4 * 0.28)  # 脱氧后残余 O
```

**脱硫 Mock**：
```python
alpha = S_g * 35 + 0.005      # alpha 与硫含量正相关
```

Mock 结果是**确定性的**（同输入 = 同输出），方便前端开发和测试。

---

## 13. 配置管理

### 13.1 配置层次

```
默认配置 (_DEFAULT_CONFIG)
    ← 覆盖 ← config.json（用户配置文件）
        ← 覆盖 ← 环境变量
```

### 13.2 关键配置项

| 配置路径 | 环境变量 | 默认值 | 说明 |
|---------|---------|--------|------|
| server.host | HOST | 127.0.0.1 | 监听地址 |
| server.port | PORT | 8000 | 监听端口 |
| factsage.dir | FACTSAGE_DIR | C:\FactSage | FactSage 安装目录 |
| factsage.timeout_seconds | — | 300 | 计算超时 (秒) |
| paths.work_root | WORK_ROOT | ./work | 工作目录 |
| paths.db_path | DB_PATH | ./data/factsage.db | SQLite 路径 |
| mock.enabled | MOCK_MODE | auto | Mock 模式开关 |

### 13.3 路径解析规则

- 相对路径：基于 `_BASE_DIR`（开发模式下为 `backend/`，打包模式下为 exe 所在目录）
- 绝对路径：原样使用
- 支持环境变量展开（`os.path.expandvars`）

---

## 14. 文件清单

```
factsage_ca_mvp/
├── backend/
│   ├── app/
│   │   ├── config.py                 # 配置管理
│   │   ├── models.py                 # Pydantic 数据模型
│   │   ├── main.py                   # FastAPI 应用入口
│   │   ├── routers/
│   │   │   └── jobs.py               # API 路由
│   │   └── services/
│   │       ├── job_manager.py        # 任务管理（SQLite + Queue）
│   │       ├── factsage_runner.py    # FactSage 调用 + Mock + 重试
│   │       ├── template_renderer.py  # 模板渲染 + 组合验证
│   │       ├── result_parser.py      # XML 结果解析
│   │       └── db.py                 # SQLite 数据库操作
│   ├── templates/
│   │   ├── equilib_estimate.equi.tpl # Equilib 输入模板
│   │   └── run_equilib.mac.tpl       # Macro 执行模板
│   ├── presets/
│   │   ├── deox_Al_target.json       # 脱氧预设
│   │   └── desul_S_target.json       # 脱硫预设
│   ├── industrial_materials.json     # 工业物料配置
│   ├── materials_whitelist.json      # 求解物质白名单
│   └── config.json                   # 用户配置（可选）
├── frontend/
│   ├── index.html                    # 单页应用 HTML
│   ├── css/style.css                 # 样式
│   └── js/app.js                     # 前端逻辑
└── docs/
    └── system-design.md              # 本文档
```
