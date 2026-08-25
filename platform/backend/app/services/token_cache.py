"""环境级 token 共享缓存：单会话目标系统的防乒乓方案。

背景：单会话系统（同账号后登录踢前登录）下，多个并行执行各自登录会互相顶失效，
401 自动重登再互踢，形成"乒乓互踢"——用例随机失败 + 登录接口被轰炸。
且此类系统同一账号在服务端本就只有一份 session 数据，独立登录买不到数据隔离。

方案：锁登录，不锁执行——
- 首个执行：加锁登录一次，token 入缓存（env_id → token），后续执行直接复用
- 请求全程并行，只有登录瞬间串行
- 遇 401：条件重登（double-checked）——缓存 token 已被他人刷新则直接复用新 token，
  只有缓存 token 仍是自己失败用的那个才真正重登，彻底消除乒乓

降级：login_config.token_share_mode = "isolated" 时走原独立登录行为（多会话系统用，
保留每执行独立 session）。默认 shared。

边界：缓存仅在进程内（与 APScheduler 同一单进程部署假设）；多 worker 部署时
退化为每 worker 各自缓存——仍无乒乓（同 worker 内共享），只是多登几次。
"""
import threading
from collections import defaultdict
from collections.abc import Callable


class EnvTokenCache:
    """环境级 token 缓存（线程安全，进程内）"""

    _locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
    _tokens: dict[int, str] = {}

    @classmethod
    def get(cls, env_id: int) -> str | None:
        """取缓存 token（无则 None），读无需加锁（GIL 下 dict 读原子）"""
        return cls._tokens.get(env_id)

    @classmethod
    def login_shared(cls, env_id: int, do_login: Callable[[], str]) -> str:
        """加锁登录：并发到达时只有第一个真正登录，其余等待者直接复用结果"""
        with cls._locks[env_id]:
            token = cls._tokens.get(env_id)
            if token:
                return token
            token = do_login()
            cls._tokens[env_id] = token
            return token

    @classmethod
    def refresh_shared(cls, env_id: int, stale_token: str, do_login: Callable[[], str]) -> str:
        """401 条件重登：token 已被他人刷新则复用新值，仅当缓存仍是失效 token 时才重登"""
        with cls._locks[env_id]:
            current = cls._tokens.get(env_id)
            if current and current != stale_token:
                return current
            token = do_login()
            cls._tokens[env_id] = token
            return token

    @classmethod
    def invalidate(cls, env_id: int) -> None:
        """清除环境缓存（环境登录配置变更时调用，避免旧 token 残留）"""
        with cls._locks[env_id]:
            cls._tokens.pop(env_id, None)
