FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend

EXPOSE 8000

# 模型权重与生成产物可挂载出来
VOLUME ["/app/models", "/app/outputs"]

CMD ["sh", "-c", "python -m app.main"]
