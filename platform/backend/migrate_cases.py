"""
迁移 test_order.py 的 6 个测试函数为平台用例，沿用代码的入参替换、响应字段提取、断言策略。

代码逻辑映射：
- bl_no：set_field ${generate_bl_no(prefix='smoke')}，改引擎后同步到上下文
- order_id：post_extract source=db，SQL 用 ${bl_no} 查询
- 后续节点：set_field ${context.order_id} / ${context.bl_no}
- 断言：db_query_equals / db_query_not_equals / db_query_count_equals

6 个用例：
1. test_create - 创建订单（断言 entrust_status=1, status=1）
2. test_distribute - 创建→分发（断言 entrust_status=2, status=1）
3. test_stash - 创建→分发→暂存（无业务断言）
4. test_submit - 创建→分发→暂存→提交（断言 status=2, effective_time≠0, business_time==effective_time）
5. test_generate_sub_order - ...→提交→生成子订单（断言 is_traverse=1）
6. test_fee_add - ...→生成子订单→录入费用（断言 fee count=16）
"""
import os
import requests
import json

BASE = "http://127.0.0.1:8000/api"

# ============ 登录获取 token（业务路由均需 Bearer 鉴权，否则 401）============
# 账号密码可通过环境变量覆盖，默认用后端首次启动创建的管理员 admin/admin123
_LOGIN_USER = os.getenv("MIGRATE_USER", "admin")
_LOGIN_PASS = os.getenv("MIGRATE_PASS", "admin123")

session = requests.Session()
_login_r = session.post(f"{BASE}/auth/login", json={"username": _LOGIN_USER, "password": _LOGIN_PASS}, timeout=15)
if _login_r.status_code != 200:
    print(f"[ERROR] 登录失败: {_login_r.status_code} {_login_r.text}")
    raise SystemExit(1)
session.headers.update({"Authorization": f"Bearer {_login_r.json()['token']}"})
print(f"=== 已登录用户 {_LOGIN_USER}，token 已注入后续请求 ===\n")

# ============ 删除旧用例（id=3~8，之前迁移的）============
print("=== 清理旧用例 ===")
for cid in range(3, 9):
    r = session.delete(f"{BASE}/testcases/{cid}")
    print(f"  删除用例 id={cid}: {r.status_code}")

# 接口 id 映射
API = {
    "create": 1,        # order_create
    "distribute": 2,    # order_distribute
    "stash": 3,         # order_stash
    "submit": 4,        # order_submit
    "gen_sub": 5,       # order_generate_sub
    "fee_add": 6,       # order_fee_add
}

# SQL 模板（${bl_no} / ${order_id} 由引擎注入上下文变量）
# 注意：引擎会自动为字符串值加单引号防注入，SQL 里不要再写引号
SQL_ORDER_BY_BL = "SELECT order_id FROM sys_order WHERE bl_no=${bl_no}"
SQL_ENTRUST_STATUS = "SELECT entrust_status FROM sys_order WHERE bl_no=${bl_no}"
SQL_STATUS = "SELECT status FROM sys_order WHERE bl_no=${bl_no}"
SQL_EFFECTIVE_TIME = "SELECT effective_time FROM sys_order WHERE bl_no=${bl_no}"
SQL_BIZ_EQ_EFFECT = "SELECT (business_time = effective_time) AS same FROM sys_order WHERE bl_no=${bl_no}"
SQL_IS_TRAVERSE = "SELECT is_traverse FROM sys_order WHERE bl_no=${bl_no}"
SQL_FEE_COUNT = "SELECT COUNT(*) AS cnt FROM sys_order_fee_real WHERE order_id=${order_id}"


def make_create_node(idx: int) -> dict:
    """创建订单节点：生成 bl_no，从 DB 提取 order_id，断言状态码+DB字段"""
    col = idx % 3
    row = idx // 3
    return {
        "id": "n_create",
        "type": "default",
        "position": {"x": col * 240, "y": row * 140},
        "data": {"label": "创建订单", "api_id": API["create"], "api_code": "order_create", "api_method": "POST", "api_path": "/api/order/orderEntrust/orderAdd"},
    }


