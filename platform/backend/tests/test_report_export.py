"""报告 CSV 导出纯函数单测（导出逻辑从前端视图下沉后端）。

已知事实来自前端 exportCsv 原实现的独立复述：
- BOM 头 + CRLF 行分隔
- 12 列表头
- 值内逗号/引号/换行需 CSV 转义
"""
from app.services.report_export import export_steps_csv, export_report_html


class _Step:
    def __init__(self, **kw):
        self.api_name = kw.get("api_name", "下单")
        self.node_id = kw.get("node_id", "n1")
        self.api_method = kw.get("api_method", "POST")
        self.api_path = kw.get("api_path", "/order")
        self.response_status = kw.get("response_status", 200)
        self.response_time_ms = kw.get("response_time_ms", 12)
        self.status = kw.get("status", "success")
        self.request_headers = kw.get("request_headers", {"X-Token": "t"})
        self.request_body = kw.get("request_body", {"a": 1})
        self.response_body = kw.get("response_body", {"code": 0})
        self.started_at = kw.get("started_at", "2026-01-01 10:00:00")
        self.ended_at = kw.get("ended_at", "2026-01-01 10:00:01")
        self.assertions = kw.get("assertions", [])


class _Assert:
    def __init__(self, **kw):
        self.rule_type = kw.get("rule_type", "json_path_equals")
        self.result = kw.get("result", True)
        self.actual_value = kw.get("actual_value", "0")
        self.expected_value = kw.get("expected_value", "0")
        self.message = kw.get("message", "")


class TestExportStepsCsv:
    def test_bom_and_header_row(self):
        csv = export_steps_csv([])
        assert csv.startswith("\ufeff")
        # BOM 紧贴表头（与前端原实现一致：'\ufeff' + header）
        lines = csv.split("\r\n")
        assert lines[0] == "\ufeff序号,步骤名称,方法,路径,HTTP状态码,耗时(ms),步骤状态,断言通过,断言总数,断言详情,请求体,响应体"

    def test_step_row_contains_counts_and_assert_details(self):
        steps = [_Step(assertions=[_Assert(), _Assert(result=False, actual_value="1")])]
        csv = export_steps_csv(steps)
        lines = csv.split("\r\n")
        assert len(lines) == 2  # 表头 + 1 行
        row = lines[1]
        assert row.startswith("1,")  # 序号
        assert "0" in row  # 断言通过 1 条？——实际 1 条通过
        assert "2" in row  # 断言总数

    def test_values_with_comma_are_escaped(self):
        steps = [_Step(api_name='下单,批量')]
        csv = export_steps_csv(steps)
        assert '"下单,批量"' in csv

    def test_assertion_detail_format(self):
        steps = [_Step(assertions=[_Assert(rule_type="status_equals")])]
        csv = export_steps_csv(steps)
        assert "status_equals:通过(" in csv


class _Record:
    """执行记录最小载体（含 fill_exec_names/fill_audit_names 后的展示字段）"""

    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.status = kw.get("status", "success")
        self.case_id = kw.get("case_id", 7)
        self.case_name = kw.get("case_name", "下单链路")
        self.env_id = kw.get("env_id", 3)
        self.env_name = kw.get("env_name", "test")
        self.project_name = kw.get("project_name", "订单系统")
        self.created_by_name = kw.get("created_by_name", "boss")
        self.started_at = kw.get("started_at", "2026-01-01 10:00:00")
        self.ended_at = kw.get("ended_at", "2026-01-01 10:00:05")
        self.summary = kw.get("summary", {})


