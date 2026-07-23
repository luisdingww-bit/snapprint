#!/usr/bin/env bash
# SnapPrint 一键启动（Linux / macOS）
set -e
cd "$(dirname "$0")/.."

echo "==> 创建虚拟环境"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> 安装依赖"
pip install -r requirements.txt

echo "==> 启动 Web 服务 http://localhost:8000"
python -m app.main