def make_node(node_id: str, api_key: str, label: str, idx: int) -> dict:
    col = idx % 3
    row = idx // 3
    api_id = API[api_key]
    return {
        "id": node_id,
        "type": "default",
        "position": {"x": col * 240, "y": row * 140},
        "data": {"label": label, "api_id": api_id, "api_method": "POST"},
    }


def make_create_config(assertions: list) -> dict:
    """创建节点配置：pre_process 生成 bl_no，post_extract 从 DB 提取 order_id"""
    return {
        "node_id": "n_create",
        "api_id": API["create"],
        "pre_process": [
            {"type": "set_field", "path": "bl_no", "value": "${generate_bl_no(prefix='smoke')}"}
        ],
        "post_extract": [
            {"name": "order_id", "source": "db", "sql": SQL_ORDER_BY_BL, "field": "order_id"}
        ],
        "assertions": [
            {"type": "response_status_equals", "expected": 200, "message": "创建订单接口状态码应为200"}
        ] + assertions,
    }


def make_followup_config(node_id: str, api_key: str, assertions: list = None) -> dict:
    """后续节点配置：set_field order_id/bl_no 从上下文取值"""
    return {
        "node_id": node_id,
        "api_id": API[api_key],
        "pre_process": [
            {"type": "set_field", "path": "order_id", "value": "${context.order_id}"},
            {"type": "set_field", "path": "bl_no", "value": "${context.bl_no}"},
        ],
        "post_extract": [],
        "assertions": [
            {"type": "response_status_equals", "expected": 200, "message": "接口状态码应为200"}
        ] + (assertions or []),
    }


def make_edge(src: str, tgt: str) -> dict:
    return {"id": f"e_{src}_{tgt}", "source": src, "target": tgt}


def create_case(name: str, description: str, nodes: list, edges: list, node_configs: list, group_id: int = None) -> dict:
    payload = {
        "project_id": 1,
        "group_id": group_id,
        "name": name,
        "description": description,
        "dag_config": {"nodes": nodes, "edges": edges},
        "node_configs": node_configs,
    }
    r = session.post(f"{BASE}/testcases", json=payload, timeout=15)
    print(f"  创建用例「{name}」: {r.status_code}")
    if r.status_code != 200:
        print(f"    错误: {r.text[:200]}")
    return r.json() if r.status_code == 200 else {}


# ============ 创建用例分组 ============
print("=== 创建用例分组 ===")
r = session.post(f"{BASE}/case-groups", json={"project_id": 1, "name": "订单全流程", "sort_order": 1}, timeout=15)
if r.status_code != 200:
    print(f"[ERROR] 创建用例分组失败: {r.status_code} {r.text}")
    raise SystemExit(1)
order_group = r.json()
print(f"  分组「订单全流程」id={order_group.get('id')}")

# ============ 1. test_create ============
print("\n=== 1. test_create ===")
create_case(
    name="test_create（创建订单）",
    description="迁移自 testcases/order/test_order.py::test_create，断言 entrust_status=1, status=1",
    nodes=[make_create_node(0)],
    edges=[],
    node_configs=[
        make_create_config([
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 1, "message": "订单分发状态应为1"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "订单生效状态应为1"},
        ])
    ],
    group_id=order_group["id"],
)

# ============ 2. test_distribute ============
print("\n=== 2. test_distribute ===")
create_case(
    name="test_distribute（创建→分发）",
    description="迁移自 testcases/order/test_order.py::test_distribute，断言分发后 entrust_status=2, status=1",
    nodes=[make_create_node(0), make_node("n_distribute", "distribute", "订单分发", 1)],
    edges=[make_edge("n_create", "n_distribute")],
    node_configs=[
        make_create_config([
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 1, "message": "创建后分发状态应为1"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "创建后生效状态应为1"},
        ]),
        make_followup_config("n_distribute", "distribute", [
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 2, "message": "分发后分发状态应为2"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "分发后生效状态应为1"},
        ]),
    ],
    group_id=order_group["id"],
)

