# 构建上下文 = 仓库根（render.yaml 中 dockerContext 指定）
# ---------- 前端构建 ----------
FROM node:22-alpine AS frontend
WORKDIR /build
COPY platform/frontend/package.json platform/frontend/package-lock.json ./
RUN npm ci
COPY platform/frontend/ ./
RUN npm run build

# ---------- 运行镜像 ----------
# 目录结构与仓库保持一致（/workspace = 仓库根）：
# app/path_setup.py 以 parents[3] 定位项目根，main.py 以 parents[2] 定位 platform/
FROM python:3.12-slim
# libgomp1：onnxruntime（ddddocr 依赖）运行时需要；ca-certificates：TiDB TLS 连接
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY platform/backend/requirements.txt ./platform/backend/requirements.txt
RUN pip install --no-cache-dir -r platform/backend/requirements.txt
COPY platform/backend/ ./platform/backend/
# 平台后端复用的仓库根工具包（expression/request_sender/runtime_service/dag_executor）
COPY utils/ ./utils/
COPY --from=frontend /build/dist ./platform/frontend/dist
EXPOSE 8000
# 单 worker：定时调度器为 in-process，多 worker 会重复调度；PORT 由 Render 注入
CMD ["sh", "-c", "cd platform/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
