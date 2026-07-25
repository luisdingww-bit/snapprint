"""SnapPrint 社区版后端（FastAPI）。

主线：用户上传自己的 3D 模型 → 系统自动可打印性分析 → 进入社区画廊 → 成员可评论。

路由：
  POST /api/upload                上传模型文件 + 自动分析，进入画廊
  POST /api/generate              照片 → 可打印 3D（离线浮雕 / AI 模式），分析后入画廊
  GET  /api/models                模型动物园（生成后端列表 + 本机权重可用性）
  GET  /api/gallery               画廊列表（分页，按时间倒序）
  GET  /api/models/{id}           模型详情 = 分析报告 + 评论
  POST /api/models/{id}/comments  发表评论
  GET  /api/presets               打印机 / 材料预设（前端下拉用）
  GET  /api/scoreboard            可打印性评分排行榜（可选）
  GET  /outputs/*                 下载上传的模型原文件

安全（可选，沿用 v0.5.0 优化）：
  设置 SNAPRINT_API_KEY 后，所有 /api/* 需携带请求头 X-API-Key；
  设置 SNAPRINT_RATE_LIMIT=N 启用每客户端每分钟 N 次限流。
  两者均未设置时完全开放（方便本地 / 公开 Demo）。
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from . import advisor
from . import db

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUTPUTS = ROOT / "outputs"
UPLOADS = OUTPUTS / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SnapPrint · 咔印3D 社区", version="0.7.0")

# 允许跨域：鉴权走请求头 X-API-Key（而非 Cookie），故无需 allow_credentials；
# 社区为公开服务，默认允许所有来源（"*"），这样前端无论托管在 CloudStudio /
# Surge / 用户自有域名都能直接连后端，无需逐个加白名单。
# 如需收紧，用 SNAPRINT_CORS_ORIGINS 以逗号分隔显式列出可信前端来源即可覆盖。
_CORS_DEFAULTS = ["*"]
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
# 安全：可选 API Key 校验 + 内存令牌桶限流（沿用 v0.5.0）
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


MAX_UPLOAD_MB = int(os.environ.get("SNAPRINT_MAX_UPLOAD_MB", "50"))


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    author: str = Form(""),
    printer: str = Form(""),
    material: str = Form(""),
    _: None = Depends(guard),
):
    """上传模型 → 自动可打印性分析 → 存入社区画廊。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")

    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件过大，上限 {MAX_UPLOAD_MB} MB")

    low = file.filename.lower()
    ext = ""
    for e in advisor.SUPPORTED_EXT:
        if low.endswith(e):
            ext = e
            break
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="不支持的格式，请上传 .stl / .obj / .ply / .3mf / .glb / .gltf / .off",
        )

    try:
        rec = advisor.analyze_upload(
            data, filename=file.filename, printer=printer, material=material
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover - 分析内部异常
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")

    sid = uuid.uuid4().hex[:12]
    dest = UPLOADS / f"{sid}{ext}"
    dest.write_bytes(data)
    db.add_submission(
        sid=sid,
        filename=file.filename,
        author=author,
        ext=ext,
        size_bytes=len(data),
        model_path=str(dest),
        report=rec,
    )
    return JSONResponse({"id": sid, "report": rec, "score": rec.get("score", 0)})


# ---------------------------------------------------------------------------
# 照片 → 可打印 3D（图生3D）：离线浮雕（零依赖，保证可跑）+ AI 模式适配层
# （Hunyuan3D / TripoSR 等需自备 GPU + 权重，缺失时返回清晰指引）。
# 生成出的网格复用 advisor 做可打印性分析，并进入社区画廊。
# ---------------------------------------------------------------------------
@app.post("/api/generate")
async def generate(
    file: UploadFile = File(...),
    mode: str = Form("relief"),
    model: str = Form(""),
    author: str = Form(""),
    printer: str = Form(""),
    material: str = Form(""),
    _: None = Depends(guard),
):
    """照片 → 可打印 3D 模型。

    - mode=relief（默认）：离线浮雕，纯 numpy/Pillow/trimesh，任何环境秒级出结果。
    - mode=ai / 指定 model：走 AI 后端（Hunyuan3D 等），需自备 GPU + 权重，
      否则会返回明确的「缺少依赖/权重」指引，不会静默失败。
    生成的网格会自动做可打印性分析并发布到社区画廊。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传图片文件")

    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件过大，上限 {MAX_UPLOAD_MB} MB")

    # 校验图片有效性（避免把非图片喂给生成管线）
    try:
        from io import BytesIO
        from PIL import Image

        Image.open(BytesIO(data)).verify()
    except Exception:
        raise HTTPException(status_code=400, detail="请上传有效的图片（jpg / png / webp 等）")

    try:
        from .pipeline import run

        result = run(data, mode=mode, model=model)
        mesh = result["mesh"]
    except Exception as e:  # 生成失败（含 AI 模式缺依赖/权重）：明确回传原因
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")

    # 导出为 .stl 字节，复用 advisor 分析链路（与上传模型一致的报告）
    import io as _io

    stl_buf = _io.BytesIO()
    try:
        mesh.export(stl_buf, file_type="stl")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")
    stl_bytes = stl_buf.getvalue()

    try:
        rec = advisor.analyze_upload(
            stl_bytes, filename="generated.stl", printer=printer, material=material
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")

    # 落盘：.stl 为通用可打印下载；另存 .obj（带顶点色）便于带色彩查看
    sid = uuid.uuid4().hex[:12]
    stem = (file.filename.rsplit(".", 1)[0] if "." in file.filename else "photo")
    stl_path = UPLOADS / f"{sid}.stl"
    stl_path.write_bytes(stl_bytes)
    try:
        mesh.export(UPLOADS / f"{sid}.obj")
    except Exception:
        pass
    db.add_submission(
        sid=sid,
        filename=f"{stem}_3d.stl",
        author=author,
        ext=".stl",
        size_bytes=len(stl_bytes),
        model_path=str(stl_path),
        report=rec,
    )
    return JSONResponse(
        {
            "id": sid,
            "mode": result.get("mode", mode),
            "report": rec,
            "score": rec.get("score", 0),
        }
    )


@app.get("/api/models")
def list_models(_: None = Depends(guard)):
    """模型动物园：列出可用生成后端（含本机权重可用性探测 + 速度/贴图标签）。

    前端用于「照片生成 3D」面板的模式选择；relief 永远可用，
    AI 模式需自备 GPU + 权重（available=false 时生成会返回指引）。
    """
    try:
        from .config import DEFAULT_CONFIG, MODEL_ZOO

        items = []
        for m in MODEL_ZOO:
            entry = dict(m)
            # 本机是否具备权重：探测 <model_dir>/<weights> 目录
            try:
                import os

                wd = os.path.join(getattr(DEFAULT_CONFIG, "model_dir", "models"), m["weights"])
                entry["available"] = os.path.isdir(wd)
            except Exception:
                entry["available"] = bool(m.get("available", False))
            items.append(entry)
        return JSONResponse({"models": items})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型列表失败: {e}")


@app.get("/api/gallery")
def gallery(limit: int = 24, offset: int = 0, _: None = Depends(guard)):
    """画廊列表（分页，按时间倒序）。"""
    items, total = db.list_submissions(limit=min(limit, 100), offset=max(offset, 0))
    return JSONResponse({"items": items, "total": total})


@app.get("/api/models/{sid}")
def model_detail(sid: str, _: None = Depends(guard)):
    """模型详情 = 分析报告 + 评论。"""
    sub = db.get_submission(sid)
    if not sub:
        raise HTTPException(status_code=404, detail="模型不存在")
    comments = db.list_comments(sid)
    return JSONResponse({"submission": sub, "comments": comments})


@app.post("/api/models/{sid}/comments")
async def post_comment(
    sid: str,
    author: str = Form(""),
    body: str = Form(""),
    _: None = Depends(guard),
):
    """发表评论。"""
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="评论内容不能为空")
    if not db.get_submission(sid):
        raise HTTPException(status_code=404, detail="模型不存在")
    db.add_comment(sid=sid, author=author, body=body)
    return JSONResponse({"ok": True})


@app.get("/api/presets")
def presets(_: None = Depends(guard)):
    """打印机 / 材料预设（前端下拉用）。"""
    return JSONResponse({"printers": advisor.PRINTERS, "materials": advisor.MATERIALS})


@app.get("/api/scoreboard")
def scoreboard(limit: int = 12, _: None = Depends(guard)):
    """可打印性评分排行榜（社区「最省心模型」）。"""
    items, _ = db.list_submissions(limit=min(limit, 100), offset=0)
    ranked = sorted(items, key=lambda x: x["score"], reverse=True)
    return JSONResponse({"items": ranked})


@app.get("/api/health")
def health():
    """健康检查（无需鉴权），供前端探测后端在线状态 / Docker 健康检查。"""
    return JSONResponse({"ok": True, "version": "0.7.0"})


# 静态下载上传的模型原文件（注册在前，优先级高于根 "/" 挂载）
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS)), name="outputs")

# 纯静态前端：与 surge 线上 Demo 共用同一份 web/。
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
