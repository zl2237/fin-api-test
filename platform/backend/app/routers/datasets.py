"""数据集路由：变量池的录入与管理入口。

单套语义：每个数据集 = 一套数据（按节点分组的入参配置见 params-view）。
服务层校验（dataset_service）抛 ValueError → 400 直给前端；
权限与项目内资源一致：登录即可管理，project_id 隔离由查询参数保证。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..services import dataset_service as svc

router = APIRouter(prefix="/api/datasets", tags=["数据集"])


def _fill_extra(db: Session, obj: models.DataSet) -> models.DataSet:
    """补齐列表/详情展示字段：审计名 + 被引用用例数"""
    crud.fill_audit_names(db, obj)
    setattr(obj, "case_bound_count", crud.count_cases_bound_to_dataset(db, obj.id))
    return obj


def _svc_call(fn, *args, **kwargs):
    """服务层 ValueError → 400（错误文案已面向用户）"""
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _get_or_404(db: Session, dataset_id: int) -> models.DataSet:
    obj = crud.get_dataset(db, dataset_id)
    if not obj:
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    return obj


def _ensure_owner_not_running(db: Session, obj: models.DataSet, what: str) -> None:
    """归属用例执行中 → 禁止改数据集（运行线程读的是库内值，保存会串版本）。"""
    if obj.case_id:
        from ..crud.executions import ensure_case_not_running
        _svc_call(ensure_case_not_running, db, obj.case_id, what)


@router.get("", response_model=list[schemas.DataSetOut])
def list_datasets(case_id: int | None = None, project_id: int | None = None, with_rows: bool = False,
                  db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """列表：按用例维度（case_id 必传语义，用例间隔离）；with_rows=1 时带行（详情页复用）"""
    q = db.query(models.DataSet)
    if case_id:
        q = q.filter(models.DataSet.case_id == case_id)
    if project_id:
        q = q.filter(models.DataSet.project_id == project_id)
    objs = q.order_by(models.DataSet.id.desc()).all()
    out = []
    for o in objs:
        if not with_rows:
            o.rows = []
        out.append(_fill_extra(db, o))
    return out


@router.post("", response_model=schemas.DataSetOut)
def create(data: schemas.DataSetCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    case = crud.get_testcase(db, data.case_id)
    if not case:
        raise HTTPException(404, f"用例不存在: {data.case_id}")
    if case.project_id != data.project_id:
        raise HTTPException(400, "project_id 与用例所属项目不一致")
    obj = _svc_call(svc.create_dataset, db, project_id=data.project_id, case_id=data.case_id,
                    name=data.name,
                    columns=[c.model_dump() for c in data.columns], user_id=user.id,
                    description=data.description)
    crud.log_operation(db, user, "create", "dataset", obj.id, obj.name)
    return _fill_extra(db, obj)


@router.post("/{dataset_id}/copy", response_model=schemas.DataSetOut)
def copy(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """复制数据集：列/单套值全量深拷贝，归属同用例（隔离语义下的复用方式）"""
    obj = _svc_call(svc.copy_dataset, db, dataset_id, user_id=user.id)
    crud.log_operation(db, user, "create", "dataset", obj.id, f"copy from #{dataset_id}")
    return _fill_extra(db, obj)


@router.get("/{dataset_id}", response_model=schemas.DataSetOut)
def get(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _fill_extra(db, _get_or_404(db, dataset_id))


@router.put("/{dataset_id}", response_model=schemas.DataSetOut)
def update(dataset_id: int, data: schemas.DataSetUpdate, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    obj = _get_or_404(db, dataset_id)
    obj = _svc_call(svc.update_dataset, db, dataset_id, name=data.name, description=data.description,
                    columns=[c.model_dump() for c in data.columns] if data.columns is not None else None)
    obj.updated_by = user.id
    db.commit()
    crud.log_operation(db, user, "update", "dataset", obj.id, obj.name)
    return _fill_extra(db, obj)


@router.delete("/{dataset_id}")
def delete(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = _get_or_404(db, dataset_id)
    _svc_call(svc.delete_dataset, db, dataset_id)
    crud.log_operation(db, user, "delete", "dataset", obj.id, obj.name)
    return {"message": "已删除"}


# ============ 变量池视图与单套值保存（每个数据集 = 一套数据） ============

@router.get("/{dataset_id}/params-view")
def params_view(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """按节点分组的入参视图（变量池界面数据源）：归属用例当前编排 × 接口字段 × 池值。

    manual=True 的参数为节点手动覆盖（编排非空值），池值不生效——展示覆盖值供解释。
    """
    _get_or_404(db, dataset_id)
    return _svc_call(svc.build_params_view, db, dataset_id)


@router.put("/{dataset_id}/values", response_model=schemas.DataSetOut)
def save_values(dataset_id: int, data: schemas.DataSetValuesSave, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """保存单套数据：values 即数据集唯一一套值；列定义随参数走（新键补列、悬空键剔除）。"""
    obj = _get_or_404(db, dataset_id)
    _ensure_owner_not_running(db, obj, "保存变量池")
    obj = _svc_call(svc.save_dataset_values, db, dataset_id, values=data.values,
                    user_id=user.id, column_types=data.column_types)
    crud.log_operation(db, user, "update", "dataset", dataset_id, f"save values ({len(data.values)} keys)")
    return _fill_extra(db, obj)


@router.put("/{dataset_id}/node-values")
def save_node_values(dataset_id: int, data: schemas.DataSetNodeValuesSave,
                     db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """保存节点级手动覆盖（节点页签编辑语义）：sets 写入该节点独有字面量（压过池值），
    clears 移除字面量回落池值；同字段跨节点异值靠此机制，池仍保持一键一值。"""
    obj = _get_or_404(db, dataset_id)
    _ensure_owner_not_running(db, obj, "保存节点参数")
    n = _svc_call(svc.save_node_values, db, dataset_id, node_id=data.node_id,
                  sets=data.sets, clears=data.clears)
    if n:
        crud.log_operation(db, user, "update", "dataset", dataset_id,
                           f"node values {data.node_id} ({n} params)")
    return {"message": "已保存", "touched": n}


@router.get("/{dataset_id}/merge-preview")
def merge_preview(dataset_id: int, source_dataset_id: int, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    """对比目标数据集（当前）与源数据集：按 api_id 配对相同节点，返回可覆盖列。

    common_nodes 为空 = 没有相同节点，无覆盖的必要（前端据此提示）。"""
    _get_or_404(db, dataset_id)
    _get_or_404(db, source_dataset_id)
    return _svc_call(svc.compare_datasets, db, dataset_id, source_dataset_id)


@router.post("/{dataset_id}/merge")
def merge_from(dataset_id: int, data: schemas.DataSetMergeRequest, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    """覆盖合并：源数据集指定行的相同节点涉及列值，刷到目标数据集全部行。"""
    _get_or_404(db, dataset_id)
    _get_or_404(db, data.source_dataset_id)
    result = _svc_call(svc.merge_from_dataset, db, dataset_id, data.source_dataset_id,
                       api_ids=data.api_ids, source_row_index=data.source_row_index or 1)
    crud.log_operation(db, user, "update", "dataset", dataset_id,
                       f"从数据集#{data.source_dataset_id}覆盖合并{result['columns']}列")
    return {"message": f"已覆盖 {result['columns']} 列", **result}
