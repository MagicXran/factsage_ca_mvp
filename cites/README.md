# FactSage Equilib - Ca add-on estimate (template MVP)

This folder shows **方式B：把 Equilib 输入文件做成“占位符模板”**，并且 **宏文件也模板化**，以便批处理+参数化。

## 这个案例做什么
- 已知：钢液(Fe/Mn/Si/Al/O/S) + 渣(CaO/Al2O3/SiO2) + 加入 Ca（数量用 `<A>` 表示未知）
- 设定：温度 T、压力 P
- 目标：让钢液中某个元素达到目标含量（常见两类）
  - **脱硫**：目标元素 = `S`（钢液中残硫）
  - **脱氧**：目标元素 = `Al`（用 Al 作为 [Al]-[O] 平衡的控制量，间接约束氧含量）
- 求解：FactSage 的 `ESTA`（Estimate Alpha）自动求出 `<A>`（即 Ca 用量）

输出：
- `alpha_Ca_g`：计算得到的 Ca 用量（g）
- 钢液关键元素 wt%（以及 O(ppm)）
- 渣中主要氧化物/硫化物 wt%

## 手动验证（强烈建议先做一遍）
1. 打开 Equilib → Reactants  
   输入钢液与渣的配比；把 Ca 的数量填成 `<A>`（不要填数值）
2. Next → 选择数据库/相（PPT 里那套）
3. Equilib Menu 窗口里：
   - Composition target：选择 **钢液相**（FTmisc-Fe-liq），选择目标元素（S 或 Al），填目标值
   - Estimate：选择 **Alpha**，给一个初值（例如 0.5）
   - Final conditions：T、P
4. 运行一次，确认在 Results 中能看到 `Alpha` 的数值

## 批处理运行（命令行）
> 需要 **Standalone/dongle** 安装；并且从 `C:\FactSage` 目录运行，避免 Initialize.ini 路径错误。

```bat
cd /d C:\FactSage
EquiSage.exe /EQUILIB /MACRO "C:\demo\jobs\<job_id>\input\case.mac"
```

## 代码运行（自动渲染模板 + 执行）
1) 把本文件夹复制到 Windows 机器，比如 `C:\demo\factsage_ca_mvp\`  
2) 打开 PowerShell/CMD：

```bat
cd /d C:\demo\factsage_ca_mvp
python run_job.py jobs\example_deoxidation.json --factsage-dir C:\FactSage --work-root C:\demo\jobs
```

输出会在：
`C:\demo\jobs\<job_id>\out\`

然后可解析：
```bat
python parse_ca_results.py C:\demo\jobs\<job_id>\out\case.xml --out C:\demo\jobs\<job_id>\out\summary.csv
```

## 多任务/多用户怎么做（核心逻辑）
- **每个任务一个独立目录**：`work_root/job_id/{input,out,log}`
- 模板渲染时把所有路径都写进该任务目录（避免互相覆盖）
- 任务调度：简单队列（FIFO）即可；同一台有 dongle 的机器通常一次跑 1 个 Equilib 进程最稳

