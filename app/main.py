"""SnapPrint Web 后端（FastAPI）。

路由：
  GET  /                    纯静态 Web UI（与 surge 共用 web/，零双份维护）
  POST /api/generate        同步生成（浮雕模式秒级，保留向后兼容）
  POST /api/generate_async  异步生成 -> 立即返回 task_id（AI 模式耗时长时用）
  GET  /api/tasks/{id}      查询任务状态 / 分阶段进度 / 结果
  POST /api/batch           批量生成（多图 -> 多个异步任务）
  POST /api/analyze         可打印性 / 支撑建议分析
  GET  /api/models          列出模型动物园（含本地权重可用性探测 + 速度/贴图标签）
  GET  /outputs/*           下载生成的 OBJ / PLY / 3MF / GLB

图生3D 生成参数（对齐 modly）：
  model                模型动物园 id（sf3d / hunyuan3d / hunyuan3d-mini-turbo / triposg / trellis2 …）
  remesh               none | triangle | quad（重网格化）
  enable_texture       是否保留生成贴图（False 烘焙为顶点色，利于打印）
  texture_resolution   贴图分辨率
  params               JSON 字符串，模型专属推理参数

可选安全（内网 / 小团队部署）：
  设置环境变量 SNAPRINT_API_KEY 启用 API Key 校验（请求头 X-API-Key）；
  设置 SNAPRINT_RATE_LIMIT=N 启用每客户端每分钟 N 次限流。
  两者均未设置时完全开放（默认，方便本地 / 公开 Demo）。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config import DEFAULT_CONFIG, MODEL_ZOO, SnapConfig, _local_weights_present
from .pipeline import run
from . import advisor

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SnapPrint · 咔印3D", version="0.5.0")

# 允许跨域：让纯静态前端（如 surge 线上 Demo）能够把请求发到用户本地后端。
# 鉴权走请求头 X-API-Key（而非 Cookie），故无需 allow_credentials；
# origins 默认锁定为「公开 Demo + 本地地址」，可用 SNAPRINT_CORS_ORIGINS
# 以逗号分隔覆盖（内网/小团队部署时建议显式列出可信前端来源）。
_CORS_DEFAULTS = [
    "https://snapprint-3d.surge.sh",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_cors_env = os.environ.get("SNAPRINT_CORS_ORIGINS", "").strip()
CORS_ORIGINS = [o for o in _cors_env.split(",") if o.strip()] or _CORS_DEFAULTS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 安全：可选 API Key 校验 + 内存令牌桶限流
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("SNAPRINT_API_KEY", "")
RATE_LIMIT = int(os.environ.get("SNAPRINT_RATE_LIMIT", "0"))  # 每分钟上限，0=不限
_RATE: dict[str, list[float]] = {}


def guard(_request: Request, x_api_key: str = Header(None)) -> None:
    """可选鉴权 + 限流依赖。未配置 SNAPRINT_API_KEY 时直接放行。"""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="无效或缺失 API Key（请求头 X-API-Key 提供）")
    if RATE_LIMIT > 0:
        fwd = _request.headers.get("x-forwarded-for", "")
        key = "key:" + (x_api_key or fwd or (_request.client.host if _request.client else "anon"))
        now = time.time()
        hits = [t for t in _RATE.get(key, []) if now - t < 60]
        if len(hits) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        hits.append(now)
        _RATE[key] = hits


# ---------------------------------------------------------------------------
# 异步任务队列（内存注册表 + 后台线程；单机部署零额外依赖）
# 可选持久化：设 SNAPRINT_TASK_PERSIST=1 时把任务注册表落盘到
# OUTPUTS/.task_registry.json，重启后端后任务仍在（生成的文件本身就在
# OUTPUTS/ 下）。默认关闭，纯内存态，重启即清空。
# ---------------------------------------------------------------------------
TASKS: dict = {}
_TASKS_LOCK = threading.Lock()
_TASK_TTL_SEC = 3600        # 完成的任务保留 1 小时
_TASK_MAX = 200             # 注册表上限（超出先清最旧的已完成任务）
_TASK_STORE_FILE = OUTPUTS / ".task_registry.json"
_TASK_PERSIST = os.environ.get("SNAPRINT_TASK_PERSIST", "0") == "1"


def _task_save() -> None:
    """（可选）把任务注册表原子落盘；失败静默，不影响内存态运行。"""
    if not _TASK_PERSIST:
        return
    try:
        import json as _json
        tmp = _TASK_STORE_FILE.with_suffix(".json.tmp")
        tmp.write_text(_json.dumps(TASKS, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_TASK_STORE_FILE)
    except Exception:  # pragma: no cover - 落盘失败不应阻断主流程
        pass


def _task_load() -> None:
    """（可选）启动时从落盘文件恢复任务注册表。"""
    if not _TASK_PERSIST or not _TASK_STORE_FILE.exists():
        return
    try:
        import json as _json
        data = _json.loads(_TASK_STORE_FILE.read_text(encoding="utf-8"))
        TASKS.update({k: v for k, v in data.items() if isinstance(v, dict)})
    except Exception:  # pragma: no cover - 损坏的落盘文件直接忽略
        pass


_task_load()


def _task_update(task_id: str, **kw) -> None:
    with _TASKS_LOCK:
        if task_id in TASKS:
            TASKS[task_id].update(kw)
            _task_save()


def _task_prune() -> None:
    """清理过期 / 超量的已完成任务（在创建新任务时顺带执行）。"""
    now = time.time()
    with _TASKS_LOCK:
        done = [(tid, t) for tid, t in TASKS.items() if t["status"] in ("done", "error")]
        for tid, t in done:
            if now - t["created"] > _TASK_TTL_SEC:
                TASKS.pop(tid, None)
        overflow = len(TASKS) - _TASK_MAX
        if overflow > 0:
            for tid, _ in sorted(done, key=lambda x: x[1]["created"])[:overflow]:
                TASKS.pop(tid, None)
        _task_save()


def _build_cfg(*, tile_w=60.0, tile_d=60.0, base=2.0, relief=4.0, target_tris=80000) -> SnapConfig:
    return SnapConfig(
        tile_width_mm=tile_w,
        tile_depth_mm=tile_d,
        base_thickness_mm=base,
        relief_depth_mm=relief,
        target_triangles=target_tris,
    )


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


def _run_task(task_id, data, mode, model, cfg, *,
               remesh="none", enable_texture=False, texture_resolution=1024,
               params=None) -> None:
    """后台线程执行体：跑流水线并把分阶段进度写进注册表。"""

    def cb(stage: str, pct: int) -> None:
        _task_update(task_id, status="running", stage=stage, progress=int(pct))

    try:
        out_dir = OUTPUTS / task_id
        result = run(
            data, mode=mode, cfg=cfg, out_dir=out_dir, name="model",
            progress_cb=cb, model=model,
            remesh=remesh, enable_texture=enable_texture,
            texture_resolution=texture_resolution, params=params,
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


def _submit_task(data: bytes, mode: str, model: str, cfg: SnapConfig, *,
                 remesh="none", enable_texture=False, texture_resolution=1024,
                 params=None) -> str:
    """提交一个生成任务到后台线程，返回 task_id。"""
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
        _task_save()
    threading.Thread(
        target=_run_task,
        args=(task_id, data, mode, model, cfg),
        kwargs=dict(remesh=remesh, enable_texture=enable_texture,
                    texture_resolution=texture_resolution, params=params),
        daemon=True,
    ).start()
    return task_id


@app.post("/api/generate")
async def generate(
    file: UploadFile = File(...),
    mode: str = Form("relief"),
    model: str = Form(""),
    remesh: str = Form("none"),
    enable_texture: bool = Form(False),
    texture_resolution: int = Form(1024),
    params: str = Form("{}"),
    tile_w: float = Form(60.0),
    tile_d: float = Form(60.0),
    base: float = Form(2.0),
    relief: float = Form(4.0),
    target_tris: int = Form(80000),
    _: None = Depends(guard),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")

    data = await file.read()
    cfg = _build_cfg(tile_w=tile_w, tile_d=tile_d, base=base, relief=relief, target_tris=target_tris)

    try:
        result = run(
            data, mode=mode, cfg=cfg, out_dir=OUTPUTS / "sync", name="model", model=model,
            remesh=remesh, enable_texture=enable_texture,
            texture_resolution=texture_resolution, params=_parse_params(params),
        )
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")

    stats = result["stats"]
    download = _files_to_download("sync", stats)
    return JSONResponse({"mode": result["mode"], "stats": stats, "files": download})


@app.post("/api/generate_async")
async def generate_async(
    file: UploadFile = File(...),
    mode: str = Form("relief"),
    model: str = Form(""),
    remesh: str = Form("none"),
    enable_texture: bool = Form(False),
    texture_resolution: int = Form(1024),
    params: str = Form("{}"),
    tile_w: float = Form(60.0),
    tile_d: float = Form(60.0),
    base: float = Form(2.0),
    relief: float = Form(4.0),
    target_tris: int = Form(80000),
    _: None = Depends(guard),
):
    """异步生成：立即返回 task_id，前端轮询 /api/tasks/{id} 获取进度。"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")

    data = await file.read()
    cfg = _build_cfg(tile_w=tile_w, tile_d=tile_d, base=base, relief=relief, target_tris=target_tris)
    task_id = _submit_task(
        data, mode, model, cfg,
        remesh=remesh, enable_texture=enable_texture,
        texture_resolution=texture_resolution, params=_parse_params(params),
    )
    return JSONResponse({"task_id": task_id})


