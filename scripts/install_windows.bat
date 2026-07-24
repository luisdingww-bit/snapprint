@echo off
REM SnapPrint 一键启动（Windows）
cd /d "%~dp0.."

REM 仅首次创建虚拟环境
if not exist .venv (
  echo ==^> 创建虚拟环境
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo ==^> 安装依赖（已装会自动跳过，首次约需几分钟）
pip install -r requirements.txt

echo ==^> 启动 Web 服务，3 秒后自动打开浏览器 http://localhost:8000
REM 延迟打开浏览器，等 uvicorn 就绪
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"

python -m app.main
pause
