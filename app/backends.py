"""生成后端：离线浮雕模式（零依赖、保证可跑）+ AI 模式适配层。

AI 模式(Hunyuan3D / TripoSR)为「可插拔适配层」——把业界开源权重
通过统一接口接入。运行 AI 模式需要用户自行放置权重与推理代码到 models/，
本仓库默认提供保证可跑的离线浮雕模式。
"""
from __future__ import annotations

import io

import numpy as np
import trimesh
from PIL import Image


def build_relief_mesh(
    image: "Image.Image",
    *,
    grid_x: int,
    grid_y: int,
    tile_w: float,
    tile_d: float,
    base_th: float,
    relief_h: float,
) -> "trimesh.Trimesh":
    """把照片转成「浮雕刻印」式可打印网格（带顶点颜色）。

    结构：底部平整底座 + 顶部按亮度起伏的浮雕面，四周封边，
    形成水密实体。零外部模型依赖，保证开箱即跑。
    """
    img = image.convert("RGB")
    small = img.resize((grid_x, grid_y), Image.BILINEAR)
    rgb = np.asarray(small, dtype=np.float32) / 255.0  # (gy, gx, 3)
    gray = rgb.mean(axis=2)                            # (gy, gx)
    h = gray.T                                          # (gx, gy) 亮度

    xs = np.linspace(0, tile_w, grid_x)
    ys = np.linspace(0, tile_d, grid_y)
    X, Y = np.meshgrid(xs, ys, indexing="ij")          # (gx, gy)
    Z = base_th + h * relief_h

    gx, gy = grid_x, grid_y
    n = gx * gy
    top = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    bottom = np.stack([X.ravel(), Y.ravel(), np.zeros(n)], axis=1)
    verts = np.vstack([top, bottom])

    # 颜色：顶部与底部都用照片颜色（侧面自然带色）
    col_top = rgb.transpose(1, 0, 2).reshape(n, 3)     # (gx,gy,3)->(n,3)
    colors = np.vstack([col_top, col_top])

    faces: list[list[int]] = []
    # 顶面
    for i in range(gx - 1):
        for j in range(gy - 1):
            a, b = i * gy + j, (i + 1) * gy + j
            c, d = (i + 1) * gy + (j + 1), i * gy + (j + 1)
            faces.append([a, b, c]); faces.append([a, c, d])
    # 底面（反向缠绕，法线朝下）
    for i in range(gx - 1):
        for j in range(gy - 1):
            a, b = n + i * gy + j, n + (i + 1) * gy + j
            c, d = n + (i + 1) * gy + (j + 1), n + i * gy + (j + 1)
            faces.append([a, c, b]); faces.append([a, d, c])
    # 四壁
    for i in range(gx - 1):  # 前 j=0 / 后 j=gy-1
        t0, t1 = i * gy, (i + 1) * gy
        b0, b1 = n + i * gy, n + (i + 1) * gy
        faces += [[t0, t1, b1], [t0, b1, b0]]
        t0, t1 = i * gy + (gy - 1), (i + 1) * gy + (gy - 1)
        b0, b1 = n + i * gy + (gy - 1), n + (i + 1) * gy + (gy - 1)
        faces += [[t0, b1, t1], [t0, b0, b1]]
    for j in range(gy - 1):  # 左 i=0 / 右 i=gx-1
        t0, t1 = j, j + 1
        b0, b1 = n + j, n + j + 1
        faces += [[t0, t1, b1], [t0, b1, b0]]
        t0, t1 = (gx - 1) * gy + j, (gx - 1) * gy + (j + 1)
        b0, b1 = n + (gx - 1) * gy + j, n + (gx - 1) * gy + (j + 1)
        faces += [[t0, b1, t1], [t0, b0, b1]]

    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.visual = trimesh.visual.ColorVisuals(
        mesh=mesh, vertex_colors=(colors * 255).astype(np.uint8)
    )
    return mesh


class Backend:
    name = "base"

    def generate(self, image: "Image.Image", **kwargs) -> "trimesh.Trimesh":
        raise NotImplementedError


class ReliefBackend(Backend):
    """离线浮雕模式：零依赖，保证开箱即跑，是项目的「最低可用版本」。"""
    name = "relief"

    def __init__(self, cfg):
        self.cfg = cfg

    def generate(self, image: "Image.Image", **kwargs) -> "trimesh.Trimesh":
        return build_relief_mesh(
            image,
            grid_x=self.cfg.grid_x,
            grid_y=self.cfg.grid_y,
            tile_w=self.cfg.tile_width_mm,
            tile_d=self.cfg.tile_depth_mm,
            base_th=self.cfg.base_thickness_mm,
            relief_h=self.cfg.relief_depth_mm,
        )


class HunyuanBackend(Backend):
    """Hunyuan3D 适配层（需自备权重 + 推理代码到 models/）。"""
    name = "hunyuan3d"

    def __init__(self, cfg):
        self.cfg = cfg
        self._model = None

    def _load(self):
        import sys
        sys.path.insert(0, self.cfg.model_dir)
        try:
            from hunyuan3d_pipeline import build_pipeline
            self._model = build_pipeline(self.cfg.model_dir)
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "AI 模式(hunyuan3d)需要把 Hunyuan3D 权重与推理代码放到 "
                f"{self.cfg.model_dir}/ 下（参考 docs/部署.md）。原始错误: {e}"
            ) from e

    def generate(self, image: "Image.Image", **kwargs) -> "trimesh.Trimesh":
        if self._model is None:
            self._load()
        mesh = self._model.image_to_mesh(image)
        return mesh


class TripoSRBackend(Backend):
    """TripoSR 适配层（轻量、快速，需自备权重到 models/）。"""
    name = "triposr"

    def __init__(self, cfg):
        self.cfg = cfg
        self._model = None

    def _load(self):
        import sys
        sys.path.insert(0, self.cfg.model_dir)
        try:
            from tsr_pipeline import build_pipeline
            self._model = build_pipeline(self.cfg.model_dir)
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "AI 模式(triposr)需要把 TripoSR 权重与推理代码放到 "
                f"{self.cfg.model_dir}/ 下。原始错误: {e}"
            ) from e

    def generate(self, image: "Image.Image", **kwargs) -> "trimesh.Trimesh":
        if self._model is None:
            self._load()
        return self._model.image_to_mesh(image)


def get_backend(mode: str, cfg):
    mode = (mode or "relief").lower()
    if mode in ("relief", "offline", "浮雕"):
        return ReliefBackend(cfg)
    if mode in ("hunyuan3d", "hunyuan", "ai"):
        return HunyuanBackend(cfg)
    if mode in ("triposr", "tripo"):
        return TripoSRBackend(cfg)
    raise ValueError(f"未知模式: {mode}")
