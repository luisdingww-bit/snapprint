# SnapPrint 咔印3D · ComfyUI 自定义节点入口
# 将本目录（SnapPrintNode）整体放入 ComfyUI 的 custom_nodes/ 目录即可启用。
from .nodes import (
    SnapPrintGenerate,
    SnapPrintAnalyze,
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
