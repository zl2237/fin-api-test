"""内置函数注册表（来源2 的执行核；函数集自旧表达式引擎注册表化迁出）。

定案（2026-09-30）：
- 函数仅由参数来源2（UI 下拉选择）调用，禁止手输完整表达式
- 函数入参允许引用上游变量/本节点 SQL 参数（args 里 {"kind": "ref"}），
  由 param_resolver 逐参求值后按关键字传入
- 旧 ${db.query_*} 数据库函数废止：SQL 取数由来源4（参数级标量 SQL）承接
"""
import hashlib
import json
import random
import re
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
    "generate_invoice_number": {"fn": generate_invoice_number, "params": ["prefix"]},
    "now": {"fn": lambda **kw: datetime.now().strftime(kw["format"]) if kw.get("format")
            else datetime.now().isoformat(), "params": ["format"]},
    "timestamp": {"fn": lambda **kw: int(datetime.now().timestamp()) + int(kw.get("offset", 0)),
                  "params": ["offset"]},
    # 13 位毫秒时间戳（offset 仍为秒，与 timestamp 语义一致）：
    # 供对接方要求毫秒级时间戳的接口（如海关 requestTime，±5 分钟窗口）
    "timestamp_ms": {"fn": lambda **kw: int(datetime.now().timestamp() * 1000)
                     + int(kw.get("offset", 0) or 0) * 1000,
                     "params": ["offset"]},
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
    # 两段拼接（a + sep + b）：常量容器内嵌后可把上游 id 拼业务后缀，
    # 如 concat(a=引用 customer_finance_id, b='_CustomerFinance')
    "concat": {"fn": lambda **kw: kw.get("sep", "").join(
                   "" if kw.get(k) is None else str(kw.get(k)) for k in ("a", "b")),
               "params": ["a", "b", "sep"]},
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


# ---- 函数调用语法解析（调试链路的示例值/覆写值求值用） ----------------------
# 字段示例值或调试 body 覆写里写 `函数名(参数...)`，发送前求值（2026-11-13）。
# 仅函数名已注册才认领，其余一律原样发送——未注册名/含括号的普通业务串不误伤。
# 执行链路取值以数据集入参（func spec）为准，不经过本解析器，两条口径互不影响。
_FUNC_CALL_RE = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)\s*$", re.DOTALL)
_IDENT_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def _split_call_args(raw: str) -> list[str]:
    """顶层逗号切分（引号内的逗号不切）。"""
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in raw:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("\"", "'"):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p for p in (s.strip() for s in parts) if p]


def _parse_call_scalar(raw: str) -> Any:
    """参数值先按 JSON 解析（数字/布尔/null/带引号串），失败按裸文本（%Y-%m-%d 等）。"""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _top_level_eq(part: str) -> int:
    """引号外第一个 = 的位置；无则 -1（值里带 = 的不误判为关键字参数）。"""
    quote: str | None = None
    for i, ch in enumerate(part):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("\"", "'"):
            quote = ch
        elif ch == "=":
            return i
    return -1


def parse_function_call(text: Any) -> dict[str, Any] | None:
    """`函数名(参数...)` 字符串 → {"func": 名, "kwargs": {...}}；其余 → None。

    - 关键字参数：timestamp_ms(offset=60)、now(format=%Y-%m-%d)
    - 位置参数按 FUNCTIONS 声明顺序补位：timestamp_ms(60) ≡ offset=60；
      已被关键字占用的形参跳过
    - 引号内逗号/等号不切分：concat(a="x,y", b=2)、md5(s="a=b")
    """
    if not isinstance(text, str):
        return None
    m = _FUNC_CALL_RE.match(text)
    if not m:
        return None
    name, raw_args = m.group(1), m.group(2).strip()
    if name not in FUNCTIONS:
        return None
    kwargs: dict[str, Any] = {}
    positional: list[Any] = []
    for part in _split_call_args(raw_args):
        eq = _top_level_eq(part)
        key = part[:eq].strip() if eq > 0 else ""
        if key and _IDENT_RE.fullmatch(key):
            kwargs[key] = _parse_call_scalar(part[eq + 1:].strip())
        else:
            positional.append(_parse_call_scalar(part))
    for pname, val in zip(FUNCTIONS[name]["params"], positional):
        kwargs.setdefault(pname, val)
    return {"func": name, "kwargs": kwargs}
