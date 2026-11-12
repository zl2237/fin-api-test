"""执行通知服务：用例单条通知 + 方案聚合通知，双渠道（企微/邮件）。

深模块约定：取数与门控都在本模块内部——执行人/项目名、环境/数据集名由
notifier 自己查表，webhook 存在性与 enable_on_success/enable_on_failure
开关（成功默认关、失败默认开）只在 _send_wecom/_send_email 各定义一份。
调用方只交对象与 id，不替通知查表；改门控语义只需改这里。失败不影响主
流程；失败通知附失败原因（失败接口/断言消息/请求异常/执行异常）。

渠道配置（Environment.notify_config JSON 列）：
- 企微：顶层 wecom_webhook + enable_on_failure/enable_on_success（历史形态不动）
- 邮件：email 子对象 {smtp_host, smtp_port, use_ssl, from_addr, auth_code,
  recipients[], enable_on_failure, enable_on_success}——host/发件人/收件人
  齐备才视为已配置；缺任一跳过该渠道。
"""
from .. import models

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
        # 后置提取未取到的变量（值为 {__error__: 原因}）：失败原因直达通知
        bad_extracts = [(k, v["__error__"])
                        for k, v in (getattr(step, "extracted_vars", None) or {}).items()
                        if isinstance(v, dict) and "__error__" in v]
        for k, reason in bad_extracts[:3]:
            _line(f"> 　　· 提取 {k} 未取到：{_clip(reason, 160)}", lines, budget)
        if not bad_asserts and not bad_extracts:
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


# ---------- 邮件渠道（SMTP；标准库 smtplib，延迟导入便于测试打桩） ----------

def _render_email_html(content: str) -> str:
    """企微 markdown 正文 → 简易 HTML：转义 + **加粗** + 引用行缩进 + 换行。"""
    import html as _html
    import re
    bold = re.compile(r"\*\*(.+?)\*\*")
    out_lines = []
    for raw in content.split("\n"):
        line = bold.sub(r"<b>\1</b>", _html.escape(raw))
        if line.lstrip().startswith("&gt;"):
            out_lines.append(f'<div style="margin:2px 0 2px 8px;color:#333">{line}</div>')
        else:
            out_lines.append(f"<div>{line}</div>")
    return "".join(out_lines)


def _send_email(email_cfg: dict, subject: str, content: str, *, success_event: bool) -> None:
    """邮件门控 + 发送单点：配置齐备性 + 成功/失败开关（默认同企微：失败开、成功关）。"""
    host = (email_cfg.get("smtp_host") or "").strip()
    from_addr = (email_cfg.get("from_addr") or "").strip()
    recipients = [r.strip() for r in (email_cfg.get("recipients") or []) if str(r).strip()]
    if not host or not from_addr or not recipients:
        print("[通知发送] 跳过：邮件渠道未配置（smtp_host/from_addr/recipients 需齐备）")
        return
    if success_event and not email_cfg.get("enable_on_success", False):
        print("[通知发送] 跳过：邮件渠道成功通知未开启")
        return
    if not success_event and not email_cfg.get("enable_on_failure", True):
        print("[通知发送] 跳过：邮件渠道失败通知已关闭")
        return
    import smtplib
    from email.header import Header
    from email.mime.text import MIMEText
    port = int(email_cfg.get("smtp_port") or 465)
    use_ssl = bool(email_cfg.get("use_ssl", True))
    auth_code = (email_cfg.get("auth_code") or "").strip()
    body = _render_email_html(content)
    msg = MIMEText(body, "html", "utf-8")
    # str(Header(...)) 即 RFC 2047 编码串（=?utf-8?b?...?=），运行时与直接赋 Header 等价
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    print(f"[通知发送] 发送邮件通知：{subject} → {recipients}")
    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    client = smtp_cls(host, port, timeout=15)
    try:
        if auth_code:
            client.login(from_addr, auth_code)
        client.sendmail(from_addr, recipients, msg.as_string())
    finally:
        try:
            client.quit()
        except Exception:
            pass


def _dispatch_channels(env, title: str, content: str, *, email_subject: str,
                       success_event: bool) -> None:
    """按环境 notify_config 分发双渠道：企微（顶层配置）+ 邮件（email 子对象）。

    两渠道互不影响，各自门控；异常各自吞掉（不影响执行主流程，也不互相阻断）。
    """
    cfg = env.notify_config or {}
    try:
        _send_wecom(cfg, title, content, success_event=success_event)
    except Exception as e:
        print(f"[通知发送] 企微通知发送失败（忽略）: {e}")
    try:
        _send_email(cfg.get("email") or {}, email_subject, content,
                    success_event=success_event)
    except Exception as e:
        print(f"[通知发送] 邮件通知发送失败（忽略）: {e}")


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
        _dispatch_channels(env, "用例执行通知", "\n".join(lines),
                           email_subject=f"用例执行通知｜{case.name}"
                                         f"（{'通过' if is_success else '失败'}）",
                           success_event=is_success)
    except Exception as e:
        # 通知失败不影响执行结果
        print(f"[通知发送] 通知发送失败（忽略）: {e}")


