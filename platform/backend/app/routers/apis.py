from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from copy import deepcopy
from datetime import datetime
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
    crud.delete_api(db, obj)
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


@router.post("/import")
def import_apis(data: schemas.ApiImportRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """从 Swagger/OpenAPI JSON 导入接口定义，自动生成字段"""
    spec = data.spec or {}
    # 兼容 OpenAPI 3.0 和 Swagger 2.0
    is_v3 = "openapi" in spec
    paths = spec.get("paths", {})
    # schema 定义位置：v3 在 components.schemas，v2 在 definitions
    schemas_map = spec.get("components", {}).get("schemas", {}) if is_v3 else spec.get("definitions", {})

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

            # 解析请求体 schema -> 字段
            fields = _extract_fields_from_spec(info, schemas_map, is_v3)

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

        # 发送请求
        try:
            if method == "GET":
                resp = client.get(api.path, params=body, timeout=15)
            else:
                resp = client.post(api.path, json=body, timeout=15)
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


def _resolve_ref(ref: str, schemas_map: dict) -> dict:
    """解析 $ref 引用，返回 schema dict"""
    if not ref:
        return {}
    # #/components/schemas/OrderCreate 或 #/definitions/OrderCreate
    parts = ref.lstrip("#/").split("/")
    cur = {"components": {"schemas": schemas_map}, "definitions": schemas_map}
    for p in parts:
        if p in ("components", "schemas", "definitions"):
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


def _extract_fields_from_spec(info: dict, schemas_map: dict, is_v3: bool) -> list:
    """从 OpenAPI/Swagger 的操作定义中提取请求体字段"""
    fields = []
    sort_order = 0

    schema = None
    if is_v3:
        # OpenAPI 3.0: requestBody.content.application/json.schema
        request_body = info.get("requestBody", {})
        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
    else:
        # Swagger 2.0: parameters 里 in=body 的 schema
        for param in info.get("parameters", []):
            if param.get("in") == "body":
                schema = param.get("schema", {})
                break

    if not schema:
        return fields

    # 解析 $ref
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], schemas_map)

    properties = schema.get("properties", {})
    required_keys = set(schema.get("required", []))

    for key, prop in properties.items():
        if "$ref" in prop:
            prop = _resolve_ref(prop["$ref"], schemas_map)
        field_type = _swagger_type_to_field_type(prop.get("type", "string"))
        # 默认值：优先 default，回退 example（多数 Swagger 文档用 example 提供示例值）
        default_value = prop.get("default")
        if default_value is None:
            default_value = prop.get("example", "")
        if default_value is None:
            default_value = ""
        # array/object 类型默认值用 JSON
        if field_type in ("array", "object") and default_value and not isinstance(default_value, str):
            import json
            default_value = json.dumps(default_value, ensure_ascii=False)

        fields.append(schemas.ApiFieldIn(
            key=key,
            label=prop.get("description", "") or prop.get("title", ""),
            field_type=field_type,
            required=key in required_keys,
            default_value=str(default_value) if default_value != "" else "",
            remark=prop.get("description", ""),
            sort_order=sort_order,
        ))
        sort_order += 1

    return fields
