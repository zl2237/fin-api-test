"""报告导出：CSV/HTML 组装（纯函数，输入 ORM 记录，输出字符串）。

从前端 ReportDetail.vue 的 exportCsv/exportHtml 下沉，
使 CI/定时任务等非交互方可复用导出能力。

HTML 报告为 Allure 式导航布局（左侧步骤导航 + 右侧详情 Tabs）：
- 失败优先：顶部失败摘要卡 + 默认选中首个失败步骤
- 内嵌无依赖 JS：搜索过滤 / 状态筛选 / 导航跳转（约 100 行）
- 自带深浅双套 CSS 变量（prefers-color-scheme），主色 #0071e3 对齐系统
- 单文件自包含，双击即可在浏览器打开
"""
import json
from datetime import datetime
from typing import Any

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


def export_steps_csv(steps: list[Any]) -> str:
    """步骤列表 → CSV 文本（BOM + CRLF，Excel 兼容 UTF-8）。字段契约与前端原实现一致。"""
    header = ["序号", "步骤名称", "方法", "路径", "HTTP状态码", "耗时(ms)", "步骤状态", "断言通过", "断言总数", "断言详情", "请求体", "响应体"]
    rows: list[str] = [",".join(header)]
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


_REPORT_HTML_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --primary: #0071e3; --primary-soft: rgba(0,113,227,.08); --primary-line: rgba(0,113,227,.35);
  --bg: #f5f5f7; --card: #ffffff; --card-2: #fafafa; --border: #e5e5ea;
  --text: #1d1d1f; --text-2: #6e6e73; --text-3: #aeaeb2;
  --ok: #34c759; --ok-soft: rgba(52,199,89,.12);
  --err: #ff3b30; --err-soft: rgba(255,59,48,.10);
  --warn: #ff9500; --warn-soft: rgba(255,149,0,.12);
  --skip: #8e8e93; --skip-soft: rgba(142,142,147,.12);
  --code-bg: #f2f2f7; --shadow: 0 1px 3px rgba(0,0,0,.06);
  --nav-w: 300px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1c1c1e; --card: #2c2c2e; --card-2: #232325; --border: #3a3a3c;
    --text: #f5f5f7; --text-2: #98989d; --text-3: #636366;
    --primary-soft: rgba(10,132,255,.16); --primary-line: rgba(10,132,255,.45);
    --err-soft: rgba(255,69,58,.14); --ok-soft: rgba(48,209,88,.14);
    --warn-soft: rgba(255,159,10,.16); --skip-soft: rgba(142,142,147,.18);
    --code-bg: #1a1a1c; --shadow: none;
  }
}
html { font-size: 15px; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg); color: var(--text); padding: 24px 16px 40px; line-height: 1.65;
}
.wrap { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }

/* ===== 报告头 ===== */
.head {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;
  padding: 18px 26px; background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; box-shadow: var(--shadow);
}
.head-title { font-size: 20px; font-weight: 700; letter-spacing: .2px; }
.head-title .rid { font-weight: 400; color: var(--text-2); margin-left: 4px; }
.head-right { display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--text-3); }
.badge { padding: 4px 16px; border-radius: 999px; font-size: 13px; font-weight: 700; }
.badge-success { background: var(--ok-soft); color: var(--ok); }
.badge-failed { background: var(--err-soft); color: var(--err); }
.badge-running { background: var(--warn-soft); color: var(--warn); }

/* ===== 概览统计 ===== */
.overview {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 1px;
  background: var(--border); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; box-shadow: var(--shadow);
}
.metric { background: var(--card); padding: 12px 18px; min-width: 0; }
.metric-label { font-size: 11px; color: var(--text-3); margin-bottom: 2px; letter-spacing: .04em; }
.metric-value { font-size: 14px; font-weight: 600; word-break: break-all; }
/* 长文本（用例名/环境/项目等）单行截断 + title 悬浮全文：超长名称会把统计卡折成几十行、高度随名称无上限膨胀 */
.metric-value.to {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; word-break: keep-all;
}
.metric.hl .metric-value { color: var(--primary); font-size: 17px; }
.metric-value .pass-c { color: var(--ok); }

