"""AuditMixin 单测：审计五字段收敛为单一事实来源。

契约：混入 AuditMixin 的 Out schema 必须暴露
created_at / created_by / created_by_name（可选、可空）。
已知事实来自现有 7 处重复声明的字段形状（手工核对）。
"""
import datetime

from pydantic import BaseModel

from app.schemas import AuditMixin, FileCategoryOut, ProjectOut


class _Obj(BaseModel):
    """最小载体：模拟 ORM 对象的可序列化属性"""


class TestAuditMixinContract:
    def test_mixin_defines_audit_fields(self):
        fields = AuditMixin.model_fields
        assert "created_at" in fields
        assert "created_by" in fields
        assert "created_by_name" in fields

    def test_file_category_out_inherits_audit(self):
        fields = FileCategoryOut.model_fields
        assert fields["created_at"].annotation in (datetime.datetime | None, )
        assert "created_by_name" in fields

    def test_project_out_inherits_audit(self):
        assert "created_by_name" in ProjectOut.model_fields
        assert "created_at" in ProjectOut.model_fields

    def test_out_serializes_with_audit_fields(self):
        """构造带审计字段的对象可正常序列化（ORMBase from_attributes）"""
        obj = ProjectOut.model_validate({
            "id": 1, "name": "冒烟", "description": "",
            "created_at": "2026-01-01T00:00:00", "created_by": 9, "created_by_name": "boss",
        })
        dumped = obj.model_dump()
        assert dumped["created_by_name"] == "boss"
        assert dumped["created_by"] == 9


class TestAuditMixinRemainingOuts:
    """审计五字段应收敛到 mixin 的其余 Out（原各自逐字段重复声明）"""

    def test_environment_out_inherits_audit(self):
        from app.schemas import EnvironmentOut
        assert issubclass(EnvironmentOut, AuditMixin)
        assert "updated_by_name" in EnvironmentOut.model_fields

    def test_field_dictionary_out_inherits_audit(self):
        from app.schemas import FieldDictionaryOut
        assert issubclass(FieldDictionaryOut, AuditMixin)

    def test_file_out_inherits_audit(self):
        from app.schemas import FileOut
        assert issubclass(FileOut, AuditMixin)


class TestBareDictContracts:
    """裸 dict 出参补 Out 契约（原 router 手拼 dict，无 response_model）"""

    def test_simple_user_out_shape(self):
        from app.schemas import SimpleUserOut
        obj = SimpleUserOut.model_validate({"id": 3, "name": "张三"})
        assert obj.model_dump() == {"id": 3, "name": "张三"}

    def test_avatar_out_shape(self):
        from app.schemas import AvatarOut
        obj = AvatarOut.model_validate({"avatar": None, "name": "张三"})
        d = obj.model_dump()
        assert d["avatar"] is None and d["name"] == "张三"
