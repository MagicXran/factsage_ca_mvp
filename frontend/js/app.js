/**
 * FactSage Ca 用量估算 - 前端逻辑
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

    const steelTbody = $("#steelTable tbody");
    const slagTbody = $("#slagTable tbody");
    const historyTbody = $("#historyTable tbody");
    const historyEmpty = $("#historyEmpty");

    // 当前选中的计算类型
    let currentType = "deoxidation";

    // 预设名称映射（从 API 动态获取）
    const TYPE_TO_PRESET = {
        deoxidation: "example_deoxidation",
        desulfurization: "example_desulfurization",
    };

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

        // 绑定事件
        tabs.forEach((tab) =>
            tab.addEventListener("click", () => switchTab(tab.dataset.type))
        );
        btnPreset.addEventListener("click", loadPreset);
        btnCalc.addEventListener("click", submitCalc);

        // 目标元素下拉联动
        $("#target_element").addEventListener("change", function () {
            currentType = this.value === "Al" ? "deoxidation" : "desulfurization";
            highlightTab(currentType);
        });

        // 加载默认预设
        await loadPreset();
    }

    // ── Tab 切换 ──────────────────────────────────────

    async function switchTab(type) {
        currentType = type;
        highlightTab(type);
        // 同步目标元素下拉
        $("#target_element").value = type === "deoxidation" ? "Al" : "S";
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
        setVal("target_element", t.element || "Al");
        setVal("target_value", t.value);
        setVal("alpha_guess", data.alpha_guess ?? 0.5);

        // 同步 tab
        currentType = t.element === "S" ? "desulfurization" : "deoxidation";
        highlightTab(currentType);
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
            },
            alpha_guess: getNum("alpha_guess") || 0.5,
        };

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
                showResult(job.result);
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
    }

    function showError(msg) {
        resultPlaceholder.classList.add("hidden");
        resultContent.classList.add("hidden");
        resultLoading.classList.add("hidden");
        resultError.classList.remove("hidden");
        errorMsg.textContent = msg;
    }

    function showResult(r) {
        resultPlaceholder.classList.add("hidden");
        resultLoading.classList.add("hidden");
        resultError.classList.add("hidden");
        resultContent.classList.remove("hidden");

        resAlpha.textContent = r.alpha_Ca_g.toFixed(4);

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
                    let alpha = "—";
                    if (j.status === "completed") {
                        try {
                            const detail = await api("GET", `/jobs/${j.job_id}`);
                            if (detail.result)
                                alpha = detail.result.alpha_Ca_g.toFixed(4);
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
