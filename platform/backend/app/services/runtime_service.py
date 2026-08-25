"""运行时服务：构建 HTTP 客户端与登录，供 DagExecutor / 接口调试 / 环境登录测试复用。

从 DagExecutor._build_http_client / _login 提取，消除路由层对 DagExecutor 私有方法的
依赖及 _DummyCase 占位对象的重复定义。行为与原 DagExecutor 实现完全一致。
"""
import time
from copy import deepcopy
from typing import Any

from jsonpath_ng import parse as jsonpath_parse
from jsonpath_ng.exceptions import JsonPathParserError
from utils.http_client import HttpClient

from .. import path_setup  # noqa: F401  确保 utils 可导入
from .token_cache import EnvTokenCache


def _extract_by_jsonpath(data: Any, path: str) -> Any:
    try:
        matches = jsonpath_parse(path).find(data)
        return matches[0].value if matches else None
    except JsonPathParserError:
        # jsonpath 语法错误（如路径写错）
        return None
    except (IndexError, KeyError, TypeError, AttributeError):
        # 数据结构不匹配：取值越界 / 字段缺失 / 类型不支持
        return None


def build_http_client(env) -> HttpClient:
    """按 env 构建 HttpClient：base_url + common_headers（空则用默认 JSON 头）。"""
    client = HttpClient(base_url=env.base_url)
    client.headers = deepcopy(env.common_headers or {}) or {"Content-Type": "application/json"}
    return client


def login(client: HttpClient, env) -> None:
    """按 env.login_config 配置登录并注册 token 刷新回调；未配置则跳过。

    - 登录时带占位鉴权头跳过验证码校验，成功后用真实 token 覆盖
    - 首次登录失败抛 RuntimeError（上层统一捕获记为执行失败）
    - 注册 401 自动重登回调：回调内失败返回 None，不抛出以免污染调用方控制流

    token 共享模式（login_config.token_share_mode，默认 shared）：
    - shared：环境级共享 token（EnvTokenCache）。同环境并行执行复用一次登录，
      401 时条件重登（已被他人刷新则直接复用），消除单会话系统下的乒乓互踢
    - isolated：每执行独立登录（原行为）。多会话系统用，保留每执行独立 session
    """
    login_cfg: dict[str, Any] = env.login_config or {}
    login_path = login_cfg.get("login_path", "/api/home/login/userLogin")
    login_body = login_cfg.get("login_body")
    token_jsonpath = login_cfg.get("token_jsonpath", "$.data.token")
    auth_header_name = login_cfg.get("auth_header_name", "Authorization")
    # 鉴权头值模板：支持 ${token} 和 ${timestamp} 占位符
    # 默认 ${token}（直接注入）；可配为 Bearer ${token}、${token}_${timestamp} 等
    auth_header_value_template = login_cfg.get("auth_header_value_template") or "${token}"
    # token 共享模式：shared 默认（单会话系统防乒乓），isolated 保留独立登录
    share_mode = login_cfg.get("token_share_mode", "shared")
    if not login_body:
        return

    def _build_header_value(token: str) -> str:
        """按模板渲染鉴权头值"""
        return (auth_header_value_template
                .replace("${token}", str(token))
                .replace("${timestamp}", str(int(time.time()))))

    def _do_login():
        # 登录时带任意 Authorization 头跳过验证码校验，登录成功后会被真实 token 覆盖
        client.set_header(auth_header_name, "skip-captcha-placeholder")
        resp = client.post(login_path, json=login_body)
        return _extract_by_jsonpath(resp, token_jsonpath)

    def _apply_token(token) -> None:
        if token:
            client.set_header(auth_header_name, _build_header_value(token))

    # 跟踪当前使用的裸 token（refresh 时识别 stale；嵌套函数写回需容器）
    current = {"token": None}

    if share_mode == "isolated":
        # 原行为：独立登录 + 独立刷新，token 不进共享缓存
        try:
            current["token"] = _do_login()
            _apply_token(current["token"])
        except Exception as e:
            raise RuntimeError(f"登录失败：{e}") from e

        def refresh():
            try:
                current["token"] = _do_login()
                _apply_token(current["token"])
                return current["token"]
            except Exception as e:
                print(f"[token刷新] 重新登录失败（忽略）: {e}")
                return None

        client.set_token_refresh_callback(refresh)
        return

    # ---- shared 模式：环境级共享 token ----
    cached = EnvTokenCache.get(env.id)
    if cached:
        # 其他执行已登录过：直接复用，零登录请求
        current["token"] = cached
        _apply_token(cached)
    else:
        # 首个执行：加锁登录一次入缓存；并发到达者等待后直接复用结果
        try:
            token = EnvTokenCache.login_shared(env.id, _do_login)
        except Exception as e:
            raise RuntimeError(f"登录失败：{e}") from e
        current["token"] = token
        _apply_token(token)

    def refresh():
        # 401 条件重登：缓存 token 已被其他执行刷新则直接复用新值（不登录），
        # 仅当缓存仍是自己失效的那个 token 时才真正重登，消除乒乓互踢
        try:
            stale = current["token"]
            if stale is None:
                return None
            token = EnvTokenCache.refresh_shared(env.id, stale, _do_login)
            current["token"] = token
            _apply_token(token)
            return token
        except Exception as e:
            print(f"[token刷新] 重新登录失败（忽略）: {e}")
            return None

    client.set_token_refresh_callback(refresh)


def build_db_client(env):
    """按 env.db_config 构建 DBClient；未配置 host 或导入/初始化失败时返回 None（降级无 DB 模式）。

    从 DagExecutor._build_db_client 提取，与 build_http_client 对称，统一运行时资源构建。
    DBClient 构造不建连（self.conn=None），实际连接在 query 时懒建立。
    """
    cfg = env.db_config or {}
    if not cfg.get("host"):
        return None
    # 延迟导入，避免无 DB 环境启动报错
    try:
        from db.db_client import DBClient
        return DBClient(
            host=cfg.get("host"),
            port=int(cfg.get("port", 3306)),
            user=cfg.get("user", ""),
            password=cfg.get("password", ""),
            database=cfg.get("database", ""),
        )
    except ImportError as e:
        # db_client 模块缺失（精简部署），降级为无 DB 模式
        print(f"[DBClient] 导入失败，跳过 DB 能力: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        # 配置项缺失或类型错误
        print(f"[DBClient] 配置异常，跳过 DB 能力: {e}")
        return None
    except Exception as e:
        # 连接失败等运行时异常
        print(f"[DBClient] 初始化失败，跳过 DB 能力: {e}")
        return None
