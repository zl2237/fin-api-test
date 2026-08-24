"""执行通知服务：用例执行完成后发送企微通知。

从 DagExecutor._send_notify 提取，供 DagExecutor 与后续 OrderFlow 编排器复用。
行为与原 DagExecutor 实现完全一致：通知失败不影响主流程。
失败时从步骤记录提取失败原因（失败接口/断言消息/请求异常/执行异常），附在通知里。
"""

# 企微 markdown content 上限 4096 字节（UTF-8），失败原因区块按字节预算控制，
# 给正文（用例名/环境等）留余量；中文 3 字节/字，不能按字符数截断
_FAIL_SECTION_MAX_BYTES = 1800


def _clip(text: str, limit: int) -> str:
    """单行截断：超长加省略号"""
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _line(line: str, lines: list[str], budget: list[int]) -> None:
    """追加一行并扣减字节预算；预算耗尽时打省略标记并停止追加。"""
    if budget[0] <= 0:
        return
    cost = len(line.encode("utf-8"))
    if budget[0] - cost < 0:
        lines.append("> …（内容超长已截断，详见执行报告）")
        budget[0] = 0
        return
    lines.append(line)
    budget[0] -= cost


def _request_error_text(step) -> str:
    """无断言失败的步骤，从响应体提取错误文本（请求异常时 response_body 为 {"error": ...}）。"""
    rb = step.response_body
    if isinstance(rb, dict):
        for key in ("error", "message", "msg"):
            if rb.get(key):
                return str(rb[key])
    return ""


def _build_fail_section(record) -> str:
    """组装失败原因区块：失败步骤（接口/状态码/断言消息/请求异常）+ 执行异常 + 未执行节点。

    record 为 ExecutionRecord ORM（steps/assertions 关系已可 lazy load）。
    返回空串表示无可提取的失败信息。
    """
    lines: list[str] = []
    budget = [_FAIL_SECTION_MAX_BYTES]

    failed_steps = [s for s in (record.steps or []) if s.status != "success"]
    for step in failed_steps[:5]:  # 最多列 5 个失败步骤，防通知超长
        _line(f"> ❌ 「{step.api_name or step.node_id}」HTTP {step.response_status if step.response_status is not None else '-'}", lines, budget)
        bad_asserts = [a for a in (step.assertions or []) if a.result is False]
        for a in bad_asserts[:3]:  # 每步最多 3 条断言详情
            detail = a.message or f"{a.rule_type} 期望 {a.expected_value} 实际 {a.actual_value}"
            _line(f"> 　　· {_clip(detail, 160)}", lines, budget)
        if not bad_asserts:
            err_text = _request_error_text(step)
            hint = f"请求异常：{_clip(err_text, 160)}" if err_text else "无断言失败（接口请求失败或响应异常）"
            _line(f"> 　　· {hint}", lines, budget)

    summary = record.summary or {}
    if summary.get("error"):
        _line(f"> ⚠️ 执行异常：{_clip(summary['error'], 300)}", lines, budget)
    leftover = summary.get("leftover") or []
    if leftover:
        _line(f"> ⏭️ 因上游失败未执行：{len(leftover)} 个节点", lines, budget)
    if len(failed_steps) > 5:
        _line(f"> …另有 {len(failed_steps) - 5} 个失败步骤已省略，详见执行报告", lines, budget)

    return "\n".join(lines)


def send_notify(env, case, record, executor_name: str = "", project_name: str = "") -> None:
    """执行完成后发送企微通知；notify_config 未配置 webhook 或开关关闭则跳过；失败不影响主流程。

    executor_name 为执行人姓名（由调用方从 record.created_by 查 User 表得到），空字符串则不显示。
    project_name 为用例所属项目名称（由调用方从 case.project_id 查 Project 表得到），空字符串则不显示。
    """
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
        lines = [
            "**用例执行通知**",
            f"> 用例：{case.name}",
            f"> 状态：{status_text}{duration}",
            f"> 通过/总数：{summary.get('passed', 0)}/{summary.get('total', 0)}",
        ]
        if not is_success:
            fail_section = _build_fail_section(record)
            if fail_section:
                lines += ["> ", "**失败原因**", fail_section]
        if project_name:
            lines.append(f"> 项目：{project_name}")
        lines += [
            f"> 环境：{env.name}",
            f"> 执行人：{executor_name}",
            f"> 时间：{record.ended_at.strftime('%Y-%m-%d %H:%M:%S') if record.ended_at else ''}",
        ]
        content = "\n".join(lines)
        WeComRobot(webhook).send_markdown("用例执行通知", content)
    except Exception as e:
        # 通知失败不影响执行结果
        print(f"[通知发送] 企微通知发送失败（忽略）: {e}")
