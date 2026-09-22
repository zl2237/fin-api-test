# 存量用例变量池迁移（数据集模式一刀切）：
# 逐用例触发 sync_case_variable_pool —— 静态入参（编排字面量/接口默认值）拆叶入池
# + 清空转引用 + 动态 ${} 默认迁为节点引用。幂等，可重复执行。
#
# --force：统一收口——pre_process 静态字面量无视"键已在池"，以节点值为准
# 覆盖池值后清空节点（节点字面量当前实际生效，收口后行为不变）；
# 形状冲突/键不合法（如方括号）仍保留为手动覆盖并在 invalid/conflicts 报告。
#
# 用法：python scripts/migrate_variable_pools.py [project_id] [--force]
import sys

sys.path.insert(0, '.')
from dotenv import load_dotenv  # noqa: E402

load_dotenv('.env')
import app.path_setup  # noqa: F401,E402
from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.services.dataset_service import sync_case_variable_pool  # noqa: E402

FORCE = "--force" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]

db = SessionLocal()
q = db.query(models.TestCase)
if args:
    q = q.filter(models.TestCase.project_id == int(args[0]))
cases = q.all()
total_cols = 0
total_kept = total_invalid = 0
for case in cases:
    if getattr(case, "case_type", "normal") == "suite":
        continue
    try:
        stats = sync_case_variable_pool(db, case, user_id=case.created_by, force=FORCE)
    except Exception as e:
        print(f"[skip] case#{case.id} {case.name}: {e}")
        continue
    total_cols += stats["columns"]
    total_kept += stats["kept"]
    total_invalid += stats["invalid"]
    flags = [f"mode={'force' if FORCE else 'idempotent'}"]
    if stats["columns"]:
        flags.append(f"入池{stats['columns']}列")
    if stats["kept"]:
        flags.append(f"保留覆盖{stats['kept']}")
    if stats["dynamic"]:
        flags.append(f"动态{stats['dynamic']}")
    if stats["conflicts"]:
        flags.append(f"形状冲突{len(stats['conflicts'])}:{','.join(stats['conflicts'][:4])}")
    if stats["invalid"]:
        flags.append(f"键不合法{stats['invalid']}")
    print(f"case#{case.id:<4} {case.name}: {'；'.join(flags)}")
print(f"\n完成：{len(cases)} 个用例 | 收集 {total_cols} 列 | 保留 {total_kept} | 键不合法 {total_invalid}")
db.close()
