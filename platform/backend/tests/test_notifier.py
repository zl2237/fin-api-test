"""notifier 模块单测：执行通知服务（企微通知）。

用 mock 替换 WeComRobot，验证通知内容拼装与异常吞掉逻辑，
不触真实网络。行为与原 DagExecutor._send_notify 完全一致。
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from app.services.notifier import send_notify


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
    )


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
        send_notify(env, case, record)

    def test_none_notify_config_skips(self):
        env = _env(notify_config=None)
        case = _case()
        record = _record()
        send_notify(env, case, record)

    def test_success_notification_sent(self):
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case(name="下单流程")
        record = _record(status="success", summary={"passed": 5, "total": 5, "failed": 0})
        ended = datetime(2026, 1, 15, 10, 30, 0)
        record.ended_at = ended

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(env, case, record)
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
            assert "2026-01-15 10:30:00" in content

    def test_failure_notification_sent(self):
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case(name="退款流程")
        record = _record(status="failed", summary={"passed": 2, "total": 3, "failed": 1})

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(env, case, record)
            content = mock_instance.send_markdown.call_args[0][1]
            assert "❌ 失败" in content
            assert "退款流程" in content
            assert "2/3" in content

    def test_duration_included_when_timestamps_present(self):
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case()
        started = datetime(2026, 1, 15, 10, 0, 0)
        ended = datetime(2026, 1, 15, 10, 0, 5)
        record = _record(status="success", started_at=started, ended_at=ended)

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(env, case, record)
            content = mock_instance.send_markdown.call_args[0][1]
            assert "5.0s" in content

    def test_no_duration_when_timestamps_missing(self):
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case()
        record = _record(status="success", started_at=None, ended_at=None)

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(env, case, record)
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
            send_notify(env, case, record)

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
            send_notify(env, case, record)
            content = mock_instance.send_markdown.call_args[0][1]
            # summary=None → record.summary or {} → 0/0
            assert "0/0" in content

    # ===== 开关判断测试 =====

    def test_success_skipped_when_enable_on_success_false(self):
        """成功但 enable_on_success=False → 不发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook", "enable_on_success": False, "enable_on_failure": True}
        env = _env(notify_config=cfg)
        case = _case()
        record = _record(status="success")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(env, case, record)
            MockRobot.return_value.send_markdown.assert_not_called()

    def test_failure_skipped_when_enable_on_failure_false(self):
        """失败但 enable_on_failure=False → 不发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook", "enable_on_success": True, "enable_on_failure": False}
        env = _env(notify_config=cfg)
        case = _case()
        record = _record(status="failed")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(env, case, record)
            MockRobot.return_value.send_markdown.assert_not_called()

    def test_failure_sent_when_enable_on_failure_true(self):
        """失败且 enable_on_failure=True → 发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook", "enable_on_success": False, "enable_on_failure": True}
        env = _env(notify_config=cfg)
        case = _case()
        record = _record(status="failed")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(env, case, record)
            MockRobot.return_value.send_markdown.assert_called_once()

    def test_enable_on_failure_defaults_to_true(self):
        """未配 enable_on_failure 时，失败默认发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook"}
        env = _env(notify_config=cfg)
        case = _case()
        record = _record(status="failed")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(env, case, record)
            MockRobot.return_value.send_markdown.assert_called_once()

    def test_enable_on_success_defaults_to_false(self):
        """未配 enable_on_success 时，成功默认不发通知"""
        cfg = {"wecom_webhook": "http://fake/webhook"}
        env = _env(notify_config=cfg)
        case = _case()
        record = _record(status="success")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(env, case, record)
            MockRobot.return_value.send_markdown.assert_not_called()
