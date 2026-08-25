"""
fin-api-test 平台后端入口。

启动方式（在 platform/backend 目录下）：
    # 方式一：使用 .env 文件（推荐，python-dotenv 自动加载）
    #   先复制 .env.example 为 .env，填写真实配置，然后：
    python -m uvicorn app.main:app --port 8000

    # 方式二：通过系统环境变量
    set JWT_SECRET_KEY=你的随机密钥
    python -m uvicorn app.main:app --reload --port 8000
"""
# 必须在导入 database/auth 之前加载 .env，否则环境变量读不到
from dotenv import load_dotenv

load_dotenv()

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth as auth_module
from . import models
from .database import SessionLocal, init_db
from .json_safe import BigintSafeJSONResponse
from .routers import (
    apis,
    auth,
    datasets,
    environments,
    executions,
    field_dictionaries,
    files,
    operation_logs,
    projects,
    reports,
    schedules,
    testcases,
    users,
    versions,
)
from .services.scheduler import scheduler_service

app = FastAPI(
    title="fin-api-test 平台",
    description="API 测试平台：DAG 编排 + 可视化断言/提取 + 结构化报告",
    version="0.1.0",
    # 自定义响应类：把超出 JS 安全整数范围的大整数（如雪花 ID）序列化为字符串，
    # 避免前端 JSON.parse 精度丢失（343557272766513152 → 343557272766513150）
    default_response_class=BigintSafeJSONResponse,
)

# CORS 白名单：从环境变量读取，逗号分隔；未配置时默认仅允许本地前端开发
# 注意：allow_origins 不能用 "*" 与 allow_credentials=True 同时使用，浏览器会拒绝
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_secret_key():
    """启动前校验 JWT 密钥：未设置则抛错中断启动，避免用默认空密钥跑起来"""
    if not os.getenv("JWT_SECRET_KEY"):
        msg = (
            "\n[启动失败] 未设置 JWT_SECRET_KEY 环境变量。\n"
            "请生成一个随机密钥并设置环境变量后重启：\n"
            "  Windows (PowerShell): $env:JWT_SECRET_KEY='你的随机密钥'\n"
            "  Windows (CMD):        set JWT_SECRET_KEY=你的随机密钥\n"
            "  Linux/Mac:            export JWT_SECRET_KEY='你的随机密钥'\n"
            "可用 Python 生成：python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        )
        sys.stderr.write(msg)
        raise RuntimeError(msg)


@app.on_event("startup")
def on_startup():
    _check_secret_key()
    init_db()
    _ensure_default_admin()
    _cleanup_old_executions()
    # 定时任务调度器：未安装 APScheduler 时优雅降级（available=False，功能关闭不报错）
    scheduler_service.start()


@app.on_event("shutdown")
def on_shutdown():
    scheduler_service.shutdown()


def _cleanup_old_executions(days: int = 30):
    """启动时自动清理指定天数前的执行记录（含步骤和断言），避免数据库无限膨胀"""
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=days)
    db = SessionLocal()
    try:
        old_execs = db.query(models.ExecutionRecord).filter(
            models.ExecutionRecord.started_at < cutoff
        ).all()
        count = len(old_execs)
        for exec_obj in old_execs:
            db.delete(exec_obj)
        if count > 0:
            db.commit()
            print(f"[启动清理] 已自动清理 {count} 条 {days} 天前的执行记录")
    except Exception as e:
        print(f"[启动清理] 清理执行记录失败（忽略）: {e}")
        db.rollback()
    finally:
        db.close()


def _ensure_default_admin():
    """首次启动且无用户时，创建默认 admin 账号（admin / admin123）"""
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            admin = models.User(
                username="admin",
                password_hash=auth_module.hash_password("admin123"),
                name="管理员",
                role="admin",
                must_change_password=True,
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()


@app.get("/")
def root():
    return {"name": "fin-api-test 平台", "docs": "/docs"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(operation_logs.router)
app.include_router(projects.router)
app.include_router(environments.router)
app.include_router(apis.router)
app.include_router(apis.group_router)
app.include_router(testcases.router)
app.include_router(testcases.group_router)
app.include_router(schedules.router)
app.include_router(datasets.router)
app.include_router(versions.router)
app.include_router(executions.router)
app.include_router(reports.router)
app.include_router(field_dictionaries.router)
app.include_router(files.router)
app.include_router(files.category_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
