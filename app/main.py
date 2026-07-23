"""SnapPrint Web 后端（FastAPI）。

路由：
  GET  /              中文 Web UI
  POST /api/generate  上传图片 -> 返回可打印 3D 模型与统计
  GET  /outputs/*     下载生成的 OBJ / PLY / 3MF
"""
from __future__ import annotations

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

app = FastAPI(title="SnapPrint · 咔印3D", version="0.1.0")


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
    # 把本地路径转成可下载 URL
    files = stats.pop("files", None) or {}
    download = {
        k: f"/outputs/{job}/{Path(v).name}"
        for k, v in files.items()
        if k not in ("3mf_error",)
    }
    if "3mf_error" in files:
        download["3mf_error"] = files["3mf_error"]

    return JSONResponse({"mode": result["mode"], "stats": stats, "files": download})


# 静态下载生成的文件
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS)), name="outputs")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
