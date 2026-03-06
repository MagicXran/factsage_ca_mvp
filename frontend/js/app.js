/**
 * FactSage 钢渣反应计算 - 前端逻辑（工业物料模式）
 */
(function () {
    "use strict";

    // ── 配置 ─────────────────────────────────────────
    const API_BASE = "/api";
    const POLL_INTERVAL_MS = 800;

    // ── DOM 缓存 ──────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const modeTag = $("#modeTag");
    const tabs = document.querySelectorAll(".tab");
    const btnPreset = $("#btnPreset");
    const btnCalc = $("#btnCalc");

    const resultPlaceholder = $("#resultPlaceholder");
    const resultContent = $("#resultContent");
    const resultLoading = $("#resultLoading");
    const resultError = $("#resultError");
    const errorMsg = $("#errorMsg");
    const resAlpha = $("#resAlpha");
    const resAlphaLabel = $("#resAlphaLabel");
    const comboWarning = $("#comboWarning");
    const btnDownload = $("#btnDownload");
    const resMaterialRow = $("#resMaterialRow");
    const resMaterialLabel = $("#resMaterialLabel");
    const resMaterialAmount = $("#resMaterialAmount");
    const resMaterialPurity = $("#resMaterialPurity");

    const steelTbody = $("#steelTable tbody");
    const slagTbody = $("#slagTable tbody");
    const historyTbody = $("#historyTable tbody");
    const historyEmpty = $("#historyEmpty");

    // 当前选中的计算类型
    let currentType = "deoxidation";
    // 当前完成的任务 ID（用于下载）
    let currentJobId = null;

    // 预设名称映射
    const TYPE_TO_PRESET = {
        deoxidation: "deox_Al_target",
        desulfurization: "desul_S_target",
    };

    // 计算选项缓存（启动时一次性加载）
    let calcOptions = null;
    // 工业物料缓存
    let industrialMaterials = null;

    // ── 初始化 ────────────────────────────────────────

    async function init() {
        // 获取运行模式
        try {
            const info = await api("GET", "/config/info");
            if (info.mock_mode) {
                modeTag.textContent = "Mock 模式";
                modeTag.className = "tag tag-mock";
            } else {
                modeTag.textContent = "生产模式";
                modeTag.className = "tag tag-prod";
            }
        } catch (_) { /* ignore */ }

        // 加载计算选项配置
        await loadCalcOptions();

        // 绑定事件
        tabs.forEach((tab) =>
            tab.addEventListener("click", () => switchTab(tab.dataset.type))
        );
        btnPreset.addEventListener("click", loadPreset);
        btnCalc.addEventListener("click", submitCalc);

        // 物料变更 → 联动目标元素、纯度、solve_species
        $("#material_select").addEventListener("change", onMaterialChange);

        // 目标元素变更 → 更新单位 + 默认值
        $("#target_element").addEventListener("change", function () {
            const elem = this.value;
            updateUnitDisplay(elem);
            setVal("target_value", getTargetDefault(elem));
        });

        // 加载默认预设
        await loadPreset();

        // 检查 URL 参数，加载历史任务
        const params = new URLSearchParams(window.location.search);
        const viewJobId = params.get("job_id") || params.get("task_id");
        if (viewJobId) {
            await loadHistoryJob(viewJobId);
        }

        // 初始加载历史记录
        await refreshHistory();
    }

    // ── 计算选项加载 ──────────────────────────────────────

    async function loadCalcOptions() {
        try {
            calcOptions = await api("GET", "/calc-options");
            industrialMaterials = calcOptions.industrial_materials || {};
        } catch (e) {
            console.warn("计算选项加载失败:", e);
        }
    }

    /** 根据计算类型填充目标元素下拉 */
    function populateTargets(calcType) {
        if (!calcOptions) return;
        const targets = calcOptions.calc_types[calcType] || [];
        const sel = $("#target_element");
        sel.innerHTML = "";
        for (const t of targets) {
            const opt = document.createElement("option");
            opt.value = t.element;
            opt.textContent = t.label;
            sel.appendChild(opt);
        }
    }

    /** 根据计算类型填充物料下拉 */
    function populateMaterials(calcType) {
        if (!industrialMaterials) return;
        const sel = $("#material_select");
        sel.innerHTML = "";
        for (const [id, mat] of Object.entries(industrialMaterials)) {
            if (mat.calc_type !== calcType) continue;
            const opt = document.createElement("option");
            opt.value = id;
            opt.textContent = mat.name;
            sel.appendChild(opt);
        }
        // 触发联动
        onMaterialChange();
    }

    /** 物料变更联动 */
    function onMaterialChange() {
        const matId = getStr("material_select");
        if (!industrialMaterials || !matId) return;
        const mat = industrialMaterials[matId];
        if (!mat) return;

        // 设定 solve_species（隐藏字段）
        setVal("solve_species", mat.solve_species);

        // 设定纯度默认值
        setVal("purity", mat.default_purity);

        // 设定目标元素
        setVal("target_element", mat.target_element);
        updateUnitDisplay(mat.target_element);

        // 设定目标默认值
        const defaultVal = getTargetDefault(mat.target_element);
        if (defaultVal) setVal("target_value", defaultVal);
    }

    /** 更新单位显示 */
    function updateUnitDisplay(targetElem) {
        const t = _findTargetInfo(targetElem);
        if (t) {
            $("#target_unit_display").textContent = t.unit === "ppm" ? "ppm" : "wt%";
        }
    }

    /** 获取目标元素的固定单位 */
    function getTargetUnit(targetElem) {
        const t = _findTargetInfo(targetElem);
        return t ? t.unit : "wtpct";
    }

    /** 获取目标元素的默认值 */
    function getTargetDefault(targetElem) {
        const t = _findTargetInfo(targetElem);
        return t ? t.default_value : 0;
    }

    /** 从缓存中查找目标元素信息 */
    function _findTargetInfo(elem) {
        if (!calcOptions) return null;
        for (const targets of Object.values(calcOptions.calc_types)) {
            const found = targets.find((x) => x.element === elem);
            if (found) return found;
        }
        return null;
    }

    // ── Tab 切换 ──────────────────────────────────────────

    async function switchTab(type) {
        currentType = type;
        highlightTab(type);
        populateTargets(type);
        populateMaterials(type);
        await loadPreset();
    }

    function highlightTab(type) {
        tabs.forEach((t) =>
            t.classList.toggle("active", t.dataset.type === type)
        );
    }

    // ── 预设加载 ──────────────────────────────────────

    async function loadPreset() {
        const name = TYPE_TO_PRESET[currentType];
        if (!name) return;
        try {
            const d = await api("GET", `/presets/${name}`);
            fillForm(d);
        } catch (e) {
            console.warn("预设加载失败:", e);
        }
    }

    function fillForm(data) {
        const s = data.steel || {};
        const g = data.slag || {};
        const c = data.conditions || {};
        const t = data.target || {};
        const calcType = data.calc_type || "deoxidation";
        const elem = t.element || "Al";

        // 1. 先填充下拉框
        currentType = calcType;
        highlightTab(calcType);
        populateTargets(calcType);
        populateMaterials(calcType);

        // 2. 设定物料（如果有）
        if (data.material_id) {
            setVal("material_select", data.material_id);
        }
        setVal("target_element", elem);
        updateUnitDisplay(elem);

        // 3. 填充表单值
        setVal("Fe_g", s.Fe_g);
        setVal("Mn_field", s.Mn_field ?? "");
        setVal("Si_g", s.Si_g);
        setVal("Al_g", s.Al_g);
        setVal("O_g", s.O_g);
        setVal("S_g", s.S_g);
        setVal("CaO_g", g.CaO_g);
        setVal("Al2O3_g", g.Al2O3_g);
        setVal("SiO2_g", g.SiO2_g);
        setVal("T_C", c.T_C);
        setVal("P_atm", c.P_atm ?? 1);
        setVal("solve_species", data.solve_species || "Al");
        setVal("target_value", t.value);
        setVal("alpha_guess", data.alpha_guess ?? 0.5);
        setVal("alpha_max", data.alpha_max ?? 10);
        setVal("purity", data.purity ?? "");
    }

    function setVal(id, val) {
        const el = document.getElementById(id);
        if (el) el.value = val ?? "";
    }

    function getNum(id) {
        return parseFloat(document.getElementById(id).value) || 0;
    }

    function getStr(id) {
        const el = document.getElementById(id);
        return el ? el.value.trim() : "";
    }

    // ── 提交计算 ──────────────────────────────────────

    async function submitCalc() {
        const materialId = getStr("material_select");
        const purity = getNum("purity");

        const body = {
            calc_type: currentType,
            steel: {
                Fe_g: getNum("Fe_g"),
                Mn_field: getStr("Mn_field"),
                Si_g: getNum("Si_g"),
                Al_g: getNum("Al_g"),
                O_g: getNum("O_g"),
                S_g: getNum("S_g"),
            },
            slag: {
                CaO_g: getNum("CaO_g"),
                Al2O3_g: getNum("Al2O3_g"),
                SiO2_g: getNum("SiO2_g"),
            },
            conditions: {
                T_C: getNum("T_C"),
                P_atm: getNum("P_atm") || 1,
            },
            target: {
                element: getStr("target_element"),
                value: getNum("target_value"),
                unit: getTargetUnit(getStr("target_element")),
            },
            solve_species: getStr("solve_species") || "Al",
            alpha_guess: getNum("alpha_guess") || 0.5,
            alpha_max: getNum("alpha_max") || 10,
        };

        // 附加物料信息
        if (materialId) {
            body.material_id = materialId;
        }
        if (purity > 0) {
            body.purity = purity;
        }

        // 基本校验
        if (!body.steel.Fe_g || !body.target.value) {
            showError("请填写完整参数（至少 Fe 和目标值）");
            return;
        }

        console.log("[FactSage] 提交请求:", JSON.stringify(body, null, 2));

        showLoading();
        btnCalc.disabled = true;

        try {
            const resp = await api("POST", "/calculate", body);
            // 轮询结果
            await pollJob(resp.job_id);
        } catch (e) {
            showError("提交失败: " + e.message);
        } finally {
            btnCalc.disabled = false;
        }
    }

    // ── 轮询 ─────────────────────────────────────────

    async function pollJob(jobId) {
        while (true) {
            const job = await api("GET", `/jobs/${jobId}`);
            if (job.status === "completed") {
                currentJobId = jobId;
                showResult(job.result, jobId);
                refreshHistory();
                return;
            }
            if (job.status === "failed") {
                showError(job.error || "计算失败");
                refreshHistory();
                return;
            }
            await sleep(POLL_INTERVAL_MS);
        }
    }

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
                    material_id: job.request.material_id,
                    purity: job.request.purity,
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
        banner.innerHTML = '\u{1F4CB} 正在查看历史任务 <code>' + jobId + '</code> <a href="/" class="btn-back">返回新建计算</a>';
        banner.classList.remove("hidden");

        // 禁用所有输入
        panel.querySelectorAll("input, select").forEach(function(el) { el.disabled = true; });
        btnCalc.classList.add("hidden");
        btnPreset.classList.add("hidden");
    }

    // ── 结果展示 ──────────────────────────────────────

    function showLoading() {
        resultPlaceholder.classList.add("hidden");
        resultContent.classList.add("hidden");
        resultError.classList.add("hidden");
        resultLoading.classList.remove("hidden");
        btnDownload.classList.add("hidden");
    }

    function showError(msg) {
        resultPlaceholder.classList.add("hidden");
        resultContent.classList.add("hidden");
        resultLoading.classList.add("hidden");
        resultError.classList.remove("hidden");
        errorMsg.textContent = msg;
        btnDownload.classList.add("hidden");
    }

    function showResult(r, jobId) {
        resultPlaceholder.classList.add("hidden");
        resultLoading.classList.add("hidden");
        resultError.classList.add("hidden");
        resultContent.classList.remove("hidden");

        // 显示下载按钮
        if (jobId) {
            btnDownload.classList.remove("hidden");
            btnDownload.onclick = () => window.open(`${API_BASE}/jobs/${jobId}/download`);
        } else {
            btnDownload.classList.add("hidden");
        }

        resAlphaLabel.textContent = (r.solve_species || "Al") + " 需要量";
        resAlpha.textContent = r.alpha_g.toFixed(4);

        // 工业物料用量
        if (r.material_name && r.material_amount_g != null) {
            resMaterialRow.classList.remove("hidden");
            resMaterialLabel.textContent = r.material_name + " 用量";
            resMaterialAmount.textContent = r.material_amount_g.toFixed(4);
            resMaterialPurity.textContent = "(纯度 " + (r.purity || 0) + "%)";
        } else {
            resMaterialRow.classList.add("hidden");
        }

        // 钢液表
        const steelRows = [
            ["Fe", r.steel.Fe_wtpct, "%"],
            ["Mn", r.steel.Mn_wtpct, "%"],
            ["Si", r.steel.Si_wtpct, "%"],
            ["Al", r.steel.Al_wtpct, "%"],
            ["O", r.steel.O_ppm, "ppm"],
            ["S", r.steel.S_wtpct, "%"],
        ];
        steelTbody.innerHTML = steelRows
            .map(([k, v, u]) => {
                const display =
                    u === "ppm" ? v.toFixed(1) + " ppm" : fmtPct(v);
                return `<tr><td>${k}</td><td>${display}</td></tr>`;
            })
            .join("");

        // 渣表
        const slagRows = [
            ["CaO", r.slag.CaO_wtpct],
            ["Al₂O₃", r.slag.Al2O3_wtpct],
            ["SiO₂", r.slag.SiO2_wtpct],
            ["MnO", r.slag.MnO_wtpct],
            ["FeO", r.slag.FeO_wtpct],
            ["CaS", r.slag.CaS_wtpct],
        ];
        slagTbody.innerHTML = slagRows
            .map(([k, v]) => `<tr><td>${k}</td><td>${fmtPct(v)}</td></tr>`)
            .join("");
    }

    function fmtPct(v) {
        if (v >= 1) return v.toFixed(2) + "%";
        if (v >= 0.01) return v.toFixed(4) + "%";
        return v.toExponential(3) + "%";
    }

    // ── 历史记录 ──────────────────────────────────────

    async function refreshHistory() {
        try {
            const jobs = await api("GET", "/jobs");
            if (!jobs.length) {
                historyEmpty.classList.remove("hidden");
                historyTbody.innerHTML = "";
                return;
            }
            historyEmpty.classList.add("hidden");

            const rows = jobs.slice(0, 50).map(function(j) {
                const typeLabel = j.calc_type === "deoxidation" ? "脱氧" : "脱硫";
                const statusLabel = {
                    pending: "等待中",
                    running: "计算中",
                    completed: "✓ 完成",
                    failed: "✗ 失败",
                }[j.status] || j.status;
                // 显示物料名称（从缓存查找）
                let materialLabel = j.solve_species || "Al";
                if (industrialMaterials) {
                    for (const [, mat] of Object.entries(industrialMaterials)) {
                        if (mat.solve_species === j.solve_species) {
                            materialLabel = mat.name;
                            break;
                        }
                    }
                }
                return '<tr>'
                    + '<td><a href="?job_id=' + j.job_id + '" class="job-link">' + j.job_id + '</a></td>'
                    + '<td>' + typeLabel + '</td>'
                    + '<td>' + materialLabel + '</td>'
                    + '<td>—</td>'
                    + '<td class="status-' + j.status + '">' + statusLabel + '</td>'
                    + '<td>' + j.created_at + '</td>'
                    + '</tr>';
            });
            historyTbody.innerHTML = rows.join("");
        } catch (_) { /* ignore */ }
    }

    // ── 工具函数 ──────────────────────────────────────

    async function api(method, path, body) {
        const opts = {
            method,
            headers: { "Content-Type": "application/json" },
        };
        if (body) opts.body = JSON.stringify(body);
        const res = await fetch(API_BASE + path, opts);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            // Pydantic 422 返回 detail 为数组，需特殊处理
            let msg = res.statusText;
            if (Array.isArray(err.detail)) {
                msg = err.detail
                    .map((e) => `${(e.loc || []).join(".")}: ${e.msg}`)
                    .join("; ");
                console.error("[FactSage] 验证错误:", err.detail);
            } else if (typeof err.detail === "string") {
                msg = err.detail;
            }
            throw new Error(msg);
        }
        return res.json();
    }

    function sleep(ms) {
        return new Promise((r) => setTimeout(r, ms));
    }

    // ── 启动 ─────────────────────────────────────────
    init();
})();
