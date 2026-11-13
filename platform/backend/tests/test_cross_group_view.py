# -*- coding: utf-8 -*-
"""跨系统用例三 bug 修复（2026-11-13）单测：按项目分组覆写 + 数据集派生可见。

背景：跨系统用例（派生归属出现在 ≥2 个项目）此前只有一个原生维度 group_id——
bug2 在 B 项目移动分组会连坐 A 项目视角掉未分组；本组测试钉住覆写语义：
- 移动分流：原生成员改列、跨系统成员写/删 (case_id, project_id) 覆写行
- 列表输出：项目视角解析覆写分组（无覆写保持原生 group_id）
- 防串写：目标分组不属于该项目 / 用例在该项目不可见 → 拒
- 分组删除：被覆写引用的分组拒绝删除
- 数据集列表：跨系统用例的数据集在涉及项目可见（bug3）
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models


@pytest.fixture()
def db():
    engine = create_engine("sqlite://",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed(db):
    """双项目 + 跨系统用例（原生 A，节点引用 B 接口）+ 双项目各自分组"""
    pa = models.Project(name="物流")
    pb = models.Project(name="亿海融")
    db.add_all([pa, pb])
    db.commit()
    ga = models.CaseGroup(project_id=pa.id, name="物流-跨系统")
    gb = models.CaseGroup(project_id=pb.id, name="亿海融-跨系统")
    db.add_all([ga, gb])
    api_a = models.ApiDefinition(project_id=pa.id, name="物流下单", code="a1",
                                 method="POST", path="/a/order", request_template={}, headers_template={})
    api_b = models.ApiDefinition(project_id=pb.id, name="推送资产", code="b1",
                                 method="POST", path="/b/asset", request_template={}, headers_template={})
    db.add_all([api_a, api_b])
    db.commit()
    cross = models.TestCase(project_id=pa.id, group_id=ga.id, name="跨系统-推送",
                            env_id=None, dag_config={"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": [
                                {"source": "n1", "target": "n2"}]})
    native_b = models.TestCase(project_id=pb.id, group_id=None, name="亿海融本地图例",
                               env_id=None, dag_config={"nodes": [], "edges": []})
    db.add_all([cross, native_b])
    db.commit()
    db.add_all([
        models.CaseNodeConfig(case_id=cross.id, node_id="n1", api_id=api_a.id),
        models.CaseNodeConfig(case_id=cross.id, node_id="n2", api_id=api_b.id),
    ])
    db.commit()
    return pa, pb, ga, gb, cross, native_b


class TestBatchMoveProjectView:
    def test_cross_move_writes_override_not_column(self, db):
        """B 项目移动跨系统用例 → 写覆写行，原生 group_id 不动（两项目互不连坐）"""
        pa, pb, ga, gb, cross, _ = _seed(db)
        n = crud.batch_move_testcases(db, [cross.id], gb.id, user_id=None, project_id=pb.id)
        assert n == 1
        assert cross.group_id == ga.id  # 原生列不动
        row = db.query(models.CaseGroupOverride).filter_by(
            case_id=cross.id, project_id=pb.id).first()
        assert row and row.group_id == gb.id

    def test_cross_move_null_deletes_override(self, db):
        """移回未分组 = 删覆写行回退（B 项目视角即未分组），幂等：无行再移也成功"""
        pa, pb, ga, gb, cross, _ = _seed(db)
        crud.batch_move_testcases(db, [cross.id], gb.id, project_id=pb.id)
        assert crud.batch_move_testcases(db, [cross.id], None, project_id=pb.id) == 1
        assert db.query(models.CaseGroupOverride).filter_by(case_id=cross.id).count() == 0
        assert crud.batch_move_testcases(db, [cross.id], None, project_id=pb.id) == 1  # 幂等

    def test_native_member_updates_column_in_place(self, db):
        """同一批里的原生成员照旧改 group_id 列（经典语义）"""
        pa, pb, ga, gb, _, native_b = _seed(db)
        crud.batch_move_testcases(db, [native_b.id], gb.id, project_id=pb.id)
        assert native_b.group_id == gb.id
        assert db.query(models.CaseGroupOverride).count() == 0

    def test_foreign_group_rejected(self, db):
        """目标分组不属于当前项目 → 拒（分组按项目隔离，防跨项目 id 串写）"""
        pa, pb, ga, gb, cross, _ = _seed(db)
        with pytest.raises(ValueError, match="不属于当前项目"):
            crud.batch_move_testcases(db, [cross.id], ga.id, project_id=pb.id)

    def test_invisible_case_rejected(self, db):
        """在该项目不可见的用例（未引用其接口）不能移入该项目分组"""
        pa, pb, ga, gb, _, native_b = _seed(db)
        with pytest.raises(ValueError, match="不可见"):
            crud.batch_move_testcases(db, [native_b.id], ga.id, project_id=pa.id)

    def test_legacy_call_without_project(self, db):
        """缺省 project_id = 经典整组替换（旧调用兼容），不落覆写表"""
        pa, pb, ga, gb, cross, _ = _seed(db)
        n = crud.batch_move_testcases(db, [cross.id], gb.id)
        assert n == 1
        assert cross.group_id == gb.id  # 旧行为：直接改列（历史调用方语义）
        assert db.query(models.CaseGroupOverride).count() == 0


class TestListViewGroupResolution:
    def test_list_resolves_override_per_project(self, db):
        """列表按项目视角给 group_id：B 视角用覆写分组，A 视角保持原生分组"""
        from app.routers import testcases as tc_router
        pa, pb, ga, gb, cross, _ = _seed(db)
        crud.batch_move_testcases(db, [cross.id], gb.id, project_id=pb.id)

        outs_b = tc_router.list_all(project_id=pb.id, db=db, user=None)
        cross_b = next(o for o in outs_b if o.id == cross.id)
        assert cross_b.group_id == gb.id          # B 视角 = 覆写分组
        outs_a = tc_router.list_all(project_id=pa.id, db=db, user=None)
        cross_a = next(o for o in outs_a if o.id == cross.id)
        assert cross_a.group_id == ga.id          # A 视角 = 原生分组（未被连坐）

    def test_list_without_override_falls_back_native(self, db):
        """无覆写行的跨系统用例：B 视角拿原生 group_id（B 分组树解析不到
        即前端未分组桶——与修复前行为一致，不产生空覆写行）"""
        from app.routers import testcases as tc_router
        pa, pb, ga, gb, cross, _ = _seed(db)
        outs_b = tc_router.list_all(project_id=pb.id, db=db, user=None)
        cross_b = next(o for o in outs_b if o.id == cross.id)
        assert cross_b.group_id == ga.id
        assert db.query(models.CaseGroupOverride).count() == 0


class TestDeleteGroupGuard:
    def test_group_with_override_refused(self, db):
        """被跨系统用例覆写引用的分组拒绝删除（先移走），空分组照删"""
        pa, pb, ga, gb, cross, _ = _seed(db)
        crud.batch_move_testcases(db, [cross.id], gb.id, project_id=pb.id)
        with pytest.raises(ValueError, match="跨系统用例"):
            crud.delete_case_group(db, gb)
        # 移走后可删
        crud.batch_move_testcases(db, [cross.id], None, project_id=pb.id)
        crud.delete_case_group(db, gb)  # 不抛即通过


class TestDatasetDerivedVisibility:
    def test_cross_dataset_listed_in_foreign_project(self, db):
        """bug3：跨系统用例的数据集在涉及项目也列出（可编辑入口）"""
        from app.routers import datasets as ds_router
        pa, pb, ga, gb, cross, native_b = _seed(db)
        ds_cross = models.DataSet(project_id=pa.id, case_id=cross.id, name="跨系统数据", bound=True)
        ds_b = models.DataSet(project_id=pb.id, case_id=native_b.id, name="本地数据", bound=True)
        db.add_all([ds_cross, ds_b])
        db.commit()

        out_b = ds_router.list_datasets(case_id=None, project_id=pb.id, with_rows=False, db=db, user=None)
        names = {o.name for o in out_b}
        assert "跨系统数据" in names and "本地数据" in names

        out_a = ds_router.list_datasets(case_id=None, project_id=pa.id, with_rows=False, db=db, user=None)
        assert {o.name for o in out_a} == {"跨系统数据"}  # 反向不串：纯 B 数据集不出现在 A
