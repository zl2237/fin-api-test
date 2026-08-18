"""导出 OpenAPI schema 到前端（供 openapi-typescript 生成前端类型）。

用法：
    python scripts/export_openapi.py            # 输出 platform/frontend/openapi.json
    python scripts/export_openapi.py -o xx.json

前端生成（package.json 已加 gen:api 脚本）：
    cd platform/frontend && npm run gen:api

说明：导入 app 前设置与 conftest 相同的环境变量，避免 database/auth 模块
在无 .env 的环境（如 CI）加载失败；仅构建路由表，不连数据库。
"""
import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET_KEY", "export-schema-only")
os.environ.setdefault("DB_PASSWORD", "export")

# 允许从任意 cwd 运行：把 backend 目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o", "--output",
        default=str(Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"),
        help="输出路径（默认 platform/frontend/openapi.json）",
    )
    args = parser.parse_args()
    schema = app.openapi()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    paths = len(schema.get("paths", {}))
    schemas = len(schema.get("components", {}).get("schemas", {}))
    print(f"导出完成: {out}（{paths} paths / {schemas} schemas）")


if __name__ == "__main__":
    main()
