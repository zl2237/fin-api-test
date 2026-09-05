import json
import time
from copy import deepcopy
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from .. import crud, models, path_setup, schemas  # noqa: F401
from ..auth import get_current_user
from ..database import get_db
from ..engine.curl_parser import parse_curl_to_previews
from ..engine.har_parser import parse_har_to_previews, previews_to_api_create
from ..services.request_sender import send_request
from ..services.spec_parser import extract_fields_from_spec, path_to_code

router = APIRouter(prefix="/api/apis", tags=["接口定义"])

# 注意：分组路由单独前缀，避免和 /api/apis/{api_id} 冲突
group_router = APIRouter(prefix="/api/api-groups", tags=["接口分组"])


# ============ 接口分组 ============
@group_router.post("", response_model=schemas.ApiGroupOut)
def create_group(data: schemas.ApiGroupCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.create_api_group(db, data)
    crud.log_operation(db, user, "create", "api_group", obj.id, obj.name)
    return obj


@group_router.get("", response_model=list[schemas.ApiGroupOut])
def list_groups(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return crud.list_api_groups(db, project_id)


@group_router.put("/{group_id}", response_model=schemas.ApiGroupOut)
def update_group(group_id: int, data: schemas.ApiGroupUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_api_group(db, group_id)
    if not obj:
        raise HTTPException(404, "接口分组不存在")
    obj = crud.update_api_group(db, obj, data)
    crud.log_operation(db, user, "update", "api_group", obj.id, obj.name)
    return obj


@group_router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_api_group(db, group_id)
    if not obj:
        raise HTTPException(404, "接口分组不存在")
    try:
        crud.delete_api_group(db, obj)
    except ValueError as e:
        # 组非空时阻止删除，前端提示用户先移走接口
        raise HTTPException(400, str(e))
    crud.log_operation(db, user, "delete", "api_group", obj.id, obj.name)
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


@router.get("/export")
def export_list(
    project_id: int,
    format: str = "excel",
    created_by: int | None = None,
    updated_by: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """接口列表导出：Excel 简表（人看）或 JSON 全量（备份/迁移），筛选条件与列表页一致。
    注意：此路由需在 /{api_id} 之前注册，否则 GET /export 会被 path 参数拦截。"""
    if format not in ("excel", "json"):
        raise HTTPException(400, "format 仅支持 excel / json")

    objs = crud.list_apis(db, project_id, created_by, updated_by)
    if not objs:
        raise HTTPException(400, "当前筛选条件下没有可导出的接口")
    crud.fill_audit_names_batch(db, objs)

    groups = crud.list_api_groups(db, project_id) if project_id else []
    group_names = {g.id: g.name for g in groups}
    project = crud.get_project(db, project_id)
    project_name = project.name if project else ""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    from ..services.export_service import export_apis_excel, export_apis_json
    # 审计在分支前统一记录（json 分支提前 return，放分支内会漏记）
    crud.log_operation(db, user, "export", "api", None, f"导出{len(objs)}个接口（{format}）")
    if format == "json":
        content = export_apis_json(objs, group_names, project_name)
        return Response(
            content=content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="apis_{stamp}.json"'},
        )
    content = export_apis_excel(objs, group_names)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="apis_{stamp}.xlsx"'},
    )


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
def batch_move(data: schemas.ApiBatchMove, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量移动接口到指定分组"""
    # 注意：此路由需在 /{api_id} 之前注册，否则会被 path 参数拦截
    updated = crud.batch_move_apis(db, data.api_ids, data.group_id)
    crud.log_operation(db, user, "update", "api", None, f"批量移动{updated}个接口")
    return {"message": f"已移动 {updated} 个接口", "updated": updated}


@router.post("/reorder")
def reorder(data: schemas.ApiReorderRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量重排序接口（组内拖拽排序）"""
    # 注意：此路由需在 /{api_id} 之前注册，否则会被 path 参数拦截
    items = [{"id": it.id, "sort_order": it.sort_order} for it in data.items]
    updated = crud.reorder_apis(db, items, user.id)
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
            code = info.get("operationId") or path_to_code(path, method)
            if crud.get_api_by_code(db, code):
                skipped.append(f"{method} {path}（编码 {code} 已存在）")
                continue

            # 解析请求参数（query/path/header）+ 请求体 schema -> 字段
            fields, is_array_body = extract_fields_from_spec(info, spec, is_v3)

            api_data = schemas.ApiCreate(
                project_id=data.project_id,
                group_id=data.group_id,
                name=name,
                code=code,
                method=method,
                path=path,
                description=info.get("description", ""),
                # 数组请求体用 [] 标记，build_request_body 据此组装为 [{...}]
                request_template=[] if is_array_body else {},
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


@router.post("/import-har/preview")
async def preview_har(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """上传 HAR 文件并返回接口预览列表，不落库。
    前端展示预览列表供用户勾选，勾选后调 /import-har 导入。"""
    if not file.filename or not file.filename.lower().endswith(".har"):
        raise HTTPException(400, "请上传 .har 文件")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50MB 上限
        raise HTTPException(400, "HAR 文件过大（超过 50MB）")

    try:
        har_data = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(400, f"HAR 文件解析失败：{e}")

    previews = parse_har_to_previews(har_data)
    return {"total": len(previews), "previews": previews}


@router.post("/import-har")
def import_har(
    data: schemas.HarImportRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """导入用户勾选的 HAR 接口预览项，落库。"""
    if not data.previews:
        raise HTTPException(400, "请至少勾选一个接口")

    # 收集已存在的 code，避免重复导入
    existing_codes: set = set()
    for preview in data.previews:
        method = preview.get("method", "GET").upper()
        path = preview.get("path", "")
        code = path_to_code(path, method)
        if crud.get_api_by_code(db, code):
            existing_codes.add(code)

    to_create, skipped = previews_to_api_create(
        data.previews, data.project_id, data.group_id, existing_codes
    )

    imported = []
    for api_data, preview in to_create:
        obj = crud.create_api(db, api_data, user.id)
        imported.append({
            "id": obj.id,
            "name": obj.name,
            "method": obj.method,
            "path": obj.path,
            "fields": len(api_data.fields),
        })

    crud.log_operation(db, user, "create", "api", None, f"HAR 导入{len(imported)}个接口")
    return {
        "message": f"已导入 {len(imported)} 个接口" + (f"，跳过 {len(skipped)} 个" if skipped else ""),
        "imported": imported,
        "skipped": skipped,
    }


@router.post("/import-curl/preview")
def preview_curl(
    data: schemas.CurlPreviewRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """解析 cURL 命令文本并返回接口预览列表，不落库。
    前端展示预览列表供用户勾选，勾选后调 /import-curl 导入。"""
    if not data.text or not data.text.strip():
        raise HTTPException(400, "请粘贴 cURL 命令")

    previews, errors = parse_curl_to_previews(data.text)
    return {"total": len(previews), "previews": previews, "errors": errors}


@router.post("/import-curl")
def import_curl(
    data: schemas.CurlImportRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """导入用户勾选的 cURL 接口预览项，落库。
    预览项结构与 HAR 完全一致，复用 previews_to_api_create 落库逻辑。"""
    if not data.previews:
        raise HTTPException(400, "请至少勾选一个接口")

    # 收集已存在的 code，避免重复导入
    existing_codes: set = set()
    for preview in data.previews:
        method = preview.get("method", "GET").upper()
        path = preview.get("path", "")
        code = path_to_code(path, method)
        if crud.get_api_by_code(db, code):
            existing_codes.add(code)

    to_create, skipped = previews_to_api_create(
        data.previews, data.project_id, data.group_id, existing_codes
    )

    imported = []
    for api_data, preview in to_create:
        obj = crud.create_api(db, api_data, user.id)
        imported.append({
            "id": obj.id,
            "name": obj.name,
            "method": obj.method,
            "path": obj.path,
            "fields": len(api_data.fields),
        })

    crud.log_operation(db, user, "create", "api", None, f"cURL 导入{len(imported)}个接口")
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

    fields, _is_array_body = extract_fields_from_spec(matched_info, spec, is_v3)
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
    登录、请求逻辑复用 runtime_service / body_builder，保证调试与实际执行行为一致。
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

    # 复用 runtime_service 的客户端构建与登录逻辑，保证调试行为与实际执行一致
    from ..services.body_builder import build_request_body, pop_file_fields_from_body
    from ..services.runtime_service import build_http_client, login
    client = build_http_client(env)
    try:
        try:
            login(client, env)
        except Exception as e:
            # login() 已包装"登录失败："前缀，此处只透传原文，避免双重前缀
            return _debug_response(api, method, {}, {}, 0, {"error": str(e)}, started_at, start_ts, login_failed=True)

        # 接口 headers_template 覆盖环境公共头（curl/HAR 导入的 Content-Type 在调试
        # 时同样生效，表单接口走表单编码——与 DAG 执行链路口径一致）
        client.headers = {**(client.headers or {}),
                          **(deepcopy(api.headers_template) or {})}

        # 构建请求体：body_override 优先，否则用 fields 组装
        if data.body_override is not None:
            body = deepcopy(data.body_override)
        else:
            body = build_request_body(api)

        # 剥离 file 类型字段：file 字段不参与 JSON body，单独组装到 multipart files
        body, file_fields = pop_file_fields_from_body(body, api)

        # 发送请求（与 DAG 执行同一实现：services.request_sender）
        req_timeout = getattr(env, "timeout", None) or 15
        status_code, response_data, error_msg = send_request(
            db, client, api, body, file_fields=file_fields, timeout=req_timeout
        )
        headers = deepcopy(client.headers or {})

        return _debug_response(api, method, headers, body, status_code, response_data, started_at, start_ts, error=error_msg)
    finally:
        try:
            if client.session:
                client.session.close()
        except Exception:
            pass


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
