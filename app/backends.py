"""生成后端：离线浮雕模式（零依赖、保证可跑）+ AI 模式适配层。

AI 模式(Hunyuan3D / TripoSR)为「可插拔适配层」——把业界开源权重
通过统一接口接入。运行 AI 模式需要用户自备 GPU + 权重（见 docs/部署.md），
本仓库默认提供保证可跑的离线浮雕模式。
"""
from __future__ import annotations

import os

import numpy as np
import trimesh
from PIL import Image

from .config import resolve_model, resolve_model_full


def _cuda_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _to_trimesh(obj) -> "trimesh.Trimesh":
    """把不同库返回的网格对象统一成 trimesh.Trimesh。"""
    if isinstance(obj, trimesh.Trimesh):
        return obj
    if isinstance(obj, trimesh.Scene):
        return obj.dump(concatenate=True)
    # hy3dgen 的 Mesh 包装对象，内含 .mesh
    if hasattr(obj, "mesh") and isinstance(obj.mesh, trimesh.Trimesh):
        return obj.mesh
    # 裸顶点/面数组
    if hasattr(obj, "vertices") and hasattr(obj, "faces"):
        return trimesh.Trimesh(vertices=np.asarray(obj.vertices),
                               faces=np.asarray(obj.faces))
    raise TypeError(f"无法把 {type(obj)!r} 转换成 trimesh.Trimesh")


def _apply_texture(mesh: "trimesh.Trimesh", enable_texture: bool, texture_resolution: int):
    """贴图处理：enable_texture=False 时把贴图烘焙为顶点色（利于切片/单色打印）。

    - enable_texture=True：保留生成时的贴图或顶点色，原样返回。
    - enable_texture=False：若网格带 TextureVisuals，烘焙成顶点色 ColorVisuals。
    无贴图的网格（已顶点色/纯色）直接返回。
    """
    if enable_texture:
        return mesh
    try:
        if isinstance(mesh.visual, trimesh.visual.TextureVisuals):
            baked = mesh.visual.to_color()
            if baked is not None:
                mesh = mesh.copy()
                mesh.visual = baked
    except Exception:
        # 烘焙失败则保留原样（不阻断主流程）
        pass
    return mesh


