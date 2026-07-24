"""SnapPrint 可打印性 / 支撑建议分析测试（advisor + /api/analyze）。"""
from __future__ import annotations

import io

import trimesh
from fastapi.testclient import TestClient
from PIL import Image

from app import advisor
from app.main import app

client = TestClient(app)


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 80, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_box_self_supporting():
    """落地方块（自支撑几何）→ 免支撑、小尺寸用 0.12 层高。"""
    m = trimesh.creation.box(extents=(40, 40, 20))
    rec = advisor.analyze(m, mode="solid3d")
    assert rec["supports"] is False
    assert rec["layer_height"] == 0.12
    assert rec["overhang_ratio"] == 0.0


def _cantilever() -> "trimesh.Trimesh":
    """落地柱 + 顶部一侧伸出的悬挑板（板底明显高于柱底 → 真悬垂）。"""
    base = trimesh.creation.box(extents=(20, 20, 20))  # z: 0..20
    cant = trimesh.creation.box(extents=(30, 20, 2))
    cant.apply_translation([15, 0, 21])  # 伸出，底面 z=20 远高于最低面 0
    return trimesh.util.concatenate([base, cant])


def test_overhang_needs_support():
    """悬挑结构 → 判定需要支撑并给出密度/类型/摆放建议。"""
    m = _cantilever()
    rec = advisor.analyze(m, mode="solid3d")
    assert rec["supports"] is True
    assert rec["support_density"] > 0
    assert rec["support_type"] in ("normal", "tree")
    assert rec["orientation_advice"]  # 应给出摆放建议


def test_relief_self_supporting():
    """浮雕模式天然自支撑，无需支撑判定。"""
    m = trimesh.creation.box(extents=(60, 60, 6))
    rec = advisor.analyze(m, mode="relief")
    assert rec["supports"] is False


def test_analyze_endpoint_image():
    """上传图片 → 走浮雕生成 → 返回建议，浮雕免支撑。"""
    r = client.post(
        "/api/analyze",
        files={"file": ("t.png", _png(), "image/png")},
        data={"mode": "relief"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert "layer_height" in j and "supports" in j
    assert j["supports"] is False


def test_analyze_endpoint_mesh():
    """上传网格（STL）→ 直接分析悬挑结构 → 返回 needs support。"""
    m = _cantilever()
    buf = io.BytesIO()
    m.export(buf, file_type="stl")
    r = client.post(
        "/api/analyze",
        files={"file": ("m.stl", buf.getvalue(), "application/octet-stream")},
        data={"mode": "solid3d"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["supports"] is True


def test_analyze_endpoint_bad_file():
    """无文件扩展名 / 非图片非网格 → 500（无法解析）。"""
    r = client.post(
        "/api/analyze",
        files={"file": ("x.bin", b"\x00\x01", "application/octet-stream")},
        data={"mode": "solid3d"},
    )
    assert r.status_code == 500
