"""
表达式引擎。

支持语法：
    ${order_id}                引用上下文中已提取的变量
    ${bl_no}
    ${env.base_url}            引用环境变量
    ${generate_bl_no()}        调用内置函数（无参）
    ${generate_bl_no(prefix='smoke')}   调用内置函数（带关键字参数）
    ${generate_unique_id()}
    ${now()}                   当前时间 ISO 字符串
    ${now(format='%Y-%m-%d')}  当前时间按指定格式
    ${timestamp()}             当前时间戳（秒）
    ${random_int(min=1, max=100)}     随机整数
    ${random_string(length=8)}         随机字符串（大小写字母+数字）
    ${uuid()}                  UUID 字符串
    ${upper(s='abc')}          转大写
    ${lower(s='ABC')}          转小写
    ${md5(s='abc')}            MD5 哈希
    ${date_add(days=1, format='%Y-%m-%d')}  当前日期加 N 天
    ${db.query_one('SELECT order_id FROM sys_order WHERE bl_no=...')}  执行SQL返回第一行dict
    ${db.query_value('SELECT order_id FROM ...', field='order_id')}    执行SQL返回标量
"""
import hashlib
import random
import re
import string
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Any, Dict

# 先把项目根目录加入 sys.path，再复用现有 utils
from .. import path_setup  # noqa: F401
from utils.generator_util import generate_bl_no, generate_unique_id, generate_invoice_number


def _parse_kwargs(args_str: str) -> Dict[str, Any]:
    """解析 key=value 形式的关键字参数，支持字符串与数字"""
    kwargs: Dict[str, Any] = {}
    for part in re.split(r",\s*(?![^']*['])", args_str.strip()):
        if not part.strip():
            continue
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        v = v.strip()
        if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
            kwargs[k] = v[1:-1]
        else:
            try:
                kwargs[k] = int(v)
            except ValueError:
                try:
                    kwargs[k] = float(v)
                except ValueError:
                    kwargs[k] = v
    return kwargs


def _strip_quotes(s: str) -> str:
    """去掉首尾配对的单引号或双引号"""
    s = s.strip()
    if len(s) >= 2 and ((s[0] == "'" and s[-1] == "'") or (s[0] == '"' and s[-1] == '"')):
        return s[1:-1]
    return s


def _now_func(**kwargs):
    """当前时间，支持 format 参数（strftime 格式），无参数时返回 ISO 字符串"""
    fmt = kwargs.get("format")
    if fmt:
        return datetime.now().strftime(fmt)
    return datetime.now().isoformat()


def _safe_int(val: Any, default: int = 0) -> int:
    """容错解析 int：_parse_kwargs 在数值参数后跟引号字符串参数时可能粘连，提取开头数字"""
    if isinstance(val, int):
        return val
    try:
        return int(val)
    except (ValueError, TypeError):
        m = re.match(r"-?\d+", str(val))
        return int(m.group()) if m else default


def _random_int_func(**kwargs):
    """随机整数，区间 [min, max]，默认 [0, 100]"""
    lo = _safe_int(kwargs.get("min", 0), 0)
    hi = _safe_int(kwargs.get("max", 100), 100)
    return random.randint(lo, hi)


def _random_string_func(**kwargs):
    """随机字符串（大小写字母+数字），默认长度 8"""
    length = _safe_int(kwargs.get("length", 8), 8)
    pool = string.ascii_letters + string.digits
    return "".join(random.choice(pool) for _ in range(length))


def _uuid_func(**kwargs):
    """UUID 字符串（小写带横杠）"""
    return str(_uuid.uuid4())


def _upper_func(**kwargs):
    """转大写"""
    return str(kwargs.get("s", "")).upper()


def _lower_func(**kwargs):
    """转小写"""
    return str(kwargs.get("s", "")).lower()