def _apply_remesh(mesh: "trimesh.Trimesh", remesh: str):
    """重网格化（modly 的 remesh 参数）：none / triangle / quad。

    返回 (mesh, note)。quad 需要 pymeshlab（部分环境无），缺失或失败则
    安全回退为三角网格并附说明 note。
    """
    note = ""
    remesh = (remesh or "none").lower()
    if remesh == "none":
        return mesh, note
    if remesh == "triangle":
        if not getattr(mesh, "is_triangles", True):
            try:
                mesh = mesh.triangulate()
            except Exception:
                pass
        return mesh, note
    if remesh == "quad":
        try:
            import tempfile
            import pymeshlab as _ms
            tmp = tempfile.mkdtemp()
            inp = os.path.join(tmp, "in.obj")
            outp = os.path.join(tmp, "out.obj")
            mesh.export(inp)
            mset = _ms.MeshSet()
            mset.load_new_mesh(inp)
            try:
                mset.meshing_quadrangulation()
            except Exception:
                # 个别 pymeshlab 版本用不同的四边形化接口
                mset.apply_filter("meshing_quadrangulation")
            mset.save_current_mesh(outp)
            mesh = trimesh.load(outp)
        except ImportError:
            note = "quad 重网格化需要 pymeshlab（本机未安装），已回退为三角网格"
            if not getattr(mesh, "is_triangles", True):
                try:
                    mesh = mesh.triangulate()
                except Exception:
                    pass
        except Exception as exc:  # 其他错误也安全回退
            note = f"quad 重网格化失败（{exc}），已回退为三角网格"
            if not getattr(mesh, "is_triangles", True):
                try:
                    mesh = mesh.triangulate()
                except Exception:
                    pass
        return mesh, note
    # 未知值按 none 处理
    return mesh, note



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
    """Hunyuan3D-2 适配层（需自备 GPU + 权重，见 docs/部署.md）。

    支持 Hunyuan3D-2 及其 Mini / Mini-Turbo / Mini-Fast 变体（通过 weights_dir
    与 variant 区分；turbo/fast 默认更少步数以提速）。
    """
    name = "hunyuan3d"

    def __init__(self, cfg, weights_dir: str = "Hunyuan3D-2", variant: str = ""):
        self.cfg = cfg
        self.weights_dir = weights_dir
        self.variant = variant or ""
        self._model = None

    def _load(self):
        try:
            from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未检测到 hy3dgen。AI 模式(Hunyuan3D)需要先准备环境：\n"
                "  1) 安装带 CUDA 的 PyTorch（按你的显卡选版本）\n"
                "     pip install torch --index-url https://download.pytorch.org/whl/cu121\n"
                "  2) pip install hy3dgen\n"
                "  3) 权重会自动从 HuggingFace 拉取，或放到 models/" + self.weights_dir + "\n"
                "详见 docs/部署.md"
            ) from e
        local = os.path.join(self.cfg.model_dir, self.weights_dir)
        source = local if os.path.isdir(local) else "tencent/Hunyuan3D-2"
        self._model = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(source)

    def generate(self, image: "Image.Image", **kwargs) -> "trimesh.Trimesh":
        if self._model is None:
            self._load()
        # 步数：turbo/fast 变体默认更少步数；否则用条目 params.steps / 全局配置
        if self.variant in ("turbo", "fast"):
            steps = int(kwargs.get("steps") or 20)
        else:
            steps = int(kwargs.get("steps")
                        or (kwargs.get("params") or {}).get("steps")
                        or self.cfg.ai_steps)
        remesh = kwargs.get("remesh", "none")
        enable_texture = bool(kwargs.get("enable_texture", False))
        texture_resolution = int(kwargs.get("texture_resolution", 1024))
        out = self._model(image=image, num_inference_steps=steps)
        mesh = _to_trimesh(out[0] if isinstance(out, (list, tuple)) else out)
        mesh = _apply_texture(mesh, enable_texture, texture_resolution)
        mesh, _note = _apply_remesh(mesh, remesh)
        return mesh


class TripoSRBackend(Backend):
    """TripoSR 适配层（轻量快速，需自备 GPU + 权重，见 docs/部署.md）。"""
    name = "triposr"

    def __init__(self, cfg, weights_dir: str = "TripoSR"):
        self.cfg = cfg
        self.weights_dir = weights_dir
        self._model = None

    def _load(self):
        import sys
        repo = os.path.join(self.cfg.model_dir, self.weights_dir)
        if os.path.isdir(repo):
            sys.path.insert(0, repo)
        try:
            from tsr.system import TSR
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未检测到 TripoSR。AI 模式(TripoSR)需要：\n"
                "  git clone https://github.com/stabilityai/TripoSR models/TripoSR\n"
                "  并安装其 requirements.txt（含 PyTorch+CUDA）\n"
                "详见 docs/部署.md"
            ) from e
        self._model = TSR.from_pretrained(
            "stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt"
        )
        dev = self.cfg.ai_device
        if dev == "auto":
            dev = "cuda" if _cuda_available() else "cpu"
        self._model.to(dev)

    def generate(self, image: "Image.Image", **kwargs) -> "trimesh.Trimesh":
        if self._model is None:
            self._load()
        # TripoSR 推荐先做去背景 + 前景缩放
        try:
            from tsr.utils import remove_background, resize_foreground
            img = remove_background(image.convert("RGB"))
            img = resize_foreground(img, 0.85)
        except Exception:
            img = image.resize((512, 512))
        arr = np.asarray(img)
        out = self._model.reconstruct([arr], batch_size=1)
        mesh = _to_trimesh(out[0] if isinstance(out, (list, tuple)) else out)
        mesh = _apply_texture(mesh, bool(kwargs.get("enable_texture", False)),
                              int(kwargs.get("texture_resolution", 1024)))
        mesh, _note = _apply_remesh(mesh, kwargs.get("remesh", "none"))
        return mesh


