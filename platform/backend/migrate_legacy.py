"""
迁移脚本：将旧版基于 pytest+YAML 的用例数据导入平台数据库。

迁移内容：
1. 从 config/env_demo.yaml 导入环境配置（base_url / db_config / common_headers）
2. 扫描 api/*.py 与 api/*/*.py，反射出接口定义（method、path）
3. 扫描 data/{env}/order/*.yaml，作为接口的请求模板
4. 基于 testcases/order/test_order.py 中编排逻辑，构造 DAG 测试用例

用法：
    cd platform/backend
    python migrate_legacy.py

设计原则：
- 幂等：基于 code 唯一约束，重复运行只更新不新增
- 非破坏性：保留已有 Project / Environment / ApiDefinition / TestCase 数据，
  仅根据 YAML 与代码重新生成 TestCase 与节点配置
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 把项目根目录加入 sys.path，使 utils.* 可被引用
_BACKEND_DIR = Path(__file__).resolve().parent          # platform/backend
_PLATFORM_DIR = _BACKEND_DIR.parent                     # platform
_PROJECT_ROOT = _PLATFORM_DIR.parent                    # fin-api-test
for p in (_PROJECT_ROOT, _BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import yaml  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_legacy")

# ============ 常量 ============
PROJECT_NAME = "订单业务测试"
PROJECT_DESC = "由旧版 pytest 用例迁移而来"

# env_demo.yaml → 环境名（与 data/{env}/* 目录一致）
DEFAULT_ENV_NAME = "test"


# ============ 工具 ============
def _read_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _coerce_dict(val: Any) -> Dict[str, Any]:
    return val if isinstance(val, dict) else {}


# ============ 1. Project ============
def ensure_project(db) -> models.Project:
    obj = db.query(models.Project).filter(models.Project.name == PROJECT_NAME).first()
    if obj:
        return obj
    obj = models.Project(name=PROJECT_NAME, description=PROJECT_DESC)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    logger.info(f"创建项目：{obj.name} (id={obj.id})")
    return obj


# ============ 2. Environment ============
def ensure_environment(db, project: models.Project, env_yaml_path: Path) -> Optional[models.Environment]:
    data = _read_yaml(env_yaml_path)
    if not data:
        logger.warning(f"环境配置文件不存在或为空：{env_yaml_path}")
        return None

    env_name = data.get("env_name", DEFAULT_ENV_NAME)
    base_url = data.get("base_url", "")
    common_headers = _coerce_dict(data.get("common_headers"))

    # mysql 配置整体作为 db_config
    db_config = _coerce_dict(data.get("mysql"))

    # 登录配置（独立存 login_config，与业务变量解耦）
    login_config: Dict[str, Any] = {
        "login_path": "/api/home/login/userLogin",
        "login_body": {},
        "token_jsonpath": "$.data.token",
        "auth_header_name": "Authorization",
    }

    # 通知配置（wecom_webhook 独立存 notify_config）
    notify_config: Dict[str, Any] = {}
    if data.get("wecom_webhook"):
        notify_config["wecom_webhook"] = data["wecom_webhook"]
        notify_config["enable_on_failure"] = True
        notify_config["enable_on_success"] = False

    # 业务变量（纯业务用途，与登录/通知解耦）
    variables: Dict[str, Any] = {}

    obj = (
        db.query(models.Environment)
        .filter(
            models.Environment.project_id == project.id,
            models.Environment.name == env_name,
        )
        .first()
    )
    if obj:
        obj.base_url = base_url
        obj.common_headers = common_headers
        obj.db_config = db_config
        obj.login_config = login_config
        obj.notify_config = notify_config
        obj.variables = variables
        obj.is_default = True
    else:
        obj = models.Environment(
            project_id=project.id,
            name=env_name,
            base_url=base_url,
            common_headers=common_headers,
            db_config=db_config,
            login_config=login_config,
            notify_config=notify_config,
            variables=variables,
            is_default=True,
        )
        db.add(obj)
    db.commit()
    db.refresh(obj)
    logger.info(f"同步环境：{obj.name} (id={obj.id}) base_url={obj.base_url}")
    return obj


# ============ 3. ApiDefinition ============
# 手工映射：旧版接口方法名 → 接口定义元数据
# 因旧版 api 类方法没有显式声明路径，这里基于 order_api.py 阅读后的结果维护
API_SPECS: List[Dict[str, Any]] = [
    {
        "code": "order_create",
        "name": "创建订单",
        "category": "order",
        "method": "POST",
        "path": "/api/order/orderEntrust/orderAdd",
        "data_file": "order/create.yaml",
        "description": "创建订单接口（旧版 OrderApi.create_order）",
    },
    {
        "code": "order_distribute",
        "name": "订单分发",
        "category": "order",
        "method": "POST",
        "path": "/api/order/orderEntrust/orderAdd",
        "data_file": "order/distribute.yaml",
        "description": "订单分发接口（旧版 OrderApi.distribute_order）",
    },
    {
        "code": "order_stash",
        "name": "暂存订单",
        "category": "order",
        "method": "POST",
        "path": "/api/order/order/orderAdd",
        "data_file": "order/stash.yaml",
        "description": "暂存订单接口（旧版 OrderApi.stash_order）",
    },
    {
        "code": "order_submit",
        "name": "提交订单",
        "category": "order",
        "method": "POST",
        "path": "/api/order/order/orderAdd",
        "data_file": "order/submit.yaml",
        "description": "提交订单接口（旧版 OrderApi.submit_order）",
    },
    {
        "code": "order_generate_sub",
        "name": "生成子订单",
        "category": "order",
        "method": "POST",
        "path": "/api/order/order/generateOrderSub",
        "data_file": None,  # 旧版请求体由代码动态构造，无 YAML 模板
        "description": "生成子订单接口（旧版 OrderApi.generate_sub_order）",
    },
    {
        "code": "order_fee_add",
        "name": "录入订舱费用",
        "category": "order",
        "method": "POST",
        "path": "/api/order/orderFee/bookRealAmountEdit",
        "data_file": "order/fee.yaml",
        "description": "编辑订舱费用接口（旧版 OrderApi.fee_add）",
    },
    {
        "code": "auth_login",
        "name": "用户登录",
        "category": "auth",
        "method": "POST",
        "path": "/api/home/login/userLogin",
        "data_file": "auth/auth_data.yaml",
        "description": "用户登录接口（旧版 AuthApi.login）",
    },
]


def _ensure_api_group(db, project: models.Project, name: str) -> models.ApiGroup:
    """确保接口分组存在（按名称幂等）"""
    obj = db.query(models.ApiGroup).filter(
        models.ApiGroup.project_id == project.id,
        models.ApiGroup.name == name,
    ).first()
    if obj:
        return obj
    obj = models.ApiGroup(project_id=project.id, name=name)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def _flatten_to_fields(template: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
    """把嵌套 dict 拍平为 ApiField 列表（点号路径）"""
    fields: List[Dict[str, Any]] = []
    import json
    for k, v in (template or {}).items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            # 嵌套对象：拍平为子字段
            fields.extend(_flatten_to_fields(v, path))
        elif isinstance(v, list):
            # 数组：整体存为 JSON 字符串
            fields.append({
                "key": path,
                "label": "",
                "field_type": "array",
                "required": False,
                "default_value": json.dumps(v, ensure_ascii=False),
                "remark": "",
                "sort_order": len(fields),
            })
        else:
            ftype = "int" if isinstance(v, int) and not isinstance(v, bool) else (
                "bool" if isinstance(v, bool) else "string"
            )
            fields.append({
                "key": path,
                "label": "",
                "field_type": ftype,
                "required": False,
                "default_value": "" if v is None else str(v),
                "remark": "",
                "sort_order": len(fields),
            })
    return fields


def _sync_api_fields(db, api_id: int, fields: List[Dict[str, Any]]):
    """全量覆盖接口的 ApiField"""
    db.query(models.ApiField).filter(models.ApiField.api_id == api_id).delete()
    for f in fields:
        obj = models.ApiField(
            api_id=api_id,
            key=f["key"],
            label=f.get("label", ""),
            field_type=f.get("field_type", "string"),
            required=f.get("required", False),
            default_value=f.get("default_value"),
            remark=f.get("remark", ""),
            sort_order=f.get("sort_order", 0),
        )
        db.add(obj)
    db.commit()


# 分组名映射：category → 中文分组名
_CATEGORY_TO_GROUP = {
    "order": "订单组",
    "auth": "认证组",
    "file": "文件组",
}


def ensure_apis(db, project: models.Project, data_dir: Path) -> Dict[str, models.ApiDefinition]:
    """根据 API_SPECS 同步接口定义，返回 code -> ApiDefinition 映射"""
    # 预创建分组
    group_map: Dict[str, models.ApiGroup] = {}
    for cat, gname in _CATEGORY_TO_GROUP.items():
        group_map[cat] = _ensure_api_group(db, project, gname)

    code_to_api: Dict[str, models.ApiDefinition] = {}
    for spec in API_SPECS:
        request_template: Dict[str, Any] = {}
        if spec["data_file"]:
            yaml_path = data_dir / spec["data_file"]
            tpl = _read_yaml(yaml_path)
            if isinstance(tpl, dict):
                request_template = tpl
            else:
                logger.warning(f"接口 {spec['code']} 的 YAML 模板不是字典：{yaml_path}")

        # 把 request_template 拍平为 ApiField 列表
        fields = _flatten_to_fields(request_template)
        # 绑定分组
        group = group_map.get(spec["category"])

        obj = db.query(models.ApiDefinition).filter(models.ApiDefinition.code == spec["code"]).first()
        if obj:
            obj.project_id = project.id
            obj.group_id = group.id if group else None
            obj.name = spec["name"]
            obj.category = spec["category"]
            obj.method = spec["method"]
            obj.path = spec["path"]
            obj.description = spec["description"]
            obj.request_template = request_template
        else:
            obj = models.ApiDefinition(
                project_id=project.id,
                group_id=group.id if group else None,
                name=spec["name"],
                code=spec["code"],
                category=spec["category"],
                method=spec["method"],
                path=spec["path"],
                description=spec["description"],
                request_template=request_template,
                headers_template={},
            )
            db.add(obj)
        db.commit()
        db.refresh(obj)
        # 同步字段
        _sync_api_fields(db, obj.id, fields)
        code_to_api[spec["code"]] = obj
        logger.info(f"同步接口：{obj.code} ({obj.method} {obj.path}) id={obj.id} 字段数={len(fields)}")
    return code_to_api


# ============ 4. TestCase + DAG ============
def build_order_full_flow(code_to_api: Dict[str, models.ApiDefinition]) -> Dict[str, Any]:
    """
    基于 testcases/order/test_order.py::test_fee_add 的业务编排，
    构造一个完整 DAG：创建→分发→暂存→提交→生成子订单→录入费用。

    每个节点配置：
    - pre_process: 注入 order_id、bl_no、动态生成 unique_id
    - post_extract: 从响应/DB 查询结果中提取 order_id、bl_no
    - assertions: 旧版 equal / not_equal 断言 → 平台 db_query_equals
    """
    def _node(node_id: str, code: str, label: str, idx: int) -> Dict[str, Any]:
        api = code_to_api.get(code)
        # 横向排列，每个节点间隔 240px；超过 3 个换行
        col = idx % 3
        row = idx // 3
        return {
            "id": node_id,
            "type": "default",
            "position": {"x": col * 240, "y": row * 140},
            "data": {
                "label": label,
                "api_id": api.id if api else None,
                "api_code": code,
                "api_method": api.method if api else "POST",
                "api_path": api.path if api else "",
            },
        }

    nodes = [
        _node("n_create", "order_create", "创建订单", 0),
        _node("n_distribute", "order_distribute", "订单分发", 1),
        _node("n_stash", "order_stash", "暂存订单", 2),
        _node("n_submit", "order_submit", "提交订单", 3),
        _node("n_gen_sub", "order_generate_sub", "生成子订单", 4),
        _node("n_fee", "order_fee_add", "录入订舱费用", 5),
    ]
    edges = [
        {"id": "e_create_distribute", "source": "n_create", "target": "n_distribute"},
        {"id": "e_distribute_stash", "source": "n_distribute", "target": "n_stash"},
        {"id": "e_stash_submit", "source": "n_stash", "target": "n_submit"},
        {"id": "e_submit_gen", "source": "n_submit", "target": "n_gen_sub"},
        {"id": "e_gen_fee", "source": "n_gen_sub", "target": "n_fee"},
    ]

    # ---- 节点配置 ----
    # 说明：断言引擎已支持 db_query_equals（带 field 参数取单字段）与
    # db_vs_jsonpath_equals（DB值 vs 响应值交叉校验）。
    # 此处仍主要使用 db_query_count_equals 做存在性校验，语义清晰。
    #
    # order_id 提取：旧代码从 DB 查询结果取 order_id；
    # 平台 extractor 已支持 source=db 提取，可直接配置 SQL + field。
    node_configs: List[Dict[str, Any]] = []

    # 1) 创建订单：bl_no 为空时动态生成
    node_configs.append({
        "node_id": "n_create",
        "api_id": code_to_api["order_create"].id,
        "pre_process": [
            {
                "type": "set_field",
                "path": "bl_no",
                "value": "${generate_bl_no(prefix='smoke')}",
            },
        ],
        "post_extract": [
            # 创建接口返回的 bl_no 用于后续节点引用
            {"name": "bl_no", "json_path": "$.data.bl_no"},
            # order_id 从 DB 提取（旧代码逻辑：创建后查库拿 order_id）
            # 现平台已支持 source=db 提取
            {
                "name": "order_id",
                "source": "db",
                "sql": "SELECT order_id FROM sys_order WHERE bl_no='${bl_no}'",
                "field": "order_id",
            },
        ],
        "assertions": [
            {
                "type": "db_query_count_equals",
                "sql": "SELECT 1 FROM sys_order WHERE bl_no='${bl_no}' AND entrust_status=1",
                "expected": 1,
                "message": "订单分发状态不一致（期望 entrust_status=1）",
            },
            {
                "type": "db_query_count_equals",
                "sql": "SELECT 1 FROM sys_order WHERE bl_no='${bl_no}' AND status=1",
                "expected": 1,
                "message": "订单生效状态不一致（期望 status=1）",
            },
        ],
    })

    # 2) 分发订单：使用上一步的 bl_no 与 order_id
    node_configs.append({
        "node_id": "n_distribute",
        "api_id": code_to_api["order_distribute"].id,
        "pre_process": [
            {"type": "set_field", "path": "order_id", "value": "${order_id}"},
            {"type": "set_field", "path": "bl_no", "value": "${bl_no}"},
        ],
        "post_extract": [],
        "assertions": [
            {
                "type": "db_query_count_equals",
                "sql": "SELECT 1 FROM sys_order WHERE bl_no='${bl_no}' AND entrust_status=2",
                "expected": 1,
                "message": "订单分发状态不一致（期望 entrust_status=2）",
            },
            {
                "type": "db_query_count_equals",
                "sql": "SELECT 1 FROM sys_order WHERE bl_no='${bl_no}' AND status=1",
                "expected": 1,
                "message": "订单生效状态不一致（期望 status=1）",
            },
        ],
    })

    # 3) 暂存订单
    node_configs.append({
        "node_id": "n_stash",
        "api_id": code_to_api["order_stash"].id,
        "pre_process": [
            {"type": "set_field", "path": "order_id", "value": "${context.order_id}"},
            {"type": "set_field", "path": "bl_no", "value": "${context.bl_no}"},
        ],
        "post_extract": [],
        "assertions": [],
    })

    # 4) 提交订单
    node_configs.append({
        "node_id": "n_submit",
        "api_id": code_to_api["order_submit"].id,
        "pre_process": [
            {"type": "set_field", "path": "order_id", "value": "${context.order_id}"},
            {"type": "set_field", "path": "bl_no", "value": "${context.bl_no}"},
        ],
        "post_extract": [],
        "assertions": [
            {
                "type": "db_query_count_equals",
                "sql": "SELECT 1 FROM sys_order WHERE bl_no='${bl_no}' AND status=2",
                "expected": 1,
                "message": "订单生效状态不一致（期望 status=2）",
            },
            {
                "type": "db_query_count_equals",
                "sql": "SELECT 1 FROM sys_order WHERE bl_no='${bl_no}' AND effective_time<>0",
                "expected": 1,
                "message": "订单生效时间为0",
            },
        ],
    })

    # 5) 生成子订单
    node_configs.append({
        "node_id": "n_gen_sub",
        "api_id": code_to_api["order_generate_sub"].id,
        "pre_process": [
            {"type": "set_field", "path": "order_id", "value": "${context.order_id}"},
        ],
        "post_extract": [],
        "assertions": [
            {
                "type": "db_query_count_equals",
                "sql": "SELECT 1 FROM sys_order WHERE bl_no='${bl_no}' AND is_traverse=1",
                "expected": 1,
                "message": "子订单状态为未生成（期望 is_traverse=1）",
            },
        ],
    })

    # 6) 录入费用：对客对商费用列表通过 iterate_set 关联 unique_id
    node_configs.append({
        "node_id": "n_fee",
        "api_id": code_to_api["order_fee_add"].id,
        "pre_process": [
            {"type": "set_field", "path": "order_id", "value": "${context.order_id}"},
            {
                "type": "iterate_set",
                "path": "to_customer.put_amount.standard_list",
                "field": "unique_id",
                "value": "${generate_unique_id()}",
            },
            {
                "type": "iterate_set",
                "path": "to_supplier.pay_amount.standard_list",
                "field": "unique_id",
                "value": "${generate_unique_id()}",
            },
        ],
        "post_extract": [],
        "assertions": [
            {
                "type": "db_query_count_equals",
                "sql": "SELECT 1 FROM sys_order_fee_real WHERE order_id='${order_id}'",
                "expected": 16,
                "message": "订单穿行异常（期望 16 条费用记录）",
            },
            # 演示 DB值 vs 响应值 交叉校验：DB中 order_id 应等于响应体返回的 order_id
            {
                "type": "db_vs_jsonpath_equals",
                "sql": "SELECT order_id FROM sys_order WHERE bl_no='${bl_no}'",
                "field": "order_id",
                "path": "$.data.order_id",
                "message": "响应返回的 order_id 与 DB 不一致",
            },
        ],
    })

    return {
        "nodes": nodes,
        "edges": edges,
        "node_configs": node_configs,
    }


def _ensure_case_group(db, project: models.Project, name: str) -> models.CaseGroup:
    """确保用例分组存在（按名称幂等）"""
    obj = db.query(models.CaseGroup).filter(
        models.CaseGroup.project_id == project.id,
        models.CaseGroup.name == name,
    ).first()
    if obj:
        return obj
    obj = models.CaseGroup(project_id=project.id, name=name)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def ensure_testcase(
    db, project: models.Project, name: str, description: str, flow: Dict[str, Any],
    group_id: Optional[int] = None,
) -> models.TestCase:
    dag_config = {"nodes": flow["nodes"], "edges": flow["edges"]}

    obj = db.query(models.TestCase).filter(
        models.TestCase.project_id == project.id,
        models.TestCase.name == name,
    ).first()

    if obj:
        obj.description = description
        obj.group_id = group_id
        obj.dag_config = dag_config
        db.commit()
        # 全量覆盖节点配置
        db.query(models.CaseNodeConfig).filter(models.CaseNodeConfig.case_id == obj.id).delete()
        for nc in flow["node_configs"]:
            db.add(models.CaseNodeConfig(
                case_id=obj.id,
                node_id=nc["node_id"],
                api_id=nc.get("api_id"),
                pre_process=nc.get("pre_process", []),
                post_extract=nc.get("post_extract", []),
                assertions=nc.get("assertions", []),
            ))
        db.commit()
        db.refresh(obj)
        logger.info(f"更新用例：{obj.name} (id={obj.id})")
        return obj

    obj = models.TestCase(
        project_id=project.id,
        group_id=group_id,
        name=name,
        description=description,
        dag_config=dag_config,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    for nc in flow["node_configs"]:
        db.add(models.CaseNodeConfig(
            case_id=obj.id,
            node_id=nc["node_id"],
            api_id=nc.get("api_id"),
            pre_process=nc.get("pre_process", []),
            post_extract=nc.get("post_extract", []),
            assertions=nc.get("assertions", []),
        ))
    db.commit()
    db.refresh(obj)
    logger.info(f"创建用例：{obj.name} (id={obj.id})")
    return obj


# ============ 主流程 ============
def main():
    logger.info("初始化数据库表结构...")
    init_db()

    db = SessionLocal()
    try:
        # 1. 项目
        project = ensure_project(db)

        # 2. 环境
        env_yaml = _PROJECT_ROOT / "config" / "env_demo.yaml"
        env = ensure_environment(db, project, env_yaml)

        # 3. 接口
        data_dir = _PROJECT_ROOT / "data" / (env.name if env else DEFAULT_ENV_NAME)
        code_to_api = ensure_apis(db, project, data_dir)
        logger.info(f"共同步 {len(code_to_api)} 个接口定义")

        # 4. 用例（基于 test_order.py::test_fee_add 完整业务流）
        flow = build_order_full_flow(code_to_api)
        ensure_testcase(
            db, project,
            name="订单全流程（创建→分发→暂存→提交→生成子订单→录入费用）",
            description="迁移自 testcases/order/test_order.py::test_fee_add，验证订单从创建到费用穿行的完整链路。",
            flow=flow,
        )

        # 额外迁移：单独的创建订单用例（test_create）
        single_flow = {
            "nodes": [flow["nodes"][0]],
            "edges": [],
            "node_configs": [flow["node_configs"][0]],
        }
        ensure_testcase(
            db, project,
            name="创建订单（冒烟）",
            description="迁移自 testcases/order/test_order.py::test_create，仅验证订单创建与落库。",
            flow=single_flow,
        )

        logger.info("=" * 60)
        logger.info("迁移完成。可在前端 http://localhost:5173 查看用例。")
        logger.info("=" * 60)
    except Exception as e:
        logger.exception(f"迁移失败：{e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
