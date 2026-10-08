"""内置函数注册表（来源2 的执行核，从旧 expression.py 函数集注册表化迁出）。

定案（2026-09-30）：
- 函数仅由参数来源2（UI 下拉选择）调用，禁止手输完整表达式
- 函数入参允许引用上游变量/本节点 SQL 参数（args 里 {"kind": "ref"}），
  由 param_resolver 逐参求值后按关键字传入
- 旧 ${db.query_*} 数据库函数废止：SQL 取数由来源4（参数级标量 SQL）承接
"""
import hashlib
import random
import string
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Any, Callable

from .. import path_setup  # noqa: F401  先把项目根加入 sys.path，再复用现有 utils
from utils.generator_util import generate_bl_no, generate_invoice_number, generate_unique_id

# 函数元数据：参数名列表（供前端下拉渲染入参表单与保存校验）
FUNCTIONS: dict[str, dict[str, Any]] = {
    "generate_bl_no": {"fn": generate_bl_no, "params": ["prefix"]},
    "generate_unique_id": {"fn": generate_unique_id, "params": []},
    "generate_invoice_number": {"fn": generate_invoice_number, "params": []},
    "now": {"fn": lambda **kw: datetime.now().strftime(kw["format"]) if kw.get("format")
            else datetime.now().isoformat(), "params": ["format"]},
    "timestamp": {"fn": lambda **kw: int(datetime.now().timestamp()), "params": []},
    "random_int": {"fn": lambda **kw: random.randint(int(kw.get("min", 0)), int(kw.get("max", 100))),
                   "params": ["min", "max"]},
    "random_string": {"fn": lambda **kw: "".join(random.choice(string.ascii_letters + string.digits)
                                                 for _ in range(int(kw.get("length", 8)))),
                      "params": ["length"]},
    "uuid": {"fn": lambda **kw: str(_uuid.uuid4()), "params": []},
    "upper": {"fn": lambda **kw: str(kw.get("s", "")).upper(), "params": ["s"]},
    "lower": {"fn": lambda **kw: str(kw.get("s", "")).lower(), "params": ["s"]},
    "md5": {"fn": lambda **kw: hashlib.md5(str(kw.get("s", "")).encode("utf-8")).hexdigest(),
            "params": ["s"]},
    "date_add": {"fn": lambda **kw: (
        # base 缺省当前时间；可传上游日期（如 ref 引用应收汇日期）做偏移基准
        (datetime.fromisoformat(str(kw["base"])) if kw.get("base") else datetime.now())
        + timedelta(days=int(kw.get("days", 0)))
    ).strftime(kw.get("format", "%Y-%m-%d")),
                 "params": ["base", "days", "format"]},
}


def call_function(name: str, kwargs: dict[str, Any]) -> Any:
    """按关键字调用内置函数；未知函数名抛 ValueError（保存时校验兜底，运行时防御）。"""
    meta = FUNCTIONS.get(name)
    if not meta:
        raise ValueError(f"未知的内置函数：{name}")
    fn: Callable = meta["fn"]
    return fn(**kwargs) if kwargs else fn()
