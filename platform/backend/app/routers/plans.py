"""执行方案路由：方案的 CRUD、成员整替与一键执行（内嵌定时的调度同步后续接入）。

方案=执行配置组合（成员独立并行）；权限与用例一致（登录即可管理）。
成员用例删除由 DB 级联清行（case_id ondelete=CASCADE），换绑数据集悬空不炸——
详情接口标 dataset_missing，执行预检会给出精确指引。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..crud.plans import get_plan, list_plans
from ..database import get_db
from ..services import plan_executor

router = APIRouter(prefix="/api/plans", tags=["执行方案"])

# 与 executions 路由的并发上限一致（批次线程池 max_workers 封顶）
MAX_CONCURRENCY = 16


def _get_or_404(db: Session, plan_id: int) -> models.ExecutionPlan:
    obj = get_plan(db, plan_id)
    if not obj:
        raise HTTPException(404, "执行方案不存在")
    return obj


def _fill_item(db: Session, item: models.ExecutionPlanItem) -> schemas.PlanItemOut:
    """成员展示回填：case/数据集实时值 + 悬空标记（不炸、标红交前端）。

    dataset_id 为空 = 沿用用例自身绑定（前端显示「用例绑定」，不在此展开——
    绑定随时可改，展开即成过期快照）。
    """
    case = crud.get_testcase(db, item.case_id)
    dataset_name = None
    dataset_missing = False
    if item.dataset_id is not None:
        ds = crud.get_dataset(db, item.dataset_id)
        if ds:
            dataset_name = ds.name
        else:
            dataset_missing = True
    return schemas.PlanItemOut(
        id=item.id, case_id=item.case_id,
        dataset_id=item.dataset_id,
        run_count=item.run_count, sort_order=item.sort_order,
        case_name=case.name if case else f"# {item.case_id}",
        case_type=getattr(case, "case_type", "normal") if case else None,
        dataset_name=dataset_name,
        case_missing=case is None, dataset_missing=dataset_missing)


def _fill_detail(db: Session, obj: models.ExecutionPlan) -> schemas.ExecutionPlanDetailOut:
    crud.fill_audit_names(db, obj)
    items = [_fill_item(db, it) for it in sorted(obj.items, key=lambda x: x.sort_order)]
    out = schemas.ExecutionPlanDetailOut.model_validate(obj, from_attributes=True)
    out.item_count = len(items)
    out.items = items
    return out


@router.get("", response_model=list[schemas.ExecutionPlanOut])
def list_all(project_id: int | None = None, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    """方案列表（新→旧）：item_count 数据库端聚合，next_run_at 由调度器回写"""
    objs = list_plans(db, project_id)
    for o in objs:
        crud.fill_audit_names(db, o)
    return objs


@router.post("", response_model=schemas.ExecutionPlanDetailOut)
def create(data: schemas.ExecutionPlanCreate, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    if not 1 <= data.concurrency <= MAX_CONCURRENCY:
        raise HTTPException(400, f"并发数须在 1~{MAX_CONCURRENCY} 之间")
    if data.project_id is not None and not crud.get_project(db, data.project_id):
        raise HTTPException(404, "项目不存在")
    if not data.name.strip():
        raise HTTPException(400, "方案名称不能为空")

    obj = models.ExecutionPlan(
        project_id=data.project_id, name=data.name.strip(), description=data.description,
        concurrency=data.concurrency, created_by=user.id, updated_by=user.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    crud.log_operation(db, user, "create", "plan", obj.id, obj.name)
    return _fill_detail(db, obj)


@router.get("/{plan_id}", response_model=schemas.ExecutionPlanDetailOut)
def get_one(plan_id: int, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    return _fill_detail(db, _get_or_404(db, plan_id))


@router.put("/{plan_id}", response_model=schemas.ExecutionPlanDetailOut)
def update(plan_id: int, data: schemas.ExecutionPlanUpdate, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    """基础字段局部更新（内嵌定时配置的调度同步后续接入）"""
    obj = _get_or_404(db, plan_id)
    if data.name is not None:
        if not data.name.strip():
            raise HTTPException(400, "方案名称不能为空")
        obj.name = data.name.strip()
    if data.description is not None:
        obj.description = data.description
    if data.concurrency is not None:
        if not 1 <= data.concurrency <= MAX_CONCURRENCY:
            raise HTTPException(400, f"并发数须在 1~{MAX_CONCURRENCY} 之间")
        obj.concurrency = data.concurrency
    if data.enabled is not None:
        obj.enabled = data.enabled

    obj.updated_by = user.id
    db.commit()
    db.refresh(obj)
    crud.log_operation(db, user, "update", "plan", obj.id, obj.name)
    return _fill_detail(db, obj)


@router.put("/{plan_id}/items", response_model=schemas.ExecutionPlanDetailOut)
def replace_items(plan_id: int, data: schemas.PlanItemsReplaceIn,
                  db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    """成员整体替换（对齐套件 members PUT 语义）：先全量校验再删旧插新，sort_order 按提交序重排"""
    obj = _get_or_404(db, plan_id)
    try:
        plan_executor.validate_plan_items(db, data.items)
    except ValueError as e:
        raise HTTPException(400, str(e))

    db.query(models.ExecutionPlanItem).filter(
        models.ExecutionPlanItem.plan_id == obj.id).delete(synchronize_session=False)
    for i, it in enumerate(data.items):
        db.add(models.ExecutionPlanItem(
            plan_id=obj.id, case_id=it.case_id, dataset_id=it.dataset_id,
            run_count=it.run_count,
            sort_order=i))
    obj.updated_by = user.id
    db.commit()
    db.refresh(obj)
    crud.log_operation(db, user, "update", "plan", obj.id, f"{obj.name} 成员×{len(data.items)}")
    return _fill_detail(db, obj)


@router.post("/{plan_id}/execute", response_model=list[schemas.ExecutionRecordOut])
def execute(plan_id: int, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    """一键执行方案：先全量预检（任一成员不可执行 → 400、零记录），
    再逐成员发射（成员独立并行，concurrency=方案配置），返回本次全部记录供轮询"""
    obj = _get_or_404(db, plan_id)
    try:
        records = plan_executor.run_plan(db, obj, user.id, trigger_type="plan")
    except ValueError as e:
        raise HTTPException(400, str(e))
    crud.log_operation(db, user, "execute", "plan", obj.id, obj.name)
    return records


@router.delete("/{plan_id}", response_model=schemas.MessageOut)
def delete(plan_id: int, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    obj = _get_or_404(db, plan_id)
    name = obj.name
    db.delete(obj)  # items 级联（delete-orphan）；执行记录 plan_id 无外键、历史存活
    db.commit()
    crud.log_operation(db, user, "delete", "plan", obj.id, name)
    return {"message": "已删除"}
