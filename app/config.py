"""SnapPrint 默认配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class SnapConfig:
    # 网格分辨率（浮雕模式下的高度图网格数，越大越精细但越慢）
    grid_x: int = 128
    grid_y: int = 128

    # 物理尺寸（毫米），直接面向 3D 打印
    tile_width_mm: float = 60.0     # 成品 X 方向尺寸
    tile_depth_mm: float = 60.0     # 成品 Y 方向尺寸
    base_thickness_mm: float = 2.0  # 底座厚度（保证可粘热床）
    relief_depth_mm: float = 4.0    # 浮雕最大起伏高度

    # 后处理
    target_triangles: int = 80000   # 减面目标面数（保护打印机/切片软件；离线浮雕约6.5万面不触发）
    fill_holes: bool = True         # 自动补洞，确保水密
    orient_up: bool = True          # 自动把模型摆正（底面朝下）

    # 导出格式
    export_obj: bool = True
    export_ply_vertex_color: bool = True   # 带顶点颜色
    export_3mf: bool = True               # 3MF（颜色 + 可打印元数据）

    # AI 模式后端选择：hunyuan3d | triposr
    ai_backend: str = "hunyuan3d"
    # 模型权重/推理代码所在目录（需用户自行放置开源权重）
    model_dir: str = "models"

    # AI 模式推理参数
    ai_steps: int = 50                 # 扩散步数（质量 vs 速度）
    ai_device: str = "auto"           # auto | cuda | cpu


DEFAULT_CONFIG = SnapConfig()


# ---------------------------------------------------------------------------
# 模型动物园（Model Zoo）
# 基础模型 + 社区微调垂类。权重需用户自备并放入 cfg.model_dir 对应子目录。
# `available` 仅作前端标注；真正的可用性由本机 models/ 目录是否存在权重决定
# （见 resolve_model / 后端 /api/models 的本地探测）。
# ---------------------------------------------------------------------------
MODEL_ZOO: list[dict] = [
    {
        "id": "hunyuan3d", "name": "Hunyuan3D-2（通用底座）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2", "domain": "通用", "available": True,
        "note": "腾讯开源通用图生3D，首次使用自动从 HuggingFace 拉取权重",
    },
    {
        "id": "triposr", "name": "TripoSR（轻量快速）", "backend": "triposr",
        "weights": "TripoSR", "domain": "通用", "available": True,
        "note": "Stability 开源，单图秒级重建，需自备 GPU 权重",
    },
    {
        "id": "figure", "name": "手办模型（社区微调）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2-figure", "domain": "手办", "available": False,
        "note": "适合人形/手办细节；将权重放置于 models/Hunyuan3D-2-figure",
    },
    {
        "id": "jewelry", "name": "珠宝模型（社区微调）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2-jewelry", "domain": "珠宝", "available": False,
        "note": "金属/宝石反光细节；权重放置于 models/Hunyuan3D-2-jewelry",
    },
    {
        "id": "ecom", "name": "电商模型（社区微调）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2-ecom", "domain": "电商", "available": False,
        "note": "商品白底图优化；权重放置于 models/Hunyuan3D-2-ecom",
    },
]

# 本地确实存在的权重目录（供 /api/models 标注 available）
def _local_weights_present(cfg, weights: str) -> bool:
    return os.path.isdir(os.path.join(getattr(cfg, "model_dir", "models"), weights))


def resolve_model(model_id: str = "", cfg=None) -> tuple:
    """把 model_id 解析为 (backend_name, weights_dir, domain)。

    - 空 / 未知 → 回退通用 hunyuan3d 的默认权重
    - 命中垂类 → 返回其 backend + 专用权重目录
    离线浮雕模式忽略 model。
    """
    if not model_id:
        return "hunyuan3d", "Hunyuan3D-2", "通用"
    for m in MODEL_ZOO:
        if m["id"] == model_id:
            return m["backend"], m["weights"], m["domain"]
    return "hunyuan3d", "Hunyuan3D-2", "通用"

