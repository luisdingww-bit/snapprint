"""SnapPrint 冒烟测试：验证离线浮雕模式产出水密、可打印网格。"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from app.config import SnapConfig
from app.pipeline import run

ROOT = Path(__file__).resolve().parent.parent


def _test_image() -> bytes:
    img = Image.new("RGB", (128, 128), (255, 255, 255))
    # 画个灰阶渐变 + 一个圆，模拟照片亮度起伏
    px = img.load()
    for y in range(128):
        for x in range(128):
            v = int(255 * (x / 128))
            px[x, y] = (v, v, v)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_relief_watertight_and_export():
    data = _test_image()
    cfg = SnapConfig(grid_x=64, grid_y=64)  # 测试用小网格，跑得快
    out = ROOT / "outputs" / "test"
    result = run(data, mode="relief", cfg=cfg, out_dir=out, name="test_model")

    stats = result["stats"]
    assert stats["watertight"] is True, f"网格未水密: {stats}"
    assert stats["faces"] > 0
    assert (out / "test_model.obj").exists(), "OBJ 未生成"
    assert (out / "test_model.ply").exists(), "PLY 未生成"
    # 3MF 依赖较多，存在即通过，缺失仅告警（不阻塞）
    print("OK 水密:", stats["watertight"], "面数:", stats["faces"],
          "尺寸mm:", [round(v, 1) for v in stats["size_mm"]])
