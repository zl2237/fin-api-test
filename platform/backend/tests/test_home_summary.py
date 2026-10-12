# -*- coding: utf-8 -*-
"""home_summary（工作台聚合）单测：多形态查询按首实参路由的 fake db。

覆盖：
- 计数（接口/用例）与 stats 聚合透传
- 最近执行行元组 → HomeRecentExecOut 映射（env 名补齐、状态/时间原样）
- 快速执行候选（最近执行过用例去重）映射
- days 越界 400
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import models
from app.routers.home import home_summary


class _Col:
    """列对象假：支持 .desc()（order_by 链）"""

    def desc(self):
        return self


class _Chain:
    """万能查询链：终态方法由构造注入（scalar/all），中间方法全自返"""

    def __init__(self, result):
        self._result = result

    def filter(self, *a):
        return self

    def join(self, *a, **kw):
        return self

    def with_entities(self, *a):
        return self

    def group_by(self, *a):
        return self

    def order_by(self, *a):
        return self

    def limit(self, n):
        return self

    def all(self):
        return self._result

    def scalar(self):
        return self._result

    def subquery(self):
        return SimpleNamespace(c=SimpleNamespace(case_id=_Col(), mid=_Col()))


class HomeDb:
    """按 query 首实参路由：count 聚合 / stats / 最近执行 / 环境名 / 快速执行候选"""

    def __init__(self, *, api_count=0, case_count=0, statuses=(),
                 recent_rows=(), env_rows=(), recent_case_rows=()):
        self.api_count = api_count
        self.case_count = case_count
        self.statuses = list(statuses)
        self.recent_rows = list(recent_rows)
        self.env_rows = list(env_rows)
        self.recent_case_rows = list(recent_case_rows)

    def query(self, *entities, **kw):
        first = entities[0]
        # count 聚合：func.count(api_definitions.id / test_cases.id)
        s = str(first)
        if s.startswith("count("):
            if "api_definitions" in s:
                return _Chain(self.api_count)
            if "test_cases" in s:
                return _Chain(self.case_count)
        # stats：ORM 实体查询（aggregate_stats 内部）
        if first is models.ExecutionRecord:
            from collections import Counter
            return _Chain(list(Counter(self.statuses).items()))
        # 最近执行：首列 ExecutionRecord.id（7 列元组）
        if first is models.ExecutionRecord.id:
            return _Chain(self.recent_rows)
        # 快速执行候选子查询：首列 ExecutionRecord.case_id
        if first is models.ExecutionRecord.case_id:
            return _Chain([])  # subquery() 链，行集不消费
        # 候选用例名 / 环境名：首列对应模型主键列
        if first is models.Environment.id:
            return _Chain(self.env_rows)
        if first is models.TestCase.id:
            return _Chain(self.recent_case_rows)
        raise AssertionError(f"未预期的查询形态: {s}")


class TestHomeSummary:
    def test_counts_stats_and_recent_execs_mapping(self):
        from datetime import datetime

        t1, t2 = datetime(2026, 10, 12, 16, 0), datetime(2026, 10, 12, 15, 0)
        db = HomeDb(api_count=225, case_count=41,
                    statuses=["success", "success", "failed"],
                    recent_rows=[
                        (11, 7, "对账用例", 2, "success", {"total": 17, "passed": 17}, t1),
                        (10, 8, "核销用例", None, "failed", {"total": 3, "passed": 1}, t2),
                    ],
                    env_rows=[(2, "预发")])
        out = home_summary(project_id=1, days=7, db=db, user=SimpleNamespace())

        assert out.api_count == 225
        assert out.case_count == 41
        assert (out.stats.count, out.stats.passed, out.stats.rate, out.stats.days) == (3, 2, 67, 7)
        assert [e.id for e in out.recent_execs] == [11, 10]
        e0 = out.recent_execs[0]
        assert (e0.case_name, e0.env_id, e0.env_name, e0.status) == ("对账用例", 2, "预发", "success")
        assert e0.summary == {"total": 17, "passed": 17}
        assert e0.started_at == t1
        # env_id 为空的行 env_name 补 None（不查环境表也不炸）
        assert out.recent_execs[1].env_name is None

    def test_recent_cases_mapping(self):
        db = HomeDb(recent_case_rows=[(7, "对账用例"), (8, "核销用例")])
        out = home_summary(project_id=1, db=db, user=SimpleNamespace())
        assert [(c.id, c.name) for c in out.recent_cases] == [(7, "对账用例"), (8, "核销用例")]

    def test_days_out_of_range_rejected(self):
        for bad in (0, 366):
            with pytest.raises(HTTPException) as ei:
                home_summary(project_id=1, days=bad, db=HomeDb(), user=SimpleNamespace())
            assert ei.value.status_code == 400
