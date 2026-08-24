"""notifier 模块单测：执行通知服务（企微通知）。

用 mock 替换 WeComRobot，验证通知内容拼装与异常吞掉逻辑，
不触真实网络。行为与原 DagExecutor._send_notify 完全一致。
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import utils.wecom_util  # noqa: F401  显式绑定子模块：utils 为命名空间包，不导入则 patch("utils.wecom_util.WeComRobot") 解析目标失败
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
        steps=[],  # 对齐 ExecutionRecord ORM：steps 关系属性恒存在（空表亦然）
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
            send_notify(env, case, record, executor_name="张三")
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
            assert "张三" in content
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

    def test_project_name_included_when_provided(self):
        """project_name 非空时插入「项目」行，且不破坏环境/执行人/时间等原有行"""
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case(name="下单流程")
        record = _record(status="success")

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(env, case, record, project_name="订单系统")
            content = mock_instance.send_markdown.call_args[0][1]
            assert "> 项目：订单系统" in content
            # 原有字段不丢失
            assert "> 环境：测试环境" in content
            assert "> 时间：" in content

    def test_project_line_absent_when_empty(self):
        """project_name 为空时不输出「项目」行（默认调用兼容）"""
        env = _env(notify_config=WEBHOOK_CFG)
        case = _case()
        record = _record()

        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            mock_instance = MockRobot.return_value
            send_notify(env, case, record)
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
            send_notify(_env(notify_config=WEBHOOK_CFG), _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "**失败原因**" in content
            assert "创建订单" in content and "HTTP 500" in content
            assert "状态码应为200" in content

    def test_fail_section_assert_fallback_to_rule(self):
        """断言无 message 时回退到 rule_type+期望/实际"""
        step = self._failed_step("分发", [self._failed_assert(message="")])
        record = self._failed_record([step])
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(_env(notify_config=WEBHOOK_CFG), _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "json_path_equals" in content and "1" in content and "2" in content

    def test_fail_section_request_error_text(self):
        """无断言失败但响应体含 error → 提取「请求异常」"""
        step = self._failed_step("付款", asserts=[], response_status=0,
                                 response_body={"error": "ConnectTimeout: 连接超时"})
        record = self._failed_record([step])
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(_env(notify_config=WEBHOOK_CFG), _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "请求异常" in content and "连接超时" in content

    def test_fail_section_error_and_leftover_lines(self):
        step = self._failed_step("创建")
        record = self._failed_record([step], summary={
            "passed": 0, "total": 3, "failed": 1, "error": "DB 断连", "leftover": ["n2", "n3"],
        })
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(_env(notify_config=WEBHOOK_CFG), _case(), record)
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
            send_notify(_env(notify_config=WEBHOOK_CFG), _case(name="名" * 100), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert len(content.encode("utf-8")) <= 4096
            assert "已截断" in content or "已省略" in content

    def test_success_has_no_fail_section(self):
        record = _record(status="success")
        record.steps = []
        with patch("utils.wecom_util.WeComRobot") as MockRobot:
            send_notify(_env(notify_config=WEBHOOK_CFG), _case(), record)
            content = MockRobot.return_value.send_markdown.call_args[0][1]
            assert "失败原因" not in content
