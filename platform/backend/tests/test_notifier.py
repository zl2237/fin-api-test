"""notifier 模块单测：执行通知服务（单条 + 批量聚合，企微通知）。

用 mock 替换 WeComRobot，验证通知内容拼装、取数（执行人/项目名、环境/数据集）
与门控（webhook + enable_on_success/enable_on_failure 单点）逻辑，不触真实网络。
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import utils.wecom_util  # noqa: F401  显式绑定子模块：utils 为命名空间包，不导入则 patch("utils.wecom_util.WeComRobot") 解析目标失败

from app import models
from app.services.notifier import send_batch_notify, send_notify


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


class TestSendBatchNotify:
    """聚合通知发送：环境/数据集取数 + 门控与单条通知同点（_send_wecom）"""

    @staticmethod
    def _rec(status="failed"):
        summary = {} if status == "success" else {"error": "断言失败"}
        return SimpleNamespace(status=status,
                               dataset_row={"row_index": 2, "label": "BL002", "data": {}},
                               summary=summary)

    _UNSET = object()  # 哨兵：区分"未提供"与"显式传 None（查无）"

    def _run(self, notify_config, records, env=_UNSET, dataset=_UNSET):
        from app.services import notifier
        if env is self._UNSET:
            env = _env(notify_config=notify_config)
        if dataset is self._UNSET:
            dataset = SimpleNamespace(name="运单数据")
        with patch("utils.wecom_util.WeComRobot") as MockRobot, \
             patch.object(notifier.crud, "get_environment", return_value=env), \
             patch.object(notifier.crud, "get_dataset", return_value=dataset):
            send_batch_notify(DB, env_id=1, dataset_id=2, records=records, case_name="下单用例")
        return MockRobot

    def test_all_success_skips(self):
        """全成功 → 不发（enable_on_success 语义）"""
        MockRobot = self._run(WEBHOOK_CFG, [self._rec("success"), self._rec("success")])
        MockRobot.return_value.send_markdown.assert_not_called()

    def test_failure_sends_summary(self):
        """有失败 → 一条汇总（标题/用例名/失败行/数据集名）"""
        MockRobot = self._run(WEBHOOK_CFG, [self._rec("success"), self._rec()])
        mock_instance = MockRobot.return_value
        mock_instance.send_markdown.assert_called_once()
        title, content = mock_instance.send_markdown.call_args[0]
        assert title == "数据驱动批量执行通知"
        assert "下单用例" in content
        assert "#2 BL002" in content
        assert "运单数据" in content  # 数据集名由 notifier 查表解析

    def test_skips_when_no_webhook(self):
        MockRobot = self._run({}, [self._rec()])
        MockRobot.return_value.send_markdown.assert_not_called()

    def test_skips_when_enable_on_failure_false(self):
        cfg = {"wecom_webhook": "http://fake/webhook", "enable_on_failure": False}
        MockRobot = self._run(cfg, [self._rec()])
        MockRobot.return_value.send_markdown.assert_not_called()

    def test_sends_when_enable_on_failure_unset(self):
        """未配 enable_on_failure → 默认开（与单条通知同一默认值）"""
        cfg = {"wecom_webhook": "http://fake/webhook"}
        MockRobot = self._run(cfg, [self._rec()])
        MockRobot.return_value.send_markdown.assert_called_once()

    def test_env_missing_skips_silently(self):
        """环境查无（已删除）→ 静默跳过不抛"""
        MockRobot = self._run(WEBHOOK_CFG, [self._rec()], env=None)
        MockRobot.return_value.send_markdown.assert_not_called()

    def test_dataset_missing_skips_silently(self):
        MockRobot = self._run(WEBHOOK_CFG, [self._rec()], dataset=None)
        MockRobot.return_value.send_markdown.assert_not_called()

    def test_wecom_exception_swallowed(self):
        with patch("utils.wecom_util.WeComRobot") as MockRobot, \
             patch("app.services.notifier.crud.get_environment",
                   return_value=_env(notify_config=WEBHOOK_CFG)), \
             patch("app.services.notifier.crud.get_dataset",
                   return_value=SimpleNamespace(name="运单数据")):
            MockRobot.return_value.send_markdown.side_effect = RuntimeError("网络不可达")
            # 不应抛出
            send_batch_notify(DB, env_id=1, dataset_id=2,
                              records=[self._rec()], case_name="下单用例")