/* ===== 失败摘要卡 ===== */
.fail-card {
  border: 1px solid var(--primary-line); border-left: 4px solid var(--err);
  border-radius: 12px; background: var(--card); box-shadow: var(--shadow); overflow: hidden;
}
.fail-card-head {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 18px; font-size: 13px; font-weight: 700; color: var(--err);
  background: var(--err-soft);
}
.fail-item {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  padding: 9px 18px; border-top: 1px solid var(--border); cursor: pointer;
  transition: background .12s;
}
.fail-item:hover { background: var(--primary-soft); }
.fail-idx { font-size: 12px; font-weight: 700; color: var(--err); flex-shrink: 0; }
.fail-name { font-weight: 600; font-size: 13px; max-width: 40%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fail-why { font-size: 12px; color: var(--err); flex: 1; min-width: 200px; max-width: 100%; overflow-wrap: anywhere; }
.fail-count { font-size: 11px; color: var(--text-3); flex-shrink: 0; }

/* ===== 主体：左导航 + 右详情 ===== */
.layout { display: grid; grid-template-columns: var(--nav-w) 1fr; gap: 14px; align-items: start; }
@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }

/* 左侧导航 */
.nav {
  position: sticky; top: 16px; display: flex; flex-direction: column;
  max-height: calc(100vh - 32px); background: var(--card);
  border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow); overflow: hidden;
}
@media (max-width: 900px) { .nav { position: static; max-height: 340px; } }
.nav-tools { padding: 12px 12px 8px; display: flex; flex-direction: column; gap: 8px; border-bottom: 1px solid var(--border); }
.nav-search {
  width: 100%; padding: 7px 12px; font: inherit; font-size: 13px;
  border: 1px solid var(--border); border-radius: 8px; outline: none;
  background: var(--card-2); color: var(--text); transition: border-color .15s;
}
.nav-search:focus { border-color: var(--primary); }
.nav-search::placeholder { color: var(--text-3); }
.filters { display: flex; gap: 6px; }
.filter-btn {
  flex: 1; padding: 5px 0; font: inherit; font-size: 12px; font-weight: 600;
  border: 1px solid var(--border); border-radius: 8px; cursor: pointer;
  background: var(--card-2); color: var(--text-2); transition: all .13s;
}
.filter-btn.on { background: var(--primary); border-color: var(--primary); color: #fff; }
.filter-btn[data-f="failed"].on { background: var(--err); border-color: var(--err); }
.nav-list { overflow-y: auto; flex: 1; padding: 6px; }
.nav-empty { padding: 22px 10px; text-align: center; font-size: 12px; color: var(--text-3); }
.nav-item {
  display: flex; align-items: center; gap: 9px; width: 100%;
  padding: 8px 10px; border: none; border-radius: 9px; cursor: pointer;
  background: transparent; text-align: left; font: inherit; transition: background .12s;
}
.nav-item:hover { background: var(--primary-soft); }
.nav-item.active { background: var(--primary-soft); box-shadow: inset 0 0 0 1.5px var(--primary); }
.nav-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.nav-dot.success { background: var(--ok); }
.nav-dot.failed { background: var(--err); }
.nav-dot.running { background: var(--warn); }
.nav-dot.skipped, .nav-dot.none { background: var(--skip); }
.nav-body { min-width: 0; flex: 1; }
.nav-name { font-size: 13px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nav-sub { font-size: 11px; color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-family: Consolas, Menlo, monospace; }
.nav-meta { font-size: 11px; color: var(--text-3); flex-shrink: 0; text-align: right; }
.nav-meta .fail-n { color: var(--err); font-weight: 700; }
.nav-item.is-hidden { display: none; }

/* 右侧详情 */
.detail {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; box-shadow: var(--shadow); overflow: hidden;
}
.step-pane { display: none; }
.step-pane.active { display: block; }
.sp-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding: 16px 22px; border-bottom: 1px solid var(--border); }
.sp-title { display: flex; align-items: center; gap: 10px; font-size: 16px; font-weight: 700; min-width: 0; max-width: 100%; }
/* 步骤名单行截断（title 属性由服务端写入悬浮全文） */
.sp-title .sp-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sp-idx { display: inline-flex; align-items: center; justify-content: center; min-width: 34px; height: 26px; border-radius: 8px; background: var(--primary-soft); color: var(--primary); font-size: 13px; font-weight: 700; }
.sp-status { padding: 3px 14px; border-radius: 999px; font-size: 12px; font-weight: 700; }
.sp-status.success { background: var(--ok-soft); color: var(--ok); }
.sp-status.failed { background: var(--err-soft); color: var(--err); }
.sp-status.running { background: var(--warn-soft); color: var(--warn); }
.sp-status.skipped { background: var(--skip-soft); color: var(--skip); }
.sp-meta { display: flex; flex-wrap: wrap; gap: 6px 22px; padding: 10px 22px; font-size: 12px; color: var(--text-2); background: var(--card-2); border-bottom: 1px solid var(--border); }
.sp-meta em { font-style: normal; color: var(--text-3); margin-right: 4px; }
.sp-meta .mono { font-family: Consolas, Menlo, monospace; overflow-wrap: anywhere; }
/* 详情内 Tab（纯 radio 实现，无 JS 参与） */
.sp-tabs { display: flex; gap: 2px; padding: 8px 14px 0; border-bottom: 1px solid var(--border); }
.sp-tab {
  padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer;
  color: var(--text-2); border-bottom: 2px solid transparent; margin-bottom: -1px;
}
.sp-tab:hover { color: var(--text); }
.sp-pane { display: none; padding: 18px 22px; }
/* Tab 切换纯 CSS（radio 兄弟选择器，无 JS 参与）：radio 紧邻 sp-tabs 与 sp-panes 之前 */
input.sp-radio { display: none; }
.step-pane .sp-panes { position: relative; }
.step-pane[data-tabbed="1"] input.sp-radio-req:checked ~ .sp-panes .sp-pane-req { display: block; }
.step-pane[data-tabbed="1"] input.sp-radio-resp:checked ~ .sp-panes .sp-pane-resp { display: block; }
.step-pane[data-tabbed="1"] input.sp-radio-assert:checked ~ .sp-panes .sp-pane-assert { display: block; }
.step-pane[data-tabbed="1"] input.sp-radio-req:checked ~ .sp-tabs label[for].sp-tab-req,
.step-pane[data-tabbed="1"] input.sp-radio-resp:checked ~ .sp-tabs label.sp-tab-resp,
.step-pane[data-tabbed="1"] input.sp-radio-assert:checked ~ .sp-tabs label.sp-tab-assert {
  color: var(--primary); border-bottom-color: var(--primary);
}
.sec { margin-bottom: 16px; }
.sec-title { font-size: 12px; font-weight: 700; color: var(--text-2); letter-spacing: .05em; margin-bottom: 6px; padding-left: 9px; border-left: 3px solid var(--primary); }
.sec-empty { font-size: 12px; color: var(--text-3); padding: 10px 0 2px; }
.code-block {
  background: var(--code-bg); color: var(--text); padding: 12px 14px; border-radius: 9px;
  font-family: Consolas, Menlo, 'Liberation Mono', monospace; font-size: 12px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-all; overflow-x: auto;
  border: 1px solid var(--border);
}
.kv { font-size: 13px; }
.kv b { font-weight: 700; }

/* 断言表 */
.assert-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.assert-table th, .assert-table td { border: 1px solid var(--border); padding: 8px 10px; text-align: left; vertical-align: top; }
.assert-table th { background: var(--card-2); font-weight: 600; color: var(--text-2); }
.assert-table .pass { color: var(--ok); font-weight: 700; }
.assert-table .fail { color: var(--err); font-weight: 700; }
.assert-table tr.row-fail td { background: var(--err-soft); }
.assert-table .mono { font-family: Consolas, Menlo, monospace; font-size: 11px; }
.assert-table .muted { color: var(--text-3); }
.assert-table .fail-msg { color: var(--err); }

.foot { text-align: center; font-size: 11px; color: var(--text-3); padding: 4px 0 0; }

/* ===== 打印兜底：隐藏导航，全部步骤单列展开 ===== */
@media print {
  body { background: #fff; padding: 0; }
  .nav, .fail-item { display: none !important; }
  .layout { display: block; }
  .detail { border: none; box-shadow: none; }
  .step-pane { display: block !important; page-break-inside: avoid; border-bottom: 1px solid #ccc; margin-bottom: 12px; }
  .sp-pane { display: block !important; }
  .sp-tabs { display: none; }
}
"""

_REPORT_HTML_JS = """
(function () {
  'use strict';
  // 步骤数据（服务端渲染时内联，仅含导航/跳转所需的轻量字段）
  var navItems = Array.prototype.slice.call(document.querySelectorAll('.nav-item'));
  var panes = Array.prototype.slice.call(document.querySelectorAll('.step-pane'));
  var emptyTip = document.querySelector('.nav-empty');
  var filter = 'all', keyword = '';

  function applyFilter() {
    var visible = 0;
    navItems.forEach(function (it) {
      var okStatus = filter === 'all'
        || (filter === 'failed' && it.dataset.status !== 'success')
        || (filter === 'passed' && it.dataset.status === 'success');
      var kw = keyword.toLowerCase();
      var okKw = !kw
        || (it.dataset.name || '').toLowerCase().indexOf(kw) >= 0
        || (it.dataset.path || '').toLowerCase().indexOf(kw) >= 0
        || (it.dataset.method || '').toLowerCase().indexOf(kw) >= 0;
      var show = okStatus && okKw;
      it.classList.toggle('is-hidden', !show);
      if (show) visible++;
    });
    if (emptyTip) emptyTip.style.display = visible ? 'none' : 'block';
    // 当前选中步骤被过滤掉时，自动迁到第一个可见步骤
    var active = document.querySelector('.nav-item.active:not(.is-hidden)');
    if (!active) {
      var first = document.querySelector('.nav-item:not(.is-hidden)');
      if (first) select(first.dataset.step);
    }
  }

  function select(stepId) {
    navItems.forEach(function (it) { it.classList.toggle('active', it.dataset.step === stepId); });
    panes.forEach(function (p) { p.classList.toggle('active', p.dataset.step === stepId); });
  }

  navItems.forEach(function (it) {
    it.addEventListener('click', function () { select(it.dataset.step); });
  });

  var search = document.querySelector('.nav-search');
  if (search) search.addEventListener('input', function () { keyword = search.value.trim(); applyFilter(); });

  Array.prototype.forEach.call(document.querySelectorAll('.filter-btn'), function (btn) {
    btn.addEventListener('click', function () {
      Array.prototype.forEach.call(document.querySelectorAll('.filter-btn'), function (b) { b.classList.remove('on'); });
      btn.classList.add('on');
      filter = btn.dataset.f;
      applyFilter();
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll('.fail-item'), function (fi) {
    fi.addEventListener('click', function () {
      select(fi.dataset.step);
      var target = document.querySelector('.nav-item[data-step="' + fi.dataset.step + '"]');
      if (target && target.classList.contains('is-hidden')) {
        // 失败跳转目标被过滤隐藏时重置筛选，保证可达
        document.querySelector('.filter-btn[data-f="all"]').click();
        if (search) { search.value = ''; keyword = ''; applyFilter(); }
      }
      if (target) target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
  });

  // 失败优先：默认选中首个失败步骤（无失败选第 1 步）——与平台 ReportDetail 行为一致
  var firstFailed = document.querySelector('.nav-item[data-status]:not([data-status="success"])');
  var init = firstFailed || navItems[0];
  if (init) select(init.dataset.step);
})();
"""


def _step_id(s: Any, idx: int) -> str:
    """导航/详情联动的步骤标识（后端生成的稳定 key，规避原始 node_id 注入）"""
    return f"step-{idx + 1}"


def _summary_metric(label: str, value: Any, hl: bool = False, nowrap: bool = False) -> str:
    """概览统计项。nowrap=True 用于长文本（用例名等）：单行截断 + title 悬浮全文。

    超长名称若依赖 word-break 折行，统计卡高度会随名称长度无限膨胀（报告 #263 的回归）。
    """
    cls = "metric hl" if hl else "metric"
    if nowrap:
        return (f'<div class="{cls}"><div class="metric-label">{_esc(label)}</div>'
                f'<div class="metric-value to" title="{_esc(value)}">{_esc(value)}</div></div>')
    return f'<div class="{cls}"><div class="metric-label">{_esc(label)}</div><div class="metric-value">{value}</div></div>'


def _nav_item(s: Any, idx: int, sid: str) -> str:
    name = s.api_name or s.node_id or "未命名步骤"
    failed_asserts = sum(1 for a in (getattr(s, "assertions", None) or []) if not a.result)
    meta: list[str] = []
    if failed_asserts:
        meta.append(f'<span class="fail-n">{failed_asserts} 断言失败</span>')
    if s.response_time_ms is not None:
        meta.append(f"{round(s.response_time_ms)}ms")
    return (
        f'<button type="button" class="nav-item" data-step="{sid}" data-status="{_esc(s.status or "none")}" '
        f'data-name="{_esc(name)}" data-method="{_esc(s.api_method or "")}" data-path="{_esc(s.api_path or "")}" '
        f'title="{_esc(name)}&#10;{_esc(s.api_method or "")} {_esc(s.api_path or "")}">'
        f'<span class="nav-dot {_esc(s.status or "none")}"></span>'
        f'<span class="nav-body"><span class="nav-name">{_esc(name)}</span>'
        f'<span class="nav-sub">{_esc((s.api_method or "") + " " + (s.api_path or ""))}</span></span>'
        f'<span class="nav-meta">{"".join(meta)}</span></button>'
    )


def _json_sec(title: str, val: Any) -> str:
    if val is None:
        return f'<div class="sec"><div class="sec-title">{_esc(title)}</div><div class="sec-empty">无</div></div>'
    return (f'<div class="sec"><div class="sec-title">{_esc(title)}</div>'
            f'<pre class="code-block">{_esc(_fmt_json(val))}</pre></div>')


def _step_pane(s: Any, idx: int, sid: str) -> str:
    name = s.api_name or s.node_id or "未命名步骤"
    assertions = getattr(s, "assertions", None) or []
    p: list[str] = []
    p.append(f'<section class="step-pane" data-step="{sid}" data-tabbed="1">')

    # 头部（步骤名单行截断 + title 悬浮全文）
    p.append('<div class="sp-head">')
    p.append(f'<div class="sp-title"><span class="sp-idx">#{idx + 1}</span>'
             f'<span class="sp-name" title="{_esc(name)}">{_esc(name)}</span>'
             f'<span class="sp-status {_esc(s.status or "none")}">{_esc(_step_status_text(s.status))}</span></div>')
    p.append("</div>")

    # meta 行
    p.append('<div class="sp-meta">')
    p.append(f'<span><em>请求</em><span class="mono">{_esc(s.api_method or "")} {_esc(s.api_path or "")}</span></span>')
    p.append(f'<span><em>HTTP</em>{_esc(s.response_status if s.response_status is not None else "-")}</span>')
    p.append(f'<span><em>耗时</em>{_esc(s.response_time_ms if s.response_time_ms is not None else "-")} ms</span>')
    p.append(f'<span><em>开始</em>{_esc(s.started_at or "-")}</span>')
    p.append(f'<span><em>结束</em>{_esc(s.ended_at or "-")}</span>')
    p.append("</div>")

    # Tabs（radio 实现：选中态纯 CSS，无 JS 依赖；顺序 radio → tabs → panes 满足兄弟选择器）
    p.append(f'<input type="radio" name="tab-{sid}" class="sp-radio sp-radio-req" id="tab-{sid}-req" checked>')
    p.append(f'<input type="radio" name="tab-{sid}" class="sp-radio sp-radio-resp" id="tab-{sid}-resp">')
    p.append(f'<input type="radio" name="tab-{sid}" class="sp-radio sp-radio-assert" id="tab-{sid}-as">')
    p.append('<div class="sp-tabs">')
    p.append(f'<label class="sp-tab sp-tab-req" for="tab-{sid}-req">请求</label>')
    p.append(f'<label class="sp-tab sp-tab-resp" for="tab-{sid}-resp">响应</label>')
    p.append(f'<label class="sp-tab sp-tab-assert" for="tab-{sid}-as">断言（{len(assertions)}）</label>')
    p.append("</div>")

    # 请求
    p.append('<div class="sp-panes">')
    p.append(f'<div class="sp-pane sp-pane-req">{_json_sec("请求头", s.request_headers)}{_json_sec("请求体", s.request_body)}</div>')
    # 响应
    resp = (f'<div class="sp-pane sp-pane-resp">'
            f'<div class="sec"><div class="sec-title">状态码</div>'
            f'<span class="kv"><b>{_esc(s.response_status if s.response_status is not None else "-")}</b></span></div>'
            f'<div class="sec"><div class="sec-title">响应耗时</div>'
            f'<span class="kv"><b>{_esc(s.response_time_ms if s.response_time_ms is not None else "-")} ms</b></span></div>'
            f'{_json_sec("响应体", s.response_body)}</div>')
    p.append(resp)
    # 断言
    if assertions:
        rows: list[str] = []
        for a in assertions:
            rows.append(f'<tr class="{"" if a.result else "row-fail"}">')
            rows.append(f'<td class="{"pass" if a.result else "fail"}">{"✓ 通过" if a.result else "✗ 失败"}</td>')
            rows.append(f"<td>{_esc(a.rule_type)}</td>")
            rows.append(f'<td class="mono">{_esc(a.actual_value if a.actual_value is not None else "—")}</td>')
            rows.append(f'<td class="mono">{_esc(a.expected_value if a.expected_value is not None else "—")}</td>')
            rows.append(f'<td class="{"muted" if a.result else "fail-msg"}">{_esc(a.message if a.message is not None else "—")}</td>')
            rows.append("</tr>")
        p.append('<div class="sp-pane sp-pane-assert">')
        p.append('<table class="assert-table"><thead><tr><th>结果</th><th>类型</th><th>实际值</th><th>期望值</th><th>消息</th></tr></thead>')
        p.append("".join(rows))
        p.append("</table></div>")
    else:
        p.append('<div class="sp-pane sp-pane-assert"><div class="sec-empty">该步骤无断言</div></div>')
    p.append("</div>")  # /sp-panes
    p.append("</section>")
    return "".join(p)


def _fail_card(steps: list[Any], sid_of: Any) -> str:
    """失败摘要卡：每个失败步骤一条（含首条失败断言消息），点击跳转"""
    failed = [i for i, s in enumerate(steps) if s.status != "success"]
    if not failed:
        return ""
    items: list[str] = []
    for i in failed:
        s = steps[i]
        name = s.api_name or s.node_id or "未命名步骤"
        failed_asserts = [a for a in (getattr(s, "assertions", None) or []) if not a.result]
        why = (failed_asserts[0].message or failed_asserts[0].rule_type) if failed_asserts else (s.status or "失败")
        items.append(
            f'<div class="fail-item" data-step="{sid_of(i)}">'
            f'<span class="fail-idx">#{i + 1}</span>'
            f'<span class="fail-name" title="{_esc(name)}">{_esc(name)}</span>'
            f'<span class="fail-why" title="{_esc(why)}">{_esc(_step_status_text(s.status))} · {_esc(why)}</span>'
            f'<span class="fail-count">{len(failed_asserts)} 条断言失败</span></div>'
        )
    return (f'<div class="fail-card"><div class="fail-card-head">'
            f'✗ 失败摘要 · {len(failed)} 个步骤未通过（点击跳转）</div>'
            f'{"".join(items)}</div>')


def export_report_html(record: Any, steps: list[Any]) -> str:
    """执行记录 + 步骤 → 自包含 HTML 报告文本（Allure 式导航布局，见模块 docstring）。"""
    sid_of = lambda i: _step_id(steps[i], i)

    parts: list[str] = []
    parts.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    parts.append(f"<title>执行报告 #{_esc(record.id)}</title>")
    parts.append(f"<style>{_REPORT_HTML_CSS}</style>")
    parts.append("</head><body>")
    parts.append('<div class="wrap">')

    # 报告头
    parts.append('<header class="head">')
    parts.append(f'<div class="head-title">执行报告<span class="rid">#{_esc(record.id)}</span></div>')
    parts.append('<div class="head-right">')
    parts.append(f'<span class="badge badge-{_esc(record.status)}">{_esc(_status_text(record.status))}</span>')
    parts.append(f"<span>生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>")
    parts.append("</div></header>")

    # 概览统计
    passed = sum(1 for s in steps if s.status == "success")
    assertion_total = sum(len(getattr(s, "assertions", None) or []) for s in steps)
    assertion_passed = sum(
        1 for s in steps for a in (getattr(s, "assertions", None) or []) if a.result
    )
    t0, t1 = _parse_dt(record.started_at), _parse_dt(record.ended_at)
    duration = _fmt_duration_ms((t1 - t0) * 1000) if t0 is not None and t1 is not None else "-"

    parts.append('<section class="overview">')
    parts.append(_summary_metric("用例", record.case_name or f"#{record.case_id}", nowrap=True))
    parts.append(_summary_metric("环境", record.env_name or f"#{record.env_id}", nowrap=True))
    parts.append(_summary_metric("项目", record.project_name or "—", nowrap=True))
    parts.append(_summary_metric("执行人", record.created_by_name or "—", nowrap=True))
    parts.append(_summary_metric("步骤", f'<span class="pass-c">{passed}</span> / {len(steps)}', True))
    parts.append(_summary_metric("断言", f'<span class="pass-c">{assertion_passed}</span> / {assertion_total}', True))
    parts.append(_summary_metric("耗时", _esc(duration), True))
    parts.append(_summary_metric("开始时间", record.started_at or "—", nowrap=True))
    parts.append("</section>")

    # 失败摘要卡（仅失败时渲染）
    parts.append(_fail_card(steps, sid_of))

    # 主体：左导航 + 右详情
    parts.append('<div class="layout">')
    parts.append('<nav class="nav">')
    parts.append('<div class="nav-tools">')
    parts.append('<input class="nav-search" type="search" placeholder="搜索步骤名 / 方法 / 路径…">')
    parts.append('<div class="filters">')
    parts.append('<button type="button" class="filter-btn on" data-f="all">全部</button>')
    parts.append('<button type="button" class="filter-btn" data-f="failed">失败</button>')
    parts.append('<button type="button" class="filter-btn" data-f="passed">通过</button>')
    parts.append("</div></div>")
    parts.append('<div class="nav-list">')
    for idx, s in enumerate(steps):
        parts.append(_nav_item(s, idx, sid_of(idx)))
    parts.append('<div class="nav-empty" style="display:none">无匹配步骤</div>')
    parts.append("</div></nav>")
    parts.append('<main class="detail">')
    for idx, s in enumerate(steps):
        parts.append(_step_pane(s, idx, sid_of(idx)))
    if not steps:
        parts.append('<div class="sec-empty" style="padding:30px">暂无步骤数据</div>')
    parts.append("</main></div>")

    parts.append(f'<footer class="foot">由 fin-api-test 平台生成 · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</footer>')
    parts.append("</div>")
    parts.append(f"<script>{_REPORT_HTML_JS}</script>")
    parts.append("</body></html>")
    return "".join(parts)
