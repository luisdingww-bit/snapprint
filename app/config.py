"""SnapPrint 默认配置。"""
from __future__ import annotations

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


DEFAULT_CONFIG = SnapConfig()
