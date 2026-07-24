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
# 对齐 modly 的多引擎图生3D 阵容：速度↔质量可选（sf3d / Hunyuan3D-2 系列 /
# TripoSG / Trellis2），外加社区微调垂类。权重需用户自备并放入
# cfg.model_dir 对应子目录。`available` 仅作前端标注；真正的可用性由本机
# models/ 目录是否存在权重决定（见 resolve_model / 后端 /api/models）。
#
# 字段说明：
#   id       前端/API 选择的模型标识
#   name     展示名
#   backend  后端路由名（hunyuan3d / triposr / sf3d / trellis）
#   weights  权重目录（相对于 cfg.model_dir）
#   domain   垂类（通用 / 手办 / 珠宝 / 电商）
#   available 本机是否已具备权重（运行时按 models/ 探测覆盖）
#   speed    速度↔质量档位：fastest / fast / balanced / quality
#   texture  是否支持生成带贴图的网格（True 时 enable_texture 可保留贴图）
#   params   模型专属默认推理参数（会合并进用户传入的 params）
#   note     前端提示
# ---------------------------------------------------------------------------
MODEL_ZOO: list[dict] = [
    {
        "id": "hunyuan3d", "name": "Hunyuan3D-2（通用底座）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2", "domain": "通用", "available": True,
        "speed": "balanced", "texture": True, "params": {"steps": 50},
        "note": "腾讯开源通用图生3D，首次使用自动从 HuggingFace 拉取权重",
    },
    {
        "id": "hunyuan3d-mini", "name": "Hunyuan3D 2 Mini（轻量）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2-mini", "domain": "通用", "available": False,
        "speed": "fast", "texture": True, "params": {"steps": 30},
        "note": "轻量版，速度更快；权重放置于 models/Hunyuan3D-2-mini",
    },
    {
        "id": "hunyuan3d-mini-turbo", "name": "Hunyuan3D 2 Mini Turbo（极速）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2-mini-turbo", "domain": "通用", "available": False,
        "speed": "fastest", "texture": True, "params": {"steps": 20},
        "note": "蒸馏加速，最快但细节略减；权重放置于 models/Hunyuan3D-2-mini-turbo",
    },
    {
        "id": "hunyuan3d-mini-fast", "name": "Hunyuan3D 2 Mini Fast（极速）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2-mini-fast", "domain": "通用", "available": False,
        "speed": "fastest", "texture": True, "params": {"steps": 20},
        "note": "蒸馏加速，最快但细节略减；权重放置于 models/Hunyuan3D-2-mini-fast",
    },
    {
        "id": "triposg", "name": "TripoSG（几何质量高）", "backend": "triposr",
        "weights": "TripoSG", "domain": "通用", "available": False,
        "speed": "balanced", "texture": False, "params": {},
        "note": "TripoSR 的图生3D继承者，几何质量高；映射到 TripoSR 后端，权重放置于 models/TripoSG",
    },
    {
        "id": "sf3d", "name": "SF3D（秒级·拓扑干净）", "backend": "sf3d",
        "weights": "SF3D", "domain": "通用", "available": False,
        "speed": "fast", "texture": False, "params": {},
        "note": "Stability 开源，秒级重建、四边形化拓扑；需安装 stability-fast-3d 与 GPU 权重",
    },
    {
        "id": "trellis2", "name": "Trellis2 GGUF（高质量）", "backend": "trellis",
        "weights": "Trellis2", "domain": "通用", "available": False,
        "speed": "quality", "texture": True, "params": {},
        "note": "高质量结构化潜空间；需 trellis 推理环境与权重，放置于 models/Trellis2",
    },
    {
        "id": "figure", "name": "手办模型（社区微调）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2-figure", "domain": "手办", "available": False,
        "speed": "balanced", "texture": True, "params": {"steps": 50},
        "note": "适合人形/手办细节；将权重放置于 models/Hunyuan3D-2-figure",
    },
    {
        "id": "jewelry", "name": "珠宝模型（社区微调）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2-jewelry", "domain": "珠宝", "available": False,
        "speed": "balanced", "texture": True, "params": {"steps": 50},
        "note": "金属/宝石反光细节；权重放置于 models/Hunyuan3D-2-jewelry",
    },
    {
        "id": "ecom", "name": "电商模型（社区微调）", "backend": "hunyuan3d",
        "weights": "Hunyuan3D-2-ecom", "domain": "电商", "available": False,
        "speed": "balanced", "texture": True, "params": {"steps": 50},
        "note": "商品白底图优化；权重放置于 models/Hunyuan3D-2-ecom",
    },
]

# 速度档位展示标签（前端 i18n 之外的基础标签）
SPEED_TAGS = {
    "fastest": "⚡ 极速",
    "fast": "🚀 快速",
    "balanced": "⚖️ 均衡",
    "quality": "💎 高质量",
}

# 本地确实存在的权重目录（供 /api/models 标注 available）
def _local_weights_present(cfg, weights: str) -> bool:
    return os.path.isdir(os.path.join(getattr(cfg, "model_dir", "models"), weights))


def _default_entry() -> dict:
    for m in MODEL_ZOO:
        if m["id"] == "hunyuan3d":
            return m
    return MODEL_ZOO[0]


def model_entry(model_id: str = "", cfg=None) -> dict:
    """返回 model_id 对应的完整条目；空/未知 → 默认通用 hunyuan3d 条目。"""
    if not model_id:
        return _default_entry()
    for m in MODEL_ZOO:
        if m["id"] == model_id:
            return m
    return _default_entry()


def resolve_model(model_id: str = "", cfg=None) -> tuple:
    """把 model_id 解析为 (backend_name, weights_dir, domain)。

    - 空 / 未知 → 回退通用 hunyuan3d 的默认权重
    - 命中条目 → 返回其 backend + 专用权重目录 + 垂类
    离线浮雕模式忽略 model。
    """
    e = model_entry(model_id, cfg)
    return e["backend"], e["weights"], e["domain"]


def resolve_model_full(model_id: str = "", cfg=None) -> dict:
    """返回 model_id 对应的完整条目字典（含 speed/texture/params 等）。"""
    return model_entry(model_id, cfg)