def _md5_func(**kwargs):
    """MD5 哈希"""
    return hashlib.md5(str(kwargs.get("s", "")).encode("utf-8")).hexdigest()


def _date_add_func(**kwargs):
    """当前日期加 N 天（默认 days=0），支持 format 参数指定输出格式"""
    days_raw = kwargs.get("days", 0)
    fmt = kwargs.get("format", "%Y-%m-%d")
    # 容错：_parse_kwargs 在"数值参数在前+引号字符串参数在后"时可能将 format 粘连到 days 值
    if isinstance(days_raw, str) and "format=" in days_raw:
        m = re.search(r"format=['\"]([^'\"]+)['\"]", days_raw)
        if m:
            fmt = m.group(1)
    days = _safe_int(days_raw, 0)
    return (datetime.now() + timedelta(days=days)).strftime(fmt)


class ExpressionEngine:
    def __init__(self, context: Dict[str, Any], db_client=None):
        self.context = context
        self.db_client = db_client
        self.functions = {
            "generate_bl_no": generate_bl_no,
            "generate_unique_id": generate_unique_id,
            "generate_invoice_number": generate_invoice_number,
            "now": _now_func,
            "timestamp": lambda **kw: int(datetime.now().timestamp()),
            "random_int": _random_int_func,
            "random_string": _random_string_func,
            "uuid": _uuid_func,
            "upper": _upper_func,
            "lower": _lower_func,
            "md5": _md5_func,
            "date_add": _date_add_func,
        }

    def evaluate(self, expr: Any) -> Any:
        """递归求值：支持字符串、字典、列表"""
        if isinstance(expr, str):
            return self._eval_str(expr)
        if isinstance(expr, dict):
            return {k: self.evaluate(v) for k, v in expr.items()}
        if isinstance(expr, list):
            return [self.evaluate(v) for v in expr]
        return expr

    def _eval_str(self, expr: str) -> Any:
        # 整串就是一个 ${...} 表达式 → 求值后返回原生类型（int/dict 等）；
        # 但未定义的变量（None）保留原占位符字符串，留给后续前置处理或下游节点注入
        if expr.startswith("${") and expr.endswith("}"):
            inner = expr[2:-1].strip()
            val = self._eval_inner(inner)
            if val is None:
                return expr
            return val

        # 字符串中内嵌多个 ${...} → 做字符串替换
        if "${" in expr:
            def repl(m):
                val = self._eval_inner(m.group(1).strip())
                # 未定义变量（None）保留原占位符，留给后续前置处理或后续节点注入；
                # 已求值的值替换为字符串（保持原行为）
                if val is None:
                    return m.group(0)
                return str(val)
            return re.sub(r"\$\{([^}]+)\}", repl, expr)
        return expr

    def _eval_inner(self, inner: str) -> Any:
        # ${name} 无前缀：从统一变量池取值（推荐写法）
        # 变量生命周期覆盖整个用例（环境全局定义 + 各节点后置提取），用例结束前不销毁
        # ${context.name}：兼容旧写法，等价于 ${name}
        if inner.startswith("context."):
            return self._resolve_path(self.context.get("extracted", {}), inner[len("context."):])
        # env.xxx → 从环境变量取值（env_vars 的原始副本，不含后置提取）
        if inner.startswith("env."):
            return self._resolve_path(self.context.get("env", {}), inner[len("env."):])
        # global.xxx
        if inner.startswith("global."):
            return self._resolve_path(self.context.get("global", {}), inner[len("global."):])
        # DB 函数：db.query_one(...) / db.query_value(...) / db.query(...)
        if inner.startswith("db."):
            return self._eval_db_func(inner)
        # 函数调用 name(...) 或 name()
        if "(" in inner and inner.endswith(")"):
            func_name = inner[:inner.index("(")]
            args_str = inner[inner.index("(") + 1:-1]
            if func_name in self.functions:
                kwargs = _parse_kwargs(args_str)
                try:
                    return self.functions[func_name](**kwargs)
                except TypeError:
                    return self.functions[func_name]()
        # 无前缀 ${name}：从统一变量池取值
        extracted = self.context.get("extracted", {})
        if inner in extracted:
            return extracted[inner]
        return expr_inner_marker(inner)

    # ---------- DB 函数 ----------
    def _eval_db_func(self, inner: str) -> Any:
        """执行 db.query_one / db.query_value / db.query 函数"""
        if not self.db_client:
            return None
        try:
            func_name = inner[:inner.index("(")]
            args_str = inner[inner.index("(") + 1:-1]
            kwargs = _parse_kwargs(args_str)
        except Exception:
            return None

        # 第一个位置参数视为 SQL（可能被当成 key=value 解析，需要兼容）
        sql = kwargs.get("sql") or kwargs.get("0")
        if not sql:
            # _parse_kwargs 把 'SELECT...' 当作 value 解析，但无 '='，被丢弃
            # 回退：直接取第一个逗号前的内容
            parts = re.split(r",\s*(?![^']*['])", args_str.strip(), maxsplit=1)
            sql = _strip_quotes(parts[0]) if parts else ""
            # 剩余部分解析 field=xxx
            if len(parts) > 1:
                for p in re.split(r",\s*(?![^']*['])", parts[1].strip()):
                    if "=" in p:
                        k, v = p.split("=", 1)
                        kwargs[k.strip()] = _strip_quotes(v)
        sql = _strip_quotes(sql)
        if not sql:
            return None

        # 注入上下文变量（${xxx}）
        sql = self._inject_vars(sql)

        try:
            rows = self.db_client.query(sql)
        except Exception:
            return None

        if func_name == "db.query":
            return rows or []
        if func_name == "db.query_one":
            return rows[0] if rows else None
        if func_name == "db.query_value":
            field = kwargs.get("field")
            if not rows:
                return None
            if field:
                return rows[0].get(field) if isinstance(rows[0], dict) else None
            # 未指定 field → 取第一行第一列
            if isinstance(rows[0], dict) and rows[0]:
                return next(iter(rows[0].values()))
            return None
        return None

    def _inject_vars(self, sql: str) -> str:
        """把 ${xxx} 替换为已提取变量值，字符串做防注入转义"""
        return inject_sql_vars(sql, self.context.get("extracted", {}))

    @staticmethod
    def _resolve_path(data: Any, path: str) -> Any:
        """按点号路径解析嵌套字典"""
        cur = data
        for k in path.split("."):
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return None
        return cur


