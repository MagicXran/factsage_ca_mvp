#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成《工业仿真专家经验数字化封装与服务化平台技术方案》Word 文档
"""
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

# ── 颜色常量 ──
PRIMARY = RGBColor(0x1A, 0x3C, 0x6E)
SECONDARY = RGBColor(0x2E, 0x5C, 0xA8)
ACCENT = RGBColor(0x3B, 0x7D, 0xD8)
DARK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x66, 0x66, 0x66)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x27, 0xAE, 0x60)
HEADER_BG = "1A3C6E"
ALT_BG = "F4F7FB"
LIGHT_BG = "E8EFF8"

doc = Document()

# ── 全局样式设置 ──
style = doc.styles["Normal"]
style.font.name = "宋体"
style.font.size = Pt(12)
style.font.color.rgb = DARK
style.paragraph_format.line_spacing = Pt(22)
style.paragraph_format.space_after = Pt(6)
style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

# 页边距
for section in doc.sections:
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.17)
    section.right_margin = Cm(3.17)


def set_cell_shading(cell, color):
    """设置单元格背景色"""
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color)
    shading.set(qn("w:val"), "clear")
    cell._tc.get_or_add_tcPr().append(shading)


def add_heading_styled(text, level=1):
    """添加带样式的标题"""
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.name = "微软雅黑"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
        if level == 1:
            run.font.size = Pt(18)
            run.font.color.rgb = PRIMARY
        elif level == 2:
            run.font.size = Pt(15)
            run.font.color.rgb = SECONDARY
        elif level == 3:
            run.font.size = Pt(13)
            run.font.color.rgb = ACCENT
    return h


def add_para(text, bold=False, indent_cm=0, alignment=None, font_name=None, font_size=None, color=None):
    """添加正文段落"""
    para = doc.add_paragraph()
    if alignment:
        para.alignment = alignment
    else:
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    para.paragraph_format.line_spacing = Pt(22)
    para.paragraph_format.space_after = Pt(6)
    if indent_cm:
        para.paragraph_format.first_line_indent = Cm(indent_cm)
    run = para.add_run(text)
    run.font.name = font_name or "宋体"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name or "宋体")
    run.font.size = font_size or Pt(12)
    run.bold = bold
    if color:
        run.font.color.rgb = color
    return para


def add_rich_para(segments, indent_cm=0, alignment=None):
    """添加富文本段落 segments = [(text, {bold, font, size, color, italic}), ...]"""
    para = doc.add_paragraph()
    para.alignment = alignment or WD_ALIGN_PARAGRAPH.JUSTIFY
    para.paragraph_format.line_spacing = Pt(22)
    para.paragraph_format.space_after = Pt(6)
    if indent_cm:
        para.paragraph_format.first_line_indent = Cm(indent_cm)
    for text, fmt in segments:
        run = para.add_run(text)
        fn = fmt.get("font", "宋体")
        run.font.name = fn
        run._element.rPr.rFonts.set(qn("w:eastAsia"), fn)
        run.font.size = fmt.get("size", Pt(12))
        run.bold = fmt.get("bold", False)
        run.italic = fmt.get("italic", False)
        if "color" in fmt:
            run.font.color.rgb = fmt["color"]
    return para


def add_table(headers, rows, col_widths=None):
    """添加格式化表格"""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"

    # 表头
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(h)
        run.bold = True
        run.font.name = "微软雅黑"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
        run.font.size = Pt(11)
        run.font.color.rgb = WHITE
        set_cell_shading(cell, HEADER_BG)

    # 数据行
    for r_idx, row_data in enumerate(rows):
        for c_idx, cell_text in enumerate(row_data):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = ""
            p = cell.paragraphs[0]
            # 首列居中加粗
            if c_idx == 0 and len(headers) > 2:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(str(cell_text))
            run.font.name = "宋体"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            run.font.size = Pt(11)
            if c_idx == 0:
                run.bold = True
            # 交替背景
            if r_idx % 2 == 1:
                set_cell_shading(cell, ALT_BG)

    # 列宽
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Cm(w)

    doc.add_paragraph()  # 表后空行
    return table


# ══════════════════════════════════════════════════
#  封面
# ══════════════════════════════════════════════════
for _ in range(4):
    doc.add_paragraph()

# 密级
p_cls = doc.add_paragraph()
p_cls.alignment = WD_ALIGN_PARAGRAPH.RIGHT
run = p_cls.add_run("【内部资料  注意保存】")
run.font.name = "微软雅黑"
run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
run.font.size = Pt(10)
run.font.color.rgb = RED
run.bold = True

for _ in range(3):
    doc.add_paragraph()

# 主标题
for line in ["工业仿真专家经验", "数字化封装与服务化平台"]:
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_title.add_run(line)
    run.font.name = "微软雅黑"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    run.font.size = Pt(28)
    run.font.color.rgb = PRIMARY
    run.bold = True

# 分隔线
p_sep = doc.add_paragraph()
p_sep.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p_sep.add_run("━" * 40)
run.font.size = Pt(10)
run.font.color.rgb = ACCENT

# 副标题
p_sub = doc.add_paragraph()
p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_sub.paragraph_format.space_before = Pt(12)
run = p_sub.add_run("技  术  方  案")
run.font.name = "微软雅黑"
run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
run.font.size = Pt(22)
run.font.color.rgb = SECONDARY

p_sub2 = doc.add_paragraph()
p_sub2.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p_sub2.add_run("基于知识资产化理念的仿真应用托管平台建设方案")
run.font.name = "微软雅黑"
run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
run.font.size = Pt(14)
run.font.color.rgb = GRAY

for _ in range(5):
    doc.add_paragraph()

# 版本信息
for label, value, vc in [
    ("版 本 号：", "V1.0", DARK),
    ("编制日期：", "2026年3月", DARK),
    ("密    级：", "内部", RED),
]:
    p_info = doc.add_paragraph()
    p_info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p_info.add_run(label)
    r1.font.name = "微软雅黑"
    r1._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    r1.font.size = Pt(12)
    r1.font.color.rgb = GRAY
    r2 = p_info.add_run(value)
    r2.font.name = "微软雅黑"
    r2._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    r2.font.size = Pt(12)
    r2.font.color.rgb = vc
    r2.bold = label == "密    级："

# ══════════════════════════════════════════════════
#  分页 + 目录页
# ══════════════════════════════════════════════════
doc.add_page_break()

p_toc_title = doc.add_paragraph()
p_toc_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_toc_title.paragraph_format.space_after = Pt(24)
run = p_toc_title.add_run("目    录")
run.font.name = "微软雅黑"
run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
run.font.size = Pt(20)
run.font.color.rgb = PRIMARY
run.bold = True

# 手动目录（python-docx 不直接支持 TOC 自动字段，手写目录更可控）
toc_items = [
    ("一、项目背景与战略定位", 1),
    ("    1.1  行业痛点分析", 2),
    ("    1.2  政策机遇与技术趋势", 2),
    ("    1.3  项目定位与目标", 2),
    ("二、核心理念：专家经验数字化封装方法论", 1),
    ("    2.1  知识工程四步法模型（KE4S）", 2),
    ("    2.2  方法论的通用性与可扩展性", 2),
    ("三、平台总体架构设计", 1),
    ("    3.1  架构设计原则", 2),
    ("    3.2  三层架构体系", 2),
    ("    3.3  核心能力：统一调度引擎", 2),
    ("四、典型案例：FactSage 热力学计算应用", 1),
    ("    4.1  业务场景与需求分析", 2),
    ("    4.2  专家经验封装过程", 2),
    ("    4.3  应用效果对比", 2),
    ("五、标准化接入机制", 1),
    ("    5.1  接入协议总览", 2),
    ("    5.2  Webapp 接入能力清单", 2),
    ("    5.3  任务生命周期与状态流转", 2),
    ("    5.4  安全与可靠性保障", 2),
    ("六、预期效益与推广价值", 1),
    ("    6.1  经济效益分析", 2),
    ("    6.2  社会效益与知识传承价值", 2),
    ("    6.3  推广路径与生态愿景", 2),
    ("附录A  术语表", 1),
]
for item_text, level in toc_items:
    p_toc = doc.add_paragraph()
    p_toc.paragraph_format.space_after = Pt(2)
    run = p_toc.add_run(item_text)
    fn = "微软雅黑" if level == 1 else "宋体"
    run.font.name = fn
    run._element.rPr.rFonts.set(qn("w:eastAsia"), fn)
    run.font.size = Pt(12) if level == 1 else Pt(11)
    run.bold = level == 1
    run.font.color.rgb = PRIMARY if level == 1 else DARK

# ══════════════════════════════════════════════════
#  第一章：项目背景与战略定位
# ══════════════════════════════════════════════════
doc.add_page_break()
add_heading_styled("一、项目背景与战略定位", 1)

add_heading_styled("1.1  行业痛点分析", 2)

add_para(
    "当前，我国冶金、材料、化工等流程工业领域面临一个深层次的结构性矛盾："
    "大量核心工艺知识以\u201C隐性经验\u201D的形态存在于少数资深专家的头脑之中，"
    "未能实现系统化沉淀与规模化复用。这一现象引发了以下关键痛点：",
    indent_cm=0.75,
)

add_rich_para([
    ("专家经验的脆弱性与不可复制性。", {"bold": True, "font": "微软雅黑"}),
    ("以钢铁冶炼过程中的热力学平衡计算为例，一位资深冶金工程师需要掌握钢液-渣系"
     "多元多相平衡理论、了解 FactSage 等专业仿真软件的操作范式、并具备根据生产工况"
     "调整模型参数的工程判断力。这种复合型能力的培养周期通常在 5—10 年以上，且高度"
     "依赖个体经验积累，难以通过传统培训手段快速复制。", {}),
], indent_cm=0.75)

add_rich_para([
    ("仿真软件的\u201C高门槛-低效率\u201D困境。", {"bold": True, "font": "微软雅黑"}),
    ("工业仿真软件（如 FactSage、Thermo-Calc、ANSYS 等）虽然具备强大的计算能力，"
     "但其操作界面复杂、参数配置繁琐、结果解读专业性强。一次完整的热力学平衡计算，"
     "从参数配置到结果分析，专家操作通常需要 15—30 分钟，而非专业人员几乎无法独立"
     "完成。这意味着昂贵的软件许可证资源长期处于低利用率状态。", {}),
], indent_cm=0.75)

add_rich_para([
    ("知识资产流失风险。", {"bold": True, "font": "微软雅黑"}),
    ("随着行业资深专家的退休和人才流动，企业面临核心工艺知识断层的严峻挑战。"
     "据行业调研数据，我国冶金行业资深工艺专家的平均年龄已超过 50 岁，"
     "未来 10 年将迎来大规模退休潮。若不能在此之前完成知识的系统化数字转化，"
     "将造成不可逆的知识资产损失。", {}),
], indent_cm=0.75)

# ── 1.2 政策机遇 ──
add_heading_styled("1.2  政策机遇与技术趋势", 2)

add_para(
    "本项目的提出恰逢我国工业数字化转型的战略窗口期，与多项国家级产业政策高度契合：",
    indent_cm=0.75,
)

add_table(
    ["政策/趋势", "与本项目的关联"],
    [
        ["《智能制造发展规划》",
         "明确提出\u201C推动工业知识软件化、模型化\u201D，本项目直接响应将专家经验"
         "固化为可执行数字模型的战略要求"],
        ["工业互联网创新发展行动计划",
         "强调\u201C工业 APP 培育\u201D和\u201C工业机理模型沉淀\u201D，"
         "本项目构建的应用托管平台即为工业 APP 的孵化与运行载体"],
        ["数字中国建设整体布局",
         "推动数字技术与实体经济深度融合，本项目实现了仿真计算能力从"
         "\u201C专家专属\u201D到\u201C按需服务\u201D的范式转变"],
        ["关键核心技术自主可控",
         "通过对进口仿真软件进行应用层封装，降低对原厂技术支持的依赖，"
         "为后续国产替代提供平滑过渡路径"],
    ],
    col_widths=[4.5, 12],
)

add_para(
    "从技术趋势来看，全球领先的工业软件企业（如 Siemens 的 Xcelerator 平台、"
    "达索系统的 3DEXPERIENCE）均在推动\u201C仿真即服务（Simulation as a Service, "
    "SaaS）\u201D的转型。本项目以自主可控的技术路线，构建面向国内工业场景的仿真"
    "应用服务化平台，在技术路径上与国际一线厂商保持同步，同时更贴合国内冶金行业"
    "的实际需求。",
    indent_cm=0.75,
)

# ── 1.3 项目定位 ──
add_heading_styled("1.3  项目定位与目标", 2)

add_rich_para([
    ("项目定位：", {"bold": True, "font": "微软雅黑", "color": PRIMARY}),
    ("构建一套\u201C专家经验数字化封装 → 标准化服务接入 → 平台化统一调度\u201D的"
     "完整技术体系，实现工业仿真知识从", {}),
    ("个人隐性经验", {"bold": True}),
    ("到", {}),
    ("组织数字资产", {"bold": True}),
    ("的系统性转化。", {}),
])

add_para("核心目标：", bold=True, font_name="微软雅黑")

add_table(
    ["编号", "目标", "量化指标"],
    [
        ["G1", "专家经验可执行化",
         "将冶金热力学计算等核心工艺知识封装为标准化 Web 应用"],
        ["G2", "操作门槛降维",
         "非专业人员可在 3 分钟内完成原需专家 30 分钟的仿真计算"],
        ["G3", "平台化统一管理",
         "所有仿真应用通过标准协议接入，实现任务队列调度与全生命周期管理"],
        ["G4", "许可证利用率提升",
         "通过集中调度与队列管理，将仿真软件许可证利用率提升至 80% 以上"],
        ["G5", "可复制推广",
         "建立通用封装方法论，可快速推广至其他仿真软件与工业领域"],
    ],
    col_widths=[2, 4, 10.5],
)

# ══════════════════════════════════════════════════
#  第二章：专家经验数字化封装方法论
# ══════════════════════════════════════════════════
doc.add_page_break()
add_heading_styled("二、核心理念：专家经验数字化封装方法论", 1)

add_para(
    "本项目提出\u201C知识工程四步法\u201D（Knowledge Engineering Four-Step Method, "
    "KE4S），作为将工业领域专家经验转化为可执行数字服务的标准化方法论。该方法论的"
    "核心思想是：将专家经验视为一种可被工程化处理的\u201C知识原料\u201D，通过系统化"
    "的萃取、建模、封装和接入流程，将其转化为具备自描述、可复用、可组合特征的数字资产。",
    indent_cm=0.75,
)

add_heading_styled("2.1  知识工程四步法模型（KE4S）", 2)

# ── 第一步 ──
add_heading_styled("第一步：知识萃取（Knowledge Extraction）", 3)
add_para(
    "通过与领域专家的深度协作，系统化提取其在特定工艺场景下的决策逻辑、经验公式、"
    "判断规则和操作范式。以钢铁冶炼热力学计算为例：",
    indent_cm=0.75,
)

add_table(
    ["萃取维度", "内容示例"],
    [
        ["输入参数体系",
         "钢液成分（Fe、Mn、Si、Al、O、S 等元素质量）、渣系成分"
         "（CaO、Al\u2082O\u2083、SiO\u2082）、工况条件（温度、压力）"],
        ["目标函数定义",
         "脱氧目标（控制 Al 含量至目标百分比）、脱硫目标"
         "（控制 S 含量至目标 ppm 值）"],
        ["求解策略选择",
         "添加剂种类选择（Ca、CaC\u2082、Mg 等）、搜索算法参数"
         "（初始猜测值、搜索上限）"],
        ["结果判读规则",
         "相平衡结果解析、各相质量百分比计算、异常结果识别与重试策略"],
    ],
    col_widths=[4.5, 12],
)

# ── 第二步 ──
add_heading_styled("第二步：模型封装（Model Encapsulation）", 3)
add_para(
    "将萃取的知识固化为可执行的计算模型。本方法论采用\u201C模板驱动 + 参数注入\u201D"
    "的技术路线：将专家的操作流程抽象为参数化模板（Template），运行时根据用户输入"
    "动态生成仿真软件所需的输入文件和宏脚本。",
    indent_cm=0.75,
)

add_rich_para([
    ("关键设计决策：", {"bold": True, "font": "微软雅黑"}),
    ("保留仿真软件的原生计算引擎（如 FactSage 的 Equilib 模块），仅在应用层进行封装。"
     "这一决策确保了计算结果的科学严谨性——所有热力学计算仍由经过国际学术界数十年"
     "验证的专业引擎完成，应用层封装仅负责降低使用门槛，不引入额外的计算误差。", {}),
])

# ── 第三步 ──
add_heading_styled("第三步：服务化包装（Service Packaging）", 3)
add_para(
    "将封装好的计算模型包装为标准化的 Web 应用（Webapp），具备完整的用户交互界面、"
    "参数校验逻辑和结果可视化能力。服务化包装遵循以下设计原则：",
    indent_cm=0.75,
)

for title, desc in [
    ("数据自治原则：",
     "每个 Webapp 独立管理自身的输入参数和输出结果，平台不存储任何业务数据。"
     "这确保了数据的安全隔离和应用的独立演进能力。"),
    ("接口标准化原则：",
     "所有 Webapp 对外暴露统一的接口契约（输入页面、输出页面、回调接口），"
     "使得平台可以以一致的方式管理和调度任意类型的仿真应用。"),
    ("异步解耦原则：",
     "仿真计算的提交与执行采用异步模式，通过消息驱动的任务队列实现请求方与"
     "计算引擎的解耦，支持长时间运行的计算任务。"),
]:
    add_rich_para([
        (title, {"bold": True, "font": "微软雅黑"}),
        (desc, {}),
    ], indent_cm=0.75)

# ── 第四步 ──
add_heading_styled("第四步：平台化接入（Platform Integration）", 3)
add_para(
    "通过标准化接入协议，将 Webapp 注册并接入仿真托管平台。平台提供统一的任务调度"
    "引擎、队列管理、状态监控和用户入口，Webapp 只需实现约定的接口契约即可获得平台"
    "的全部能力加持。",
    indent_cm=0.75,
)
add_para(
    "这一\u201C即插即用\u201D的接入模式，使得新的专家经验应用从开发到上线的周期"
    "可以压缩至数天级别，极大地降低了知识数字化的边际成本。",
    indent_cm=0.75,
)

# ── 2.2 通用性 ──
add_heading_styled("2.2  方法论的通用性与可扩展性", 2)
add_para(
    "KE4S 方法论并非仅适用于 FactSage 热力学计算这一特定场景。"
    "其设计之初即以\u201C通用性\u201D为核心约束，可推广至以下领域：",
    indent_cm=0.75,
)

add_table(
    ["应用领域", "典型仿真软件", "可封装的专家经验"],
    [
        ["冶金热力学", "FactSage、Thermo-Calc",
         "钢渣平衡计算、脱氧脱硫工艺优化、夹杂物预测"],
        ["结构力学", "ANSYS、Abaqus",
         "零部件强度校核、疲劳寿命预测、模态分析"],
        ["流体动力学", "Fluent、OpenFOAM",
         "连铸流场模拟、管道流阻计算、换热器优化"],
        ["材料科学", "JMatPro、CALPHAD",
         "合金相图计算、材料性能预测、热处理工艺优化"],
        ["工艺仿真", "Aspen Plus、ProModel",
         "化工流程模拟、产线排产优化、能耗分析"],
    ],
    col_widths=[3.5, 4, 9],
)

add_para(
    "上述任何领域的专家经验，均可通过 KE4S 方法论完成数字化封装，并通过同一套"
    "平台协议接入统一的仿真托管平台。这种\u201C一次建设平台，持续接入应用\u201D"
    "的模式，使得平台的价值随接入应用数量的增长而呈指数级放大。",
    indent_cm=0.75,
)

# ══════════════════════════════════════════════════
#  第三章：平台总体架构设计
# ══════════════════════════════════════════════════
doc.add_page_break()
add_heading_styled("三、平台总体架构设计", 1)

add_heading_styled("3.1  架构设计原则", 2)
add_para(
    "平台架构设计遵循以下核心原则，以确保系统的可扩展性、可维护性和业务适配性：",
    indent_cm=0.75,
)

add_table(
    ["设计原则", "具体内涵"],
    [
        ["关注点分离",
         "平台仅负责任务调度与生命周期管理，不涉及具体业务逻辑；"
         "业务参数的存储、计算、展示完全由 Webapp 自主管理"],
        ["协议驱动集成",
         "平台与 Webapp 之间通过标准化 HTTP 协议进行通信，双方仅需遵循约定的"
         "接口契约，无需了解彼此的内部实现"],
        ["数据主权归属",
         "遵循\u201C谁产生、谁管理\u201D的数据治理原则，所有业务数据由 Webapp "
         "本地持久化，平台不存储任何业务参数"],
        ["弹性调度能力",
         "支持基于优先级的任务队列管理，当计算资源空闲时可即时调度，"
         "繁忙时自动排队等待"],
        ["渐进式扩展",
         "新应用的接入不影响已有应用的运行，平台能力随接入应用数量的增长而自然丰富"],
    ],
    col_widths=[3.5, 13],
)

add_heading_styled("3.2  三层架构体系", 2)
add_para(
    "平台采用经典的三层架构设计，自上而下分为应用层、平台层和资源层：",
    indent_cm=0.75,
)

add_heading_styled("应用层（Application Layer）", 3)
add_para(
    "由各类已封装的仿真 Webapp 组成。每个 Webapp 是一个独立的 Web 应用，具备完整"
    "的输入界面、计算逻辑和结果展示能力。应用层的核心特征是\u201C自治\u201D——"
    "每个应用独立开发、独立部署、独立演进，彼此之间无耦合关系。",
    indent_cm=0.75,
)

add_heading_styled("平台层（Platform Layer）", 3)
add_para("平台层是整个体系的核心枢纽，提供以下关键能力：", indent_cm=0.75)

for title, desc in [
    ("统一调度引擎：",
     "基于 FIFO（先进先出）策略的任务队列管理器，负责接收来自各 Webapp 的"
     "计算请求，按序调度至可用的计算资源。支持单任务执行和并发控制，确保仿真"
     "软件许可证不被过载。"),
    ("任务生命周期管理：",
     "对每个计算任务从创建到终结的全过程进行精细化状态跟踪。支持六种任务状态"
     "（待填写、排队中、执行中、已完成、已失败、已中止），状态流转遵循严格的"
     "有限状态机模型，终态不可逆转。"),
    ("心跳监控机制：",
     "要求执行中的 Webapp 按固定频率上报心跳信号，平台据此判断任务执行的健康状态。"
     "超时未收到心跳的任务将被标记为异常，触发告警或自动回收。"),
    ("应用注册中心：",
     "管理所有已接入 Webapp 的注册信息，包括输入页面地址、输出页面地址、"
     "回调接口地址等元数据。平台在页面跳转和调度回调时从注册中心获取目标地址，"
     "实现\u201C配置即注册\u201D。"),
]:
    add_rich_para([
        (title, {"bold": True, "font": "微软雅黑"}),
        (desc, {}),
    ], indent_cm=0.75)

add_heading_styled("资源层（Resource Layer）", 3)
add_para(
    "资源层管理底层的计算资源和仿真软件许可证。在当前阶段，资源层主要包括：部署有 "
    "FactSage 等仿真软件的 Windows 计算节点、仿真软件的许可证授权、以及 SQLite/"
    "PostgreSQL 等持久化存储设施。未来可扩展至基于容器化的弹性计算资源池。",
    indent_cm=0.75,
)

add_heading_styled("3.3  核心能力：统一调度引擎", 2)
add_para(
    "统一调度引擎是平台层最核心的能力模块，其设计思想源自操作系统的进程调度机制"
    "和消息队列中间件的事件驱动范式。",
    indent_cm=0.75,
)

add_para("调度引擎的工作流程如下：", bold=True, font_name="微软雅黑")

steps = [
    ("① ", "Webapp 完成参数采集后，向平台发送\u201C提交就绪\u201D信号"
     "（不携带业务数据）；"),
    ("② ", "平台将任务加入 FIFO 队列，状态变更为\u201C排队中\u201D；"),
    ("③ ", "调度引擎检测到可用计算资源，从队头取出任务；"),
    ("④ ", "引擎通过注册中心查询目标 Webapp 的回调接口，发送\u201C开始执行\u201D指令；"),
    ("⑤ ", "Webapp 接收指令后启动计算，同步开启心跳上报；"),
    ("⑥ ", "计算完成后，Webapp 向平台发送\u201C标记完成\u201D"
     "或\u201C标记失败\u201D信号；"),
    ("⑦ ", "调度引擎推进队列，调度下一个等待中的任务。"),
]
for num, desc in steps:
    add_rich_para([
        (num, {"bold": True, "color": ACCENT}),
        (desc, {}),
    ], indent_cm=0.75)

add_para("")
add_para(
    "这一调度模型的精妙之处在于：平台与 Webapp 之间的通信完全基于"
    "\u201C信号\u201D而非\u201C数据\u201D——平台不需要理解 Webapp 在计算什么，"
    "只需要知道任务何时就绪、何时完成。这种极致的关注点分离，使得平台可以"
    "无差别地调度任何类型的仿真应用。",
    indent_cm=0.75,
)

# ══════════════════════════════════════════════════
#  第四章：典型案例
# ══════════════════════════════════════════════════
doc.add_page_break()
add_heading_styled("四、典型案例：FactSage 热力学计算应用", 1)

add_heading_styled("4.1  业务场景与需求分析", 2)
add_para(
    "FactSage 是国际冶金与材料科学领域最权威的热力学计算软件之一，由加拿大 CRCT"
    "（Centre for Research in Computational Thermochemistry）开发维护，集成了经过"
    "数十年实验验证的热力学数据库。在钢铁冶炼过程中，FactSage 被广泛用于：",
    indent_cm=0.75,
)

for title, desc in [
    ("钢液脱氧计算：",
     "确定向钢液中添加脱氧剂（如 Ca、Al）的最优加入量，使钢液中的溶解氧含量"
     "降至目标水平。"),
    ("钢液脱硫计算：",
     "计算添加脱硫剂（如 CaC\u2082、Ca）后钢渣系统的平衡状态，预测脱硫效果"
     "及最终硫含量（ppm 级精度）。"),
    ("渣系优化：",
     "通过调整渣系成分（CaO-Al\u2082O\u2083-SiO\u2082 三元系），优化炉渣的"
     "物化性质，提升精炼效果。"),
]:
    add_rich_para([
        (title, {"bold": True, "font": "微软雅黑"}),
        (desc, {}),
    ], indent_cm=0.75)

add_para(
    "传统操作模式下，工程师需要手动打开 FactSage 软件 → 配置 Equilib 模块参数 → "
    "选择物种数据库 → 设置 ESTA（Evolutionary Search for Target Achievement）"
    "求解器参数 → 运行计算 → 逐项解读 XML 格式的输出结果。整个过程对操作者的"
    "专业背景要求极高，且极易因参数配置疏忽导致计算失败或结果偏差。",
    indent_cm=0.75,
)

add_heading_styled("4.2  专家经验封装过程", 2)
add_para(
    "按照 KE4S 方法论，我们对 FactSage 热力学计算场景进行了系统化的专家经验封装：",
    indent_cm=0.75,
)

add_heading_styled("知识萃取阶段", 3)
add_para(
    "与冶金工艺专家进行了多轮深度访谈，梳理出钢液-渣系平衡计算的完整知识图谱。"
    "关键成果包括：",
    indent_cm=0.75,
)

for title, desc in [
    ("参数约束矩阵：",
     "建立了\u201C添加剂种类 × 目标类型 × 允许/推荐/禁止\u201D的三维校验矩阵。"
     "例如，CaC\u2082 被推荐用于脱硫计算，但被禁止用于脱氧计算；"
     "Si 类物质在当前工艺条件下被全面禁止作为求解变量。"),
    ("搜索策略知识：",
     "专家在长期使用 ESTA 求解器的过程中积累的经验规则——当初始搜索范围无法收敛时，"
     "应如何渐进式扩大搜索上限而非简单重试。我们将这一经验固化为\u201C自适应重试"
     "算法\u201D：首次使用用户指定的搜索上限，失败后按梯度扩展"
     "（10 → 100），每次重试仅扩大不收缩。"),
    ("物种子集选择：",
     "FactSage 数据库包含数千种化学物种，但特定计算场景仅需考虑约 150 种相关物种。"
     "专家的物种子集选择经验被固化到计算模板中，避免了非专业用户因物种选择不当"
     "导致的计算发散。"),
]:
    add_rich_para([
        (title, {"bold": True, "font": "微软雅黑"}),
        (desc, {}),
    ], indent_cm=0.75)

add_heading_styled("模型封装阶段", 3)
add_para("将 FactSage 的 Equilib 计算流程封装为参数化模板体系：", indent_cm=0.75)

for title, desc in [
    ("输入模板（.equi）：",
     "将 FactSage 专有的 Equilib 输入文件格式模板化，所有可变参数以占位符形式标注，"
     "运行时根据用户输入动态填充。模板中固化了专家精选的物种子集、相平衡定义"
     "和数据库引用。"),
    ("宏脚本模板（.mac）：",
     "将 FactSage 的批处理执行流程（设置温度/压力 → 加载输入 → 运行计算 → "
     "导出结果）封装为参数化宏脚本，实现了从手动操作到自动化执行的转变。"),
]:
    add_rich_para([
        (title, {"bold": True, "font": "微软雅黑"}),
        (desc, {}),
    ], indent_cm=0.75)

add_heading_styled("服务化包装阶段", 3)
add_para(
    "基于 FastAPI + 原生 Web 技术栈，将封装后的计算模型包装为完整的 Web 应用：",
    indent_cm=0.75,
)

add_table(
    ["能力模块", "功能描述"],
    [
        ["智能输入界面",
         "提供参数化输入表单，内置预设方案一键加载、实时参数组合校验、单位自动转换"],
        ["异步计算引擎",
         "提交后即返回任务 ID，后台异步调用 FactSage 引擎，计算过程不阻塞用户交互"],
        ["自适应求解",
         "内置智能重试机制，当 ESTA 求解器在当前搜索范围内无法收敛时，"
         "自动扩展搜索空间并重新计算"],
        ["结果可视化",
         "自动解析 FactSage 输出的 XML 结果，以直观的数据表格展示钢液/渣系平衡组成"],
        ["历史追溯",
         "所有计算任务持久化存储，支持历史记录浏览、参数回溯和结果复查"],
    ],
    col_widths=[4, 12.5],
)

# ── 4.3 效果对比 ──
add_heading_styled("4.3  应用效果对比", 2)
add_para(
    "通过对 FactSage 热力学计算场景的专家经验封装，实现了显著的效率提升和门槛降低：",
    indent_cm=0.75,
)

add_table(
    ["对比维度", "封装前（传统模式）", "封装后（Web 应用）"],
    [
        ["操作人员要求",
         "资深冶金工程师，需掌握 FactSage 操作",
         "普通技术人员，仅需填写工艺参数"],
        ["单次计算耗时",
         "15—30 分钟（含参数配置与结果解读）",
         "2—3 分钟（含输入与等待计算）"],
        ["参数配置出错率",
         "较高（物种选择、单位转换易出错）",
         "极低（内置校验与预设方案）"],
        ["计算失败处理",
         "需专家手动调整参数重试",
         "系统自动扩展搜索范围重试"],
        ["结果可追溯性",
         "依赖个人文件管理，难以追溯",
         "全量历史记录，一键回溯"],
        ["多人协作能力",
         "单机单用户，许可证独占",
         "多用户并发提交，队列调度共享许可证"],
    ],
    col_widths=[3.5, 6.5, 6.5],
)

# ══════════════════════════════════════════════════
#  第五章：标准化接入机制
# ══════════════════════════════════════════════════
doc.add_page_break()
add_heading_styled("五、标准化接入机制", 1)

add_heading_styled("5.1  接入协议总览", 2)
add_para(
    "为实现\u201C任意仿真应用即插即用\u201D的平台化目标，我们设计了一套轻量级、"
    "基于 HTTP 的标准化接入协议。该协议定义了平台与 Webapp 之间的所有通信契约，"
    "覆盖任务创建、参数提交、调度执行、状态监控和结果查看的完整生命周期。",
    indent_cm=0.75,
)

add_para("协议设计的核心特征：", indent_cm=0.75)

for title, desc in [
    ("极简接口数量：",
     "Webapp 仅需实现 1 个回调接口 + 2 个页面地址即可完成接入，"
     "接口复杂度压缩至最低限度。"),
    ("信号驱动而非数据驱动：",
     "平台与 Webapp 之间传递的是\u201C信号\u201D（开始执行、完成、失败）"
     "而非\u201C数据\u201D（业务参数），实现了业务逻辑与平台逻辑的彻底解耦。"),
    ("配置即注册：",
     "Webapp 的所有 URL（输入页面、输出页面、回调接口）在注册时一次性配置，"
     "运行时平台从注册中心自动获取，无需重复传递。"),
]:
    add_rich_para([
        (title, {"bold": True, "font": "微软雅黑"}),
        (desc, {}),
    ], indent_cm=0.75)

add_heading_styled("5.2  Webapp 接入能力清单", 2)
add_para(
    "一个 Webapp 接入仿真托管平台，需实现以下六项标准化能力：",
    indent_cm=0.75,
)

add_table(
    ["序号", "能力项", "说明"],
    [
        ["1", "回调接口",
         "接收平台发送的\u201C开始执行\u201D和\u201C中止任务\u201D"
         "两种操作指令，并返回标准化响应"],
        ["2", "输入页面",
         "接收任务标识参数，展示参数输入表单，用户提交后将参数保存至本地存储"],
        ["3", "输出页面",
         "接收任务标识参数，从本地存储检索计算结果并以可视化方式展示"],
        ["4", "心跳上报",
         "计算执行期间按固定频率（30秒）向平台上报存活信号，用于健康监控"],
        ["5", "状态上报",
         "计算完成或失败时主动通知平台，触发状态流转"],
        ["6", "本地存储",
         "以任务标识为键存储输入参数和输出结果，实现数据自治"],
    ],
    col_widths=[1.5, 3, 12],
)

add_heading_styled("5.3  任务生命周期与状态流转", 2)
add_para(
    "平台对每个计算任务实施精细化的生命周期管理，任务状态遵循严格的有限状态机模型：",
    indent_cm=0.75,
)

add_table(
    ["状态码", "状态名称", "语义说明"],
    [
        ["0", "PENDING",   "待填写 — 任务已创建，等待用户通过输入页面填写参数"],
        ["1", "QUEUED",    "排队中 — 参数已提交，任务在调度队列中等待可用计算资源"],
        ["2", "RUNNING",   "执行中 — 平台已调度，Webapp 正在执行仿真计算"],
        ["3", "COMPLETED", "已完成 — 终态，计算成功完成，结果可查看"],
        ["4", "FAILED",    "已失败 — 终态，计算过程出现错误"],
        ["5", "ABORTED",   "已中止 — 终态，管理员或用户主动取消"],
    ],
    col_widths=[2, 3, 11.5],
)

add_rich_para([
    ("状态流转的铁律：", {"bold": True, "font": "微软雅黑", "color": RED}),
    ("终态（COMPLETED / FAILED / ABORTED）不可逆转。任何试图变更终态任务的请求"
     "将被协议层直接拒绝，返回\u201C状态冲突\u201D错误。这一设计确保了任务历史"
     "的完整性和审计的可追溯性。", {}),
])

add_heading_styled("5.4  安全与可靠性保障", 2)

for title, desc in [
    ("心跳超时检测：",
     "平台对执行中的任务实施心跳监控，若超过预设阈值未收到心跳信号，"
     "平台将主动标记任务为失败状态，释放占用的计算资源。"),
    ("优雅中止机制：",
     "当管理员发起中止操作时，平台不会粗暴地终止计算进程，而是向 Webapp 发送"
     "\u201C中止请求\u201D信号，由 Webapp 自行完成资源释放和状态清理，"
     "确保不会产生数据残留或资源泄漏。"),
    ("异常恢复机制：",
     "平台在重启时自动扫描处于非终态的\u201C孤儿任务\u201D"
     "（如因系统崩溃未正常终结的任务），将其标记为失败状态，"
     "防止任务长期滞留在无效的中间状态。"),
    ("幂等性设计：",
     "所有状态变更接口均包含前置状态校验，重复提交同一操作不会导致状态混乱，"
     "保证了在网络抖动等异常场景下的协议健壮性。"),
]:
    add_rich_para([
        (title, {"bold": True, "font": "微软雅黑"}),
        (desc, {}),
    ])

# ══════════════════════════════════════════════════
#  第六章：预期效益与推广价值
# ══════════════════════════════════════════════════
doc.add_page_break()
add_heading_styled("六、预期效益与推广价值", 1)

add_heading_styled("6.1  经济效益分析", 2)

add_table(
    ["效益维度", "预期效果"],
    [
        ["人工成本节约",
         "单次仿真计算从专家 30 分钟降至非专业人员 3 分钟，"
         "按年均 2000 次计算量估算，每年可节约资深工程师约 900 工时"],
        ["许可证利用率",
         "通过集中调度与队列管理，将原本\u201C一人一证\u201D的独占模式转变为"
         "\u201C多人共享、按需调度\u201D模式，许可证利用率预计从 30% 提升至 80% 以上"],
        ["培训成本降低",
         "新员工无需接受为期数月的 FactSage 操作培训，仅需了解 Web 表单的"
         "参数含义即可独立完成计算"],
        ["计算失误减少",
         "通过内置的参数校验矩阵和预设方案，将人为配置失误导致的"
         "计算失败率降低 80% 以上"],
        ["响应效率提升",
         "生产现场工程师可在现场即时提交计算请求，无需排队等待专家操作，"
         "工艺决策响应时间大幅缩短"],
    ],
    col_widths=[4, 12.5],
)

add_heading_styled("6.2  社会效益与知识传承价值", 2)

for title, desc in [
    ("知识资产化：",
     "将专家的隐性经验转化为可运行的数字资产，从根本上解决了"
     "\u201C人走知识走\u201D的行业痼疾。封装后的计算应用成为企业的永久知识储备，"
     "不受人员流动影响。"),
    ("能力民主化：",
     "将原本仅少数专家掌握的高端仿真能力，转化为任何技术人员均可使用的标准化服务。"
     "这不是在\u201C替代\u201D专家，而是在\u201C放大\u201D专家的影响力——"
     "一位专家的经验可以同时服务于整个组织。"),
    ("人才培养加速：",
     "新员工通过使用封装后的计算应用，可以在实际操作中逐步理解参数含义、"
     "计算逻辑和结果判读，形成\u201C边用边学\u201D的沉浸式培养模式，"
     "大幅缩短人才成长周期。"),
]:
    add_rich_para([
        (title, {"bold": True, "font": "微软雅黑"}),
        (desc, {}),
    ])

add_heading_styled("6.3  推广路径与生态愿景", 2)

add_heading_styled("近期（1—2 年）：纵向深化", 3)
add_para(
    "以 FactSage 热力学计算为标杆，在冶金领域纵向扩展更多计算场景"
    "（如连铸凝固模拟、轧制力计算、夹杂物预测等），丰富平台的冶金仿真应用矩阵。",
    indent_cm=0.75,
)

add_heading_styled("中期（2—3 年）：横向拓展", 3)
add_para(
    "将 KE4S 方法论推广至其他工业仿真领域，依次接入结构力学（ANSYS）、"
    "流体动力学（Fluent）、材料科学（JMatPro）等领域的专家经验应用，"
    "构建跨领域的工业仿真应用生态。",
    indent_cm=0.75,
)

add_heading_styled("远期（3—5 年）：平台生态", 3)
add_para(
    "面向行业开放平台接入能力，形成\u201C平台运营方 + 应用开发方 + 使用方\u201D"
    "的三方生态格局。各领域的专家团队可以基于 KE4S 方法论和标准化接入协议，"
    "独立开发仿真应用并上架平台，实现工业仿真知识的社会化共享与交易。",
    indent_cm=0.75,
)

# 结语
add_para("")
add_para("—" * 30, alignment=WD_ALIGN_PARAGRAPH.CENTER, color=GRAY)
add_para("")

add_rich_para([
    ("本项目的价值不在于开发了一个\u201C好用的计算工具\u201D，",
     {"italic": True, "color": GRAY}),
    ("而在于建立了一套可复制、可推广的\u201C专家经验数字化方法论\u201D和"
     "\u201C标准化平台接入体系\u201D。",
     {"italic": True, "bold": True, "color": PRIMARY}),
    ("FactSage 热力学计算只是第一个\u201C样板间\u201D——证明这条路走得通。"
     "真正的想象空间，在于当这套方法论被应用到更多领域、更多专家经验时，"
     "所能释放的知识红利。",
     {"italic": True, "color": GRAY}),
], alignment=WD_ALIGN_PARAGRAPH.CENTER)

# ══════════════════════════════════════════════════
#  附录：术语表
# ══════════════════════════════════════════════════
doc.add_page_break()
add_heading_styled("附录A  术语表", 1)

add_table(
    ["术语", "释义"],
    [
        ["KE4S",
         "Knowledge Engineering Four-Step Method，知识工程四步法，"
         "本项目提出的专家经验数字化封装方法论"],
        ["FactSage",
         "由加拿大 CRCT 开发的国际权威热力学计算软件，集成 Equilib、"
         "Phase Diagram 等多个计算模块"],
        ["ESTA",
         "Evolutionary Search for Target Achievement，FactSage 内置的目标搜索算法，"
         "用于求解满足目标约束的最优添加量"],
        ["Webapp",
         "基于 B/S 架构的 Web 应用程序，用户通过浏览器访问，无需安装客户端"],
        ["SaaS",
         "Simulation as a Service，仿真即服务，将仿真计算能力以云服务形式"
         "对外提供的交付模式"],
        ["FIFO",
         "First In, First Out，先进先出，一种经典的队列调度策略"],
        ["有限状态机",
         "Finite State Machine，一种数学计算模型，用于描述对象在有限个状态之间"
         "按规则进行切换的行为"],
        ["幂等性",
         "同一操作执行多次与执行一次产生的效果相同，是分布式系统中保障"
         "数据一致性的重要特性"],
        ["心跳机制",
         "分布式系统中用于检测节点存活状态的周期性信号，类似于人体心跳反映生命体征"],
    ],
    col_widths=[3.5, 13],
)

# ══════════════════════════════════════════════════
#  保存
# ══════════════════════════════════════════════════
out_path = os.path.join(
    os.path.dirname(__file__),
    "工业仿真专家经验数字化封装与服务化平台技术方案.docx",
)
doc.save(out_path)
print(f"Document saved: {out_path}")
print(f"Size: {os.path.getsize(out_path) / 1024:.1f} KB")
