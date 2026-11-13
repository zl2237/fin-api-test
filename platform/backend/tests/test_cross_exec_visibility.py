# -*- coding: utf-8 -*-
"""跨系统用例执行记录可见性（2026-11-13）：派生归属口径统一。

背景：用例列表早已按派生归属（原生 ∪ 节点引用项目）过滤，但执行记录/
统计/工作台仍按 case.project_id 原生过滤——亿海融视角能跑跨系统用例，
执行记录却只在物流视角出现。本组测试钉住三处同口径：
- list/count_executions：跨系统用例的执行在涉及项目可见
- aggregate_stats：跨系统用例的执行计入涉及项目统计
- home_summary：case_count / recent_execs / recent_cases 同口径
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models
from app.crud.executions import aggregate_stats
from app.routers import home as home_router


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
    """双项目 + 跨系统用例（原生 A，节点引用 B 接口）+ 纯 B 本地用例 + 各一条执行"""
    pa = models.Project(name="物流")
    pb = models.Project(name="亿海融")
    db.add_all([pa, pb])
    db.commit()
    api_a = models.ApiDefinition(project_id=pa.id, name="物流下单", code="a1",
                                 method="POST", path="/a/order", request_template={}, headers_template={})
    api_b = models.ApiDefinition(project_id=pb.id, name="推送资产", code="b1",
                                 method="POST", path="/b/asset", request_template={}, headers_template={})
    db.add_all([api_a, api_b])
    db.commit()
    cross = models.TestCase(project_id=pa.id, name="跨系统-推送", env_id=None,
                            dag_config={"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": []})
    native_b = models.TestCase(project_id=pb.id, name="亿海融本地图例", env_id=None,
                               dag_config={"nodes": [], "edges": []})
    db.add_all([cross, native_b])
    db.commit()
    db.add_all([
        models.CaseNodeConfig(case_id=cross.id, node_id="n1", api_id=api_a.id),
        models.CaseNodeConfig(case_id=cross.id, node_id="n2", api_id=api_b.id),
    ])
    db.commit()
    exec_cross = models.ExecutionRecord(case_id=cross.id, env_id=None, status="success")
    exec_local = models.ExecutionRecord(case_id=native_b.id, env_id=None, status="failed")
    db.add_all([exec_cross, exec_local])
    db.commit()
    return pa, pb, cross, native_b, exec_cross, exec_local


class TestExecutionListVisibility:
    def test_cross_execution_visible_in_both_projects(self, db):
        """跨系统用例的执行记录：原生 A 与派生 B 视角都能看到；B 的纯本地执行不出现在 A"""
        pa, pb, cross, native_b, exec_cross, exec_local = _seed(db)
        for pid in (pa.id, pb.id):
            rows = crud.list_executions(db, project_id=pid)
            assert any(e.id == exec_cross.id for e in rows), f"exec_cross 应在项目{pid}可见"
        ids_a = {e.id for e in crud.list_executions(db, project_id=pa.id)}
        assert exec_local.id not in ids_a          # 反向不串：纯 B 执行不进 A 视角
        assert crud.count_executions(db, project_id=pb.id) == 2  # count 与 list 同口径

    def test_case_name_filter_keeps_cross_view(self, db):
        """B 视角 + 用例名模糊：跨系统用例名可命中"""
        pa, pb, cross, native_b, exec_cross, _ = _seed(db)
        rows = crud.list_executions(db, project_id=pb.id, case_name="跨系统")
        assert [e.id for e in rows] == [exec_cross.id]


class TestAggregateStatsVisibility:
    def test_stats_count_cross_execution_in_both(self, db):
        """统计口径：跨系统执行计入两个项目——A 视角 1 条（仅跨系统），
        B 视角 2 条（跨系统 + 本地），通过数口径不变"""
        pa, pb, *_ = _seed(db)
        s_a = aggregate_stats(db, pa.id, days=7)
        assert (s_a["count"], s_a["passed"]) == (1, 1)
        s_b = aggregate_stats(db, pb.id, days=7)
        assert (s_b["count"], s_b["passed"]) == (2, 1)


class TestHomeSummaryVisibility:
    def test_home_counts_and_recent_include_cross(self, db):
        """工作台：B 视角 case_count 含跨系统用例；recent_execs/recent_cases 含其执行"""
        pa, pb, cross, native_b, exec_cross, _ = _seed(db)
        out = home_router.home_summary(project_id=pb.id, days=7, db=db, user=None)
        assert out.case_count == 2                       # 跨系统 + 本地图例
        assert any(e.id == exec_cross.id for e in out.recent_execs)
        assert {c.id for c in out.recent_cases} == {cross.id, native_b.id}
        # A 视角不串 B 的本地图例
        out_a = home_router.home_summary(project_id=pa.id, days=7, db=db, user=None)
        assert out_a.case_count == 1
        assert {c.id for c in out_a.recent_cases} == {cross.id}
