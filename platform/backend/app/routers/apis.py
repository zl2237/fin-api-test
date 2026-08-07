from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from copy import deepcopy
from datetime import datetime
from typing import Any
import json
import time
from jsonpath_ng import parse as jsonpath_parse

from ..database import get_db
from .. import crud, schemas, models, path_setup  # noqa: F401
from ..auth import get_current_user
from utils.http_client import HttpClient
from utils.exceptions import HttpStatusError, BusinessError, AuthError, HttpTimeoutError, JsonParseError

router = APIRouter(prefix="/api/apis", tags=["接口定义"])

# 注意：分组路由单独前缀，避免和 /api/apis/{api_id} 冲突
group_router = APIRouter(prefix="/api/api-groups", tags=["接口分组"])


# ============ 接口分组 ============
@group_router.post("", response_model=schemas.ApiGroupOut)
def create_group(data: schemas.ApiGroupCreate, db: Session = Depends(get_db)):
    obj = crud.create_api_group(db, data)
    crud.log_operation(db, None, "create", "api_group", obj.id, obj.name)
    return obj


@group_router.get("", response_model=list[schemas.ApiGroupOut])
def list_groups(project_id: int, db: Session = Depends(get_db)):
    return crud.list_api_groups(db, project_id)


@group_router.put("/{group_id}", response_model=schemas.ApiGroupOut)
def update_group(group_id: int, data: schemas.ApiGroupUpdate, db: Session = Depends(get_db)):
    obj = crud.get_api_group(db, group_id)
    if not obj:
        raise HTTPException(404, "接口分组不存在")
    obj = crud.update_api_group(db, obj, data)
    crud.log_operation(db, None, "update", "api_group", obj.id, obj.name)
    return obj


@group_router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    obj = crud.get_api_group(db, group_id)
    if not obj:
        raise HTTPException(404, "接口分组不存在")
    try:
        crud.delete_api_group(db, obj)
    except ValueError as e:
        # 组非空时阻止删除，前端提示用户先移走接口
        raise HTTPException(400, str(e))
    crud.log_operation(db, None, "delete", "api_group", obj.id, obj.name)
    return {"message": "已删除"}


