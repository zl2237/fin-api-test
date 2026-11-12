"""notifier 模块单测：执行通知服务（单条 + 方案聚合，企微/邮件双渠道）。

用 mock 替换 WeComRobot 与 smtplib.SMTP_SSL，验证通知内容拼装、取数（执行人/
项目名、环境/数据集）与门控（webhook/email + enable_on_success/enable_on_failure
单点）逻辑，不触真实网络。
"""
import smtplib
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import utils.wecom_util  # noqa: F401  显式绑定子模块：utils 为命名空间包，不导入则 patch("utils.wecom_util.WeComRobot") 解析目标失败

from app import crud, models
from app.services.notifier import all_terminal, send_notify, send_plan_notify


def _env(name="测试环境", notify_config=None):
    return SimpleNamespace(name=name, notify_config=notify_config or {})


def _case(name="测试用例"):
    return SimpleNamespace(name=name)


def _record(status="success", summary=None, started_at=None, ended_at=None):
    return SimpleNamespace(
        status=status,
        summary=summary or {"passed": 3, "total": 3, "failed": 0},
        started_at=started_at,
        ended_at=ended_at,
        steps=[],  # 对齐 ExecutionRecord ORM：steps 关系属性恒存在（空表亦然）
    )


class _NullDb:
    """取数替身：query(Model).filter().first() 一律返回 None（执行人/项目名解析为空）"""

    def query(self, model):
        class _Q:
            def filter(self, *a, **kw):
                return self

            def first(self):
                return None
        return _Q()


DB = _NullDb()


def _name_db(user=None, project=None):
    """取数替身：query 按模型返回预置对象（执行人/项目名解析的正路径）"""
    results = {models.User: user, models.Project: project}

    class _Db:
        def query(self, model):
            class _Q:
                def filter(self, *a, **kw):
                    return self

                def first(self):
                    return results.get(model)
            return _Q()
    return _Db()


# 企微 webhook 配置（字段名与前端/数据库一致：wecom_webhook）
WEBHOOK_CFG = {
    "wecom_webhook": "http://fake/webhook",
    "enable_on_failure": True,
    "enable_on_success": True,
}


