"""用例导入（导出 v2 迁移包）单测：真 SQLite 内存库走真 ORM 路径。

覆盖：v1/v3 拒绝、dry_run 资产统计（只读不落库）、接口复用与快照重建
（method+path 匹配 / code 生成 / 字段表回放）、数据集行回放与绑定、
env/group 覆盖、同名警告、契约模板不迁移警告、
以及金标准——导出→导入→再导出的结构等价（roundtrip）。
（与 fin-ui-test 同构，裁剪了 UI 元素/动作部分。）
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.services import case_import_service as imp
from app.services.export_service import export_cases_json


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _project(db, name="源项目"):
    p = models.Project(name=name)
    db.add(p)
    db.commit()
    return p


def _env(db, name="test"):
    e = models.Environment(name=name, base_url="http://t")
    db.add(e)
    db.commit()
    return e


def _api(db, project_id, name="创建订单", method="POST", path="/api/order/add", fields=None):
    a = models.ApiDefinition(
        project_id=project_id, name=name, code=f"p{project_id}_{path}_{method}".replace("/", "_"),
        method=method, path=path, request_template={}, headers_template={})
    db.add(a)
    db.commit()
    for f in (fields or []):
        db.add(models.ApiField(api_id=a.id, key=f["key"], label=f.get("label"),
                               field_type=f.get("field_type", "string"),
                               required=f.get("required", False),
                               default_value=f.get("default_value"),
                               sort_order=f.get("sort_order", 0)))
    db.commit()
    db.refresh(a)
    return a


def _case(db, project_id, env, api, group_id=None, contract_template_id=None):
    """含两节点用例（第二节点引用同接口 + 契约模板绑定）+ 一数据集一行。"""
    case = models.TestCase(
        project_id=project_id, group_id=group_id, name="下单冒烟",
        description="导入源用例", env_id=env.id,
        dag_config={
            "nodes": [
                {"id": "n1", "position": {"x": 1, "y": 2}, "data": {"label": "创建"}},
                {"id": "n2", "position": {"x": 3, "y": 4}, "data": {"label": "查询"}},
            ],
            "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
        })
    db.add(case)
    db.commit()
    db.add(models.CaseNodeConfig(
        case_id=case.id, node_id="n1", api_id=api.id,
        post_extract=[{"name": "order_id", "source": "body", "jsonpath": "$.data.id"}],
        assertions=[{"type": "response_status_equals", "expected": 200}],
        wait_after_ms=100, contract_template_id=contract_template_id))
    db.add(models.CaseNodeConfig(
        case_id=case.id, node_id="n2", api_id=api.id,
        post_extract=[], assertions=[], wait_after_ms=0))
    ds = models.DataSet(project_id=project_id, case_id=case.id, name="默认数据集")
    db.add(ds)
    db.commit()
    db.add(models.DataSetRow(dataset_id=ds.id, row_index=1,
                             data={"nodes": {"n1": {"params": {"body": {"order_no": "A1"}}}}}))
    db.commit()
    case.dataset_id = ds.id
    db.commit()
    db.refresh(case)
    return case


def _export(db, cases, project):
    group_names: dict[int, str] = {}
    case_ids = [c.id for c in cases]
    dss = (db.query(models.DataSet)
           .filter(models.DataSet.case_id.in_(case_ids)).order_by(models.DataSet.id).all())
    datasets_by_case: dict[int, list] = {}
    for d in dss:
        if d.rows:
            datasets_by_case.setdefault(d.case_id, []).append(d)
    return json.loads(export_cases_json(cases, group_names, project.name, datasets_by_case, db=db))


def _payload_fixture(db):
    p1, p2 = _project(db, "源"), _project(db, "目标")
    env = _env(db)
    api = _api(db, p1.id, fields=[{"key": "order_no", "label": "订单号", "required": True,
                                   "default_value": "A1"}])
    case = _case(db, p1.id, env, api)
    payload = _export(db, [case], p1)
    return p1, p2, env, api, case, payload


# ============ 载荷校验 ============

class TestPayloadValidation:
    def test_reject_v1(self, db):
        with pytest.raises(imp.ImportPayloadError, match="v1"):
            imp.import_cases(db, {"type": "cases", "items": [{"name": "x"}]}, 1)

    def test_reject_wrong_type(self, db):
        with pytest.raises(imp.ImportPayloadError, match="type=cases"):
            imp.import_cases(db, {"type": "apis", "version": 2}, 1)

    def test_reject_v3(self, db):
        with pytest.raises(imp.ImportPayloadError, match="v3"):
            imp.import_cases(db, {"type": "cases", "version": 3, "items": []}, 1)

    def test_reject_empty_items(self, db):
        with pytest.raises(imp.ImportPayloadError, match="items 为空"):
            imp.import_cases(db, {"type": "cases", "version": 2, "items": []}, 1)

    def test_reject_missing_project(self, db):
        _project(db)
        with pytest.raises(imp.ImportPayloadError, match="目标项目不存在"):
            imp.import_cases(db, {"type": "cases", "version": 2, "items": [{"name": "x"}]}, 999)

    def test_reject_bad_group_or_env(self, db):
        p = _project(db)
        payload = {"type": "cases", "version": 2, "items": [{"name": "x", "nodes": []}]}
        with pytest.raises(imp.ImportPayloadError, match="分组不存在"):
            imp.import_cases(db, payload, p.id, group_id=999)
        with pytest.raises(imp.ImportPayloadError, match="环境不存在"):
            imp.import_cases(db, payload, p.id, env_id=999)


# ============ dry_run 预演 ============

class TestDryRun:
    def test_plan_only_no_writes(self, db):
        p1, p2, env, api, case, payload = _payload_fixture(db)
        # 目标项目预置同 method+path 接口 → 应判复用
        _api(db, p2.id, name="同名接口", method="POST", path="/api/order/add")

        result = imp.import_cases(db, payload, p2.id, dry_run=True)
        assert result["dry_run"] is True and result["case_count"] == 1
        assert result["cases"][0] == {"name": "下单冒烟", "nodes": 2, "ui_nodes": 0,
                                      "datasets": 1, "rows": 1}
        assert result["reuse_apis"] == ["POST /api/order/add"] and result["create_apis"] == []
        # UI 维度恒空（API 平台无 UI 资产）
        assert result["create_elements"] == [] and result["create_actions"] == []
        # 只读：目标项目零新增
        assert db.query(models.TestCase).filter(models.TestCase.project_id == p2.id).count() == 0
        assert db.query(models.ApiDefinition).filter(models.ApiDefinition.project_id == p2.id).count() == 1

    def test_same_name_warning(self, db):
        p1, p2, env, api, case, payload = _payload_fixture(db)
        db.add(models.TestCase(project_id=p2.id, name="下单冒烟", dag_config={"nodes": [], "edges": []}))
        db.commit()
        result = imp.import_cases(db, payload, p2.id, dry_run=True)
        assert any("同名" in w for w in result["warnings"])


# ============ 真导入 ============

class TestImport:
    def test_full_import_reuse(self, db):
        p1, p2, env, api, case, payload = _payload_fixture(db)
        target_api = _api(db, p2.id, name="目标已有", method="POST", path="/api/order/add")
        env2 = _env(db, "prod")

        result = imp.import_cases(db, payload, p2.id, user_id=7, env_id=env2.id)
        assert result["case_count"] == 1 and result["created"]["apis"] == 0
        assert result["reused"]["apis"] == 1
        new_case = db.query(models.TestCase).get(result["case_ids"][0])
        assert new_case.name == "下单冒烟" and new_case.env_id == env2.id
        assert len(new_case.dag_config["nodes"]) == 2 and new_case.dag_config["edges"]
        cfgs = {nc.node_id: nc for nc in new_case.node_configs}
        assert cfgs["n1"].api_id == target_api.id  # method+path 复用目标已有接口
        assert cfgs["n1"].post_extract[0]["name"] == "order_id"
        assert cfgs["n1"].wait_after_ms == 100
        # 数据集：名称/行数据/绑定回放
        dss = db.query(models.DataSet).filter(models.DataSet.case_id == new_case.id).all()
        assert len(dss) == 1 and dss[0].name == "默认数据集"
        rows = db.query(models.DataSetRow).filter(models.DataSetRow.dataset_id == dss[0].id).all()
        assert len(rows) == 1
        assert rows[0].data["nodes"]["n1"]["params"]["body"]["order_no"] == "A1"
        assert new_case.dataset_id == dss[0].id

    def test_api_snapshot_rebuild_with_fields_and_code(self, db):
        """目标项目无同 path 接口：用快照重建（字段全量、code 自动生成）"""
        p1, p2, env, api, case, payload = _payload_fixture(db)
        result = imp.import_cases(db, payload, p2.id)
        assert result["created"]["apis"] == 1
        new_api = (db.query(models.ApiDefinition)
                   .filter(models.ApiDefinition.project_id == p2.id).first())
        assert new_api.method == "POST" and new_api.path == "/api/order/add"
        assert new_api.code.startswith("imported_post_api_order_add")
        fields = new_api.fields
        assert len(fields) == 1 and fields[0].key == "order_no" and fields[0].required is True
        # 两个节点都应指向重建接口
        new_case = db.query(models.TestCase).get(result["case_ids"][0])
        assert all(nc.api_id == new_api.id for nc in new_case.node_configs)

    def test_roundtrip_structure_equal(self, db):
        """金标准：导出 → 导入到新项目 → 再导出，两次结构等价"""
        p1, p2, env, api, case, payload = _payload_fixture(db)
        imp.import_cases(db, payload, p2.id, env_id=env.id)
        new_case = db.query(models.TestCase).filter(
            models.TestCase.project_id == p2.id).first()
        payload2 = _export(db, [new_case], p2)

        a, b = payload["items"][0], payload2["items"][0]
        assert b["name"] == a["name"] and b["description"] == a["description"]
        assert b["env"] == a["env"] and b["dataset_name"] == a["dataset_name"]
        assert b["edges"] == a["edges"]
        assert [n["id"] for n in b["nodes"]] == [n["id"] for n in a["nodes"]]
        assert b["nodes"][0]["api_snapshot"]["fields"] == a["nodes"][0]["api_snapshot"]["fields"]
        assert b["nodes"][0]["config"] == a["nodes"][0]["config"]
        assert b["datasets"][0]["rows"] == a["datasets"][0]["rows"]

    def test_import_twice_idempotent_assets(self, db):
        """同一文件导入两次：接口按 (method,path) 幂等复用，不重复创建"""
        p1, p2, env, api, case, payload = _payload_fixture(db)
        imp.import_cases(db, payload, p2.id)
        result = imp.import_cases(db, payload, p2.id)
        assert result["created"]["apis"] == 0 and result["reused"]["apis"] == 1
        assert db.query(models.ApiDefinition).filter(models.ApiDefinition.project_id == p2.id).count() == 1
        assert db.query(models.TestCase).filter(models.TestCase.project_id == p2.id).count() == 2

    def test_group_override(self, db):
        p1, p2, env, api, case, payload = _payload_fixture(db)
        g = models.CaseGroup(project_id=p2.id, name="冒烟组")
        db.add(g)
        db.commit()
        result = imp.import_cases(db, payload, p2.id, group_id=g.id)
        new_case = db.query(models.TestCase).get(result["case_ids"][0])
        assert new_case.group_id == g.id

    def test_contract_template_not_migrated_warns(self, db):
        """契约模板绑定不随迁移：导入后 NULL + 节点级警告"""
        p1, p2 = _project(db, "源"), _project(db, "目标")
        env = _env(db)
        api = _api(db, p1.id)
        tpl = models.ApiContractTemplate(api_id=api.id, name="下单契约", field_keys=["order_no"])
        db.add(tpl)
        db.commit()
        case = _case(db, p1.id, env, api, contract_template_id=tpl.id)
        payload = _export(db, [case], p1)

        result = imp.import_cases(db, payload, p2.id)
        assert any("契约模板" in w for w in result["warnings"])
        nc = db.query(models.CaseNodeConfig).filter(
            models.CaseNodeConfig.case_id == result["case_ids"][0]).first()
        assert nc.contract_template_id is None

    def test_node_without_config_skipped(self, db):
        """导出端无配置节点（config=None）：导入端不建 CaseNodeConfig 行，不报错"""
        p1, p2 = _project(db, "源"), _project(db, "目标")
        case = models.TestCase(project_id=p1.id, name="裸节点",
                               dag_config={"nodes": [{"id": "n1"}], "edges": []})
        db.add(case)
        db.commit()
        payload = _export(db, [case], p1)
        result = imp.import_cases(db, payload, p2.id)
        new_case = db.query(models.TestCase).get(result["case_ids"][0])
        assert new_case.node_configs == []

    def test_missing_api_snapshot_warns(self, db):
        """api_id 有值但快照缺失（源接口已删后导出）：节点不绑接口 + 警告"""
        p2 = _project(db, "目标")
        payload = {"type": "cases", "version": 2, "items": [{
            "name": "悬空", "nodes": [{"id": "n1", "api_id": 99,
                                       "api_snapshot": None,
                                       "config": {"post_extract": [], "assertions": [],
                                                  "wait_after_ms": 0, "contract_template_id": None}}],
            "edges": [], "datasets": []}]}
        result = imp.import_cases(db, payload, p2.id)
        assert any("无快照" in w for w in result["warnings"])
        nc = db.query(models.CaseNodeConfig).filter(
            models.CaseNodeConfig.case_id == result["case_ids"][0]).first()
        assert nc.api_id is None
