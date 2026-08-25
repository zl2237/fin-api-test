"""数据集路由：数据驱动测试的录入与管理入口。

服务层校验（dataset_service）抛 ValueError → 400 直给前端；
权限与项目内资源一致：登录即可管理，project_id 隔离由查询参数保证。
导入（Excel/CSV）接口在周期 3 补充。
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..services import dataset_service as svc

router = APIRouter(prefix="/api/datasets", tags=["数据集"])


def _fill_extra(db: Session, obj: models.DataSet) -> models.DataSet:
    """补齐列表/详情展示字段：审计名 + 被引用用例数；node_configs NULL 兜底为 []（响应 schema 要求 list）"""
    if obj.node_configs is None:
        obj.node_configs = []
    crud.fill_audit_names(db, obj)
    obj.case_bound_count = crud.count_cases_bound_to_dataset(db, obj.id)
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


@router.post("/generate")
def generate_from_case(data: schemas.DataSetGenerateIn, db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)):
    """从用例生成数据集：写死请求参数各成一列 + 1 行原值快照（绑定即生效，改值即参数化）。

    返回 stats 说明收集结果（列数/冲突跳过字段/动态与嵌套计数），前端据此提示。
    """
    if not crud.get_testcase(db, data.case_id):
        raise HTTPException(404, f"用例不存在: {data.case_id}")
    ds, stats = _svc_call(svc.generate_dataset_from_case, db, case_id=data.case_id,
                          name=data.name, user_id=user.id)
    crud.log_operation(db, user, "create", "dataset", ds.id, f"generate from case#{data.case_id}")
    return {"dataset": _fill_extra(db, ds), "stats": stats}


@router.post("/{dataset_id}/copy", response_model=schemas.DataSetOut)
def copy(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """复制数据集：列/行/节点配置快照全量深拷贝，归属同用例（隔离语义下的复用方式）"""
    obj = _svc_call(svc.copy_dataset, db, dataset_id, user_id=user.id)
    crud.log_operation(db, user, "create", "dataset", obj.id, f"copy from #{dataset_id}")
    return _fill_extra(db, obj)


@router.post("/{dataset_id}/resync")
def resync(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """重新同步节点配置快照：用例当前编排整块替换进数据集（列/行数据不动）"""
    _get_or_404(db, dataset_id)
    n = _svc_call(svc.resync_node_configs, db, dataset_id)
    crud.log_operation(db, user, "update", "dataset", dataset_id, f"resync {n} node configs")
    return {"message": f"已重新同步 {n} 个节点的配置快照", "nodes": n}


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


# ============ 行操作 ============

@router.get("/{dataset_id}/rows", response_model=list[schemas.DataSetRowOut])
def list_rows(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    _get_or_404(db, dataset_id)
    return crud.list_rows(db, dataset_id)


@router.post("/{dataset_id}/rows", response_model=schemas.DataSetRowOut)
def add_row(dataset_id: int, data: schemas.DataSetRowCreate, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    _get_or_404(db, dataset_id)
    row = _svc_call(svc.add_row, db, dataset_id, data=data.data)
    crud.log_operation(db, user, "update", "dataset", dataset_id, f"add row#{row.row_index}")
    return row


@router.put("/{dataset_id}/rows", response_model=list[schemas.DataSetRowOut])
def replace_rows(dataset_id: int, data: schemas.DataSetRowsReplace, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    """批量保存（表格整页保存语义）：整体替换，row_index 后端重排"""
    _get_or_404(db, dataset_id)
    rows = _svc_call(svc.replace_rows, db, dataset_id, rows_data=data.rows)
    crud.log_operation(db, user, "update", "dataset", dataset_id, f"replace {len(rows)} rows")
    return rows


@router.delete("/{dataset_id}/rows")
def clear_rows(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    _get_or_404(db, dataset_id)
    _svc_call(svc.clear_rows, db, dataset_id)
    crud.log_operation(db, user, "update", "dataset", dataset_id, "clear rows")
    return {"message": "已清空"}


@router.post("/{dataset_id}/rows/{row_id}/copy", response_model=schemas.DataSetRowOut)
def copy_row(dataset_id: int, row_id: int, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    """复制行：原行数据追加为新行（row_index 顺延），便于改少数字段快速造近似数据"""
    _get_or_404(db, dataset_id)
    row = _svc_call(svc.copy_row, db, dataset_id, row_id)
    crud.log_operation(db, user, "update", "dataset", dataset_id, f"copy row#{row_id}")
    return row


@router.put("/{dataset_id}/rows/{row_id}", response_model=schemas.DataSetRowOut)
def update_row(dataset_id: int, row_id: int, data: schemas.DataSetRowCreate, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    _get_or_404(db, dataset_id)
    return _svc_call(svc.update_row, db, dataset_id, row_id, data=data.data)


@router.delete("/{dataset_id}/rows/{row_id}")
def delete_row(dataset_id: int, row_id: int, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    _get_or_404(db, dataset_id)
    _svc_call(svc.delete_row, db, dataset_id, row_id)
    crud.log_operation(db, user, "update", "dataset", dataset_id, f"delete row#{row_id}")
    return {"message": "已删除"}


@router.post("/{dataset_id}/import")
async def import_rows(dataset_id: int, file: UploadFile = File(...), preview: bool = False,
                      db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Excel/CSV 导入：首行表头映射列 key。preview=1 只解析返回预览不落库。

    落库为整体替换语义（与表格整页保存一致）：当前行全部丢弃、以导入内容重排。
    """
    obj = _get_or_404(db, dataset_id)
    content = await file.read()
    rows, warnings = _svc_call(svc.parse_import_file, file.filename, content, obj.columns or [])
    if preview:
        return {"preview": True, "count": len(rows), "rows": rows, "warnings": warnings}
    saved = _svc_call(svc.replace_rows, db, dataset_id, rows_data=rows)
    crud.log_operation(db, user, "import", "dataset", dataset_id, f"{file.filename} → {len(saved)} rows")
    return {"preview": False, "count": len(saved), "warnings": warnings}
