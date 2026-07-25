# SnapPrint 社区版 — 一键自托管镜像
# 后端(FastAPI + SQLite) 与前端(web/) 一体，跑在任何装了 Docker 的机器上都完整可用。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码（app/ web/ scripts/ 等）
COPY app ./app
COPY web ./web
COPY scripts ./scripts

# 数据与上传文件用卷持久化（见 docker-compose.yml）
VOLUME ["/app/data", "/app/outputs"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

CMD ["python", "-m", "app.main"]
