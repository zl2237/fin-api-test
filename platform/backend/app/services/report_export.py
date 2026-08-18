"""报告导出：CSV/HTML 组装（纯函数，输入 ORM 记录，输出字符串）。

从前端 ReportDetail.vue 的 exportCsv/exportHtml 下沉，
使 CI/定时任务等非交互方可复用导出能力。
HTML 结构与 CSS 与前端原实现保持一致（自包含，双击即可在浏览器打开）。
"""
import json
from datetime import datetime
from typing import Any, List


# ============ CSV ============

def _csv_escape(v: Any) -> str:
    """CSV 值转义：含逗号/引号/换行的值加引号包裹，内部引号翻倍"""
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    if any(c in s for c in (",", '"', "\n", "\r")):
        return '"' + s.replace('"', '""') + '"'
    return s


def _norm(v: Any) -> str:
    """dict/list 转 JSON 字符串（与前端 JSON.stringify 行为对齐），None 转 ''"""
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def export_steps_csv(steps: List[Any]) -> str:
    """步骤列表 → CSV 文本（BOM + CRLF，Excel 兼容 UTF-8）。字段契约与前端原实现一致。"""
    header = ["序号", "步骤名称", "方法", "路径", "HTTP状态码", "耗时(ms)", "步骤状态", "断言通过", "断言总数", "断言详情", "请求体", "响应体"]
    rows: List[str] = [",".join(header)]
    for idx, s in enumerate(steps):
        assertions = getattr(s, "assertions", None) or []
        assert_details = " | ".join(
            f"{a.rule_type}:{'通过' if a.result else '失败'}({a.actual_value or ''} vs {a.expected_value or ''})"
            for a in assertions
        )
        rows.append(",".join([
            str(idx + 1),
            _csv_escape(s.api_name or s.node_id or ""),
            _norm(s.api_method),
            _csv_escape(s.api_path or ""),
            _norm(s.response_status),
            _norm(s.response_time_ms),
            _norm(s.status),
            str(sum(1 for a in assertions if a.result)),
            str(len(assertions)),
            _csv_escape(assert_details),
            _csv_escape(_norm(s.request_body)),
            _csv_escape(_norm(s.response_body)),
        ]))
    return "\ufeff" + "\r\n".join(rows)


# ============ HTML ============

def _esc(s: Any) -> str:
    """HTML 转义"""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _fmt_json(v: Any) -> str:
    """JSON 美化（dict/list 缩进 2 空格，None 显示 '-'，与前端 formatJson 一致）"""
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(v)


def _status_text(s: Any) -> str:
    return {"success": "通过", "running": "执行中", "failed": "失败"}.get(s, s if s else "-")


def _step_status_text(s: Any) -> str:
    return {"success": "通过", "failed": "失败", "skipped": "跳过", "running": "执行中"}.get(s, s if s else "-")


def _fmt_duration_ms(ms: float) -> str:
    if ms < 1000:
        return f"{round(ms)} ms"
    return f"{ms / 1000:.2f} s"


