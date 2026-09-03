"""执行通知服务：用例执行完成后的企微通知（单条 + 数据驱动批量聚合）。

深模块约定：取数与门控都在本模块内部——执行人/项目名、环境/数据集名由
notifier 自己查表，webhook 存在性与 enable_on_success/enable_on_failure
开关（成功默认关、失败默认开）只在 _send_wecom 定义一份。调用方只交对象
与 id，不替通知查表；改门控语义只需改这里。失败不影响主流程；失败通知
附失败原因（失败接口/断言消息/请求异常/执行异常）。
"""
from .. import crud, models

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


def build_batch_notify_content(records, case_name: str, dataset_name: str):
    """数据驱动批量执行聚合通知内容（方案定案 #7）。

    - 全成功 → None（不发，沿用 enable_on_success 语义）
    - 有失败 → 一条汇总：用例名 + 数据集名 + 失败行号列表（#行号 首列值）+ 首个失败原因
    """
    failed = [r for r in records if getattr(r, "status", None) != "success"]
    if not failed:
        return None
    row_list = "、".join(
        f"#{r.dataset_row['row_index']} {r.dataset_row.get('label', '')}".rstrip()
        for r in failed if r.dataset_row
    )
    first_error = next((str((r.summary or {}).get("error")) for r in failed
                        if (r.summary or {}).get("error")), "无失败摘要（详见执行报告）")
    passed = len(records) - len(failed)
    lines = [
        "**数据驱动批量执行通知**",
        f"> 用例：{case_name}",
        f"> 数据集：{dataset_name}",
        f"> 状态：❌ {len(failed)}/{len(records)} 行失败（通过 {passed}/{len(records)}）",
    ]
    if row_list:
        lines += ["> ", "**失败行**", f"> {row_list}"]
    lines += ["> ", "**首个失败原因**", f"> {_clip(first_error, 300)}"]
    return "\n".join(lines)


def _resolve_executor_name(db, record) -> str:
    """执行人姓名：record.created_by → User 表；未绑定或查无则空串"""
    if not getattr(record, "created_by", None):
        return ""
    user = db.query(models.User).filter(models.User.id == record.created_by).first()
    return user.username if user else ""


def _resolve_project_name(db, case) -> str:
    """项目名：case.project_id → Project 表；未绑定或查无则空串"""
    if not getattr(case, "project_id", None):
        return ""
    project = db.query(models.Project).filter(models.Project.id == case.project_id).first()
    return project.name if project else ""


def _send_wecom(notify_config: dict, title: str, content: str, *, success_event: bool) -> None:
    """门控 + 发送单点：webhook 存在性 + 成功/失败开关（成功默认关、失败默认开）。"""
    webhook = notify_config.get("wecom_webhook")
    if not webhook:
        print("[通知发送] 跳过：未配置 wecom_webhook")
        return
    if success_event and not notify_config.get("enable_on_success", False):
        print("[通知发送] 跳过：用例成功但 enable_on_success=False")
        return
    if not success_event and not notify_config.get("enable_on_failure", True):
        print("[通知发送] 跳过：用例失败但 enable_on_failure=False")
        return
    from utils.wecom_util import WeComRobot
    print(f"[通知发送] 发送企微通知：{title}")
    WeComRobot(webhook).send_markdown(title, content)


def send_notify(db, env, case, record) -> None:
    """单条执行完成后的企微通知：执行人/项目名由本函数查表解析（调用方不再替通知取数）。

    notify_config 未配置 webhook 或开关关闭则跳过；失败不影响主流程。
    """
    try:
        is_success = record.status == "success"
        executor_name = _resolve_executor_name(db, record)
        project_name = _resolve_project_name(db, case)
        summary = record.summary or {}
        duration = ""
        if record.started_at and record.ended_at:
            secs = (record.ended_at - record.started_at).total_seconds()
            duration = f"（耗时 {secs:.1f}s）"
        lines = [
            "**用例执行通知**",
            f"> 用例：{case.name}",
            f"> 状态：{'✅ 通过' if is_success else '❌ 失败'}{duration}",
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
        _send_wecom(env.notify_config or {}, "用例执行通知", "\n".join(lines),
                    success_event=is_success)
    except Exception as e:
        # 通知失败不影响执行结果
        print(f"[通知发送] 企微通知发送失败（忽略）: {e}")


def send_batch_notify(db, env_id: int, dataset_id: int, records, case_name: str) -> None:
    """数据驱动批量执行的聚合通知：环境/数据集名取数与门控都收敛在本模块。

    全成功不发（enable_on_success 语义）；有失败发一条汇总。失败不影响主流程。
    """
    try:
        env = crud.get_environment(db, env_id)
        dataset = crud.get_dataset(db, dataset_id)
        if not env or not dataset:
            return
        content = build_batch_notify_content(records, case_name, dataset.name)
        if content is None:
            print("[聚合通知] 跳过：数据驱动批量全部成功")
            return
        _send_wecom(env.notify_config or {}, "数据驱动批量执行通知", content,
                    success_event=False)
    except Exception as e:
        # 聚合通知失败不影响执行结果
        print(f"[聚合通知] 发送失败（忽略）: {e}")
