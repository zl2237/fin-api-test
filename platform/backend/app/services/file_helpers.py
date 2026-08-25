"""文件中心纯函数工具：路径构建、预览类型判断。

提取到独立模块便于单元测试，避免测试时触发 FastAPI 路由装饰器加载。
"""
import os
from pathlib import Path

# 上传根目录：默认 backend/uploads，可通过 .env UPLOAD_ROOT 覆盖
UPLOAD_ROOT = os.getenv("UPLOAD_ROOT", "uploads")

# 预览支持的 MIME 类型
IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif",
    "image/webp", "image/svg+xml", "image/bmp",
}
PDF_TYPE = "application/pdf"


def get_backend_dir() -> Path:
    """获取 backend 目录绝对路径"""
    return Path(__file__).resolve().parent.parent.parent


def get_upload_dir() -> Path:
    """获取上传根目录绝对路径：{backend}/{UPLOAD_ROOT}/files"""
    upload_dir = get_backend_dir() / UPLOAD_ROOT / "files"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def build_storage_path(sha256: str) -> str:
    """构建相对存储路径：files/{sha256前2位}/{sha256}"""
    return f"files/{sha256[:2]}/{sha256}"


def resolve_physical_path(storage_path: str) -> Path:
    """storage_path 形如 'files/a3/a3f5...' → 返回 {UPLOAD_ROOT}/a3/a3f5..."""
    backend_dir = get_backend_dir()
    # 去掉前缀 "files/"
    rel = storage_path.removeprefix("files/")
    return backend_dir / UPLOAD_ROOT / rel


def is_previewable(content_type: str) -> bool:
    """判断 MIME 类型是否支持浏览器内嵌预览（图片/PDF）"""
    return content_type in IMAGE_TYPES or content_type == PDF_TYPE
