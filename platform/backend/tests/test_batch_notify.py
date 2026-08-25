"""批量数据驱动失败聚合通知（周期 7，方案定案 #7）。

- 聚合内容纯函数：失败行号列表 + 首个失败原因；全成功返回 None（不发）
- 选行执行/临时换数据集：plan_case_expansion 的覆盖参数
逐条通知抑制（suppress_notify）与聚合轮询线程属编排胶水，接口层自测覆盖。
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import dataset_service as svc
from app.services.notifier import build_batch_notify_content


def _rec(row_index, label, status="failed", error=None):
    return SimpleNamespace(status=status,
                           dataset_row={"row_index": row_index, "label": label, "data": {}},
                           summary={"error": error} if error else {})


class TestBuildBatchNotifyContent:
    def test_all_success_returns_none(self):
        """全成功不发（沿用 enable_on_success 语义，聚合侧直接跳过）"""
        assert build_batch_notify_content(
            [_rec(1, "BL001", "success"), _rec(2, "BL002", "success")],
            case_name="下单用例", dataset_name="运单数据") is None

    def test_failed_rows_listed_with_labels(self):
        """失败行号列表（行号+首列值）+ 数据集名 + 用例名 + 首个失败原因"""
        content = build_batch_notify_content(
            [_rec(1, "BL001", "success"),
             _rec(2, "BL002", "failed", error="断言失败: 金额不符"),
             _rec(3, "BL003", "failed", error="HTTP 500")],
            case_name="下单用例", dataset_name="运单数据")
        assert "下单用例" in content
        assert "运单数据" in content
        assert "#2 BL002" in content and "#3 BL003" in content
        assert "#1" not in content  # 成功行不列
        assert "金额不符" in content  # 首个失败原因
        assert "1/3" in content  # 通过/总数

    def test_failed_without_error_still_listed(self):
        """失败但无 error 摘要：仍列行号，不崩"""
        content = build_batch_notify_content([_rec(5, "BL005")], "用例", "数据集")
        assert "#5 BL005" in content


class TestPlanExpansionSelectors:
    """执行面板交互：临时换数据集 / 仅执行部分行"""

    def _rows(self):
        return [SimpleNamespace(id=i, dataset_id=7, row_index=i, data={"bl_no": f"BL{i:03d}"})
                for i in (1, 2, 3)]

    def test_row_ids_filters_rows(self):
        """row_ids 只执行选中行（单行手动执行=逐条通知的来源）"""
        rows = self._rows()
        case = SimpleNamespace(id=11, dataset_id=7)
        ds = SimpleNamespace(id=7, case_id=11, node_configs=[],
                             columns=[{"key": "bl_no", "type": "string"}], rows=rows)
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "list_rows", return_value=rows):
            plan = svc.plan_case_expansion(SimpleNamespace(), case, row_ids=[2, 3])
        assert [p["row"]["row_index"] for p in plan] == [2, 3]

    def test_row_ids_unknown_rejected(self):
        """row_ids 含不存在的行 → 拒"""
        rows = self._rows()
        case = SimpleNamespace(id=11, dataset_id=7)
        ds = SimpleNamespace(id=7, case_id=11, node_configs=[],
                             columns=[{"key": "bl_no", "type": "string"}], rows=rows)
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "list_rows", return_value=rows):
            with pytest.raises(ValueError, match="不存在"):
                svc.plan_case_expansion(SimpleNamespace(), case, row_ids=[99])

    def test_override_dataset_id(self):
        """临时换数据集（执行面板下拉）：覆盖用例绑定，不改动绑定本身"""
        rows = [SimpleNamespace(id=1, dataset_id=9, row_index=1, data={"x": "1"})]
        case = SimpleNamespace(id=11, dataset_id=7)
        ds9 = SimpleNamespace(id=9, case_id=11, node_configs=[],
                              columns=[{"key": "x", "type": "string"}], rows=rows)
        with patch.object(svc.crud, "get_dataset", return_value=ds9) as g, \
             patch.object(svc.crud, "list_rows", return_value=rows):
            plan = svc.plan_case_expansion(SimpleNamespace(), case, dataset_id=9)
        assert plan[0]["dataset_id"] == 9
        g.assert_called_once()
        _, kwargs = g.call_args
        assert kwargs.get("dataset_id") == 9 or g.call_args[0][1] == 9  # 查询的是覆盖后的 id
