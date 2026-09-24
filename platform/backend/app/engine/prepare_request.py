"""请求组装深模块：参数三层解析优先级的唯一定义点，编排顺序成为直接可测单元。

执行参数取值优先级（定案，按参数名自动解析）：
1. 手动覆盖：节点 pre_process set_field/add_field 的非空值（字面量或 ${} 动态绑定），
   在自动解析之后由 PreProcessor 写入，天然取胜
2. 套件注入：context.suite_vars——套件链上游成员的白名单快照（最高优先级注入）
3. 数据集域静态变量：row_vars——绑定数据集当前行的列值（点路径键）

运行时变量（后置提取 / 前序 set_field 求值同步）不参与按名解析：
非动态参数要么取自变量池（数据集域），要么手动填写；
运行时变量一律走 ${} 显式引用。

接口字段默认值不再作为兜底层（一刀切）：静态默认由保存钩子
（dataset_service.sync_case_variable_pool）迁入数据集变量池，动态 ${} 默认
迁为节点 pre_process 引用；运行时组装只认上述三层。
无必填概念（定案）：三层皆空的参数按字段类型发空值占位
（string/file → ""，其余 → null），不报错、不省略。

按名解析（_lookup）在单域内的取值顺序：
- 精确匹配（含点路径键，如 to_customer.put_amount）；整键与叶键并存时
  （select_list 整列 + select_list.0.order_id 叶键），叶键覆盖整键值对应位置
  ——细粒度配置压过粗粒度整值
- 前缀拆叶展开：键为父路径（如 obj），池中存其拆叶键（obj.a / obj.b.c）——
  收集器把嵌套 JSON 递归拆叶入池，解析时逆向展开还原
- 整对象列（存量兼容）：池键为键的前缀且值为 dict（如 to_customer 列），
  按剩余子路径取值

编排顺序（不可调换的两处约定保持不变）：
    骨架+自动解析 → ${} 求值 → pre_process → 再求值
    → JSON 字符串还原 → 字段类型强转 → 剥离 file 字段 → headers 求值
- 第二次求值必须在 pre_process 之后（前置处理写入上下文的新变量注入 body）
- coerce/apply_field_types 必须在求值之后（"[${id}]" → "[123]" 才能还原成 list）
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ..engine.preprocessor import get_nested_value, set_nested_value
from .preprocessor import PreProcessor
from .type_coercer import apply_field_types, coerce_json_strings
from ..services.body_builder import pop_file_fields_from_body


@dataclass
class RequestParts:
    """组装产物：JSON body（file 字段已剥离）、最终 headers、multipart file 字段。"""

    body: Any
    headers: dict
    file_fields: list  # [(path, file_id)]


def _lookup(pool: dict | None, key: str) -> dict | None:
    """单域按名取值：返回 {完整路径: 值} 或 None。空值（None/""，未配置）视为不存在。"""
    if not isinstance(pool, dict):
        return None
    v = pool.get(key)
    # 叶键（细粒度配置，如 select_list.0.order_id = ${order_id}）
    leaves = {k: lv for k, lv in pool.items()
              if k.startswith(key + ".") and lv is not None and lv != ""}
    if v is not None and v != "":
        if not leaves:
            return {key: v}
        # 整键与叶键并存（如 select_list 整列字面量 + 细粒度叶键引用）：
        # 以整键值为底，叶键覆盖对应位置——细粒度配置压过粗粒度整值，
        # 否则精确匹配整键直接命中，叶键引用永远不生效（曾致请求发 666
        # 而非上游 order_id）
        merged = deepcopy(v)
        for lk, lv in leaves.items():
            set_nested_value(merged, lk[len(key) + 1:], lv)
        return {key: merged}
    # 前缀拆叶展开：键是父路径，池中存收集时拆出的叶键
    if leaves:
        return leaves
    # 整对象列（存量数据集）：池键是 key 的前缀且值为 dict，按剩余子路径取值
    prefixes = [p for p in pool if key.startswith(p + ".") and isinstance(pool[p], dict)]
    if prefixes:
        p = max(prefixes, key=len)
        sub = get_nested_value(pool[p], key[len(p) + 1:])
        if sub is not None:
            return {key: sub}
    return None


def prepare_request(api, config, *, context, row_vars,
                    base_headers, db_client) -> RequestParts:
    """按三层优先级组装一个节点的请求。

    - api：ApiDefinition（fields / request_template）
    - config：CaseNodeConfig 或 None（使用其 pre_process）
    - context：ExecutionContext（to_dict() 供求值；suite_vars 供套件注入解析；
      extracted 供 set_field 同步回写）
    - row_vars：数据驱动行值（数据集域，第 3 层；普通执行传 None）
    - base_headers：http_client.headers（深拷贝后原地求值，不污染客户端）
    - db_client：DBClient 或 None（set_field 的 ${db.query_value(...)} 取值用）
    """
    fields = getattr(api, "fields", None) or []
    actions = (config.pre_process if config else None) or []

    # 三态分拣：pre_process 非空值 = 手动覆盖/动态绑定（第 1 层，PreProcessor 生效）；
    # 空值 = 自动引用占位（清空转引用后的形态），参与按名解析
    manual_paths: set[str] = set()
    ref_paths: list[str] = []
    for act in actions:
        if act.get("type") not in ("set_field", "add_field"):
            continue
        path = act.get("path") or ""
        if not path:
            continue  # 空行占位（前端表格留空）非有效动作
        val = act.get("value")
        if val is None or val == "":
            ref_paths.append(path)
        else:
            manual_paths.add(path)

    # 骨架：有字段定义 → 空 dict（接口默认值不再兜底）；无字段 → request_template
    # 深拷贝（模板体的静态值原样保留，未解析到的模板键不删除）
    if fields:
        body: Any = {}
        resolve_keys = [f.key for f in fields if f.key]
    else:
        body = deepcopy(api.request_template if api.request_template is not None else {})
        if isinstance(body, dict):
            # 模板顶层键即该接口的事实参数声明（curl 导入前的手工/HAR 接口）
            resolve_keys = list(body.keys())
        else:
            resolve_keys = []
    resolve_keys = list(dict.fromkeys([*resolve_keys, *ref_paths]))
    field_types = {f.key: (f.field_type or "string") for f in fields if f.key}

    # 第 2/3 层自动解析：套件注入 → 数据集域；无必填概念（定案）——
    # 三层皆空的参数按字段类型发空值占位（string/file/未知 → ""，其余 → null），
    # 不报错不省略；模板体的静态值例外：模板已有值的键不被空值覆盖
    # 运行时变量（extracted：后置提取 / set_field 同步）不参与按名解析，仅 ${} 显式引用可取
    suite_vars = getattr(context, "suite_vars", None)
    for key in resolve_keys:
        if key in manual_paths:
            continue  # 第 1 层手动覆盖，pre_process 阶段生效
        target = body
        if isinstance(target, list) and target and isinstance(target[0], dict):
            target = target[0]
        got = _lookup(suite_vars, key) or _lookup(row_vars, key)
        if not got:
            if get_nested_value(target, key) is not None:
                continue  # 模板静态值保留，不用空值占位覆盖
            ftype = field_types.get(key, "string")
            # array 空占位发 []（PHP 语义的空数组参数，与原"空数组默认值入池"行为
            # 等价——收集器已把空集合默认视为未配置，空占位补位保持请求形态）
            got = {key: "" if ftype in ("string", "file") else ([] if ftype == "array" else None)}
        for full, v in got.items():
            set_nested_value(target, full, v)

    # 数组请求体（字段骨架路径）：request_template 为 list 表示 body 本身是 [{...}]
    if fields and isinstance(api.request_template, list):
        body = [body]

    # headers：环境公共头 + 接口 headers_template 覆盖（curl/HAR 导入的 Content-Type
    # 在此生效，如 x-www-form-urlencoded 表单接口不必改环境公共头）；
    # headers_template 值为 null = 显式剔除该头（外部系统接口排除环境注入的
    # 鉴权头，如 fin token 发往 newshopadmin 老系统会被直接断连）
    headers = {**deepcopy(base_headers or {}),
               **deepcopy(getattr(api, "headers_template", None) or {})}
    headers = {k: v for k, v in headers.items() if v is not None}

    # PreProcessor 持有 db_client，使 set_field 的值能通过 ${db.query_value(...)} 从 DB 取值
    preprocessor = PreProcessor(context.to_dict(), db_client)
    # 对组装后的 body 递归求值 ${...}（覆盖 array/object 字段中嵌入的表达式）；
    # 未定义变量保留占位符，不替换为空，留给后续前置处理或下游注入
    body = preprocessor.expr.evaluate(body)
    if actions:
        # 传入 context.extracted（引用），set_field 求值后的值同步到统一池，
        # 使后续 post_extract 的 SQL 与后续节点的 ${xxx} 显式引用可用
        body = preprocessor.process(body, actions, context.extracted)
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
