"""EnvTokenCache 单测：环境级共享 token 缓存（防乒乓互踢核心）。

覆盖：
- login_shared：并发只登录一次，等待者复用结果（锁登录不锁执行）
- refresh_shared：double-checked 条件重登——缓存已被他人刷新则复用，否则重登
- invalidate：清缓存
- get：无缓存返回 None
"""
import threading

import pytest

from app.services.token_cache import EnvTokenCache


@pytest.fixture(autouse=True)
def _reset_cache():
    """类级缓存，用例间必须清空隔离。"""
    EnvTokenCache._tokens.clear()
    yield
    EnvTokenCache._tokens.clear()


class TestGet:
    def test_no_cache_returns_none(self):
        assert EnvTokenCache.get(999) is None

    def test_after_login_returns_token(self):
        EnvTokenCache._tokens[1] = "T1"
        assert EnvTokenCache.get(1) == "T1"


class TestLoginShared:
    def test_first_login_caches(self):
        calls = []

        def do_login():
            calls.append(1)
            return "TOKEN"

        assert EnvTokenCache.login_shared(1, do_login) == "TOKEN"
        assert calls == [1]
        assert EnvTokenCache.get(1) == "TOKEN"

    def test_second_call_reuses_without_login(self):
        EnvTokenCache.login_shared(1, lambda: "T1")
        # 第二次：do_login 不应被调用
        assert EnvTokenCache.login_shared(1, lambda: (_ for _ in ()).throw(AssertionError("不应登录"))) == "T1"

    def test_concurrent_only_one_login(self):
        """8 线程并发登录同一环境：登录动作只发生一次，人人拿到同一 token。"""
        calls = []
        lock = threading.Lock()

        def do_login():
            with lock:
                calls.append(1)
            threading.Event().wait(0.05)  # 模拟登录耗时，放大竞争窗口
            return "SHARED"

        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()  # 尽量同时冲锁
            results.append(EnvTokenCache.login_shared(1, do_login))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(calls) == 1
        assert results == ["SHARED"] * 8

    def test_different_envs_independent(self):
        EnvTokenCache.login_shared(1, lambda: "A")
        assert EnvTokenCache.login_shared(2, lambda: "B") == "B"
        assert EnvTokenCache.get(1) == "A"
        assert EnvTokenCache.get(2) == "B"


class TestRefreshShared:
    def test_cache_refreshed_by_other_reuses_new(self):
        """乒乓消除关键路径：自己 token 失效，但缓存已被他人刷新 → 直接复用，不重登。"""
        EnvTokenCache._tokens[1] = "NEW"
        login_calls = []

        def do_login():
            login_calls.append(1)
            return "MINE"

        result = EnvTokenCache.refresh_shared(1, "OLD_STALE", do_login)
        assert result == "NEW"
        assert login_calls == []  # 未发生登录

    def test_cache_still_stale_relogs(self):
        """缓存仍是自己失效的 token → 真正重登并更新缓存。"""
        EnvTokenCache._tokens[1] = "STALE"
        result = EnvTokenCache.refresh_shared(1, "STALE", lambda: "FRESH")
        assert result == "FRESH"
        assert EnvTokenCache.get(1) == "FRESH"

    def test_no_cache_relogs(self):
        # 缓存被清空（如环境配置变更）→ 直接重登
        result = EnvTokenCache.refresh_shared(1, "OLD", lambda: "T")
        assert result == "T"
        assert EnvTokenCache.get(1) == "T"

    def test_concurrent_refresh_single_login(self):
        """多执行同时 401：第一个重登，其余复用——不会登录风暴。"""
        EnvTokenCache._tokens[1] = "STALE"
        calls = []

        def do_login():
            calls.append(1)
            threading.Event().wait(0.05)
            return "FRESH"

        results = []
        barrier = threading.Barrier(6)

        def worker():
            barrier.wait()
            results.append(EnvTokenCache.refresh_shared(1, "STALE", do_login))

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(calls) == 1
        assert results == ["FRESH"] * 6


class TestInvalidate:
    def test_clears_cache(self):
        EnvTokenCache._tokens[1] = "T1"
        EnvTokenCache.invalidate(1)
        assert EnvTokenCache.get(1) is None

    def test_missing_env_is_noop(self):
        EnvTokenCache.invalidate(404)  # 不应抛错
