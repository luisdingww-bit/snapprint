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
) -> dict:
    """执行一次「照片 -> 可打印 3D」转换。

    返回：
        {
          "mode": str,
          "stats": {...},          # 水密/体积/面数/尺寸
          "files": {...} | None,   # 导出文件路径（若给了 out_dir）
          "mesh": trimesh.Trimesh  # 调用方可继续处理（不序列化）
        }
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    backend = get_backend(mode, cfg)
    raw = backend.generate(image)

    processed = postprocess(
        raw,
        target_triangles=cfg.target_triangles,
        fill_holes=cfg.fill_holes,
        orient_up=cfg.orient_up,
    )

    stats = mesh_stats(processed)

    files = None
    if out_dir is not None:
        files = export_all(
            processed,
            out_dir,
            name,
            export_obj=cfg.export_obj,
            export_ply_vertex_color=cfg.export_ply_vertex_color,
            export_3mf=cfg.export_3mf,
        )
        stats["files"] = files

    return {"mode": backend.name, "stats": stats, "files": files, "mesh": processed}
