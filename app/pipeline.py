"""SnapPrint 主流水线：照片 -> 后端生成 -> 可打印后处理 -> 导出。

对外唯一入口：run()。Web 后端与 CLI 都调用它。
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from .config import DEFAULT_CONFIG
from .backends import get_backend
from .postprocess import export_all, mesh_stats, postprocess


def run(
    image_bytes: bytes,
    *,
    mode: str = "relief",
    cfg=DEFAULT_CONFIG,
    out_dir: "str | Path | None" = None,
    name: str = "model",
    progress_cb=None,
    model: str = "",
) -> dict:
    """执行一次「照片 -> 可打印 3D」转换。

    参数：
        progress_cb: 可选回调 ``cb(stage: str, percent: int)``，
                     用于异步任务队列向前端上报分阶段进度。

    返回：
        {
          "mode": str,
          "stats": {...},          # 水密/体积/面数/尺寸
          "files": {...} | None,   # 导出文件路径（若给了 out_dir）
          "mesh": trimesh.Trimesh  # 调用方可继续处理（不序列化）
        }
    """

    def _p(stage: str, pct: int) -> None:
        if progress_cb is not None:
            try:
                progress_cb(stage, pct)
            except Exception:  # 进度上报永不打断主流程
                pass

    _p("解码图片", 5)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    backend = get_backend(mode, cfg, model)
    _p(f"生成原始网格（{backend.name}）", 15)
    raw = backend.generate(image, steps=cfg.ai_steps, device=cfg.ai_device)

    _p("打印级后处理（水密 / 减面 / 摆正）", 65)
    processed = postprocess(
        raw,
        target_triangles=cfg.target_triangles,
        fill_holes=cfg.fill_holes,
        orient_up=cfg.orient_up,
    )

    _p("统计与质检", 82)
    stats = mesh_stats(processed)

    files = None
    if out_dir is not None:
        _p("导出 OBJ / PLY / 3MF", 90)
        files = export_all(
            processed,
            out_dir,
            name,
            export_obj=cfg.export_obj,
            export_ply_vertex_color=cfg.export_ply_vertex_color,
            export_3mf=cfg.export_3mf,
        )
        stats["files"] = files

    _p("完成", 100)
    return {"mode": backend.name, "stats": stats, "files": files, "mesh": processed}
