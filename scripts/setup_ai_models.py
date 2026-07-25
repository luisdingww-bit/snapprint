"""准备 AI 模式所需的环境与权重（可选；离线浮雕模式完全不需要本脚本）。

SnapPrint 的「AI 图生 3D」是适配层：本脚本帮你把业界开源权重 / 推理代码
落地到 models/ 下，并把 Python 依赖装好。AI 模式需要 NVIDIA GPU + CUDA。

两层能力：
  1) 依赖准备：克隆 TripoSR 仓库、安装 hy3dgen 等（见各 --xxx 开关）。
  2) 权重下载：把 HuggingFace / ModelScope 上的权重拉到 models/<Dir>，
     使其与 backends.py / config.py 中的权重目录一一对应，实现「开箱即用 /
     离线预置」。国内用户可加 --mirror hf（hf-mirror.com）或 --mirror modelscope。

用法：
    # 依赖 + 权重 一键到位（示例：Hunyuan3D-2 全量）
    python scripts/setup_ai_models.py --hunyuan3d --download tencent/Hunyuan3D-2
    # 仅下载权重（国内走镜像）
    python scripts/setup_ai_models.py --download tencent/Hunyuan3D-2mini --mirror hf
    # 便捷开关：克隆 TripoSR 并装依赖
    python scripts/setup_ai_models.py --triposr
    # 检查各后端当前可用性
    python scripts/setup_ai_models.py --check

各后端的权重目录（models/ 下）与推理入口差异见 docs/部署.md。
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

# ---------------------------------------------------------------------------
# 权重索引：逻辑名 -> (HF 仓库 ID, 本地目录, [ModelScope 仓库 ID], 备注)
# 本地目录与 app/config.py 的 MODEL_ZOO「weights」字段严格对应，
# 这样 backends 才能用 from_pretrained(<本地目录>) 直接加载。
# ---------------------------------------------------------------------------
WEIGHTS: dict[str, dict] = {
    "hunyuan3d": {
        "hf": "tencent/Hunyuan3D-2",
        "local": "Hunyuan3D-2",
        "ms": "AI-ModelScope/Hunyuan3D-2",
        "note": "腾讯通用底座（含几何 + 贴图）；约 6GB(仅几何分支)起，完整含贴图更大",
    },
    "hunyuan3d-mini": {
        "hf": "tencent/Hunyuan3D-2mini",
        "local": "Hunyuan3D-2mini",
        "ms": "AI-ModelScope/Hunyuan3D-2mini",
        "note": "0.6B 轻量，速度快；从_pretrained 需 subfolder='hunyuan3d-dit-v2-mini'",
    },
    "hunyuan3d-mini-turbo": {
        "hf": "tencent/Hunyuan3D-2-mini-turbo",
        "local": "Hunyuan3D-2-mini-turbo",
        "ms": "AI-ModelScope/Hunyuan3D-2-mini-turbo",
        "note": "蒸馏步数加速版 (0.6B)",
    },
    "hunyuan3d-mini-fast": {
        "hf": "tencent/Hunyuan3D-2-mini-fast",
        "local": "Hunyuan3D-2-mini-fast",
        "ms": "AI-ModelScope/Hunyuan3D-2-mini-fast",
        "note": "引导蒸馏加速版 (0.6B)",
    },
    "triposg": {
        "hf": "VAST-AI/TripoSG",
        "local": "TripoSG",
        "ms": None,
        "note": "VAST 高保真图生3D；映射到 triposr 后端。另需 RMBG-1.4 与 DINOv3",
    },
    "sf3d": {
        "hf": "stabilityai/stable-fast-3d",
        "local": "SF3D",
        "ms": None,
        "note": "Stability SF3D（Gated 仓库，需先 huggingface-cli login 同意协议）",
    },
    "trellis2": {
        "hf": "microsoft/TRELLIS-image-large",
        "local": "Trellis2",
        "ms": None,
        "note": "Microsoft TRELLIS 图像版(1.2B)；需按官方指引装 trellis 推理环境",
    },
}


def _run(cmd: list[str]) -> int:
    print("▶", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def enable_mirror(mirror: str) -> None:
    """设置下载镜像环境变量。

    - hf        : export HF_ENDPOINT=https://hf-mirror.com（国内加速）
    - modelscope: 后续权重改用 modelscope.snapshot_download
    - none      : 直连 HuggingFace
    """
    if mirror == "hf":
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        print("[mirror] 使用 hf-mirror.com 加速 HuggingFace 下载")
    elif mirror == "modelscope":
        print("[mirror] 将优先用 ModelScope 镜像下载（仅部分模型有对应仓库）")
    else:
        print("[mirror] 直连 HuggingFace（如遇网络问题可加 --mirror hf）")


def _download_hf(repo_id: str, local_dir: str, allow: list[str] | None = None) -> bool:
    """优先用 huggingface_hub 下载；缺失则回退 CLI。返回是否成功。"""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / local_dir
    target.mkdir(parents=True, exist_ok=True)
    # 1) huggingface_hub（最稳，支持断点续传 / allow_patterns）
    try:
        from huggingface_hub import snapshot_download
        print(f"[hf] snapshot_download {repo_id} -> models/{local_dir}")
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target),
            allow_patterns=allow,
            local_dir_use_symlinks=False,
        )
        return True
    except ImportError:
        pass
    # 2) CLI 回退
    cmd = [
        "huggingface-cli", "download", "--resume-download",
        repo_id, "--local-dir", str(target),
    ]
    if allow:
        for p in allow:
            cmd += ["--include", p]
    return _run(cmd) == 0


def _download_ms(repo_id_ms: str, local_dir: str) -> bool:
    try:
        from modelscope import snapshot_download
    except ImportError:
        print("[modelscope] 未安装 modelscope，先 pip install modelscope")
        return False
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / local_dir
    print(f"[ms] snapshot_download {repo_id_ms} -> models/{local_dir}")
    model_dir = snapshot_download(repo_id_ms, cache_dir=str(target))
    print(f"[ms] 已下载至 {model_dir}")
    return True


def download_weights(name: str, mirror: str = "none") -> bool:
    """按逻辑名下载权重到 models/<local>。"""
    info = WEIGHTS.get(name)
    if not info:
        print(f"[skip] 未知权重名 {name!r}，请用 --download <HF仓库ID> 直传")
        return False
    local = info["local"]
    if (MODELS_DIR / local).exists() and any((MODELS_DIR / local).iterdir()):
        print(f"[skip] models/{local} 已存在，跳过下载（如需重下请先删除该目录）")
        return True
    # ModelScope 优先（当指定且存在对应仓库）
    if mirror == "modelscope" and info.get("ms"):
        if _download_ms(info["ms"], local):
            return True
        print("[warn] ModelScope 下载失败，回退 HuggingFace")
    return _download_hf(info["hf"], local)


def download_raw(repo_id: str, local_dir: str | None = None, mirror: str = "none") -> bool:
    """直接按 HuggingFace 仓库 ID 下载（unknown 仓库用）。"""
    local_dir = local_dir or repo_id.split("/")[-1]
    if mirror == "modelscope":
        print("[warn] 直传仓库ID时 ModelScope 映射不可知，改走 HuggingFace")
    return _download_hf(repo_id, local_dir)


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
    print("[ok] TripoSR 准备完成；启动后端后选 AI 模式 + triposr 即可（权重首次运行自动拉取）。")


def setup_hunyuan3d() -> None:
    """安装 Hunyuan3D 推理包 hy3dgen（权重可后续用 --download 预置）。"""
    print("[info] Hunyuan3D-2 需要带 CUDA 的 PyTorch；若尚未安装请先按显卡选版本：")
    print("       pip install torch --index-url https://download.pytorch.org/whl/cu121")
    _run([PY, "-m", "pip", "install", "hy3dgen"])
    print("[ok] hy3dgen 已安装；权重可自动从 HuggingFace 拉取，或用 --download 预置到 models/Hunyuan3D-2。")


def check() -> None:
    """打印各后端当前可用性（依赖是否装好、权重目录是否存在）。"""
    def has(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except Exception:
            return False

    print("后端               依赖就绪     权重目录")
    print("-" * 52)
    rows = [
        ("TripoSR (triposg)", "tsr", "TripoSR"),
        ("Hunyuan3D-2", "hy3dgen", "Hunyuan3D-2"),
        ("Hunyuan3D-2 mini", "hy3dgen", "Hunyuan3D-2mini"),
        ("TripoSG", "tsr", "TripoSG"),
        ("SF3D", "stability-fast-3d", "SF3D"),
        ("Trellis2", "trellis", "Trellis2"),
    ]
    for name, mod, wdir in rows:
        ok_dep = "✓" if has(mod) else "✗ (需安装)"
        ok_w = "✓" if (MODELS_DIR / wdir).is_dir() else "✗ (缺权重)"
        print(f"{name:<20} {ok_dep:<12} {ok_w}")


def main() -> None:
    ap = argparse.ArgumentParser(description="SnapPrint AI 模式环境 / 权重准备")
    ap.add_argument("--triposr", action="store_true", help="克隆 TripoSR 并装依赖")
    ap.add_argument("--hunyuan3d", action="store_true", help="安装 hy3dgen（Hunyuan3D 推理包）")
    # 便捷权重下载开关
    ap.add_argument("--hunyuan3d-mini", action="store_true", help="下载 Hunyuan3D-2mini 权重")
    ap.add_argument("--triposg", action="store_true", help="下载 TripoSG 权重")
    ap.add_argument("--sf3d", action="store_true", help="下载 SF3D 权重（需先 huggingface-cli login）")
    ap.add_argument("--trellis", action="store_true", help="下载 Trellis2 权重")
    ap.add_argument("--download", metavar="REPO", help="按 HF 仓库ID直接下载，如 tencent/Hunyuan3D-2")
    ap.add_argument("--local-dir", metavar="DIR", help="配合 --download 指定 models/ 下的子目录名")
    ap.add_argument("--all", action="store_true", help="准备所有可一键安装/下载的 backend 与权重")
    ap.add_argument("--check", action="store_true", help="仅检查当前可用性")
    ap.add_argument("--mirror", choices=["none", "hf", "modelscope"], default="none",
                    help="下载镜像：hf=hf-mirror.com；modelscope=ModelScope")
    args = ap.parse_args()

    if args.check:
        check()
        return
    if not any([args.triposr, args.hunyuan3d, args.hunyuan3d_mini, args.triposg,
               args.sf3d, args.trellis, args.download, args.all]):
        ap.print_help()
        return

    enable_mirror(args.mirror)

    # 依赖准备
    if args.triposr or args.all:
        setup_triposr()
    if args.hunyuan3d or args.all:
        setup_hunyuan3d()

    # 权重下载
    if args.all:
        for n in ["hunyuan3d", "hunyuan3d-mini", "triposg", "sf3d", "trellis2"]:
            download_weights(n, args.mirror)
    if args.hunyuan3d_mini:
        download_weights("hunyuan3d-mini", args.mirror)
    if args.triposg:
        download_weights("triposg", args.mirror)
    if args.sf3d:
        download_weights("sf3d", args.mirror)
    if args.trellis:
        download_weights("trellis2", args.mirror)
    if args.download:
        download_raw(args.download, args.local_dir, args.mirror)

    print("\n[完成] 权重已就位。启动后端后在 Web UI 选择对应 AI 模式即可。")


if __name__ == "__main__":
    main()