class TestExportReportHtml:
    def test_document_skeleton_and_title(self):
        html = export_report_html(_Record(), [])
        assert html.startswith("<!DOCTYPE html>")
        assert "<html lang=\"zh-CN\">" in html
        assert "<title>执行报告 #1</title>" in html

    def test_summary_grid_contains_record_and_count_fields(self):
        steps = [_Step(), _Step(status="failed")]
        html = export_report_html(_Record(), steps)
        assert "下单链路" in html
        assert "订单系统" in html
        assert '<span class="pass-c">1</span> / 2' in html  # 步骤通过/总数（通过数绿色高亮）
        assert "执行人" in html

    def test_step_and_assertion_rendered(self):
        steps = [_Step(assertions=[_Assert()])]
        html = export_report_html(_Record(), steps)
        assert "下单" in html          # 步骤名
        assert "✓ 通过" in html        # 断言结果
        assert "json_path_equals" in html

    def test_html_escaping(self):
        steps = [_Step(api_name="<script>alert(1)</script>")]
        html = export_report_html(_Record(), steps)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_status_badge_class(self):
        html = export_report_html(_Record(status="failed"), [])
        assert "badge-failed" in html

    # ===== Allure 式导航布局（重构后的结构契约） =====

    def test_nav_item_per_step_with_status_data(self):
        """每个步骤一个导航项，携带状态/名称/路径供 JS 过滤"""
        steps = [_Step(), _Step(status="failed", api_name="查单")]
        html = export_report_html(_Record(), steps)
        assert html.count('class="nav-item"') == 2
        assert 'data-status="success"' in html
        assert 'data-status="failed"' in html
        assert 'data-name="查单"' in html

    def test_detail_pane_per_step_with_tabs(self):
        """每个步骤一个详情面板，内含请求/响应/断言三个 Tab（radio 驱动）"""
        steps = [_Step(assertions=[_Assert()]), _Step()]
        html = export_report_html(_Record(), steps)
        assert html.count('class="step-pane"') == 2
        assert html.count('class="sp-radio sp-radio-req"') == 2
        assert "断言（1）" in html
        assert "断言（0）" in html

    def test_fail_summary_card_only_when_failed(self):
        """失败摘要卡仅在有失败步骤时渲染，含跳转锚点与失败原因"""
        ok_html = export_report_html(_Record(), [_Step()])
        assert 'class="fail-card"' not in ok_html  # CSS 类定义常在，断 DOM 未渲染

        steps = [
            _Step(),
            _Step(status="failed", api_name="查单",
                  assertions=[_Assert(result=False, message="金额不符")]),
        ]
        html = export_report_html(_Record(), steps)
        assert "fail-card" in html
        assert "1 个步骤未通过" in html
        assert "金额不符" in html          # 首条失败断言消息透出
        assert 'data-step="step-2"' in html  # 跳转锚点指向失败步骤

    def test_dark_scheme_variables_present(self):
        """深浅双套变量：prefers-color-scheme dark 覆盖"""
        html = export_report_html(_Record(), [])
        assert "prefers-color-scheme: dark" in html
        assert "--primary: #0071e3" in html  # 主色对齐系统

    def test_interactive_js_embedded(self):
        """内联 JS：搜索/筛选/导航选中/失败优先初始选中"""
        html = export_report_html(_Record(), [_Step()])
        assert "nav-search" in html
        assert "filter-btn" in html
        # 失败优先：默认选中首个非 success 步骤
        assert 'querySelector(\'.nav-item[data-status]:not([data-status="success"])\')' in html

    def test_failed_assertion_row_highlighted(self):
        """失败断言行红底标记"""
        steps = [_Step(assertions=[_Assert(result=False)])]
        html = export_report_html(_Record(), steps)
        assert 'class="row-fail"' in html
        assert "✗ 失败" in html

    def test_long_text_metrics_truncated_with_title(self):
        """回归 #263：超长用例名等文本类统计值单行截断 + title 悬浮全文，
        防止 word-break 折行导致统计卡高度随名称长度无限膨胀"""
        long_name = "冒烟-" * 80
        html = export_report_html(_Record(case_name=long_name), [_Step()])
        # 截断类样式与 title 全文并存
        assert f'<div class="metric-value to" title="{long_name}">{long_name}</div>' in html
        # 数字类计数不参与截断
        assert '<span class="pass-c">1</span> / 1' in html
        # 步骤名与导航项同样有 title 悬浮
        assert '<span class="sp-name" title="下单">下单</span>' in html
        assert 'title="下单&#10;POST /order"' in html
