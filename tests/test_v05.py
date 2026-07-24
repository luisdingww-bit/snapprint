"""v0.5 测试：多引擎模型动物园（对齐 modly）+ 图生3D 生成参数（remesh/贴图）。

覆盖：
  - config.resolve_model / resolve_model_full 对新引擎的路由与 rich 字段
  - backends.get_backend 路由到新后端类（Sf3dBackend / TrellisBackend）
  - _apply_remesh / _apply_texture 在 trimesh 网格上的行为（none/triangle/quad 回退、贴图烘焙）
  - API /api/models 返回 speed/texture 字段
  - API /api/generate 接受 remesh/enable_texture/texture_resolution/params
"""
from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
import trimesh

from app.config import MODEL_ZOO, resolve_model, resolve_model_full
from app.backends import _apply_remesh, _apply_texture, get_backend


# ---------------------------------------------------------------------------
# 模型动物园（对齐 modly 多引擎阵容）
# ---------------------------------------------------------------------------
def test_modly_engines_present():
    ids = {m["id"] for m in MODEL_ZOO}
    for e in ("sf3d", "hunyuan3d", "hunyuan3d-mini", "hunyuan3d-mini-turbo",
             "hunyuan3d-mini-fast", "triposg", "trellis2", "figure",
             "jewelry", "ecom"):
        assert e in ids, f"模型动物园缺少引擎：{e}"


def test_resolve_model_routing():
    assert resolve_model("sf3d")[0] == "sf3d"
    assert resolve_model("trellis2")[0] == "trellis"
    assert resolve_model("triposg")[0] == "triposr"
    assert resolve_model("hunyuan3d-mini-turbo")[0] == "hunyuan3d"
    # 未知 / 空 → 默认 hunyuan3d
    assert resolve_model("")[0] == "hunyuan3d"
    assert resolve_model("not-a-real-id")[0] == "hunyuan3d"


def test_resolve_full_has_rich_fields():
    e = resolve_model_full("sf3d")
    assert e["speed"] == "fast"
    assert "texture" in e and "params" in e and "domain" in e
    # 每个引擎都应声明速度档位
    for m in MODEL_ZOO:
        assert m["speed"] in ("fastest", "fast", "balanced", "quality")


def test_get_backend_new_classes():
    assert get_backend("ai", None, "sf3d").__class__.__name__ == "Sf3dBackend"
    assert get_backend("ai", None, "trellis2").__class__.__name__ == "TrellisBackend"
    assert get_backend("ai", None, "hunyuan3d-mini-turbo").__class__.__name__ == "HunyuanBackend"


# ---------------------------------------------------------------------------
# 生成参数 helper
# ---------------------------------------------------------------------------
def _textured_box():
    m = trimesh.creation.box()
    img = Image.new("RGB", (4, 4), (255, 0, 0))
    m.visual = trimesh.visual.TextureVisuals(image=img)
    return m


def test_apply_texture_bakes_to_vertex_color():
    m = _textured_box()
    assert isinstance(m.visual, trimesh.visual.TextureVisuals)
    out = _apply_texture(m, False, 1024)
    assert isinstance(out.visual, trimesh.visual.ColorVisuals)


def test_apply_texture_keep():
    m = _textured_box()
    out = _apply_texture(m, True, 1024)
    assert isinstance(out.visual, trimesh.visual.TextureVisuals)


def test_apply_remesh_none_and_triangle():
    m = trimesh.creation.box()
    out, note = _apply_remesh(m, "none")
    assert note == "" and isinstance(out, trimesh.Trimesh)
    out2, note2 = _apply_remesh(m, "triangle")
    assert isinstance(out2, trimesh.Trimesh)  # 三角网格无需改动


def test_apply_remesh_quad_fallback_without_pymeshlab():
    m = trimesh.creation.box()
    out, note = _apply_remesh(m, "quad")
    # 本环境未装 pymeshlab → 安全回退为三角网格并给出说明
    assert note and isinstance(out, trimesh.Trimesh)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def test_models_api_has_speed_texture():
    c = TestClient(__import__("app.main", fromlist=["app"]).app)
    r = c.get("/api/models")
    assert r.status_code == 200
    models = r.json()["models"]
    byid = {m["id"]: m for m in models}
    assert "speed" in byid["sf3d"] and "texture" in byid["sf3d"]
    assert byid["sf3d"]["speed"] == "fast"


def test_generate_accepts_gen_params():
    from app.main import app
    c = TestClient(app)
    img = Image.new("RGB", (8, 8), (120, 80, 200))
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    r = c.post(
        "/api/generate",
        files={"file": ("a.png", buf.read(), "image/png")},
        data={
            "mode": "relief",
            "remesh": "triangle",
            "enable_texture": "false",
            "texture_resolution": "512",
            "params": '{"foo": 1}',
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "stats" in body and body["stats"]["faces"] > 0
