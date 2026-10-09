# -*- coding: utf-8 -*-
"""DBClient 无参数执行的 % 字面量回归测试（生产报告 912 根因）。

pymysql cursor.execute(sql, args) 在 args 非 None 时做 sql % args 格式化：
args=[] 会把 SQL 里的字面量 %（如 LIKE '%'）误当占位符，
报 not enough arguments for format string——SQL 根本没发到数据库。
"""
import pytest

from db.db_client import DBClient


class _FakeCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, args=None):
        self.calls.append((sql, args))

    def fetchall(self):
        return [{"pay_demand_id": 1}]


class _FakeConn:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.open = True

    def ping(self, reconnect=True):
        return None

    def cursor(self):
        return self.cursor_obj


@pytest.fixture()
def client():
    c = DBClient(host="h", port=1, user="u", password="p", database="d")
    c.conn = _FakeConn()
    return c


def test_query_no_args_passes_none(client):
    # 912 事故现场：LIKE CONCAT 里的字面量 %，引擎调用 query(sql) 不传参数
    sql = ("SELECT pay_demand_id FROM sys_pay_demand "
           "WHERE bl_nos LIKE CONCAT('%', 'BL20261009113513QSSE', '%') LIMIT 1")
    client.query(sql)
    assert client.conn.cursor_obj.calls == [(sql, None)]


def test_query_empty_list_passes_none(client):
    client.query("SELECT 1", [])
    assert client.conn.cursor_obj.calls[0][1] is None


def test_query_with_args_keeps_args(client):
    client.query("SELECT %s", ["a"])
    assert client.conn.cursor_obj.calls[0] == ("SELECT %s", ["a"])


def test_execute_no_args_passes_none(client):
    client.execute("UPDATE t SET remark='100%折扣'")
    assert client.conn.cursor_obj.calls == [("UPDATE t SET remark='100%折扣'", None)]