@app.post("/api/batch")
async def batch_generate(
    files: list[UploadFile] = File(...),
    mode: str = Form("relief"),
    model: str = Form(""),
    remesh: str = Form("none"),
    enable_texture: bool = Form(False),
    texture_resolution: int = Form(1024),
    params: str = Form("{}"),
    _: None = Depends(guard),
):
    """批量生成：多张图片 -> 各自一个异步任务，返回 task_id 列表。"""
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个文件")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="单次批量上限 50 个")
    cfg = _build_cfg()
    tids = []
    for f in files:
        data = await f.read()
        tids.append(_submit_task(
            data, mode, model, cfg,
            remesh=remesh, enable_texture=enable_texture,
            texture_resolution=texture_resolution, params=_parse_params(params),
        ))
    return JSONResponse({"count": len(tids), "task_ids": tids})


def _parse_params(raw: str):
    """把 params 表单字段（JSON 字符串）解析为 dict；非法则回退空字典。"""
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


@app.get("/api/tasks/{task_id}")
def task_status(task_id: str):
    """查询任务：status(queued/running/done/error) + stage + progress + result。"""
    with _TASKS_LOCK:
        t = TASKS.get(task_id)
        if t is None:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        return JSONResponse(dict(t))


@app.get("/api/models")
def list_models():
    """列出模型动物园；标注本机是否已具备权重（models/ 下对应目录存在）。"""
    out = []
    for m in MODEL_ZOO:
        present = _local_weights_present(DEFAULT_CONFIG, m["weights"])
        out.append({**m, "available": bool(present or m["available"])})
    return JSONResponse({"models": out})


@app.post("/api/analyze")
async def analyze_endpoint(
    file: UploadFile = File(...),
    mode: str = Form("relief"),
    printer: str = Form(""),
    _: None = Depends(guard),
):
    """可打印性 / 支撑建议分析。

    上传图片（走浮雕生成）或网格文件（stl/obj/ply/3mf/glb/off），
    返回结构化切片与支撑建议 JSON（供 Blender / ComfyUI / Web 复用）。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")
    data = await file.read()
    try:
        rec = advisor.analyze_upload(
            data,
            mode=mode,
            filename=file.filename or "",
            printer=printer,
            content_type=file.content_type or "",
        )
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")
    return JSONResponse(rec)


# 静态下载生成的文件（注册在前，优先级高于根 "/" 挂载）
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS)), name="outputs")

# 纯静态前端：与 surge 线上 Demo 共用同一份 web/，避免双份维护。
# html=True 时 "/" 自动返回 index.html，相对路径的 JS/CSS 也由此提供。
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
