"""datasets 域：数据集/数据行的数据访问与业务规则（数据驱动测试）。

服务层（services/dataset_service.py）做校验与编排，本模块只做纯落库；
与 executions 域同分工。
"""

from sqlalchemy.orm import Session

from .. import models


def get_dataset(db: Session, dataset_id: int) -> models.DataSet | None:
    return db.query(models.DataSet).filter(models.DataSet.id == dataset_id).first()


def list_datasets(db: Session, project_id: int) -> list[models.DataSet]:
    return (db.query(models.DataSet)
            .filter(models.DataSet.project_id == project_id)
            .order_by(models.DataSet.id)
            .all())


def get_row(db: Session, row_id: int) -> models.DataSetRow | None:
    return db.query(models.DataSetRow).filter(models.DataSetRow.id == row_id).first()


def list_rows(db: Session, dataset_id: int) -> list[models.DataSetRow]:
    return (db.query(models.DataSetRow)
            .filter(models.DataSetRow.dataset_id == dataset_id)
            .order_by(models.DataSetRow.row_index)
            .all())


def count_cases_bound_to_dataset(db: Session, dataset_id: int) -> int:
    """绑定该数据集的用例数（删除数据集前的引用校验）"""
    return (db.query(models.TestCase)
            .filter(models.TestCase.dataset_id == dataset_id)
            .count())
