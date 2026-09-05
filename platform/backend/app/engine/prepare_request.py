"""请求组装深模块：三级取值优先级的唯一定义点，编排顺序成为直接可测单元。

请求参数三级取值优先级（引擎定案）：
1. 数据集行值（快照保真过滤 filter_row_vars_for_node + apply_row_overrides）
2. 用例编排 set_field 字面量（PreProcessor；非动态字面量让位行值，${} 动态绑定照常求值）
3. 接口字段默认值（build_request_body 兜底组装）

编排顺序（此前只活在 DagExecutor._execute_node 的 40 行胶水里——各纯函数
有单测，但顺序本身无测试，正是 bug 温床）：

    默认组装 → 行值覆盖 → ${} 求值 → pre_process → 再求值
    → JSON 字符串还原 → 字段类型强转 → 剥离 file 字段 → headers 求值

两个顺序约定不可调换：
- 第二次求值必须在 pre_process 之后（前置处理写入上下文的新变量注入 body）
- coerce/apply_field_types 必须在求值之后（"[${id}]" → "[123]" 才能还原成 list）
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ..services.body_builder import (
    apply_row_overrides,
    build_request_body,
    pop_file_fields_from_body,
)
from ..services.dataset_service import filter_row_vars_for_node
from .preprocessor import PreProcessor
from .type_coercer import apply_field_types, coerce_json_strings


@dataclass
class RequestParts:
    """组装产物：JSON body（file 字段已剥离）、最终 headers、multipart file 字段。"""

    body: Any
    headers: dict
    file_fields: list  # [(path, file_id)]


def prepare_request(api, config, *, context, row_vars, row_origins,
                    base_headers, db_client) -> RequestParts:
    """按三级优先级组装一个节点的请求。

    - api：ApiDefinition（fields / request_template）
    - config：CaseNodeConfig 或 None（使用其 pre_process）
    - context：ExecutionContext（to_dict() 供求值；extracted 供 set_field 同步回写）
    - row_vars / row_origins：数据驱动行值与列快照原值（普通执行传 None）
    - base_headers：http_client.headers（深拷贝后原地求值，不污染客户端）
    - db_client：DBClient 或 None（set_field 的 ${db.query_value(...)} 取值用）
    """
    # 优先级 3：接口字段默认值兜底组装
    body = build_request_body(api)
    # 优先级 1：数据集行值（快照保真过滤后覆盖同名字段，${} 动态绑定除外）
    node_row_vars = filter_row_vars_for_node(
        row_vars, row_origins, api,
        config.pre_process if config else None)
    if node_row_vars:
        body = apply_row_overrides(body, node_row_vars)
    # headers：环境公共头 + 接口 headers_template 覆盖（curl/HAR 导入的 Content-Type
    # 在此生效，如 x-www-form-urlencoded 表单接口不必改环境公共头）
    headers = {**deepcopy(base_headers or {}),
               **deepcopy(getattr(api, "headers_template", None) or {})}

    # PreProcessor 持有 db_client，使 set_field 的值能通过 ${db.query_value(...)} 从 DB 取值
    preprocessor = PreProcessor(context.to_dict(), db_client, row_vars=node_row_vars)
    # 对组装后的 body 递归求值 ${...}（覆盖 array/object 字段中嵌入的表达式）；
    # 未定义变量保留占位符，不替换为空，留给后续前置处理或下游注入
    body = preprocessor.expr.evaluate(body)
    if config and config.pre_process:
        # 传入 context.extracted（引用），set_field 求值后的值同步到上下文，
        # 使后续 post_extract 的 SQL 和后续节点的 ${xxx} 能引用到
        body = preprocessor.process(body, config.pre_process, context.extracted)
        # 前置处理可能往上下文写入新变量，对 body 再求值一次，注入此时已具备的变量
        # （保留仍未定义的占位符原样，便于排查未注入字段）
        body = preprocessor.expr.evaluate(body)
    # array/object 字段经表达式求值后仍是字符串（如 "[${id}]" → "[123]"），
    # 转回原生 JSON 类型，使接口收到的是列表/对象而非字符串
    body = coerce_json_strings(body)
    # 按接口字段定义强转标量类型，避免表达式求值后类型丢失
    # （如 ${order_id} 提取为 int，但字段定义为 string 时应转字符串发送）
    body = apply_field_types(body, api)
    # 提取 file 类型字段：从 body 中剥离，单独组装到 multipart files
    # （file 字段不参与 JSON body，避免被 JSON 序列化为字符串）
    body, file_fields = pop_file_fields_from_body(body, api)
    # headers 中支持表达式
    for k, v in list(headers.items()):
        if isinstance(v, str) and "${" in v:
            headers[k] = preprocessor.expr.evaluate(v)
    return RequestParts(body=body, headers=headers, file_fields=file_fields)
