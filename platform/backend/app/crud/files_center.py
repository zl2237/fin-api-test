"""文件中心域：批量删除（多条件组合，复用单删引用计数语义）。

自 UI 平台同款移植（2026-10-29）：与单删同一语义——ref_count-1，归零才清物理文件。"""
from sqlalchemy.orm import Session

from .. import models, schemas
from .legacy import delete_file


def query_files_for_batch(db: Session, data: schemas.FileBatchDeleteRequest) -> list[models.TestFile]:
    """批量删除候选查询：项目强约束 + 条件 AND 组合（至少一个条件由路由层校验）。"""
    q = db.query(models.TestFile).filter(models.TestFile.project_id == data.project_id)
    if data.ids:
        q = q.filter(models.TestFile.id.in_(data.ids))
    if data.category_id is not None:
        q = q.filter(models.TestFile.category_id == data.category_id)
    if data.name_contains:
        q = q.filter(models.TestFile.name.like(f"%{data.name_contains}%"))
    if data.content_type_prefix:
        q = q.filter(models.TestFile.content_type.like(f"{data.content_type_prefix}%"))
    if data.created_by is not None:
        q = q.filter(models.TestFile.created_by == data.created_by)
    if data.created_after is not None:
        q = q.filter(models.TestFile.created_at >= data.created_after)
    if data.created_before is not None:
        q = q.filter(models.TestFile.created_at <= data.created_before)
    return q.order_by(models.TestFile.id).all()


def batch_delete_files(db: Session, rows: list[models.TestFile]) -> dict:
    """逐条删除（ref_count-1，归零才删物理），与单删同一语义；返回统计与待清理物理路径。"""
    deleted = 0
    physical_paths: list[str] = []
    for obj in rows:
        storage_path = obj.storage_path
        removed = delete_file(db, obj)
        deleted += 1
        if removed:
            physical_paths.append(storage_path)
    return {"deleted": deleted, "physical_paths": physical_paths}
