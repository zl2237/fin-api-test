# 构建上下文 = platform/（render.yaml 中 dockerContext 指定）
# ---------- 前端构建 ----------
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- 运行镜像 ----------
FROM python:3.12-slim
# libgomp1：onnxruntime（ddddocr 依赖）运行时需要；ca-certificates：TiDB TLS 连接
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /build/dist ./frontend/dist
EXPOSE 8000
# 单 worker：定时调度器为 in-process，多 worker 会重复调度；PORT 由 Render 注入
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
