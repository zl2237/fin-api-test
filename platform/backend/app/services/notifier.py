"""执行通知服务：用例执行完成后发送企微通知。

从 DagExecutor._send_notify 提取，供 DagExecutor 与后续 OrderFlow 编排器复用。
行为与原 DagExecutor 实现完全一致：通知失败不影响主流程。
"""


def send_notify(env, case, record) -> None:
    """执行完成后发送企微通知；notify_config 未配置 webhook 或开关关闭则跳过；失败不影响主流程。"""
    try:
        notify_config = env.notify_config or {}
        webhook = notify_config.get("wecom_webhook")
        if not webhook:
            print("[通知发送] 跳过：未配置 wecom_webhook")
            return
        # 按开关决定是否通知：成功时看 enable_on_success，失败时看 enable_on_failure
        is_success = record.status == "success"
        if is_success and not notify_config.get("enable_on_success", False):
            print("[通知发送] 跳过：用例成功但 enable_on_success=False")
            return
        if not is_success and not notify_config.get("enable_on_failure", True):
            print("[通知发送] 跳过：用例失败但 enable_on_failure=False")
            return
        print(f"[通知发送] 发送企微通知：用例={case.name} 状态={record.status}")
        from utils.wecom_util import WeComRobot
        status_text = "✅ 通过" if is_success else "❌ 失败"
        summary = record.summary or {}
        duration = ""
        if record.started_at and record.ended_at:
            secs = (record.ended_at - record.started_at).total_seconds()
            duration = f"（耗时 {secs:.1f}s）"
        content = (
            f"**用例执行通知**\n"
            f"> 用例：{case.name}\n"
            f"> 状态：{status_text}{duration}\n"
            f"> 通过/总数：{summary.get('passed', 0)}/{summary.get('total', 0)}\n"
            f"> 环境：{env.name}\n"
            f"> 时间：{record.ended_at.strftime('%Y-%m-%d %H:%M:%S') if record.ended_at else ''}"
        )
        WeComRobot(webhook).send_markdown("用例执行通知", content)
    except Exception as e:
        # 通知失败不影响执行结果
        print(f"[通知发送] 企微通知发送失败（忽略）: {e}")