class TestSendNotify:
    def test_no_webhook_skips(self):
        env = _env(notify_config={})
        case = _case()
        record = _record()
        # 无 webhook → 不发通知，不抛异常
        send_notify(DB, env, case, record)

    def test_none_notify_config_skips(self):
        env = _env(notify_config=None)
        case = _case()
        record = _record()
        send_notify(DB, env, case, record)

    def test_success_notification_sent(self):
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case(name="下单流程")
        record = _record(status="success", summary={"passed": 5, "total": 5, "failed": 0})
        record.created_by = 9
        ended = datetime(2026, 1, 15, 10, 30, 0)
        record.ended_at = ended

        db = _name_db(user=SimpleNamespace(username="张三"))
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(db, env, case, record)
            MockRobot.assert_called_once_with("http://fake/webhook")
            mock_instance.send_markdown.assert_called_once()
            args = mock_instance.send_markdown.call_args
            title = args[0][0]
            content = args[0][1]
            assert title == "用例执行通知"
            assert "下单流程" in content
            assert "✅ 通过" in content
            assert "5/5" in content
            assert "测试环境" in content
            assert "张三" in content  # 执行人姓名由 notifier 查 User 表解析
            assert "2026-01-15 10:30:00" in content

    def test_executor_lookup_miss_renders_empty(self):
        """created_by 有值但查无此人 → 执行人行显示为空，不崩"""
        env = _env(notify_config=WEBHOOK_CFG)
        record = _record(status="success")
        record.created_by = 404
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(_name_db(), env, _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "> 执行人：\n" in content or content.endswith("> 执行人：")

    def test_failure_notification_sent(self):
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case(name="退款流程")
        record = _record(status="failed", summary={"passed": 2, "total": 3, "failed": 1})

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(DB, env, case, record)
            content = mock_instance.send_markdown.call_args[0][1]
            assert "❌ 失败" in content
            assert "退款流程" in content
            assert "2/3" in content

    def test_project_name_resolved_when_bound(self):
        """case 绑定项目 → notifier 查 Project 表得到项目名并插入「项目」行"""
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case(name="下单流程")
        case.project_id = 3
        record = _record(status="success")

        db = _name_db(project=SimpleNamespace(name="订单系统"))
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(db, env, case, record)
            content = mock_instance.send_markdown.call_args[0][1]
            assert "> 项目：订单系统" in content
            # 原有字段不丢失
            assert "> 环境：测试环境" in content
            assert "> 时间：" in content

    def test_project_line_absent_when_unbound(self):
        """未绑定项目（无 project_id）时不查询不输出「项目」行"""
        env = _env(notify_config=WEBHOOK_CFG)
        record = _record()

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(DB, env, _case(), record)
            content = mock_instance.send_markdown.call_args[0][1]
            assert "> 项目：" not in content
            assert "> 环境：测试环境" in content

    def test_duration_included_when_timestamps_present(self):
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case()
        started = datetime(2026, 1, 15, 10, 0, 0)
        ended = datetime(2026, 1, 15, 10, 0, 5)
        record = _record(status="success", started_at=started, ended_at=ended)

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(DB, env, case, record)
            content = mock_instance.send_markdown.call_args[0][1]
            assert "5.0s" in content

    def test_no_duration_when_timestamps_missing(self):
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case()
        record = _record(status="success", started_at=None, ended_at=None)

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(DB, env, case, record)
            content = mock_instance.send_markdown.call_args[0][1]
            assert "耗时" not in content

    def test_wecom_exception_swallowed(self):
        """WeComRobot 抛异常时 send_notify 不应传播异常"""
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case()
        record = _record()

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            MockRobot.return_value.send_markdown.side_effect = RuntimeError("网络不可达")
            # 不应抛出
            send_notify(DB, env, case, record)

    def test_none_summary_uses_defaults(self):
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case()
        # 直接构造 record，绕过 _record 的 summary 默认值
        record = SimpleNamespace(
            status="success", summary=None,
            started_at=None, ended_at=None,
        )

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(DB, env, case, record)
            content = mock_instance.send_markdown.call_args[0][1]
            # summary=None → record.summary or {} → 0/0
            assert "0/0" in content

    # ===== 开关判断（门控单点 _send_wecom）=====

    def test_success_skipped_when_enable_on_success_false(self):
        """成功但 enable_on_success=False → 不发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook", "enable_on_success": False, "enable_on_failure": True}
        record = _record(status="success")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=cfg), _case(), record)
            MockRobot.return_value.send_markdown.assert_not_called()

    def test_failure_skipped_when_enable_on_failure_false(self):
        """失败但 enable_on_failure=False → 不发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook", "enable_on_success": True, "enable_on_failure": False}
        record = _record(status="failed")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=cfg), _case(), record)
            MockRobot.return_value.send_markdown.assert_not_called()

    def test_failure_sent_when_enable_on_failure_true(self):
        """失败且 enable_on_failure=True → 发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook", "enable_on_success": False, "enable_on_failure": True}
        record = _record(status="failed")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=cfg), _case(), record)
            MockRobot.return_value.send_markdown.assert_called_once()

    def test_enable_on_failure_defaults_to_true(self):
        """未配 enable_on_failure 时，失败默认发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook"}
        record = _record(status="failed")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=cfg), _case(), record)
            MockRobot.return_value.send_markdown.assert_called_once()

    def test_enable_on_success_defaults_to_false(self):
        """未配 enable_on_success 时，成功默认不发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook"}
        record = _record(status="success")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=cfg), _case(), record)
            MockRobot.return_value.send_markdown.assert_not_called()

    # ===== 失败原因区块（_build_fail_section）=====

    @staticmethod
    def _failed_record(steps, summary=None):
        return SimpleNamespace(
            status="failed",
            summary=summary or {"passed": 0, "total": len(steps), "failed": len(steps)},
            started_at=None, ended_at=None,
            steps=steps,
        )

    @staticmethod
    def _failed_step(api_name, asserts=(), response_status=500, response_body=None):
        return SimpleNamespace(
            status="failed", api_name=api_name, node_id="n1",
            response_status=response_status, response_body=response_body,
            assertions=list(asserts),
        )

    @staticmethod
    def _failed_assert(message=None, result=False):
        return SimpleNamespace(
            result=result, message=message,
            rule_type="json_path_equals", expected_value="1", actual_value="2",
        )

    def test_fail_section_includes_step_and_assertion(self):
        step = self._failed_step("创建订单", [self._failed_assert("状态码应为200")])
        record = self._failed_record([step])
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=WEBHOOK_CFG), _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "**失败原因**" in content
            assert "创建订单" in content and "HTTP 500" in content
            assert "状态码应为200" in content

    def test_fail_section_assert_fallback_to_rule(self):
        """断言无 message 时回退到 rule_type+期望/实际"""
        step = self._failed_step("分发", [self._failed_assert(message="")])
        record = self._failed_record([step])
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=WEBHOOK_CFG), _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "json_path_equals" in content and "1" in content and "2" in content

    def test_fail_section_request_error_text(self):
        """无断言失败但响应体含 error → 提取「请求异常」"""
        step = self._failed_step("付款", asserts=[], response_status=0,
                                 response_body={"error": "ConnectTimeout: 连接超时"})
        record = self._failed_record([step])
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=WEBHOOK_CFG), _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "请求异常" in content and "连接超时" in content

    def test_fail_section_error_and_leftover_lines(self):
        step = self._failed_step("创建")
        record = self._failed_record([step], summary={
            "passed": 0, "total": 3, "failed": 1, "error": "DB 断连", "leftover": ["n2", "n3"],
        })
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=WEBHOOK_CFG), _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "执行异常：DB 断连" in content
            assert "未执行：2 个节点" in content

    def test_byte_budget_prevents_oversize(self):
        """极端失败信息（8 步 × 3 断言 × 500 字中文）下通知不超企微 4096 字节"""
        long_msg = "钱" * 500  # 1500 字节/条
        steps = [
            self._failed_step(f"接口{i}", [self._failed_assert(long_msg) for _ in range(3)])
            for i in range(8)
        ]
        record = self._failed_record(steps, summary={
            "passed": 0, "total": 8, "failed": 8, "error": "异" * 400,
        })
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=WEBHOOK_CFG), _case(name="名" * 100), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert len(content.encode("utf-8")) <= 4096
            assert "已截断" in content or "已省略" in content

    def test_success_has_no_fail_section(self):
        record = _record(status="success")
        record.steps = []
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(DB, _env(notify_config=WEBHOOK_CFG), _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "失败原因" not in content


# ===== 邮件渠道（_send_email：SMTP 打桩，不触网络） =====

EMAIL_CFG = {
    "smtp_host": "smtp.test.com",
    "smtp_port": 465,
    "use_ssl": True,
    "from_addr": "bot@test.com",
    "auth_code": "authcode123",
    "recipients": ["leader@corp.com", "qa@corp.com"],
    "enable_on_failure": True,
    "enable_on_success": True,
}


def _mime_body(payload: str) -> str:
    """MIMEText as_string 载荷 → 解码后的 HTML 正文（base64 CTE）。"""
    from email import message_from_string
    msg = message_from_string(payload)
    return msg.get_payload(decode=True).decode("utf-8")


class _FakeSMTP:
    """smtplib.SMTP_SSL 替身：记录构造/login/sendmail 参数"""
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.login_args = None
        self.sent = []
        _FakeSMTP.instances.append(self)

    def login(self, user, pwd):
        self.login_args = (user, pwd)

    def sendmail(self, from_addr, to, payload):
        self.sent.append((from_addr, list(to), payload))

    def quit(self):
        pass


class TestEmailChannel:
    def test_success_sent_via_ssl_with_login(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
        _FakeSMTP.instances.clear()
        cfg = dict(WEBHOOK_CFG)
        cfg["email"] = EMAIL_CFG
        record = _record(status="success", summary={"passed": 2, "total": 2, "failed": 0})
        started = datetime(2026, 1, 15, 10, 0, 0)
        record.started_at, record.ended_at = started, datetime(2026, 1, 15, 10, 0, 3)

        send_notify(DB, _env(notify_config=cfg), _case(name="邮件用例"), record)
        assert len(_FakeSMTP.instances) == 1
        inst = _FakeSMTP.instances[0]
        assert inst.host == "smtp.test.com" and inst.port == 465
        assert inst.login_args == ("bot@test.com", "authcode123")
        assert len(inst.sent) == 1
        from_addr, to, payload = inst.sent[0]
        assert from_addr == "bot@test.com"
        assert to == ["leader@corp.com", "qa@corp.com"]
        body = _mime_body(payload)
        assert "邮件用例" in body  # HTML 正文含用例名（base64 解码后）

    def test_skipped_when_config_incomplete(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
        _FakeSMTP.instances.clear()
        cfg = dict(WEBHOOK_CFG)
        cfg["email"] = {"smtp_host": "", "from_addr": "bot@test.com",
                        "recipients": ["a@b.com"]}  # 缺 host → 未配置
        send_notify(DB, _env(notify_config=cfg), _case(), _record())
        assert _FakeSMTP.instances == []

    def test_success_skipped_when_not_enabled(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
        _FakeSMTP.instances.clear()
        cfg = dict(WEBHOOK_CFG)
        cfg["email"] = {**EMAIL_CFG, "enable_on_success": False}
        send_notify(DB, _env(notify_config=cfg), _case(), _record(status="success"))
        assert _FakeSMTP.instances == []

    def test_failure_sent_by_default(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
        _FakeSMTP.instances.clear()
        cfg = {"email": {k: v for k, v in EMAIL_CFG.items()
                         if k not in ("enable_on_failure", "enable_on_success")}}
        send_notify(DB, _env(notify_config=cfg), _case(), _record(status="failed"))
        assert len(_FakeSMTP.instances) == 1  # 失败默认开

    def test_smtp_exception_swallowed(self, monkeypatch):
        class _Boom(_FakeSMTP):
            def login(self, user, pwd):
                raise RuntimeError("SMTP 认证失败")

        monkeypatch.setattr(smtplib, "SMTP_SSL", _Boom)
        cfg = dict(WEBHOOK_CFG)
        cfg["email"] = EMAIL_CFG
        # 不应抛出（_dispatch_channels 各渠道独立兜底）
        send_notify(DB, _env(notify_config=cfg), _case(), _record())

    def test_plain_smtp_when_ssl_off(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
        _FakeSMTP.instances.clear()
        cfg = {"email": {**EMAIL_CFG, "use_ssl": False,
                         "enable_on_success": True}}
        send_notify(DB, _env(notify_config=cfg), _case(), _record())
        assert len(_FakeSMTP.instances) == 1  # 走 SMTP（非 SSL）分支


# ===== 方案聚合通知（send_plan_notify / all_terminal） =====

def _plan_record(rid, case_id=1, env_id=1, status="success", trigger_type="plan",
                 summary=None, started=None, ended=None):
    return SimpleNamespace(
        id=rid, case_id=case_id, env_id=env_id, status=status,
        trigger_type=trigger_type, summary=summary or {},
        started_at=started, ended_at=ended, case_name=f"用例{case_id}",
    )


class _PlanDb:
    """方案聚合取数替身：records .filter().all()；plan/env 走 .get(id)。"""

    def __init__(self, records, plan=None, env_by_id=None):
        self._records = records
        self._plan = plan
        self._env_by_id = env_by_id or {}

    def query(self, model):
        parent = self
        kind = {models.ExecutionRecord: "rec", models.ExecutionPlan: "plan",
                models.Environment: "env"}.get(model)

        class _Q:
            def filter(self, *a, **kw):
                return self

            def all(self):
                return list(parent._records) if kind == "rec" else []

            def get(self, pk):
                if kind == "plan":
                    return parent._plan
                if kind == "env":
                    return parent._env_by_id.get(pk)
                return None
        return _Q()


@pytest.fixture(autouse=True)
def _no_fill_exec_names(monkeypatch):
    """send_plan_notify 内部延迟导入 crud.fill_exec_names——打桩为 no-op
    （测试记录已带 case_name，真实回填需 ORM 联表，不在单测范围）。"""
    monkeypatch.setattr(crud, "fill_exec_names", lambda db, objs: None)


class TestAllTerminal:
    def test_empty_is_not_terminal(self):
        assert all_terminal([]) is False

    def test_running_blocks(self):
        recs = [_plan_record(1, status="success"), _plan_record(2, status="running")]
        assert all_terminal(recs) is False

    def test_all_success(self):
        recs = [_plan_record(1), _plan_record(2)]
        assert all_terminal(recs) is True

    def test_terminated_is_terminal(self):
        assert all_terminal([_plan_record(1, status="terminated")]) is True


class TestSendPlanNotify:
    def _plan(self, name="冒烟方案", mode="chain"):
        return SimpleNamespace(name=name, mode=mode)

    def test_all_success_sends_one_summary(self):
        env = _env(notify_config=WEBHOOK_CFG)
        recs = [
            _plan_record(11, case_id=1, started=datetime(2026, 1, 15, 10, 0, 0),
                         ended=datetime(2026, 1, 15, 10, 0, 10)),
            _plan_record(12, case_id=2, ended=datetime(2026, 1, 15, 10, 0, 8)),
        ]
        db = _PlanDb(recs, plan=self._plan(), env_by_id={1: env})
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_plan_notify(db, 5, [11, 12])
            mock = MockRobot.return_value
            mock.send_markdown.assert_called_once()
            title, content = mock.send_markdown.call_args[0]
            assert title == "方案执行通知"
            assert "冒烟方案" in content
            assert "串行链" in content
            assert "✅ 全部通过" in content
            assert "2/0/0" in content  # 成功/失败/终止
            assert "方案定时" not in content
            assert "10.0s" in content  # 最早 start → 最晚 end

    def test_failures_listed_with_exec_id(self):
        env = _env(notify_config=WEBHOOK_CFG)
        recs = [
            _plan_record(21, case_id=1, trigger_type="plan_schedule"),
            _plan_record(22, case_id=2, status="failed",
                         summary={"error": "断言失败：金额应为 0.90 实际 6.3"}),
            _plan_record(23, case_id=3, status="failed"),
        ]
        db = _PlanDb(recs, plan=self._plan(name="回归链", mode="combo"),
                     env_by_id={1: env})
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_plan_notify(db, 5, [21, 22, 23])
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "❌ 存在失败" in content
            assert "用例2（#22）" in content and "断言失败" in content
            assert "用例3（#23）" in content
            assert "方案定时" in content  # trigger_type=plan_schedule 覆盖
            assert "并行组合" in content

    def test_dispatch_per_distinct_env(self):
        env1 = _env(name="环境A", notify_config=WEBHOOK_CFG)
        env2 = _env(name="环境B", notify_config=WEBHOOK_CFG)
        recs = [_plan_record(31, case_id=1, env_id=1),
                _plan_record(32, case_id=2, env_id=2)]
        db = _PlanDb(recs, plan=self._plan(), env_by_id={1: env1, 2: env2})
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_plan_notify(db, 5, [31, 32])
            # 两个环境各发一条（同一 webhook 构造两次）
            assert MockRobot.call_count == 2
            assert MockRobot.return_value.send_markdown.call_count == 2

    def test_deleted_plan_falls_back_to_id(self):
        env = _env(notify_config=WEBHOOK_CFG)
        recs = [_plan_record(41)]
        db = _PlanDb(recs, plan=None, env_by_id={1: env})
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_plan_notify(db, 77, [41])
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "已删除方案 #77" in content

    def test_no_channels_no_env_silent(self):
        recs = [_plan_record(51)]  # 环境已删（env_by_id 空）
        db = _PlanDb(recs, plan=self._plan(), env_by_id={})
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_plan_notify(db, 5, [51])  # 不抛异常、不发企微
            MockRobot.return_value.send_markdown.assert_not_called()

    def test_terminated_counts_as_failure_event(self):
        env = _env(notify_config={**WEBHOOK_CFG, "enable_on_success": True,
                                  "enable_on_failure": False})
        recs = [_plan_record(61), _plan_record(62, status="terminated")]
        db = _PlanDb(recs, plan=self._plan(), env_by_id={1: env})
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_plan_notify(db, 5, [61, 62])
            # 终止 ⇒ 失败事件；该环境失败通知已关 ⇒ 不发
            MockRobot.return_value.send_markdown.assert_not_called()

    def test_plan_notify_email_channel(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
        _FakeSMTP.instances.clear()
        env = _env(notify_config={"email": EMAIL_CFG})
        recs = [_plan_record(71), _plan_record(72, case_id=2, status="failed")]
        db = _PlanDb(recs, plan=self._plan(name="邮件冒烟"), env_by_id={1: env})
        send_plan_notify(db, 5, [71, 72])
        assert len(_FakeSMTP.instances) == 1
        _, _, payload = _FakeSMTP.instances[0].sent[0]
        body = _mime_body(payload)
        assert "邮件冒烟" in body and "用例2" in body
