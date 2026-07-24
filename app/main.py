"""SnapPrint Web 后端（FastAPI）。

路由：
  GET  /                    中文 Web UI
  POST /api/generate        同步生成（浮雕模式秒级，保留向后兼容）
  POST /api/generate_async  异步生成 -> 立即返回 task_id（AI 模式耗时长时用）
  GET  /api/tasks/{id}      查询任务状态 / 分阶段进度 / 结果
  GET  /outputs/*           下载生成的 OBJ / PLY / 3MF
"""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import SnapConfig
from .pipeline import run

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SnapPrint · 咔印3D", version="0.2.0")

# ---------------------------------------------------------------------------
# 异步任务队列（内存注册表 + 后台线程；单机部署零额外依赖）
# ---------------------------------------------------------------------------
TASKS: dict = {}
_TASKS_LOCK = threading.Lock()
_TASK_TTL_SEC = 3600        # 完成的任务保留 1 小时
_TASK_MAX = 200             # 注册表上限（超出先清最旧的已完成任务）


def _task_update(task_id: str, **kw) -> None:
    with _TASKS_LOCK:
        if task_id in TASKS:
            TASKS[task_id].update(kw)


def _task_prune() -> None:
    """清理过期 / 超量的已完成任务（在创建新任务时顺带执行）。"""
    now = time.time()
    with _TASKS_LOCK:
        done = [
            (tid, t)
            for tid, t in TASKS.items()
            if t["status"] in ("done", "error")
        ]
        for tid, t in done:
            if now - t["created"] > _TASK_TTL_SEC:
                TASKS.pop(tid, None)
        overflow = len(TASKS) - _TASK_MAX
        if overflow > 0:
            for tid, _ in sorted(done, key=lambda x: x[1]["created"])[:overflow]:
                TASKS.pop(tid, None)


def _files_to_download(job: str, stats: dict) -> dict:
    """把 pipeline 输出的本地文件路径转成可下载 URL。"""
    files = stats.pop("files", None) or {}
    download = {
        k: f"/outputs/{job}/{Path(v).name}"
        for k, v in files.items()
        if k not in ("3mf_error",)
    }
    if "3mf_error" in files:
        download["3mf_error"] = files["3mf_error"]
    return download


def _run_task(task_id: str, data: bytes, mode: str, cfg: SnapConfig) -> None:
    """后台线程执行体：跑流水线并把分阶段进度写进注册表。"""

    def cb(stage: str, pct: int) -> None:
        _task_update(task_id, status="running", stage=stage, progress=int(pct))

    try:
        out_dir = OUTPUTS / task_id
        result = run(
            data, mode=mode, cfg=cfg, out_dir=out_dir, name="model", progress_cb=cb
        )
        stats = result["stats"]
        download = _files_to_download(task_id, stats)
        _task_update(
            task_id,
            status="done",
            stage="完成",
            progress=100,
            result={"mode": result["mode"], "stats": stats, "files": download},
        )
    except Exception as e:
        _task_update(task_id, status="error", stage="失败", error=str(e))


@app.get("/", response_class=HTMLResponse)
def index():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.post("/api/generate")
async def generate(
    file: UploadFile = File(...),
    mode: str = Form("relief"),
    tile_w: float = Form(60.0),
    tile_d: float = Form(60.0),
    base: float = Form(2.0),
    relief: float = Form(4.0),
    target_tris: int = Form(80000),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")

    data = await file.read()
    cfg = SnapConfig(
        tile_width_mm=tile_w,
        tile_depth_mm=tile_d,
        base_thickness_mm=base,
        relief_depth_mm=relief,
        target_triangles=target_tris,
    )

    job = uuid.uuid4().hex[:8]
    out_dir = OUTPUTS / job
    try:
        result = run(data, mode=mode, cfg=cfg, out_dir=out_dir, name="model")
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")

    stats = result["stats"]
    download = _files_to_download(job, stats)
    return JSONResponse({"mode": result["mode"], "stats": stats, "files": download})


@app.post("/api/generate_async")
async def generate_async(
    file: UploadFile = File(...),
    mode: str = Form("relief"),
    tile_w: float = Form(60.0),
    tile_d: float = Form(60.0),
    base: float = Form(2.0),
    relief: float = Form(4.0),
    target_tris: int = Form(80000),
):
    """异步生成：立即返回 task_id，前端轮询 /api/tasks/{id} 获取进度。"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")

    data = await file.read()
    cfg = SnapConfig(
        tile_width_mm=tile_w,
        tile_depth_mm=tile_d,
        base_thickness_mm=base,
        relief_depth_mm=relief,
        target_triangles=target_tris,
    )

    _task_prune()
    task_id = uuid.uuid4().hex[:12]
    with _TASKS_LOCK:
        TASKS[task_id] = {
            "id": task_id,
            "status": "queued",
            "stage": "排队中",
            "progress": 0,
            "created": time.time(),
            "result": None,
            "error": None,
        }
    threading.Thread(
        target=_run_task, args=(task_id, data, mode, cfg), daemon=True
    ).start()
    return JSONResponse({"task_id": task_id})


@app.get("/api/tasks/{task_id}")
def task_status(task_id: str):
    """查询任务：status(queued/running/done/error) + stage + progress + result。"""
    with _TASKS_LOCK:
        t = TASKS.get(task_id)
        if t is None:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        return JSONResponse(dict(t))


# 静态下载生成的文件
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS)), name="outputs")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
