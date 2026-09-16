"""列表导出服务：Excel 简表（人看）+ JSON 全量（备份/迁移）+ OpenAPI 3.0（外部平台迁移）。

口径：跟随列表页的后端筛选条件（project_id / created_by / updated_by）；
勾选导出时按 ids 精确圈定（优先于筛选）。keyword 为前端本地过滤，不参与导出。
Excel 列为摘要级；JSON 含字段、断言、节点配置全量；OpenAPI 供 Postman/Apifox 导入。
"""
import io
import json
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def _style_header(ws, ncols: int) -> None:
    """表头样式：加粗 + 浅灰底"""
    fill = PatternFill("solid", fgColor="F2F3F5")
    for col in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True)
        cell.fill = fill


def _autosize(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def export_apis_excel(apis: list, group_names: dict[int, str]) -> bytes:
    """接口列表 Excel 简表。apis 为 ApiDefinition ORM 列表（已 fill_audit_names）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "接口列表"
    headers = ["ID", "名称", "分组", "方法", "路径", "字段数", "创建人", "更新人", "创建时间", "描述"]
    ws.append(headers)
    _style_header(ws, len(headers))
    for a in apis:
        fields = a.fields or []
        ws.append([
            a.id, a.name, group_names.get(a.group_id, "") if a.group_id else "未分组",
            a.method, a.path, len(fields),
            getattr(a, "created_by_name", "") or "", getattr(a, "updated_by_name", "") or "",
            _fmt(a.created_at), a.description or "",
        ])
    _autosize(ws, [7, 26, 16, 8, 44, 8, 10, 10, 19, 28])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_apis_json(apis: list, group_names: dict[int, str], project_name: str) -> bytes:
    """接口全量 JSON：含字段明细，可后续做导入还原。"""
    data = {
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "apis",
        "project": project_name,
        "count": len(apis),
        "items": [
            {
                "id": a.id, "name": a.name,
                "group": group_names.get(a.group_id) if a.group_id else None,
                "method": a.method, "path": a.path, "description": a.description,
                "sort_order": a.sort_order,
                "fields": [
                    {"key": f.key, "label": f.label, "field_type": f.field_type,
                     "required": f.required, "default_value": f.default_value,
                     "remark": f.remark, "sort_order": f.sort_order}
                    for f in (a.fields or [])
                ],
                "created_at": _fmt(a.created_at),
            }
            for a in apis
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


# ===== OpenAPI 3.0 导出（Postman / Apifox 等可直接导入） =====
_OPENAPI_TYPE_MAP = {
    "string": "string", "str": "string",
    "int": "integer", "integer": "integer",
    "number": "number", "float": "number", "double": "number",
    "bool": "boolean", "boolean": "boolean",
    "object": "object", "array": "array",
}


def _field_leaf_schema(f) -> dict:
    """单字段叶子 schema：类型映射 + 描述 + 默认值（${...} 表达式等非字面量降级为 example）。"""
    t = _OPENAPI_TYPE_MAP.get((f.field_type or "string").strip().lower(), "string")
    schema: dict = {"type": t}
    desc = " / ".join(str(x) for x in (f.label, f.remark) if x)
    if desc:
        schema["description"] = desc
    dv = (f.default_value or "").strip() if f.default_value else ""
    if dv:
        if t == "string":
            schema["default"] = dv
        else:
            try:
                schema["default"] = json.loads(dv)
            except (json.JSONDecodeError, TypeError):
                schema["example"] = dv
    return schema


def _fields_to_properties(fields) -> tuple[dict, list[str]]:
    """字段列表转 properties 树（a.b 嵌套路径逐级展开为 object）+ 顶层 required。"""
    props: dict = {}
    required: list[str] = []
    for f in sorted(fields or [], key=lambda x: x.sort_order or 0):
        segs = [s for s in (f.key or "").split(".") if s]
        if not segs:
            continue
        node = props
        for s in segs[:-1]:
            holder = node.setdefault(s, {"type": "object", "properties": {}})
            node = holder.setdefault("properties", {})
        node[segs[-1]] = _field_leaf_schema(f)
        if len(segs) == 1 and f.required:
            required.append(segs[0])
    return props, required


def export_apis_openapi(apis: list, group_names: dict[int, str], project_name: str) -> bytes:
    """OpenAPI 3.0.3 文档：分组映射 tags、接口编码映射 operationId。

    POST/PUT/PATCH 字段转 requestBody（application/json，schema 按编码收进 components）；
    GET/DELETE 字段转 query 参数；同 path 多 method 合并进同一 pathItem。
    """
    paths: dict = {}
    schemas: dict = {}
    tags: list[dict] = []
    seen_tags: set[str] = set()
    for a in apis:
        tag = group_names.get(a.group_id) if a.group_id else None
        if tag and tag not in seen_tags:
            seen_tags.add(tag)
            tags.append({"name": tag})
        path = a.path if (a.path or "").startswith("/") else f"/{a.path}"
        item = paths.setdefault(path, {})
        method = (a.method or "POST").upper()
        op: dict = {"tags": [tag] if tag else [], "summary": a.name, "operationId": a.code}
        if a.description:
            op["description"] = a.description
        fields = a.fields or []
        if method in ("POST", "PUT", "PATCH"):
            props, required = _fields_to_properties(fields)
            schemas[a.code] = {"type": "object", "properties": props, **({"required": required} if required else {})}
            op["requestBody"] = {
                "required": bool(required),
                "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{a.code}"}}},
            }
        elif fields:
            op["parameters"] = [
                {"name": f.key, "in": "query", "required": bool(f.required),
                 **({"description": f.label} if f.label else {}),
                 "schema": _field_leaf_schema(f)}
                for f in sorted(fields, key=lambda x: x.sort_order or 0)
            ]
        op["responses"] = {"200": {"description": "成功（断言与响应结构请在平台内维护）"}}
        item[method.lower()] = op
    doc = {
        "openapi": "3.0.3",
        "info": {"title": f"{project_name} 接口定义", "version": "1.0.0",
                 "description": f"由 fin-api-test 平台导出于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"},
        **({"tags": tags} if tags else {}),
        "paths": paths,
        **({"components": {"schemas": schemas}} if schemas else {}),
    }
    return json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")


def export_cases_excel(cases: list, group_names: dict[int, str]) -> bytes:
    """用例列表 Excel 简表。cases 为 TestCase ORM 列表（已 fill_audit_names + node_configs 预载）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "用例列表"
    headers = ["ID", "名称", "分组", "节点数", "创建人", "更新人", "更新时间", "描述"]
    ws.append(headers)
    _style_header(ws, len(headers))
    for c in cases:
        n = len((c.dag_config or {}).get("nodes", []))
        ws.append([
            c.id, c.name, group_names.get(c.group_id, "") if c.group_id else "未分组",
            n, getattr(c, "created_by_name", "") or "", getattr(c, "updated_by_name", "") or "",
            _fmt(c.updated_at), c.description or "",
        ])
    _autosize(ws, [7, 40, 16, 8, 10, 10, 19, 30])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_cases_json(cases: list, group_names: dict[int, str], project_name: str) -> bytes:
    """用例全量 JSON：含 DAG 结构与节点配置（断言/提取/前置处理），用于备份/迁移。"""
    items = []
    for c in cases:
        cfg_map = {nc.node_id: nc for nc in (c.node_configs or [])}
        nodes_out = []
        for n in (c.dag_config or {}).get("nodes", []):
            nc = cfg_map.get(n.get("id"))
            nodes_out.append({
                "id": n.get("id"),
                "label": (n.get("data") or {}).get("label"),
                "api_id": nc.api_id if nc else None,
                "position": n.get("position"),
                "config": {
                    "pre_process": (nc.pre_process or []) if nc else [],
                    "post_extract": (nc.post_extract or []) if nc else [],
                    "assertions": (nc.assertions or []) if nc else [],
                    "wait_after_ms": (nc.wait_after_ms or 0) if nc else 0,
                } if nc else None,
            })
        items.append({
            "id": c.id, "name": c.name,
            "group": group_names.get(c.group_id) if c.group_id else None,
            "description": c.description,
            "edges": (c.dag_config or {}).get("edges", []),
            "nodes": nodes_out,
            "updated_at": _fmt(c.updated_at),
        })
    data = {
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "cases",
        "project": project_name,
        "count": len(items),
        "items": items,
    }
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
