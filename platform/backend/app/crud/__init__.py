"""crud 包：按域组织的数据访问与业务规则模块。

迁移策略：
- 原平铺 crud.py 已移至 legacy.py，所有旧函数从这里 re-export 保持兼容；
- 各域逻辑逐步迁移为子模块（如 users / executions），router 逐步改用域模块；
- 新代码一律写域模块，不往 legacy.py 加内容。
"""
from .datasets import (  # noqa: F401  数据集域（数据驱动测试）
    count_cases_bound_to_dataset,
    get_dataset,
    get_row,
    list_datasets,
    list_rows,
)
from .legacy import *  # noqa: F401,F403  兼容期：旧引用 from app import crud; crud.xxx 继续可用
from .legacy import (  # noqa: F401  显式 re-export
    fill_audit_names_batch as fill_audit_names_batch,
    log_operation as log_operation,
)
from .versions import (  # noqa: F401  项目版本域（快照/diff/回滚，自 legacy 整族迁出）
    build_project_snapshot,
    create_project_version,
    delete_project_version,
    diff_project_versions,
    fill_version_audit_names,
    get_project_version,
    list_project_versions,
    rollback_project_version,
)
