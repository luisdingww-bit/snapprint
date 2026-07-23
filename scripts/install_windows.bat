@echo off
REM SnapPrint 一键启动（Windows）
cd /d "%~dp0.."

echo ==^> 创建虚拟环境
python -m venv .venv
call .venv\Scripts\activate.bat

echo ==^> 安装依赖
pip install -r requirements.txt

echo ==^> 启动 Web 服务 http://localhost:8000
python -m app.main
pause
