"""内置模型实例库（app/shapes.py + /api/shapes*）测试。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shapes import SHAPES, build

client = TestClient(app)


def test_all_shapes_watertight():
    """16 款实例默认参数下全部水密且体积为正。"""
    assert len(SHAPES) == 16
    for s in SHAPES:
        mesh = build(s["id"])
        assert mesh.is_watertight, f"{s['id']} 非水密"
        assert mesh.volume > 0, f"{s['id']} 体积异常"


def test_build_custom_params_clamped():
    """参数会被安全钳制，极端值不报错。"""
    mesh = build("vase", {"H": 99999, "D": -5, "seg": 1, "twist": 9999, "lobes": 999})
    assert mesh.is_watertight
    # H 钳到 300，D 钳到 5
    ext = mesh.bounding_box.extents
    assert ext[2] <= 301


def test_build_unknown_raises():
    with pytest.raises(ValueError):
        build("nope")


def test_api_shapes_list():
    r = client.get("/api/shapes")
    assert r.status_code == 200
    shapes = r.json()["shapes"]
    assert len(shapes) == 16
    assert all("build" not in s for s in shapes)  # 不泄漏内部函数
    assert {"id", "name", "emoji", "tag", "defaults"} <= set(shapes[0].keys())


def test_api_shape_generate_and_gallery():
    r = client.post("/api/shapes/gem/generate", data={"author": "pytest"})
    assert r.status_code == 200
    j = r.json()
    assert j["shape"]["id"] == "gem"
    assert j["report"]["watertight"] is True
    assert j["score"] > 0
    # 已入画廊
    g = client.get("/api/gallery").json()
    assert any(it["id"] == j["id"] for it in g["items"])


def test_api_shape_generate_unknown_404():
    assert client.post("/api/shapes/nope/generate").status_code == 404