def expr_inner_marker(inner: str) -> str:
    """未识别的表达式原样返回（保留 ${} 包裹，便于排查）"""
    return "${" + inner + "}"


# ============ SQL 变量注入（公共函数，消除三处重复） ============
_SQL_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def inject_sql_vars(sql: str, extracted: Dict[str, Any]) -> str:
    """把 ${xxx} 替换为已提取变量值，字符串做防注入转义。

    支持 ${context.xxx} / ${extracted.xxx} 前缀，等价于 ${xxx}。
    - 字符串值：用单引号包裹，内部单引号转义为两个单引号
    - None：转 NULL
    - 其他（int/float 等）：转 str
    - 未定义变量：m.group(0) 作为字符串返回（会被引号包裹）

    被 ExpressionEngine._inject_vars / Extractor._inject_vars /
    AssertionEngine._inject_extracted 共用，消除三份重复的转义逻辑。
    """
    def repl(m):
        key = m.group(1).strip()
        if key.startswith("context."):
            key = key[len("context."):]
        elif key.startswith("extracted."):
            key = key[len("extracted."):]
        val = extracted.get(key, m.group(0))
        if isinstance(val, str):
            return "'" + val.replace("'", "''") + "'"
        if val is None:
            return "NULL"
        return str(val)

    return _SQL_VAR_RE.sub(repl, sql)
