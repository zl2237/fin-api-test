from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, path_setup, schemas  # noqa: F401
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/api/environments", tags=["环境"])


@router.post("", response_model=schemas.EnvironmentOut)
def create(data: schemas.EnvironmentCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.create_environment(db, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "create", "environment", obj.id, obj.name)
    return obj


@router.get("", response_model=list[schemas.EnvironmentOut])
def list_all(project_id: int | None = None, created_by: int | None = None, updated_by: int | None = None, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    objs = crud.list_environments(db, project_id, created_by, updated_by)
    crud.fill_audit_names_batch(db, objs)
    return objs


@router.get("/{env_id}", response_model=schemas.EnvironmentOut)
def get_one(env_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_environment(db, env_id)
    if not obj:
        raise HTTPException(404, "环境不存在")
    crud.fill_audit_names(db, obj)
    return obj


@router.put("/{env_id}", response_model=schemas.EnvironmentOut)
def update(env_id: int, data: schemas.EnvironmentUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_environment(db, env_id)
    if not obj:
        raise HTTPException(404, "环境不存在")
    obj = crud.update_environment(db, obj, data, user.id)
    # 登录配置可能变更：失效共享 token 缓存，下次执行重新登录
    from ..services.token_cache import EnvTokenCache
    EnvTokenCache.invalidate(env_id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "update", "environment", obj.id, obj.name)
    return obj


@router.delete("/{env_id}")
def delete(env_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_environment(db, env_id)
    if not obj:
        raise HTTPException(404, "环境不存在")
    # 清理共享 token 缓存与该环境的定时任务（先移 job——remove_by_env 需查业务行取 id，再删业务行）
    from ..services.scheduler import scheduler_service
    from ..services.token_cache import EnvTokenCache
    EnvTokenCache.invalidate(env_id)
    scheduler_service.remove_by_env(env_id)
    db.query(models.TestSchedule).filter(models.TestSchedule.env_id == env_id).delete()
    db.commit()
    crud.delete_environment(db, obj)
    crud.log_operation(db, user, "delete", "environment", obj.id, obj.name)
    return {"message": "已删除"}


@router.post("/reorder")
def reorder(data: schemas.EnvironmentReorderRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    items = [{"id": it["id"], "sort_order": it["sort_order"]} for it in data.items]
    updated = crud.reorder_environments(db, items, user.id)
    return {"message": f"已更新 {updated} 个环境排序", "updated": updated}


@router.post("/{env_id}/copy", response_model=schemas.EnvironmentOut)
def copy(env_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_environment(db, env_id)
    if not obj:
        raise HTTPException(404, "环境不存在")
    new_obj = crud.copy_environment(db, obj)
    new_obj.created_by = user.id
    new_obj.updated_by = user.id
    db.commit()
    db.refresh(new_obj)
    crud.fill_audit_names(db, new_obj)
    crud.log_operation(db, user, "copy", "environment", new_obj.id, new_obj.name)
    return new_obj


@router.post("/{env_id}/test-db")
def test_db(env_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """
    测试数据库连接：按 env 已保存的 db_config 尝试连接并执行 SELECT 1。
    DBClient 构建方式与 runtime_service.build_db_client 一致，但此处需显式报告连接错误，
    故直接构造而非使用 build_db_client（其失败时静默返回 None）。
    """
    env = crud.get_environment(db, env_id)
    if not env:
        raise HTTPException(404, "环境不存在")
    cfg = env.db_config or {}
    if not cfg.get("host"):
        return {"ok": False, "message": "未配置数据库 host，跳过测试"}

    try:
        from db.db_client import DBClient
        client = DBClient(
            host=cfg.get("host"),
            port=int(cfg.get("port", 3306)),
            user=cfg.get("user", ""),
            password=cfg.get("password", ""),
            database=cfg.get("database", ""),
        )
        # 执行简单查询验证连接
        result = client.query("SELECT 1 AS test")
        client.close()
        return {
            "ok": True,
            "message": f"连接成功：{cfg.get('host')}:{cfg.get('port', 3306)}/{cfg.get('database', '')}",
            "test_result": result,
        }
    except Exception as e:
        return {"ok": False, "message": f"连接失败：{e}"}


@router.post("/{env_id}/test-login")
def test_login(env_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """
    测试登录配置：按 env 已保存的 login_config 尝试登录并提取 token。
    复用 runtime_service 的 build_http_client + login 逻辑，保证测试与实际执行行为一致。
    """
    env = crud.get_environment(db, env_id)
    if not env:
        raise HTTPException(404, "环境不存在")
    login_cfg = env.login_config or {}
    if not login_cfg.get("login_body"):
        return {"ok": False, "message": "未配置登录请求体，跳过测试"}

    # 复用 runtime_service 的登录逻辑
    from ..services.runtime_service import build_http_client, login

    try:
        client = build_http_client(env)
        try:
            login(client, env)
            # session 模式：无鉴权头可回显，改为展示已保持的 Cookie
            if (login_cfg.get("login_mode") or "token") == "session":
                cookie_names = [c.name for c in client.session.cookies]
                preview = ", ".join(cookie_names[:5]) or "无"
                return {
                    "ok": True,
                    "message": f"登录成功（session 模式），已保持 {len(cookie_names)} 个 Cookie：{preview}",
                    "base_url": env.base_url,
                }
            # 登录成功，提取实际注入的鉴权头
            auth_header_name = login_cfg.get("auth_header_name", "Authorization")
            auth_value = client.headers.get(auth_header_name, "")
            # 脱敏：只返回前20字符
            masked = auth_value[:20] + "..." if len(auth_value) > 20 else auth_value
            return {
                "ok": True,
                "message": f"登录成功，token 已注入到 {auth_header_name} 头",
                "auth_header_name": auth_header_name,
                "auth_header_preview": masked,
                "base_url": env.base_url,
            }
        finally:
            try:
                if client.session:
                    client.session.close()
            except Exception:
                pass
    except Exception as e:
        # login() 已包装"登录失败："前缀，此处不再重复
        return {"ok": False, "message": str(e)}