# ---------- 方案聚合通知（plan 执行完全部结束后一条汇总） ----------

# 失败成员列表上限（同上限保护企微 4096 字节预算；轮数多时同名成员会各占一行）
_PLAN_FAIL_LIST_MAX = 5

_TERMINAL_STATUSES = {"success", "failed", "terminated"}


def all_terminal(records) -> bool:
    """记录集是否全部到达终态（success/failed/terminated）——方案看门狗轮询用。"""
    return bool(records) and all(r.status in _TERMINAL_STATUSES for r in records)


def _plan_trigger_label(trigger_types: set) -> str:
    """触发方式文案：以本次记录集中出现的 trigger_type 汇总。"""
    if "plan_schedule" in trigger_types:
        return "方案定时"
    if "plan" in trigger_types:
        return "手动执行"
    return "-"


def send_plan_notify(db, plan_id: int | None, record_ids: list) -> None:
    """方案执行全量结束后的一条聚合通知。

    - 汇总口径：本批 record_ids 的终态计数（成功/失败/终止/未结束）、耗时
      （最早 started_at → 最晚 ended_at）、失败成员清单（≤5 条，含执行编号）。
    - 渠道路由：按本批记录涉及的**去重环境**各发一条（多环境方案每个环境
      的订阅方各自收到汇总；环境已删除则跳过）——沿用各环境自己的
      notify_config 双渠道与开关，方案不新增通知配置面。
    - success_event 语义：全部成功才算成功事件（有失败/终止/未结束即为失败
      事件），走各渠道 enable_on_success/enable_on_failure 开关。
    - 任何异常吞掉打日志（通知绝不影响执行主流程）。
    """
    try:
        if not record_ids:
            return
        records = (db.query(models.ExecutionRecord)
                   .filter(models.ExecutionRecord.id.in_(list(record_ids)))
                   .all())
        if not records:
            return
        from ..crud import fill_exec_names  # 延迟导入防环；case_name 为暂挂属性需运行时回填
        fill_exec_names(db, records)
        plan = db.query(models.ExecutionPlan).get(plan_id) if plan_id else None
        plan_name = plan.name if plan else f"已删除方案 #{plan_id}"

        n_total = len(records)
        n_success = sum(1 for r in records if r.status == "success")
        n_failed = sum(1 for r in records if r.status == "failed")
        n_terminated = sum(1 for r in records if r.status == "terminated")
        n_running = n_total - n_success - n_failed - n_terminated
        is_success = n_failed == 0 and n_terminated == 0 and n_running == 0

        starts = [r.started_at for r in records if r.started_at]
        ends = [r.ended_at for r in records if r.ended_at]
        duration = ""
        if starts and ends:
            duration = f"（耗时 {(max(ends) - min(starts)).total_seconds():.1f}s）"
        lines = [
            "**方案执行通知**",
            f"> 方案：{plan_name}",
            f"> 结果：{'✅ 全部通过' if is_success else '❌ 存在失败/终止'}{duration}",
            f"> 成功/失败/终止：{n_success}/{n_failed}/{n_terminated}"
            + (f"/未结束 {n_running}" if n_running else "")
            + f"（共 {n_total} 条）",
        ]
        failed_records = [r for r in records if r.status == "failed"]
        if failed_records:
            lines += ["> ", "**失败成员**"]
            budget = [_FAIL_SECTION_MAX_BYTES]
            for r in failed_records[:_PLAN_FAIL_LIST_MAX]:
                reason = ""
                summary = r.summary or {}
                if summary.get("error"):
                    reason = f"：{_clip(str(summary['error']), 120)}"
                member = r.case_name or f"用例#{r.case_id}"
                _line(f"> ❌ {member}（#{r.id}）{_clip(reason, 140)}", lines, budget)
            if len(failed_records) > _PLAN_FAIL_LIST_MAX:
                _line(f"> …另有 {len(failed_records) - _PLAN_FAIL_LIST_MAX} 条失败已省略，"
                      f"详见平台报告", lines, budget)
        trigger_label = _plan_trigger_label({r.trigger_type for r in records
                                             if getattr(r, "trigger_type", None)})
        lines += [
            f"> 触发：{trigger_label}",
            f"> 时间：{max(ends).strftime('%Y-%m-%d %H:%M:%S') if ends else ''}",
        ]
        content = "\n".join(lines)
        result_label = "全部通过" if is_success else "存在失败"

        env_ids = []
        for r in records:
            if r.env_id and r.env_id not in env_ids:
                env_ids.append(r.env_id)
        for env_id in env_ids:
            env = db.query(models.Environment).get(env_id)
            if env is None:
                continue
            _dispatch_channels(
                env, "方案执行通知", content,
                email_subject=f"方案执行通知｜{plan_name}（{result_label}）",
                success_event=is_success)
    except Exception as e:
        print(f"[通知发送] 方案聚合通知发送失败（忽略）: {e}")
