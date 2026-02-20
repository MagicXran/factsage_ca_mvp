/**
 * FactSage 钢渣反应计算 - 前端逻辑
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

        // 加载计算选项配置（替代原 loadWhitelist）
        await loadCalcOptions();

        // 绑定事件
        tabs.forEach((tab) =>
            tab.addEventListener("click", () => switchTab(tab.dataset.type))
        );
        btnPreset.addEventListener("click", loadPreset);
        btnCalc.addEventListener("click", submitCalc);

        // 目标元素变更 → 更新求解物质下拉 + 单位 + 默认值
        $("#target_element").addEventListener("change", function () {
            const elem = this.value;
            populateSpecies(elem);
            updateUnitDisplay(elem);
            setVal("target_value", getTargetDefault(elem));
            currentType = elem === "S" ? "desulfurization" : "deoxidation";
            highlightTab(currentType);
            checkCombination();
        });

        // 求解物质变更 → 检查组合警告
        $("#solve_species").addEventListener("change", checkCombination);

        // 加载默认预设
        await loadPreset();
    }

    // ── 计算选项加载 ──────────────────────────────────────

    async function loadCalcOptions() {
        try {
            calcOptions = await api("GET", "/calc-options");
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

    /** 根据目标元素填充求解物质下拉（推荐在前 + 可用在后） */
    function populateSpecies(targetElem) {
        if (!calcOptions) return;
        const info = calcOptions.species_by_target[targetElem];
        if (!info) return;
        const sel = $("#solve_species");
        sel.innerHTML = "";
        for (const sp of info.recommended) {
            const opt = document.createElement("option");
            opt.value = sp;
            opt.textContent = sp + " (推荐)";
            sel.appendChild(opt);
        }
        for (const sp of info.allowed) {
            const opt = document.createElement("option");
            opt.value = sp;
            opt.textContent = sp;
            sel.appendChild(opt);
        }
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

    // ── 组合验证 ─────────────────────────────────────────

    let comboBlocked = false;

    async function checkCombination() {
        const sp = getStr("solve_species");
        const te = getStr("target_element");
        if (!sp || !te) return;
        try {
            const r = await api(
                "GET",
                `/validate-combination?solve_species=${encodeURIComponent(sp)}&target_elem=${encodeURIComponent(te)}`
            );
            if (r.level === "reject") {
                comboWarning.textContent = "⛔ " + r.message;
                comboWarning.className = "combo-warning combo-reject";
                comboBlocked = true;
                btnCalc.disabled = true;
            } else if (r.level === "warn") {
                comboWarning.textContent = "⚠️ " + r.message;
                comboWarning.className = "combo-warning combo-warn";
                comboBlocked = false;
                btnCalc.disabled = false;
            } else {
                comboWarning.textContent = "";
                comboWarning.className = "combo-warning hidden";
                comboBlocked = false;
                btnCalc.disabled = false;
            }
        } catch (_) {
            comboWarning.className = "combo-warning hidden";
            comboBlocked = false;
            btnCalc.disabled = false;
        }
    }

    // ── Tab 切换 ──────────────────────────────────────────

    async function switchTab(type) {
        currentType = type;
        highlightTab(type);
        populateTargets(type);
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

        // 1. 先填充下拉框（保证后续 setVal 能选中正确选项）
        currentType = calcType;
        highlightTab(calcType);
        populateTargets(calcType);
        setVal("target_element", elem);
        populateSpecies(elem);
        updateUnitDisplay(elem);

        // 2. 填充表单值
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
        setVal("solve_species", data.solve_species || "Ca");
        setVal("target_value", t.value);
        setVal("alpha_guess", data.alpha_guess ?? 0.5);
        setVal("alpha_max", data.alpha_max ?? 10);
    }

    function setVal(id, val) {
        const el = document.getElementById(id);
        if (el) el.value = val ?? "";
    }

    function getNum(id) {
        return parseFloat(document.getElementById(id).value) || 0;
    }

    function getStr(id) {
        return document.getElementById(id).value.trim();
    }

    // ── 提交计算 ──────────────────────────────────────

    async function submitCalc() {
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
            solve_species: getStr("solve_species") || "Ca",
            alpha_guess: getNum("alpha_guess") || 0.5,
            alpha_max: getNum("alpha_max") || 10,
        };

        // 基本校验
        if (!body.steel.Fe_g || !body.target.value) {
            showError("请填写完整参数（至少 Fe 和目标值）");
            return;
        }
        if (comboBlocked) {
            showError("当前求解物质+目标元素组合不可用，请先调整");
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

        resAlphaLabel.textContent = (r.solve_species || "Ca") + " 需要量";
        resAlpha.textContent = r.alpha_g.toFixed(4);

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

            // 获取完成任务的详细结果
            const rows = await Promise.all(
                jobs.slice(0, 20).map(async (j) => {
                    let species = "—";
                    let alpha = "—";
                    if (j.status === "completed") {
                        try {
                            const detail = await api("GET", `/jobs/${j.job_id}`);
                            if (detail.result) {
                                species = detail.result.solve_species || "Ca";
                                alpha = detail.result.alpha_g.toFixed(4);
                            }
                        } catch (_) { /* ignore */ }
                    }
                    const typeLabel =
                        j.calc_type === "deoxidation" ? "脱氧" : "脱硫";
                    const statusLabel = {
                        pending: "等待中",
                        running: "计算中",
                        completed: "✓ 完成",
                        failed: "✗ 失败",
                    }[j.status] || j.status;
                    return `<tr>
                        <td>${j.job_id}</td>
                        <td>${typeLabel}</td>
                        <td>${species}</td>
                        <td>${alpha}</td>
                        <td class="status-${j.status}">${statusLabel}</td>
                        <td>${j.created_at}</td>
                    </tr>`;
                })
            );
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