# ============ 3. test_stash ============
print("\n=== 3. test_stash ===")
create_case(
    name="test_stash（创建→分发→暂存）",
    description="迁移自 testcases/order/test_order.py::test_stash，无业务断言（只断状态码）",
    nodes=[
        make_create_node(0),
        make_node("n_distribute", "distribute", "订单分发", 1),
        make_node("n_stash", "stash", "暂存订单", 2),
    ],
    edges=[make_edge("n_create", "n_distribute"), make_edge("n_distribute", "n_stash")],
    node_configs=[
        make_create_config([
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 1, "message": "创建后分发状态应为1"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "创建后生效状态应为1"},
        ]),
        make_followup_config("n_distribute", "distribute", [
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 2, "message": "分发后分发状态应为2"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "分发后生效状态应为1"},
        ]),
        make_followup_config("n_stash", "stash"),
    ],
    group_id=order_group["id"],
)

# ============ 4. test_submit ============
print("\n=== 4. test_submit ===")
create_case(
    name="test_submit（创建→分发→暂存→提交）",
    description="迁移自 testcases/order/test_order.py::test_submit，断言 status=2, effective_time≠0, business_time==effective_time",
    nodes=[
        make_create_node(0),
        make_node("n_distribute", "distribute", "订单分发", 1),
        make_node("n_stash", "stash", "暂存订单", 2),
        make_node("n_submit", "submit", "提交订单", 3),
    ],
    edges=[
        make_edge("n_create", "n_distribute"),
        make_edge("n_distribute", "n_stash"),
        make_edge("n_stash", "n_submit"),
    ],
    node_configs=[
        make_create_config([
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 1, "message": "创建后分发状态应为1"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "创建后生效状态应为1"},
        ]),
        make_followup_config("n_distribute", "distribute", [
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 2, "message": "分发后分发状态应为2"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "分发后生效状态应为1"},
        ]),
        make_followup_config("n_stash", "stash"),
        make_followup_config("n_submit", "submit", [
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 2, "message": "提交后分发状态应为2"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 2, "message": "提交后生效状态应为2"},
            {"type": "db_query_not_equals", "sql": SQL_EFFECTIVE_TIME, "field": "effective_time", "expected": 0, "message": "订单生效时间不应为0"},
            {"type": "db_query_equals", "sql": SQL_BIZ_EQ_EFFECT, "field": "same", "expected": 1, "message": "业务发生时间应等于订单生效时间"},
        ]),
    ],
    group_id=order_group["id"],
)

# ============ 5. test_generate_sub_order ============
print("\n=== 5. test_generate_sub_order ===")
create_case(
    name="test_generate_sub_order（...→提交→生成子订单）",
    description="迁移自 testcases/order/test_order.py::test_generate_sub_order，断言 is_traverse=1",
    nodes=[
        make_create_node(0),
        make_node("n_distribute", "distribute", "订单分发", 1),
        make_node("n_stash", "stash", "暂存订单", 2),
        make_node("n_submit", "submit", "提交订单", 3),
        make_node("n_gen_sub", "gen_sub", "生成子订单", 4),
    ],
    edges=[
        make_edge("n_create", "n_distribute"),
        make_edge("n_distribute", "n_stash"),
        make_edge("n_stash", "n_submit"),
        make_edge("n_submit", "n_gen_sub"),
    ],
    node_configs=[
        make_create_config([
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 1, "message": "创建后分发状态应为1"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "创建后生效状态应为1"},
        ]),
        make_followup_config("n_distribute", "distribute", [
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 2, "message": "分发后分发状态应为2"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "分发后生效状态应为1"},
        ]),
        make_followup_config("n_stash", "stash"),
        make_followup_config("n_submit", "submit", [
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 2, "message": "提交后分发状态应为2"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 2, "message": "提交后生效状态应为2"},
            {"type": "db_query_not_equals", "sql": SQL_EFFECTIVE_TIME, "field": "effective_time", "expected": 0, "message": "订单生效时间不应为0"},
            {"type": "db_query_equals", "sql": SQL_BIZ_EQ_EFFECT, "field": "same", "expected": 1, "message": "业务发生时间应等于订单生效时间"},
        ]),
        # 生成子订单：请求体只有 order_id，无需 bl_no
        {
            "node_id": "n_gen_sub",
            "api_id": API["gen_sub"],
            "pre_process": [
                {"type": "set_field", "path": "order_id", "value": "${context.order_id}"}
            ],
            "post_extract": [],
            "assertions": [
                {"type": "response_status_equals", "expected": 200, "message": "生成子订单接口状态码应为200"},
                {"type": "db_query_equals", "sql": SQL_IS_TRAVERSE, "field": "is_traverse", "expected": 1, "message": "子订单状态应为已生成(is_traverse=1)"},
            ],
        },
    ],
    group_id=order_group["id"],
)

