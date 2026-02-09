# -*- coding: utf-8 -*-
"""构建打包脚本 - 生成独立分发目录"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "FactSage_Ca_App"
VENV_SCRIPTS = ROOT / ".venv" / "Scripts"


def main():
    # ── 1. PyInstaller 打包 ─────────────────────────────
    print("[1/4] 运行 PyInstaller (--onedir) ...")
    subprocess.run(
        [
            str(VENV_SCRIPTS / "pyinstaller.exe"),
            str(ROOT / "factsage_ca_app.spec"),
            "--noconfirm",
            "--distpath", str(ROOT / "dist"),
            "--workpath", str(ROOT / "build"),
        ],
        check=True,
    )

    # ── 2. 复制外部资源 ────────────────────────────────
    print("[2/4] 复制外部资源 ...")

    # config.json — 修改路径为打包版本
    with open(ROOT / "backend" / "config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("paths", {})
    cfg["paths"]["templates_dir"] = "templates"
    cfg["paths"]["presets_dir"] = "presets"
    cfg["paths"]["frontend_dir"] = "frontend"
    cfg["paths"]["work_root"] = "./work"
    cfg["server"]["host"] = "127.0.0.1"
    with open(DIST / "config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

    # templates/
    _copy_dir(ROOT / "cites" / "templates", DIST / "templates")

    # presets/
    _copy_dir(ROOT / "cites" / "jobs", DIST / "presets")

    # frontend/
    _copy_dir(ROOT / "frontend", DIST / "frontend")

    # work/ (空目录)
    (DIST / "work").mkdir(exist_ok=True)

    # ── 3. README ──────────────────────────────────────
    print("[3/4] 生成说明文件 ...")
    readme = """\
===================================================
  FactSage Ca 用量估算 App
===================================================

【使用方法】
  双击 FactSage_Ca_App.exe 启动，浏览器自动打开。

【配置修改】
  编辑 config.json (UTF-8 编码):

  server.host         — 监听地址 (默认 127.0.0.1)
  server.port         — 监听端口 (默认 10687)
  factsage.dir        — FactSage 安装目录
  factsage.exe_name   — 可执行文件名
  mock.enabled        — true/false/auto

【文件说明】
  FactSage_Ca_App.exe — 主程序
  config.json         — 配置文件 (可编辑)
  templates/          — FactSage 模板 (可编辑)
  presets/            — 预设参数文件
  frontend/           — Web 前端
  work/               — 运行时工作目录 (自动生成)
  _internal/          — 程序依赖 (勿删)
"""
    (DIST / "README.txt").write_text(readme, encoding="utf-8")

    # ── 4. 完成 ───────────────────────────────────────
    size_mb = sum(
        f.stat().st_size for f in DIST.rglob("*") if f.is_file()
    ) / 1024 / 1024
    print(f"[4/4] ✅ 构建完成  ({size_mb:.1f} MB)")
    print(f"       位置: {DIST}")
    print(f"       运行: {DIST / 'FactSage_Ca_App.exe'}")


def _copy_dir(src: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


if __name__ == "__main__":
    main()
