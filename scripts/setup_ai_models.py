"""准备 AI 模式所需的环境与权重（可选；离线浮雕模式完全不需要本脚本）。

SnapPrint 的「AI 图生 3D」是适配层：本脚本帮你把业界开源权重/推理代码
落地到 models/ 下，并把 Python 依赖装好。AI 模式需要 NVIDIA GPU + CUDA。

用法：
    python scripts/setup_ai_models.py --triposr      # 克隆 TripoSR + 装依赖（最易上手）
    python scripts/setup_ai_models.py --hunyuan3d   # 安装 hy3dgen（权重首次运行自动拉取）
    python scripts/setup_ai_models.py --all         # 上述全部
    python scripts/setup_ai_models.py --check        # 仅打印各后端当前可用性

各后端的权重位置与推理入口差异见 docs/部署.md。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
PY = sys.executable


def _run(cmd: list[str]) -> int:
    print("▶", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def setup_triposr() -> None:
    """克隆 TripoSR 并安装其依赖（轻量、快速，适合首次体验 AI 模式）。"""
    repo = MODELS_DIR / "TripoSR"
    if repo.exists():
        print(f"[skip] 已存在 {repo}")
    else:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        _run([
            "git", "clone", "--depth", "1",
            "https://github.com/stabilityai/TripoSR", str(repo),
        ])
    req = repo / "requirements.txt"
    if req.exists():
        _run([PY, "-m", "pip", "install", "-r", str(req)])
    print("[ok] TripoSR 准备完成；启动后端后选 AI 模式 + triposg 即可。")


def setup_hunyuan3d() -> None:
    """安装 Hunyuan3D-2 的 hy3dgen（权重首次运行自动从 HuggingFace 拉取）。"""
    print("[info] Hunyuan3D-2 需要带 CUDA 的 PyTorch；若尚未安装请先按显卡选版本：")
    print("       pip install torch --index-url https://download.pytorch.org/whl/cu121")
    _run([PY, "-m", "pip", "install", "hy3dgen"])
    print("[ok] hy3dgen 已安装；启动后端后选 AI 模式 + hunyuan3d 即可。")


def check() -> None:
    """打印各后端当前可用性（依赖是否装好、权重目录是否存在）。"""
    def has(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except Exception:
            return False

    print("后端           依赖就绪   权重目录")
    print("-" * 48)
    rows = [
        ("TripoSR (triposg)", "tsr", "TripoSR"),
        ("Hunyuan3D-2", "hy3dgen", "Hunyuan3D-2"),
        ("SF3D", "sf3d", "SF3D"),
        ("Trellis2", "trellis", "Trellis2"),
    ]
    for name, mod, wdir in rows:
        ok_dep = "✓" if has(mod) else "✗ (需安装)"
        ok_w = "✓" if (MODELS_DIR / wdir).is_dir() else "✗ (放 models/%s)" % wdir
        print(f"{name:<18} {ok_dep:<12} {ok_w}")


def main() -> None:
    ap = argparse.ArgumentParser(description="SnapPrint AI 模式环境准备")
    ap.add_argument("--triposr", action="store_true", help="克隆 TripoSR 并装依赖")
    ap.add_argument("--hunyuan3d", action="store_true", help="安装 hy3dgen")
    ap.add_argument("--all", action="store_true", help="准备所有可一键安装的 backend")
    ap.add_argument("--check", action="store_true", help="仅检查当前可用性")
    args = ap.parse_args()

    if args.check:
        check()
        return
    if not (args.triposr or args.hunyuan3d or args.all):
        ap.print_help()
        return

    if args.triposr or args.all:
        setup_triposr()
    if args.hunyuan3d or args.all:
        setup_hunyuan3d()


if __name__ == "__main__":
    main()
