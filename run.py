# -*- coding: utf-8 -*-
"""FactSage Ca 用量估算 App - 统一入口（开发 / 打包均可用）"""
import sys
import os
from pathlib import Path

# 开发模式：将 backend/ 加入模块搜索路径
if not getattr(sys, "frozen", False):
    _backend = str(Path(__file__).resolve().parent / "backend")
    if _backend not in sys.path:
        sys.path.insert(0, _backend)

import threading
import webbrowser

import uvicorn

from app.main import app
from app.config import settings


def main():
    host = settings.server_host
    port = settings.server_port
    url = f"http://127.0.0.1:{port}"

    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    print("=" * 50)
    print("  FactSage Ca 用量估算 App")
    print(f"  访问地址: {url}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 50)

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
