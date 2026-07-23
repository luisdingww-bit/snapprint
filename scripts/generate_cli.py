#!/usr/bin/env python
"""SnapPrint 命令行生成（适合 GPU 服务器批量跑）。

示例：
  # 离线浮雕
  python scripts/generate_cli.py photo.jpg --mode relief --out outputs/cli

  # Hunyuan3D（需 GPU + hy3dgen）
  python scripts/generate_cli.py photo.jpg --mode hunyuan3d --device cuda --steps 50

  # TripoSR
  python scripts/generate_cli.py photo.jpg --mode triposr --device cuda
"""
from __future__ import annotations

import argparse

from app.config import SnapConfig
from app.pipeline import run


def main() -> None:
    ap = argparse.ArgumentParser(description="SnapPrint 照片转可打印 3D")
    ap.add_argument("image", help="输入图片路径")
    ap.add_argument("--mode", default="relief",
                    choices=["relief", "hunyuan3d", "triposr"],
                    help="生成模式")
    ap.add_argument("--out", default="outputs/cli", help="输出目录")
    ap.add_argument("--device", default="auto", help="auto | cuda | cpu")
    ap.add_argument("--steps", type=int, default=50, help="AI 模式扩散步数")
    args = ap.parse_args()

    data = open(args.image, "rb").read()
    cfg = SnapConfig(ai_device=args.device, ai_steps=args.steps)
    result = run(data, mode=args.mode, cfg=cfg, out_dir=args.out, name="model")

    stats = result["stats"]
    print(f"模式: {result['mode']}")
    print(f"水密: {stats['watertight']}  面数: {stats['faces']}  "
          f"尺寸(mm): {[round(v, 1) for v in stats['size_mm']]}")
    print("文件:", result.get("files"))


if __name__ == "__main__":
    main()
