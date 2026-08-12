"""文件中心纯函数单测：覆盖路径构建、预览类型判断等无 DB 依赖逻辑。

不覆盖完整 CRUD 流程（需 MySQL 环境），仅测试可独立验证的辅助函数。
"""
from app.services.file_helpers import (
    build_storage_path,
    resolve_physical_path,
    is_previewable,
    IMAGE_TYPES,
    PDF_TYPE,
)


class TestBuildStoragePath:
    def test_normal_sha256(self):
        sha = "a3f5b2c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2"
        path = build_storage_path(sha)
        assert path == f"files/a3/{sha}"

    def test_short_sha256(self):
        sha = "ab1234"
        path = build_storage_path(sha)
        assert path == "files/ab/ab1234"


class TestResolvePhysicalPath:
    def test_resolve_normal_path(self):
        storage = "files/a3/a3f5b2..."
        physical = resolve_physical_path(storage)
        # 验证路径以 UPLOAD_ROOT/a3/... 结尾
        assert physical.name == "a3f5b2..."
        assert physical.parent.name == "a3"

    def test_resolve_already_relative(self):
        storage = "a3/a3f5b2..."
        physical = resolve_physical_path(storage)
        assert physical.name == "a3f5b2..."
        assert physical.parent.name == "a3"


class TestIsPreviewable:
    def test_image_types_previewable(self):
        for ct in IMAGE_TYPES:
            assert is_previewable(ct) is True, f"{ct} 应支持预览"

    def test_pdf_previewable(self):
        assert is_previewable(PDF_TYPE) is True

    def test_other_types_not_previewable(self):
        assert is_previewable("application/zip") is False
        assert is_previewable("application/octet-stream") is False
        assert is_previewable("text/plain") is False
        assert is_previewable("video/mp4") is False

    def test_empty_type_not_previewable(self):
        assert is_previewable("") is False
