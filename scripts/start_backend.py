"""启动 SnapPrint 本地后端（供 Blender 插件 / ComfyUI 节点 / 可打印性分析调用）。

用法：
    python scripts/start_backend.py            # 默认 http://localhost:8000
    PORT=8080 python scripts/start_backend.py  # 自定义端口

启动后：
    - Web UI + 同步接口   http://localhost:8000/
    - 异步生成            POST /api/generate_async
    - 任务查询            GET  /api/tasks/{id}
    - 可打印性分析        POST /api/analyze
Blender 插件与 ComfyUI 节点默认连接 http://localhost:8000。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    print(f"[SnapPrint] 启动后端 → http://localhost:{port}/")
    print("[SnapPrint] 供 Blender 插件 / ComfyUI 节点调用；Ctrl+C 退出。")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