# ============ 接口定义 ============
@router.post("", response_model=schemas.ApiOut)
def create(data: schemas.ApiCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if crud.get_api_by_code(db, data.code):
        raise HTTPException(400, f"接口编码已存在: {data.code}")
    obj = crud.create_api(db, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "create", "api", obj.id, obj.name)
    return obj


@router.get("", response_model=list[schemas.ApiOut])
def list_all(project_id: int | None = None, created_by: int | None = None, updated_by: int | None = None, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    objs = crud.list_apis(db, project_id, created_by, updated_by)
    crud.fill_audit_names_batch(db, objs)
    return objs


@router.get("/{api_id}", response_model=schemas.ApiOut)
def get_one(api_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_api(db, api_id)
    if not obj:
        raise HTTPException(404, "接口不存在")
    crud.fill_audit_names(db, obj)
    return obj


@router.put("/{api_id}", response_model=schemas.ApiOut)
def update(api_id: int, data: schemas.ApiUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_api(db, api_id)
    if not obj:
        raise HTTPException(404, "接口不存在")
    # code 变更时校验唯一性，避免触发数据库 unique 约束的 500 错误
    if data.code is not None and data.code != obj.code:
        existing = crud.get_api_by_code(db, data.code)
        if existing and existing.id != api_id:
            raise HTTPException(400, f"接口编码已存在: {data.code}")
    obj = crud.update_api(db, obj, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "update", "api", obj.id, obj.name)
    return obj


@router.delete("/{api_id}")
def delete(api_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_api(db, api_id)
    if not obj:
        raise HTTPException(404, "接口不存在")
    try:
        crud.delete_api(db, obj)
    except ValueError as e:
        # 接口被用例引用时阻止删除，前端提示用户先移除用例中的该节点
        raise HTTPException(400, str(e))
    crud.log_operation(db, user, "delete", "api", obj.id, obj.name)
    return {"message": "已删除"}


@router.post("/{api_id}/copy", response_model=schemas.ApiOut)
def copy(api_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_api(db, api_id)
    if not obj:
        raise HTTPException(404, "接口不存在")
    new_obj = crud.copy_api(db, obj)
    new_obj.created_by = user.id
    new_obj.updated_by = user.id
    db.commit()
    db.refresh(new_obj)
    crud.fill_audit_names(db, new_obj)
    crud.log_operation(db, user, "copy", "api", new_obj.id, new_obj.name)
    return new_obj


@router.post("/batch-move")
def batch_move(data: schemas.ApiBatchMove, db: Session = Depends(get_db)):
    """批量移动接口到指定分组"""
    # 注意：此路由需在 /{api_id} 之前注册，否则会被 path 参数拦截
    updated = crud.batch_move_apis(db, data.api_ids, data.group_id)
    return {"message": f"已移动 {updated} 个接口", "updated": updated}


@router.post("/reorder")
def reorder(data: schemas.ApiReorderRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量重排序接口（组内拖拽排序）"""
    # 注意：此路由需在 /{api_id} 之前注册，否则会被 path 参数拦截
    items = [{"id": it.id, "sort_order": it.sort_order} for it in data.items]
    updated = crud.reorder_apis(db, items)
    return {"message": f"已更新 {updated} 个接口排序", "updated": updated}


@router.post("/import")
def import_apis(data: schemas.ApiImportRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """从 Swagger/OpenAPI JSON 导入接口定义，自动生成字段"""
    spec = data.spec or {}
    # 兼容 OpenAPI 3.0 和 Swagger 2.0
    is_v3 = "openapi" in spec
    paths = spec.get("paths", {})

    imported = []
    skipped = []
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, info in methods.items():
            method = method.upper()
            if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                continue
            # 接口名：优先 summary，其次 operationId，最后 path
            name = info.get("summary") or info.get("operationId") or path
            # code：优先 operationId，其次 path 转下划线
            code = info.get("operationId") or _path_to_code(path, method)
            if crud.get_api_by_code(db, code):
                skipped.append(f"{method} {path}（编码 {code} 已存在）")
                continue

            # 解析请求参数（query/path/header）+ 请求体 schema -> 字段
            fields = _extract_fields_from_spec(info, spec, is_v3)

            api_data = schemas.ApiCreate(
                project_id=data.project_id,
                group_id=data.group_id,
                name=name,
                code=code,
                method=method,
                path=path,
                description=info.get("description", ""),
                request_template={},
                headers_template={},
                fields=fields,
            )
            obj = crud.create_api(db, api_data, user.id)
            imported.append({"id": obj.id, "name": obj.name, "method": method, "path": path, "fields": len(fields)})

    crud.log_operation(db, user, "create", "api", None, f"批量导入{len(imported)}个接口")
    return {
        "message": f"已导入 {len(imported)} 个接口" + (f"，跳过 {len(skipped)} 个" if skipped else ""),
        "imported": imported,
        "skipped": skipped,
    }


@router.post("/{api_id}/import-fields", response_model=schemas.ApiImportFieldsResponse)
def import_fields_from_swagger(
    api_id: int,
    data: schemas.ApiImportFieldsRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """用 Swagger 覆盖指定接口的字段：只解析返回字段列表，不落库。
    前端拿到字段后展示新旧对比，用户确认后再调 PUT /apis/{id} 覆盖。"""
    api = crud.get_api(db, api_id)
    if not api:
        raise HTTPException(404, "接口不存在")

    spec = data.spec or {}
    is_v3 = "openapi" in spec
    paths = spec.get("paths", {}) or {}

    # 用 method + path 定位 spec 中的 operation（支持大小写、前导斜杠差异）
    target_method = (data.method or api.method).upper()
    target_path = (data.path or api.path).lstrip("/")
    matched_path = None
    matched_method = None
    matched_info = None
    for p, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        p_norm = p.lstrip("/")
        if p_norm != target_path:
            continue
        for m, info in methods.items():
            if m.upper() == target_method:
                matched_path = p
                matched_method = m.upper()
                matched_info = info
                break
        if matched_info:
            break

    if not matched_info or not isinstance(matched_info, dict):
        return schemas.ApiImportFieldsResponse(
            matched=False,
            method=target_method,
            path=data.path or api.path,
            operation_summary=None,
            fields=[],
        )

    fields = _extract_fields_from_spec(matched_info, spec, is_v3)
    summary = matched_info.get("summary") or matched_info.get("operationId") or matched_path
    return schemas.ApiImportFieldsResponse(
        matched=True,
        method=matched_method,
        path=matched_path,
        operation_summary=summary,
        fields=fields,
    )


@router.post("/{api_id}/debug")
def debug_api(
    api_id: int,
    data: schemas.ApiDebugRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    单接口调试：指定环境执行一次接口，返回请求/响应详情。
    仅支持 GET/POST（与 DAG 执行引擎一致）；PUT/DELETE 给出明确提示。
    登录、请求逻辑复用 dag_executor 的同名私有方法，保证调试与实际执行行为一致。
    """
    api = crud.get_api(db, api_id)
    if not api:
        raise HTTPException(404, "接口不存在")
    env = crud.get_environment(db, data.env_id)
    if not env:
        raise HTTPException(404, "环境不存在")

    method = (api.method or "GET").upper()
    if method not in ("GET", "POST"):
        raise HTTPException(400, f"调试暂不支持 {method} 方法，仅支持 GET/POST")

    started_at = datetime.now()
    start_ts = time.time()

    # 复用 dag_executor 的客户端构建与登录逻辑，保证调试行为与实际执行一致
    from ..engine.dag_executor import DagExecutor
    executor = DagExecutor(db, _DummyCase(), env)
    client = executor._build_http_client()
    try:
        try:
            executor._login(client)
        except Exception as e:
            return _debug_response(api, method, {}, {}, 0, {"error": f"登录失败：{e}"}, started_at, start_ts, login_failed=True)

        # 构建请求体：body_override 优先，否则用 fields 组装
        if data.body_override is not None:
            body = deepcopy(data.body_override)
        else:
            body = executor._build_request_body(api)

        headers = deepcopy(client.headers or {})

        # 超时时间取环境配置（向后兼容：未配置时默认 15 秒）
        req_timeout = getattr(env, "timeout", None) or 15
        # 发送请求
        try:
            if method == "GET":
                resp = client.get(api.path, params=body, timeout=req_timeout)
            else:
                resp = client.post(api.path, json=body, timeout=req_timeout)
            status_code = 200
            response_data = resp if isinstance(resp, (dict, list)) else {"text": str(resp)}
            error_msg = None
        except HttpStatusError as e:
            status_code = e.status_code
            response_data = {"error": str(e)}
            error_msg = str(e)
        except BusinessError as e:
            status_code = 200
            response_data = {"code": e.code, "msg": e.msg, "error": str(e)}
            error_msg = str(e)
        except (AuthError, HttpTimeoutError, JsonParseError) as e:
            status_code = 0
            response_data = {"error": str(e)}
            error_msg = str(e)
        except Exception as e:
            status_code = 0
            response_data = {"error": str(e)}
            error_msg = str(e)

        return _debug_response(api, method, headers, body, status_code, response_data, started_at, start_ts, error=error_msg)
    finally:
        try:
            if client.session:
                client.session.close()
        except Exception:
            pass


class _DummyCase:
    """DagExecutor 构造需要一个 case 对象，调试时用空 case 占位"""
    id = 0
    dag_config = {"nodes": [], "edges": []}
    node_configs = []
    name = "debug"


def _debug_response(api, method, headers, body, status_code, response_data, started_at, start_ts, error=None, login_failed=False):
    elapsed = int((time.time() - start_ts) * 1000)
    return {
        "api_id": api.id,
        "api_name": api.name,
        "method": method,
        "path": api.path,
        "request_headers": headers,
        "request_body": body,
        "response_status": status_code,
        "response_body": response_data,
        "response_time_ms": elapsed,
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "ok": error is None and not login_failed,
        "login_failed": login_failed,
        "error": error,
    }


def _path_to_code(path: str, method: str) -> str:
    """路径转接口编码：/api/order/create -> order_create"""
    # 去掉前导 /api/，按 / 分割取最后两段
    parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
    if len(parts) >= 2:
        code = "_".join(parts[-2:])
    elif parts:
        code = parts[-1]
    else:
        code = "api"
    return f"{code}_{method.lower()}"


def _resolve_ref(ref: str, spec: dict) -> dict:
    """解析 $ref 引用，支持 #/components/schemas、#/components/parameters、#/definitions"""
    if not ref:
        return {}
    parts = ref.lstrip("#/").split("/")
    cur: Any = spec
    for p in parts:
        if p in ("components", "schemas", "parameters", "definitions"):
            cur = cur.get(p, {}) if isinstance(cur, dict) else {}
            continue
        cur = cur.get(p, {}) if isinstance(cur, dict) else {}
    return cur if isinstance(cur, dict) else {}

def _swagger_type_to_field_type(swagger_type: str) -> str:
    """Swagger type 映射到平台 field_type"""
    mapping = {
        "string": "string",
        "integer": "int",
        "number": "string",
        "boolean": "bool",
        "array": "array",
        "object": "object",
    }
    return mapping.get(swagger_type, "string")

def _pick_default_value(node: dict) -> Any:
    """从 OpenAPI schema/parameter 节点按优先级提取默认值：
    default > example(单数) > examples(复数,取第一个value) > enum[0] > ""
    覆盖 OpenAPI 3.0 的多种示例写法。
    """
    if not isinstance(node, dict):
        return ""
    val = node.get("default")
    if val is not None:
        return val
    val = node.get("example")
    if val is not None:
        return val
    # OpenAPI 3.0 examples（复数）：{"examples": {"foo": {"value": ...}}}
    examples = node.get("examples")
    if isinstance(examples, dict) and examples:
        first = next(iter(examples.values()))
        if isinstance(first, dict) and "value" in first:
            return first["value"]
        if first is not None:
            return first
    # 枚举类型取第一个值作为示例
    enum_vals = node.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        return enum_vals[0]
    return ""

def _coerce_default(default_value: Any, field_type: str) -> str:
    """将默认值统一为字符串；array/object 用 JSON 序列化"""
    if default_value == "" or default_value is None:
        return ""
    if field_type in ("array", "object") and not isinstance(default_value, str):
        return json.dumps(default_value, ensure_ascii=False)
    return str(default_value)

def _extract_fields_from_spec(info: dict, spec: dict, is_v3: bool) -> list:
    """从 OpenAPI/Swagger 操作定义中提取字段：
    1. parameters（query/path/cookie/formData，跳过 header）→ 有默认值才导入
    2. requestBody body schema 的 properties → 有默认值才导入
    默认值来源优先级：
      property 自身: default > example(单数) > examples(复数) > enum[0]
      body 字段额外回退: schema 顶层 example（完整请求体示例对象）中对应 key 的值
    无默认值（空字符串/None）的字段不导入。
    """
    fields: list = []
    sort_order = 0
    seen_keys: set = set()

    # ---- 1. 提取 parameters（query/path/cookie/formData，跳过 header）----
    for param in info.get("parameters", []) or []:
        if not isinstance(param, dict):
            continue
        # v3: parameter 可能 $ref 引用 #/components/parameters/{name}
        if "$ref" in param:
            param = _resolve_ref(param["$ref"], spec)
            if not param:
                continue
        loc = param.get("in", "query")
        # 跳过 header 参数（由环境配置/headers_template 管理，不作为业务字段导入）
        if loc == "header":
            continue
        name = param.get("name")
        if not name or name in seen_keys:
            continue
        # schema 来源：v3 在 param.schema（可能 $ref），v2 直接平铺在 param 上
        if is_v3:
            pschema = param.get("schema", {}) or {}
            if "$ref" in pschema:
                pschema = _resolve_ref(pschema["$ref"], spec)
            swagger_type = pschema.get("type", "string")
            # 默认值：优先 parameter 顶层 example/examples，再回退 schema
            default_value = _pick_default_value(param)
            if default_value == "":
                default_value = _pick_default_value(pschema)
        else:
            # Swagger 2.0: type/default/example 直接在 param 上
            swagger_type = param.get("type", "string")
            default_value = _pick_default_value(param)
        field_type = _swagger_type_to_field_type(swagger_type)
        coerced = _coerce_default(default_value, field_type)
        # 只导入有默认值的参数
        if not coerced:
            continue
        description = param.get("description", "") or ""
        fields.append(schemas.ApiFieldIn(
            key=name,
            label=description or param.get("title", ""),
            field_type=field_type,
            required=bool(param.get("required", False)),
            default_value=coerced,
            remark=f"{loc}参数" + (f"：{description}" if description else ""),
            sort_order=sort_order,
        ))
        seen_keys.add(name)
        sort_order += 1

    # ---- 2. 提取 requestBody body 字段 ----
    schema = None
    json_content = None
    if is_v3:
        request_body = info.get("requestBody", {}) or {}
        content = request_body.get("content", {}) or {}
        # 优先 application/json，回退第一个 media type
        json_content = content.get("application/json")
        if not json_content:
            for _mc in content.values():
                json_content = _mc
                break
        if json_content:
            schema = json_content.get("schema", {}) or {}
    else:
        for param in info.get("parameters", []) or []:
            if isinstance(param, dict) and param.get("in") == "body":
                schema = param.get("schema", {}) or {}
                break

    if schema:
        if "$ref" in schema:
            schema = _resolve_ref(schema["$ref"], spec)
        properties = schema.get("properties", {}) or {}
        required_keys = set(schema.get("required", []) or [])
        # schema 顶层 example（完整请求体示例对象）作为字段默认值回退源
        schema_example = schema.get("example")
        if not isinstance(schema_example, dict):
            schema_example = {}
        # v3 media type 级别的 example 也作为回退源
        media_example = json_content.get("example") if json_content else None
        if not isinstance(media_example, dict):
            media_example = {}
        for key, prop in properties.items():
            if key in seen_keys:
                continue
            if "$ref" in prop:
                prop = _resolve_ref(prop["$ref"], spec)
            field_type = _swagger_type_to_field_type(prop.get("type", "string"))
            # 默认值：property 自身 > schema 顶层 example[key] > media type example[key]
            default_value = _pick_default_value(prop)
            if default_value == "" and key in schema_example:
                default_value = schema_example[key]
            if default_value == "" and key in media_example:
                default_value = media_example[key]
            coerced = _coerce_default(default_value, field_type)
            # body 字段是请求体核心结构，无论是否有默认值都导入（默认值可空）；
            # query/path 等参数才适用"有默认值才导入"规则
            description = prop.get("description", "") or prop.get("title", "") or ""
            fields.append(schemas.ApiFieldIn(
                key=key,
                label=description,
                field_type=field_type,
                required=key in required_keys,
                default_value=coerced,
                remark=prop.get("description", ""),
                sort_order=sort_order,
            ))
            seen_keys.add(key)
            sort_order += 1

    return fields
