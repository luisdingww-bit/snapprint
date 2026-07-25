"""SnapPrint 分析引擎测试（可打印性 / 评分）。"""
from __future__ import annotations

import io

import pytest
import trimesh

from app import advisor


def _box(extents=(40, 30, 20)) -> "trimesh.Trimesh":
    return trimesh.creation.box(extents=extents)


def test_analyze_box_watertight():
    rec = advisor.analyze(_box(), "import")
    assert rec["watertight"] is True
    assert rec["supports"] is False


def test_score_full_for_good_box():
    rec = advisor.analyze(_box(), "import")
    assert advisor.score(rec) == 100


def test_analyze_upload_grid_file():
    buf = io.BytesIO()
    _box().export(buf, file_type="stl")
    data = buf.getvalue()
    rec = advisor.analyze_upload(data, filename="m.stl", material="pla")
    assert rec["watertight"] is True
    assert "score" in rec
    assert rec["grams"] > 0 and rec["minutes"] > 0
    assert rec["material"]["id"] == "pla"


def test_analyze_upload_rejects_bad_ext():
    with pytest.raises(ValueError):
        advisor.analyze_upload(b"fake", filename="x.png")


def test_nonwatertight_lowers_score():
    # 四面体缺一面 -> 非水密
    verts = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
    faces = [[0, 1, 2], [0, 1, 3], [0, 2, 3]]  # 缺一面
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    rec = advisor.analyze(m, "import")
    assert rec["watertight"] is False
    assert advisor.score(rec) < 100


def test_supported_ext_constant():
    assert ".stl" in advisor.SUPPORTED_EXT
    assert ".glb" in advisor.SUPPORTED_EXT
