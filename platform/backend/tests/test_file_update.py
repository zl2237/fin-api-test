"""文件更新（PUT /api/files/{id}）单测。

覆盖：
- category_id 显式传 null → 置为未分类
- 请求未携带 category_id → 保持原分类
- 正常改分类 / 重命名 / 改标签
"""
from types import SimpleNamespace

from app.schemas import FileUpdateRequest
from app.crud import update_file


class FakeDb:
    def __init__(self):
        self.committed = False
        self.added = []
        self.deleted = []

    def query(self, *args, **kwargs):
        db = self

        class _Query:
            def filter(self, *a, **kw):
                return self

            def delete(self, synchronize_session=False):
                db.deleted.append(True)
                return None

            def all(self):
                return []

        return _Query()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, _obj):
        pass


def _make_file():
    return SimpleNamespace(id=1, name="old.txt", category_id=5, updated_by=None)


class TestUpdateFile:
    def test_explicit_null_clears_category(self):
        """显式传 category_id=None → 更新为未分类"""
        file = _make_file()
        db = FakeDb()
        data = FileUpdateRequest(name="old.txt", category_id=None, tag_ids=[])

        update_file(db, file, data, user_id=9)

        assert file.category_id is None
        assert db.committed is True

    def test_field_absent_keeps_category(self):
        """请求未携带 category_id → 保持原分类"""
        file = _make_file()
        db = FakeDb()
        data = FileUpdateRequest(name="renamed.txt")

        update_file(db, file, data, user_id=9)

        assert file.category_id == 5
        assert file.name == "renamed.txt"

    def test_normal_category_change(self):
        """正常改分类"""
        file = _make_file()
        db = FakeDb()
        data = FileUpdateRequest(category_id=8)

        update_file(db, file, data, user_id=9)

        assert file.category_id == 8

    def test_rename_only(self):
        """仅重命名，不动分类和标签"""
        file = _make_file()
        db = FakeDb()
        data = FileUpdateRequest(name="new-name.txt")

        update_file(db, file, data, user_id=9)

        assert file.name == "new-name.txt"
        assert file.category_id == 5

    def test_tag_update_rebuilds_relations(self):
        """传 tag_ids 时先删旧关联再建新关联"""
        file = _make_file()
        db = FakeDb()
        data = FileUpdateRequest(tag_ids=[2, 3])

        update_file(db, file, data, user_id=9)

        assert db.deleted  # 旧关联被清
        assert len(db.added) == 2  # 新关联两条