def _parse_dt(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.timestamp()
    try:
        return datetime.fromisoformat(str(v)).timestamp()
    except Exception:
        return None


def _summary_item(label: str, value: Any, highlight: bool = False) -> str:
    cls = "metric metric-hl" if highlight else "metric"
    return f'<div class="{cls}"><div class="metric-label">{_esc(label)}</div><div class="metric-value">{_esc(value)}</div></div>'


def _json_section(title: str, val: Any) -> str:
    return (f'<section class="subsection"><h3>{_esc(title)}</h3>'
            f'<pre class="json-block">{_esc(_fmt_json(val))}</pre></section>')


_REPORT_HTML_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: #f5f7fa; color: #1f2937; padding: 32px 16px; line-height: 1.6;
}
.report { max-width: 960px; margin: 0 auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.report-head { display: flex; align-items: center; justify-content: space-between; padding: 24px 32px; background: linear-gradient(135deg, #409eff 0%, #2b7fd6 100%); color: #fff; }
.head-title { font-size: 22px; font-weight: 600; }
.head-id { font-weight: 400; opacity: 0.9; margin-left: 4px; }
.status-badge { padding: 4px 14px; border-radius: 999px; font-size: 13px; font-weight: 600; background: rgba(255,255,255,0.25); border: 1px solid rgba(255,255,255,0.4); }
.status-success { background: rgba(255,255,255,0.25); }
.status-failed { background: rgba(255,80,80,0.45); }
.status-running { background: rgba(255,200,80,0.45); }
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 20px 32px; background: #fafbfc; border-bottom: 1px solid #ebeef5; }
.metric { padding: 8px 0; }
.metric-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.metric-value { font-size: 14px; font-weight: 500; color: #303133; word-break: break-all; }
.metric-hl .metric-value { color: #409eff; font-size: 16px; font-weight: 600; }
.step { padding: 24px 32px; border-bottom: 1px solid #ebeef5; }
.step:last-of-type { border-bottom: none; }
.step-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.step-title { font-size: 16px; font-weight: 600; color: #303133; }
.step-idx { display: inline-block; min-width: 28px; height: 24px; line-height: 24px; text-align: center; background: #ecf5ff; color: #409eff; border-radius: 6px; font-size: 13px; margin-right: 8px; }
.step-status { padding: 2px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.step-status.status-success { background: #f0f9eb; color: #67c23a; }
.step-status.status-failed { background: #fef0f0; color: #f56c6c; }
.step-status.status-running { background: #fdf6ec; color: #e6a23c; }
.step-status.status-skipped { background: #f4f4f5; color: #909399; }
.step-meta { display: flex; flex-wrap: wrap; gap: 8px 24px; font-size: 12px; color: #606266; margin-bottom: 16px; padding: 10px 14px; background: #fafbfc; border-radius: 6px; }
.step-meta em { font-style: normal; color: #909399; margin-right: 4px; }
.subsection { margin-bottom: 14px; }
.subsection h3 { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 6px; padding-left: 8px; border-left: 3px solid #409eff; }
.json-block { background: #1e2a3a; color: #c8d3e0; padding: 12px 14px; border-radius: 6px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; overflow-x: auto; }
.assert-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.assert-table th, .assert-table td { border: 1px solid #ebeef5; padding: 8px 10px; text-align: left; vertical-align: top; }
.assert-table th { background: #fafbfc; font-weight: 600; color: #606266; }
.assert-table .pass { color: #67c23a; font-weight: 600; }
.assert-table .fail { color: #f56c6c; font-weight: 600; }
.assert-table .mono { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 11px; }
.assert-table .muted { color: #909399; }
.col-result { width: 90px; } .col-type { width: 180px; } .col-actual, .col-expected { width: 22%; }
.report-foot { padding: 16px 32px; text-align: center; font-size: 12px; color: #909399; background: #fafbfc; }
@media print { body { padding: 0; background: #fff; } .report { box-shadow: none; border-radius: 0; max-width: none; } .step { break-inside: avoid; } }
"""


def export_report_html(record: Any, steps: List[Any]) -> str:
    """执行记录 + 步骤 → 自包含 HTML 报告文本。结构/字段与前端原 exportHtml 一致。"""
    parts: List[str] = []
    parts.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    parts.append(f"<title>执行报告 #{_esc(record.id)}</title>")
    parts.append(f"<style>{_REPORT_HTML_CSS}</style>")
    parts.append("</head><body>")
    parts.append('<div class="report">')

    # 报告头
    parts.append('<header class="report-head">')
    parts.append(f'<div class="head-title">执行报告 <span class="head-id">#{_esc(record.id)}</span></div>')
    parts.append(f'<span class="status-badge status-{_esc(record.status)}">{_esc(_status_text(record.status))}</span>')
    parts.append("</header>")

    # 摘要
    passed = sum(1 for s in steps if s.status == "success")
    assertion_total = sum(len(getattr(s, "assertions", None) or []) for s in steps)
    assertion_passed = sum(
        1 for s in steps for a in (getattr(s, "assertions", None) or []) if a.result
    )
    t0, t1 = _parse_dt(record.started_at), _parse_dt(record.ended_at)
    duration = _fmt_duration_ms((t1 - t0) * 1000) if t0 is not None and t1 is not None else "-"

    parts.append('<section class="summary-grid">')
    parts.append(_summary_item("用例", record.case_name or f"#{record.case_id}"))
    parts.append(_summary_item("环境", record.env_name or f"#{record.env_id}"))
    parts.append(_summary_item("项目", record.project_name or "—"))
    parts.append(_summary_item("执行人", record.created_by_name or "—"))
    parts.append(_summary_item("步骤通过 / 总数", f"{passed} / {len(steps)}", True))
    parts.append(_summary_item("断言通过 / 总数", f"{assertion_passed} / {assertion_total}", True))
    parts.append(_summary_item("开始时间", record.started_at or "—"))
    parts.append(_summary_item("结束时间", record.ended_at or "—"))
    parts.append(_summary_item("耗时", duration, True))
    parts.append("</section>")

    # 各步骤
    for idx, s in enumerate(steps):
        parts.append('<article class="step">')
        parts.append('<header class="step-head">')
        parts.append(f'<div class="step-title"><span class="step-idx">#{idx + 1}</span> {_esc(s.api_name or s.node_id or "未命名步骤")}</div>')
        parts.append(f'<span class="step-status status-{_esc(s.status)}">{_esc(_step_status_text(s.status))}</span>')
        parts.append("</header>")
        parts.append('<div class="step-meta">')
        parts.append(f"<span><em>请求</em> {_esc(s.api_method or '')} {_esc(s.api_path or '')}</span>")
        parts.append(f"<span><em>HTTP</em> {_esc(s.response_status if s.response_status is not None else '-')}</span>")
        parts.append(f"<span><em>耗时</em> {_esc(s.response_time_ms if s.response_time_ms is not None else '-')} ms</span>")
        parts.append(f"<span><em>开始</em> {_esc(s.started_at or '')}</span>")
        parts.append(f"<span><em>结束</em> {_esc(s.ended_at or '')}</span>")
        parts.append("</div>")

        parts.append(_json_section("请求头", s.request_headers))
        parts.append(_json_section("请求体", s.request_body))
        parts.append(_json_section("响应体", s.response_body))

        assertions = getattr(s, "assertions", None) or []
        if assertions:
            parts.append('<section class="subsection">')
            parts.append(f"<h3>断言（{len(assertions)}）</h3>")
            parts.append('<table class="assert-table"><thead><tr>')
            parts.append('<th class="col-result">结果</th><th class="col-type">类型</th>')
            parts.append('<th class="col-actual">实际值</th><th class="col-expected">期望值</th><th>消息</th>')
            parts.append("</tr></thead><tbody>")
            for a in assertions:
                cls = "pass" if a.result else "fail"
                parts.append("<tr>")
                parts.append(f'<td class="{cls}">{"✓ 通过" if a.result else "✗ 失败"}</td>')
                parts.append(f"<td>{_esc(a.rule_type)}</td>")
                parts.append(f'<td class="mono">{_esc(a.actual_value if a.actual_value is not None else "—")}</td>')
                parts.append(f'<td class="mono">{_esc(a.expected_value if a.expected_value is not None else "—")}</td>')
                parts.append(f'<td class="muted">{_esc(a.message if a.message is not None else "—")}</td>')
                parts.append("</tr>")
            parts.append("</tbody></table>")
            parts.append("</section>")
        parts.append("</article>")

    parts.append('<footer class="report-foot">')
    parts.append(f"由 fin-api-test 平台生成 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append("</footer>")

    parts.append("</div></body></html>")
    return "".join(parts)
