"""SnapPrint 社区版后端（FastAPI）。

主线：用户上传自己的 3D 模型 → 系统自动可打印性分析 → 进入社区画廊 → 成员可评论。

路由：
  POST /api/upload                上传模型文件 + 自动分析，进入画廊
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

app = FastAPI(title="SnapPrint · 咔印3D 社区", version="0.6.0")

# 允许跨域：鉴权走请求头 X-API-Key（而非 Cookie），故无需 allow_credentials；
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


# 静态下载上传的模型原文件（注册在前，优先级高于根 "/" 挂载）
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS)), name="outputs")

# 纯静态前端：与 surge 线上 Demo 共用同一份 web/。
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
