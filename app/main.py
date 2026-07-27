"""SnapPrint 社区版后端（FastAPI）。

主线：用户上传自己的 3D 模型 → 系统自动可打印性分析 → 进入社区画廊 → 成员可评论。

路由：
  POST /api/upload                上传模型文件 + 自动分析，进入画廊
  POST /api/generate              照片 → 可打印 3D（离线浮雕 / AI 模式），分析后入画廊
  GET  /api/models                模型动物园（生成后端列表 + 本机权重可用性）
  GET  /api/shapes                内置模型实例库（16 款参数化真 3D 几何）
  POST /api/shapes/{id}/generate  一键生成模型实例，分析后入画廊
  GET  /api/gallery               画廊列表（分页，按时间倒序）
  GET  /api/models/{id}           模型详情 = 分析报告 + 评论 + 社区评分统计
  POST /api/models/{id}/comments  发表评论
  POST /api/models/{id}/rate      社区评分（1–5 星 + 必填文字，每作者限评一次）
  GET  /api/presets               打印机 / 材料预设（前端下拉用）
  GET  /api/scoreboard            排行榜（sort=community|printability）
  GET  /api/stats                 社区全局统计（顶部数据条用）
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

app = FastAPI(title="SnapPrint · 咔印3D 社区", version="0.8.0")

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


@app.get("/api/shapes")
def list_shapes(_: None = Depends(guard)):
    """内置模型实例库：16 款参数化真 3D 几何（花瓶/宝石/圆环/棋子/灯笼…）。

    v0.5 浏览器版「内置模型库」的后端移植：无需照片、纯参数驱动，
    全部水密可直接切片打印。前端用于「模型实例」一键生成面板。
    """
    try:
        from .shapes import shape_list

        return JSONResponse({"shapes": shape_list()})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"实例列表失败: {e}")


@app.post("/api/shapes/{shape_id}/generate")
async def generate_shape(
    shape_id: str,
    H: float = Form(0),
    D: float = Form(0),
    seg: int = Form(0),
    twist: float = Form(0),
    lobes: int = Form(-1),
    author: str = Form(""),
    printer: str = Form(""),
    material: str = Form(""),
    _: None = Depends(guard),
):
    """一键生成内置模型实例 → 可打印性分析 → 发布到社区画廊。

    参数（表单，可全部留空用默认值）：H=高 mm、D=直径 mm、seg=分段、
    twist=扭转度数、lobes=棱数。生成的 .stl 可直接下载切片，
    另存带顶点色 .obj 便于彩色查看。
    """
    from .shapes import build, by_id

    sh = by_id(shape_id)
    if sh is None:
        raise HTTPException(status_code=404, detail=f"未知模型实例: {shape_id}")

    params: dict = {}
    if H > 0:
        params["H"] = H
    if D > 0:
        params["D"] = D
    if seg > 0:
        params["seg"] = seg
    if twist:
        params["twist"] = twist
    if lobes >= 0:
        params["lobes"] = lobes

    try:
        mesh = build(shape_id, params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")

    import io as _io

    stl_buf = _io.BytesIO()
    try:
        mesh.export(stl_buf, file_type="stl")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")
    stl_bytes = stl_buf.getvalue()

    try:
        rec = advisor.analyze_upload(
            stl_bytes, filename=f"{shape_id}.stl", printer=printer, material=material
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")

    sid = uuid.uuid4().hex[:12]
    stl_path = UPLOADS / f"{sid}.stl"
    stl_path.write_bytes(stl_bytes)
    try:
        mesh.export(UPLOADS / f"{sid}.obj")  # 带顶点色
    except Exception:
        pass
    db.add_submission(
        sid=sid,
        filename=f"{sh['name']}_{shape_id}.stl",
        author=author,
        ext=".stl",
        size_bytes=len(stl_bytes),
        model_path=str(stl_path),
        report=rec,
    )
    return JSONResponse(
        {
            "id": sid,
            "shape": {"id": sh["id"], "name": sh["name"], "emoji": sh["emoji"], "tag": sh["tag"]},
            "report": rec,
            "score": rec.get("score", 0),
        }
    )


@app.get("/api/gallery")
def gallery(limit: int = 24, offset: int = 0, _: None = Depends(guard)):
    """画廊列表（分页，按时间倒序）。"""
    items, total = db.list_submissions(limit=min(limit, 100), offset=max(offset, 0))
    return JSONResponse({"items": items, "total": total})


@app.get("/api/models/{sid}")
def model_detail(sid: str, _: None = Depends(guard)):
    """模型详情 = 分析报告 + 评论 + 社区评分统计（含贝叶斯调整分）。"""
    sub = db.get_submission(sid)
    if not sub:
        raise HTTPException(status_code=404, detail="模型不存在")
    comments = db.list_comments(sid)
    rstats = db.get_rating_stats(sid)
    g = db.global_rating_stats()
    # 贝叶斯调整分（IMDB 式）：样本少时向全局均值收敛，防刷分虚高
    C = 5.0
    M = g["avg_rating"] or 0.0
    n = rstats["count"]
    rstats["bayes"] = (
        round((C * M + rstats["avg"] * n) / (C + n), 2) if n else round(sub.get("score", 0), 2)
    )
    rstats["printability"] = sub.get("score", 0)
    return JSONResponse({"submission": sub, "comments": comments, "rating": rstats, "global": g})


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


@app.post("/api/models/{sid}/rate")
async def rate_model(
    sid: str,
    author: str = Form(""),
    stars: int = Form(0),
    review: str = Form(""),
    _: None = Depends(guard),
):
    """社区评分：1–5 星 + 必填文字评价（每作者限评一次，重复提交覆盖）。"""
    author = (author or "").strip()
    review = (review or "").strip()
    if not author or author == "匿名":
        raise HTTPException(status_code=400, detail="评分需填写昵称（不可匿名）")
    if not (1 <= stars <= 5):
        raise HTTPException(status_code=400, detail="星级需在 1–5 之间")
    if len(review) < 10:
        raise HTTPException(status_code=400, detail="评价至少 10 个字，说说打印体验或改进建议")
    if not db.get_submission(sid):
        raise HTTPException(status_code=404, detail="模型不存在")
    db.add_rating(sid=sid, author=author, stars=stars, review=review)
    return JSONResponse({"ok": True, "rating": db.get_rating_stats(sid)})


@app.get("/api/presets")
def presets(_: None = Depends(guard)):
    """打印机 / 材料预设（前端下拉用）。"""
    return JSONResponse({"printers": advisor.PRINTERS, "materials": advisor.MATERIALS})


@app.get("/api/scoreboard")
def scoreboard(limit: int = 12, sort: str = "community", _: None = Depends(guard)):
    """社区排行榜。sort=community（默认）按贝叶斯社区评分；sort=printability 按自动可打印性分。"""
    items, _ = db.list_submissions(limit=min(limit, 100), offset=0)
    g = db.global_rating_stats()
    C = 5.0
    M = g["avg_rating"] or 0.0
    for it in items:
        rs = db.get_rating_stats(it["id"])
        it["rating_count"] = rs["count"]
        it["community_rating"] = (
            round((C * M + rs["avg"] * rs["count"]) / (C + rs["count"]), 2)
            if rs["count"] else round(it["score"], 2)
        )
    if sort == "printability":
        ranked = sorted(items, key=lambda x: x["score"], reverse=True)
    else:
        ranked = sorted(items, key=lambda x: x["community_rating"], reverse=True)
    return JSONResponse({"items": ranked, "sort": sort, "global": g})


@app.get("/api/stats")
def stats(_: None = Depends(guard)):
    """社区全局统计（顶部数据条用）。"""
    return JSONResponse(db.global_rating_stats())


@app.get("/api/health")
def health():
    """健康检查（无需鉴权），供前端探测后端在线状态 / Docker 健康检查。"""
    return JSONResponse({"ok": True, "version": "0.8.0"})


# 静态下载上传的模型原文件（注册在前，优先级高于根 "/" 挂载）
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS)), name="outputs")

# 纯静态前端：与 surge 线上 Demo 共用同一份 web/。
app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
