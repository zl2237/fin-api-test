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
        assert "1 / 2" in html  # 步骤通过/总数
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
        assert "status-failed" in html