class Sf3dBackend(Backend):
    """SF3D 适配层（Stability Fast 3D，需自备 GPU + 权重，见 docs/部署.md）。

    stability-fast-3d 的具体加载/推理 API 随版本而变；本适配层在依赖就绪时
    应在此对接官方示例。依赖缺失时给出清晰指引，不静默失败。
    """
    name = "sf3d"

    def __init__(self, cfg, weights_dir: str = "SF3D"):
        self.cfg = cfg
        self.weights_dir = weights_dir
        self._model = None

    def _load(self):
        try:
            import sf3d  # stability-fast-3d
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未检测到 SF3D。AI 模式(SF3D)需要：\n"
                "  pip install stability-fast-3d\n"
                "  并准备 GPU 权重（放置于 models/" + self.weights_dir + "）\n"
                "详见 docs/部署.md"
            ) from e
        # 依赖已装：按你安装的 stability-fast-3d 版本在此初始化推理管线。
        # 不同版本入口不同（如 sf3d.pipelines / sf3d.apis），请对齐官方示例。
        raise RuntimeError(
            "SF3D 后端依赖已装，但加载调用需按你安装的 stability-fast-3d 版本对接"
            "（见其官方示例），或先把权重放到 models/" + self.weights_dir
        )

    def generate(self, image: "Image.Image", **kwargs) -> "trimesh.Trimesh":
        if self._model is None:
            self._load()
        out = self._model(image=image)
        mesh = _to_trimesh(out[0] if isinstance(out, (list, tuple)) else out)
        mesh = _apply_texture(mesh, bool(kwargs.get("enable_texture", False)),
                              int(kwargs.get("texture_resolution", 1024)))
        mesh, _note = _apply_remesh(mesh, kwargs.get("remesh", "none"))
        return mesh


class TrellisBackend(Backend):
    """Trellis2 适配层（高质量结构化潜空间，需自备 GPU + 权重，见 docs/部署.md）。

    与 SF3D 类似，Trellis 的具体推理 API 随版本而变；依赖就绪时在此对接。
    """
    name = "trellis"

    def __init__(self, cfg, weights_dir: str = "Trellis2"):
        self.cfg = cfg
        self.weights_dir = weights_dir
        self._model = None

    def _load(self):
        try:
            import trellis  # trellis / trellis2 推理环境
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未检测到 Trellis。AI 模式(Trellis2)需要：\n"
                "  按官方指引准备 trellis 推理环境与 GPU 权重\n"
                "  （放置于 models/" + self.weights_dir + "）\n"
                "详见 docs/部署.md"
            ) from e
        raise RuntimeError(
            "Trellis2 后端依赖已装，但加载调用需按你安装的 trellis 版本对接"
            "（见其官方示例），或先把权重放到 models/" + self.weights_dir
        )

    def generate(self, image: "Image.Image", **kwargs) -> "trimesh.Trimesh":
        if self._model is None:
            self._load()
        out = self._model(image=image)
        mesh = _to_trimesh(out[0] if isinstance(out, (list, tuple)) else out)
        mesh = _apply_texture(mesh, bool(kwargs.get("enable_texture", False)),
                              int(kwargs.get("texture_resolution", 1024)))
        mesh, _note = _apply_remesh(mesh, kwargs.get("remesh", "none"))
        return mesh


def get_backend(mode: str, cfg, model_id: str = ""):
    mode = (mode or "relief").lower()
    if mode in ("relief", "offline", "浮雕"):
        return ReliefBackend(cfg)
    # AI 模式：若有 model_id（模型动物园），按条目路由；否则回退默认 hunyuan3d
    entry = resolve_model_full(model_id) if model_id else resolve_model_full("")
    backend_name = entry["backend"]
    weights_dir = entry["weights"]
    if backend_name == "triposr":
        return TripoSRBackend(cfg, weights_dir)
    if backend_name == "sf3d":
        return Sf3dBackend(cfg, weights_dir)
    if backend_name == "trellis":
        return TrellisBackend(cfg, weights_dir)
    # 默认 / hunyuan3d（含 Mini / Turbo / Fast 变体，通过 weights_dir + variant 区分）
    variant = "turbo" if "turbo" in (model_id or "") else ("fast" if "fast" in (model_id or "") else "")
    return HunyuanBackend(cfg, weights_dir, variant=variant)