# ============ 6. test_fee_add ============
print("\n=== 6. test_fee_add ===")
create_case(
    name="test_fee_add（...→生成子订单→录入费用）",
    description="迁移自 testcases/order/test_order.py::test_fee_add，断言 fee count=16",
    nodes=[
        make_create_node(0),
        make_node("n_distribute", "distribute", "订单分发", 1),
        make_node("n_stash", "stash", "暂存订单", 2),
        make_node("n_submit", "submit", "提交订单", 3),
        make_node("n_gen_sub", "gen_sub", "生成子订单", 4),
        make_node("n_fee", "fee_add", "录入订舱费用", 5),
    ],
    edges=[
        make_edge("n_create", "n_distribute"),
        make_edge("n_distribute", "n_stash"),
        make_edge("n_stash", "n_submit"),
        make_edge("n_submit", "n_gen_sub"),
        make_edge("n_gen_sub", "n_fee"),
    ],
    node_configs=[
        make_create_config([
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 1, "message": "创建后分发状态应为1"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "创建后生效状态应为1"},
        ]),
        make_followup_config("n_distribute", "distribute", [
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 2, "message": "分发后分发状态应为2"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 1, "message": "分发后生效状态应为1"},
        ]),
        make_followup_config("n_stash", "stash"),
        make_followup_config("n_submit", "submit", [
            {"type": "db_query_equals", "sql": SQL_ENTRUST_STATUS, "field": "entrust_status", "expected": 2, "message": "提交后分发状态应为2"},
            {"type": "db_query_equals", "sql": SQL_STATUS, "field": "status", "expected": 2, "message": "提交后生效状态应为2"},
            {"type": "db_query_not_equals", "sql": SQL_EFFECTIVE_TIME, "field": "effective_time", "expected": 0, "message": "订单生效时间不应为0"},
            {"type": "db_query_equals", "sql": SQL_BIZ_EQ_EFFECT, "field": "same", "expected": 1, "message": "业务发生时间应等于订单生效时间"},
        ]),
        {
            "node_id": "n_gen_sub",
            "api_id": API["gen_sub"],
            "pre_process": [
                {"type": "set_field", "path": "order_id", "value": "${context.order_id}"}
            ],
            "post_extract": [],
            "assertions": [
                {"type": "response_status_equals", "expected": 200, "message": "生成子订单接口状态码应为200"},
                {"type": "db_query_equals", "sql": SQL_IS_TRAVERSE, "field": "is_traverse", "expected": 1, "message": "子订单状态应为已生成(is_traverse=1)"},
            ],
        },
        # 录入费用：set_field order_id，iterate_set 给 customer/supplier 列表同位置生成相同 unique_id
        {
            "node_id": "n_fee",
            "api_id": API["fee_add"],
            "pre_process": [
                {"type": "set_field", "path": "order_id", "value": "${context.order_id}"},
                # iterate_set：遍历对客列表生成 unique_id，同步设置对商列表同位置
                {
                    "type": "iterate_set",
                    "list_path": "to_customer.put_amount.standard_list",
                    "sync_list": "to_supplier.pay_amount.standard_list",
                    "field": "unique_id",
                    "value": "${generate_unique_id()}"
                },
            ],
            "post_extract": [],
            "assertions": [
                {"type": "response_status_equals", "expected": 200, "message": "录入费用接口状态码应为200"},
                {"type": "db_query_count_equals", "sql": SQL_FEE_COUNT, "expected": 16, "message": "订单穿行费用应为16条"},
            ],
        },
    ],
    group_id=order_group["id"],
)

print("\n=== 迁移完成 ===")
# 列出所有用例
r = session.get(f"{BASE}/testcases", timeout=15)
if r.status_code == 200:
    print("\n当前用例列表:")
    for tc in r.json():
        print(f"  id={tc['id']} name={tc['name']}")
else:
    print(f"[WARN] 列出用例失败: {r.status_code} {r.text[:200]}")
