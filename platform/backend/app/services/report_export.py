"""报告导出：CSV/HTML 组装（纯函数，输入 ORM 记录，输出字符串）。

从前端 ReportDetail.vue 的 exportCsv/exportHtml 下沉，
使 CI/定时任务等非交互方可复用导出能力。

HTML 报告为档案风（Dossier）导航布局（左侧卷内目录 + 右侧卷宗详情 Tabs）：
- 失败优先：顶部未通过核查单 + 默认选中首个失败步骤
- 封皮：双规线 + 衬线大标题 + 状态印章（印泥三色：通过绿/失败红/执行中琥珀）+ 打印存档入口
- 内嵌无依赖 JS：搜索过滤 / 状态筛选 / 导航跳转（约 100 行）
- 自带深浅双套 CSS 变量（prefers-color-scheme：纸面档案 / 暗夜档案），--primary 保留系统蓝
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
/* 档案风变量：纸色 + 墨字 + 印泥三色（通过/失败/执行中）；--primary 保留系统蓝作链接/交互辅助色 */
:root {
  --primary: #0071e3; --primary-soft: rgba(0,113,227,.08); --primary-line: rgba(0,113,227,.35);
  --bg: #edeae0; --card: #faf8f1; --card-2: #f1eee3; --border: #d6cfbd;
  --rule: #a89f8a; --ink: #2b281f;
  --text: #2b281f; --text-2: #6f6959; --text-3: #9a937f;
  --ok: #1e7e4e; --ok-soft: rgba(30,126,78,.10);
  --err: #c23a2b; --err-soft: rgba(194,58,43,.08);
  --warn: #a8742a; --warn-soft: rgba(168,116,42,.10);
  --skip: #8b8574; --skip-soft: rgba(139,133,116,.12);
  --code-bg: #f4eeda; --shadow: 0 1px 2px rgba(60,52,30,.08), 0 6px 18px rgba(60,52,30,.05);
  --nav-w: 300px;
  --serif: Georgia, 'Times New Roman', 'Noto Serif SC', 'Songti SC', 'SimSun', serif;
  --mono: Consolas, Menlo, 'Liberation Mono', monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #191a17; --card: #232420; --card-2: #1d1e1b; --border: #38392f;
    --rule: #555748; --ink: #ece9dd;
    --text: #ece9dd; --text-2: #a8a390; --text-3: #7c7765;
    --ok: #4cc38a; --err: #ff6a5a; --warn: #e0a94f;
    --ok-soft: rgba(76,195,138,.12); --err-soft: rgba(255,106,90,.12);
    --warn-soft: rgba(224,169,79,.13); --skip-soft: rgba(139,133,116,.16);
    --primary-soft: rgba(10,132,255,.16); --primary-line: rgba(10,132,255,.45);
    --code-bg: #1c1d18; --shadow: none;
  }
}
html { font-size: 15px; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg); color: var(--text); padding: 24px 16px 40px; line-height: 1.65;
}
.wrap { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }

/* ===== 档案封皮（粗顶线 + 细规线双规，衬线大标题，右侧状态印章） ===== */
.head {
  position: relative; display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 16px; padding: 24px 30px 20px;
  background: var(--card); border: 1px solid var(--border); border-top: 4px solid var(--ink);
  border-radius: 4px; box-shadow: var(--shadow);
}
.head::before { content: ''; position: absolute; left: 0; right: 0; top: 6px; border-top: 1px solid var(--rule); }
.head-main { min-width: 0; }
.eyebrow { font-size: 10px; letter-spacing: .3em; font-weight: 600; color: var(--text-3); margin-bottom: 7px; }
.head-title { font-family: var(--serif); font-size: 30px; font-weight: 700; letter-spacing: .02em; line-height: 1.25; }
.head-title .rid { font-family: var(--mono); font-size: 17px; font-weight: 500; color: var(--text-2); margin-left: 10px; }
.head-notes { margin-top: 9px; font-size: 12px; color: var(--text-2); font-family: var(--mono); }
.head-side { display: flex; align-items: center; gap: 20px; }
/* 状态印章：双圈 + 印泥色 + 轻微旋转（盖印感） */
.badge {
  width: 88px; height: 88px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; position: relative;
  border: 2.5px solid currentColor; transform: rotate(-8deg);
  font-family: var(--serif); font-size: 19px; font-weight: 700; letter-spacing: .18em; text-indent: .18em;
}
.badge::after { content: ''; position: absolute; inset: 4px; border: 1px solid currentColor; border-radius: 50%; opacity: .5; }
.badge-success { color: var(--ok); background: var(--ok-soft); }
.badge-failed { color: var(--err); background: var(--err-soft); }
.badge-running { color: var(--warn); background: var(--warn-soft); }
.print-btn {
  font: inherit; font-size: 12px; letter-spacing: .08em; padding: 8px 16px; cursor: pointer;
  border: 1px solid var(--rule); border-radius: 3px; background: transparent; color: var(--text-2);
  transition: all .15s;
}
.print-btn:hover { color: var(--text); border-color: var(--text); }

/* ===== 著录项（概览统计） ===== */
.overview {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1px;
  background: var(--border); border: 1px solid var(--border); border-radius: 4px; overflow: hidden; box-shadow: var(--shadow);
}
.metric { background: var(--card); padding: 13px 18px 11px; min-width: 0; }
.metric-label { font-size: 10px; color: var(--text-3); margin-bottom: 4px; letter-spacing: .18em; }
.metric-value { font-family: var(--serif); font-size: 15px; font-weight: 700; word-break: break-all; }
/* 长文本（用例名/环境/项目等）单行截断 + title 悬浮全文：超长名称会把统计卡折成几十行、高度随名称无上限膨胀 */
.metric-value.to {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; word-break: keep-all;
}
.metric.hl .metric-value { color: var(--ink); font-size: 19px; }
.metric-value .pass-c { color: var(--ok); }

/* ===== 未通过核查单（失败摘要卡） ===== */
.fail-card {
  border: 1px solid var(--border); border-left: 5px solid var(--err);
  border-radius: 4px; background: var(--card); box-shadow: var(--shadow); overflow: hidden;
}
.fail-card-head {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 18px; font-size: 13px; font-weight: 700; color: var(--err);
  background: var(--err-soft); letter-spacing: .05em; border-bottom: 1px solid var(--border);
}
.fail-item {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  padding: 9px 18px; border-top: 1px solid var(--border); cursor: pointer;
  transition: background .12s;
}
.fail-item:first-of-type { border-top: none; }
.fail-item:hover { background: var(--code-bg); }
.fail-idx { font-size: 12px; font-weight: 700; color: var(--err); flex-shrink: 0; font-family: var(--mono); }
.fail-name { font-weight: 600; font-size: 13px; max-width: 40%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fail-why { font-size: 12px; color: var(--err); flex: 1; min-width: 200px; max-width: 100%; overflow-wrap: anywhere; }
.fail-count { font-size: 11px; color: var(--text-3); flex-shrink: 0; }

/* ===== 契约出入提示卡（黄条同构：只标注不阻断，2026-10-10 定案 Q3） ===== */
.contract-card {
  border: 1px solid var(--border); border-left: 5px solid var(--warn);
  border-radius: 4px; background: var(--card); box-shadow: var(--shadow); overflow: hidden;
}
.contract-card-head {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 18px; font-size: 13px; font-weight: 700; color: var(--warn);
  background: var(--warn-soft); letter-spacing: .05em; border-bottom: 1px solid var(--border);
}
.contract-item {
  padding: 8px 18px; font-size: 12px; line-height: 1.8; border-top: 1px solid var(--border);
  overflow-wrap: anywhere;
}
.contract-item:first-of-type { border-top: none; }
.contract-tip {
  padding: 7px 18px; font-size: 11px; color: var(--text-3); border-top: 1px dashed var(--border);
}

/* ===== 主体：左卷内目录 + 右卷宗详情 ===== */
.layout { display: grid; grid-template-columns: var(--nav-w) 1fr; gap: 14px; align-items: start; }
@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }

/* 左侧导航（档案盒标签头 + 索引目录） */
.nav {
  position: sticky; top: 16px; display: flex; flex-direction: column;
  max-height: calc(100vh - 32px); background: var(--card);
  border: 1px solid var(--border); border-radius: 4px; box-shadow: var(--shadow); overflow: hidden;
}
@media (max-width: 900px) { .nav { position: static; max-height: 340px; } }
.nav-cap {
  display: flex; align-items: baseline; justify-content: space-between;
  background: #2c2a24; color: #efe9d8; padding: 9px 16px;
  font-size: 12px; font-weight: 700; letter-spacing: .22em;
}
.nav-cap .nav-cap-n { font-family: var(--mono); font-size: 11px; font-weight: 500; letter-spacing: 0; color: #b5ae97; }
.nav-tools { padding: 12px 12px 8px; display: flex; flex-direction: column; gap: 8px; border-bottom: 1px solid var(--border); }
.nav-search {
  width: 100%; padding: 7px 12px; font: inherit; font-size: 13px;
  border: 1px solid var(--border); border-radius: 3px; outline: none;
  background: var(--card-2); color: var(--text); transition: border-color .15s;
}
.nav-search:focus { border-color: var(--ink); }
.nav-search::placeholder { color: var(--text-3); }
.filters { display: flex; gap: 6px; }
.filter-btn {
  flex: 1; padding: 5px 0; font: inherit; font-size: 12px; font-weight: 600;
  border: 1px solid var(--border); border-radius: 3px; cursor: pointer;
  background: var(--card-2); color: var(--text-2); transition: all .13s;
}
.filter-btn.on { background: var(--ink); border-color: var(--ink); color: var(--bg); }
.filter-btn[data-f="failed"].on { background: var(--err); border-color: var(--err); color: #fff; }
.nav-list { overflow-y: auto; flex: 1; padding: 6px; }
.nav-empty { padding: 22px 10px; text-align: center; font-size: 12px; color: var(--text-3); }
.nav-item {
  display: flex; align-items: center; gap: 9px; width: 100%;
  padding: 8px 10px; border: none; border-radius: 3px; cursor: pointer;
  background: transparent; text-align: left; font: inherit; transition: background .12s;
}
.nav-item:hover { background: var(--code-bg); }
.nav-item.active { background: var(--code-bg); box-shadow: inset 3px 0 0 var(--ink); }
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

/* 右侧详情（卷宗卡片） */
.detail {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 4px; box-shadow: var(--shadow);
  /* overflow 改 visible：让内部 .sp-sticky 能相对视口固定（hidden 会成为 scroll container 截断 sticky） */
  overflow: visible;
}
/* 步骤标题区粘顶：节点名 + meta + Tab 栏滚动时常驻视口顶部 */
.sp-sticky {
  position: sticky; top: 0; z-index: 10; background: var(--card);
  border-radius: 4px 4px 0 0;
}
.step-pane { display: none; }
.step-pane.active { display: block; }
.sp-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding: 16px 22px; border-bottom: 1px solid var(--border); }
.sp-title { display: flex; align-items: center; gap: 10px; font-size: 16px; font-weight: 700; min-width: 0; max-width: 100%; }
/* 步骤名单行截断（title 属性由服务端写入悬浮全文） */
.sp-title .sp-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sp-idx {
  display: inline-flex; align-items: center; justify-content: center; min-width: 40px; height: 26px;
  border-radius: 3px; background: var(--ink); color: var(--bg);
  font-family: var(--mono); font-size: 12px; font-weight: 700; letter-spacing: .04em;
}
.sp-status { padding: 3px 13px; border-radius: 3px; font-size: 12px; font-weight: 700; letter-spacing: .06em; }
.sp-status.success { background: var(--ok-soft); color: var(--ok); }
.sp-status.failed { background: var(--err-soft); color: var(--err); }
.sp-status.running { background: var(--warn-soft); color: var(--warn); }
.sp-status.skipped { background: var(--skip-soft); color: var(--skip); }
.sp-meta { display: flex; flex-wrap: wrap; gap: 6px 22px; padding: 10px 22px; font-size: 12px; color: var(--text-2); background: var(--card-2); border-bottom: 1px solid var(--border); }
.sp-meta em { font-style: normal; color: var(--text-3); margin-right: 4px; }
.sp-meta .mono { font-family: Consolas, Menlo, monospace; overflow-wrap: anywhere; }
/* 详情内 Tab（纯 radio 实现，无 JS 参与）——索引签样式：选中纸黄底 + 顶墨线 */
.sp-tabs { display: flex; gap: 2px; padding: 8px 14px 0; border-bottom: 1px solid var(--border); }
.sp-tab {
  padding: 7px 18px; font-size: 13px; font-weight: 600; cursor: pointer;
  color: var(--text-2); border: 1px solid transparent; border-bottom: 2px solid transparent;
  border-radius: 4px 4px 0 0; margin-bottom: -1px;
}
.sp-tab:hover { color: var(--text); }
.sp-pane { display: none; padding: 18px 22px; }
/* Tab 切换用 :has() 取代 ~ 兄弟选择器：radio 与 sp-tabs 同处 .sp-sticky 内、
   sp-panes 在 .sp-sticky 外（包容器粘顶时不影响兄弟关系判断） */
input.sp-radio { display: none; }
.step-pane .sp-panes { position: relative; }
.step-pane[data-tabbed="1"]:has(input.sp-radio-req:checked) .sp-pane-req,
.step-pane[data-tabbed="1"]:has(input.sp-radio-resp:checked) .sp-pane-resp,
.step-pane[data-tabbed="1"]:has(input.sp-radio-extract:checked) .sp-pane-extract,
.step-pane[data-tabbed="1"]:has(input.sp-radio-assert:checked) .sp-pane-assert { display: block; }
.step-pane[data-tabbed="1"]:has(input.sp-radio-req:checked) .sp-tabs label.sp-tab-req,
.step-pane[data-tabbed="1"]:has(input.sp-radio-resp:checked) .sp-tabs label.sp-tab-resp,
.step-pane[data-tabbed="1"]:has(input.sp-radio-extract:checked) .sp-tabs label.sp-tab-extract,
.step-pane[data-tabbed="1"]:has(input.sp-radio-assert:checked) .sp-tabs label.sp-tab-assert {
  color: var(--text); background: var(--code-bg); border-bottom-color: var(--code-bg);
  box-shadow: inset 0 2px 0 var(--ink);
}
.sec { margin-bottom: 16px; }
.sec-title { font-size: 11px; font-weight: 700; color: var(--text-2); letter-spacing: .14em; margin-bottom: 6px; padding-left: 9px; border-left: 3px solid var(--ink); }
.sec-empty { font-size: 12px; color: var(--text-3); padding: 10px 0 2px; }
.code-block {
  background: var(--code-bg); color: var(--text); padding: 12px 14px; border-radius: 3px;
  font-family: var(--mono); font-size: 12px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-all; overflow-x: auto;
  border: 1px solid var(--border); border-left: 3px solid var(--rule);
}
.kv { font-size: 13px; }
.kv b { font-weight: 700; }

/* 断言表（档案台账：细线 + 表头字距） */
.assert-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.assert-table th, .assert-table td { border: 1px solid var(--border); padding: 8px 10px; text-align: left; vertical-align: top; }
.assert-table th { background: var(--card-2); font-weight: 600; font-size: 10px; letter-spacing: .12em; color: var(--text-2); }
.assert-table .pass { color: var(--ok); font-weight: 700; }
.assert-table .fail { color: var(--err); font-weight: 700; }
.assert-table tr.row-fail td { background: var(--err-soft); }
.assert-table .mono { font-family: var(--mono); font-size: 11px; }
.assert-table .muted { color: var(--text-3); }
.assert-table .fail-msg { color: var(--err); }
.assert-table .fail-text { color: var(--err); }

.foot { text-align: center; font-size: 11px; color: var(--text-3); padding: 10px 0 0; border-top: 1px solid var(--border); }

/* ===== 打印兜底：隐藏导航/按钮，全部步骤单列展开（印章随纸面落档） ===== */
@media print {
  body { background: #fff; padding: 0; }
  .nav, .fail-item, .print-btn { display: none !important; }
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


# ===== 后置提取展示辅助（文案与前端 ReportDetail 一致；_value_text 供提取值展示复用） =====

def _value_text(v: Any) -> str:
    """快照值为执行时规则原文：字符串原样（可含 ${} 引用），对象/数组 JSON 化，None 显示 '—'"""
    if v is None:
        return "—"
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        return str(v)


def _extract_pane(post_extract: list[Any], extracted_vars: Any) -> str:
    """提取 Tab：变量名 / 来源 / 规则 / 实际提取结果（规则失败或值缺失时明确标注）"""
    if not post_extract:
        return '<div class="sp-pane sp-pane-extract"><div class="sec-empty">该步骤无提取规则</div></div>'
    vars_dict = extracted_vars if isinstance(extracted_vars, dict) else {}
    rows: list[str] = []
    for r in post_extract:
        if not isinstance(r, dict):
            continue
        name = r.get("name")
        if r.get("source") == "db":
            rule = r.get("sql") or "—"
            if r.get("field"):
                rule = f"{rule} → {r['field']}"
        else:
            rule = r.get("json_path") or "—"
        has = name is not None and name in vars_dict
        val = vars_dict.get(name)
        if has and isinstance(val, dict) and "__error__" in val:
            # 提取未取到：值本身就是 {__error__: 原因}（引擎判节点失败）
            actual = f'<span class="fail-text">未提取到：{_esc(str(val["__error__"]))}</span>'
        elif has:
            actual = f'<span class="mono">{_esc(_value_text(val))}</span>'
        else:
            actual = '<span class="muted">未提取到</span>'
        rows.append("<tr>"
                    f'<td class="mono">{_esc(name if name is not None else "—")}</td>'
                    f"<td>{'数据库' if r.get('source') == 'db' else '响应'}</td>"
                    f'<td class="mono">{_esc(rule)}</td>'
                    f"<td>{actual}</td></tr>")
    return ('<div class="sp-pane sp-pane-extract">'
            '<table class="assert-table"><thead><tr><th>变量名</th><th>来源</th><th>规则</th><th>提取结果</th></tr></thead>'
            + "".join(rows) + "</table></div>")


def _step_pane(s: Any, idx: int, sid: str) -> str:
    name = s.api_name or s.node_id or "未命名步骤"
    assertions = getattr(s, "assertions", None) or []
    post_extract = getattr(s, "post_extract", None) or []
    extracted_vars = getattr(s, "extracted_vars", None) or {}
    p: list[str] = []
    p.append(f'<section class="step-pane" data-step="{sid}" data-tabbed="1">')

    # 标题区粘顶容器：节点名 + meta + Tab 栏滚动时常驻视口顶部
    p.append('<div class="sp-sticky">')

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

    # Tabs（radio 实现：选中态用 :has() 纯 CSS，无 JS 依赖；radio 与 sp-tabs 同在 sp-sticky 内）
    p.append(f'<input type="radio" name="tab-{sid}" class="sp-radio sp-radio-req" id="tab-{sid}-req" checked>')
    p.append(f'<input type="radio" name="tab-{sid}" class="sp-radio sp-radio-resp" id="tab-{sid}-resp">')
    p.append(f'<input type="radio" name="tab-{sid}" class="sp-radio sp-radio-extract" id="tab-{sid}-ex">')
    p.append(f'<input type="radio" name="tab-{sid}" class="sp-radio sp-radio-assert" id="tab-{sid}-as">')
    p.append('<div class="sp-tabs">')
    p.append(f'<label class="sp-tab sp-tab-req" for="tab-{sid}-req">请求</label>')
    p.append(f'<label class="sp-tab sp-tab-resp" for="tab-{sid}-resp">响应</label>')
    p.append(f'<label class="sp-tab sp-tab-extract" for="tab-{sid}-ex">提取（{len(post_extract)}）</label>')
    p.append(f'<label class="sp-tab sp-tab-assert" for="tab-{sid}-as">断言（{len(assertions)}）</label>')
    p.append("</div>")

    p.append("</div>")  # /sp-sticky

    # 请求（前置处理快照不再展示：配置原文与请求体重复，信息噪音大于价值）
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
    # 提取
    p.append(_extract_pane(post_extract, extracted_vars))
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


def _contract_card(record: Any, steps: list[Any]) -> str:
    """契约出入卡（与报告页黄条同构）：summary.contract_gaps = {节点ID: {missing/extra}}。

    只标注不阻断（2026-10-10 定案 Q3）；节点名取步骤名（api_name 优先）。
    """
    gaps = (getattr(record, "summary", None) or {}).get("contract_gaps")
    if not isinstance(gaps, dict) or not gaps:
        return ""
    name_of = {s.node_id: (s.api_name or s.node_id) for s in steps}
    items: list[str] = []
    for nid, g in gaps.items():
        if not isinstance(g, dict):
            continue
        seg: list[str] = []
        missing = [str(m) for m in (g.get("missing") or [])]
        extra = [e for e in (g.get("extra") or []) if isinstance(e, dict)]
        if missing:
            seg.append(f'{len(missing)} 个字段未配置（{_esc("、".join(missing))}），已按空值占位发送')
        if extra:
            paths = _esc("、".join(str(e.get("path")) for e in extra))
            has_dyn = any(e.get("dynamic") for e in extra)
            seg.append(f'携带契约外参数 {paths}（{"含动态来源" if has_dyn else "接口已无这些字段"}）')
        if not seg:
            continue
        items.append(f'<div class="contract-item"><b>{_esc(name_of.get(nid, nid))}</b>：{"；".join(seg)}</div>')
    if not items:
        return ""
    return (f'<div class="contract-card"><div class="contract-card-head">'
            f'⚠ 请求参数与接口契约有出入（只标注，不影响结论判定）</div>'
            f'{"".join(items)}'
            f'<div class="contract-tip">字段增删请到「接口管理」维护，保存时可一键同步到所有数据集；数据集页保存节点时也会提示同步。</div></div>')


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

    # 档案封皮：眉题 + 衬线大标题 + 归档时间，右侧状态印章与打印入口
    parts.append('<header class="head">')
    parts.append('<div class="head-main">')
    parts.append('<div class="eyebrow">FIN-API-TEST · EXECUTION ARCHIVE</div>')
    parts.append(f'<div class="head-title">执行报告<span class="rid">#{_esc(record.id)}</span></div>')
    parts.append(f'<div class="head-notes">归档于 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>')
    parts.append("</div>")
    parts.append('<div class="head-side">')
    parts.append(f'<span class="badge badge-{_esc(record.status)}">{_esc(_status_text(record.status))}</span>')
    parts.append('<button type="button" class="print-btn" onclick="window.print()">打印 / 存档 PDF</button>')
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
    pass_rate = f"{round(passed / len(steps) * 100)}%" if steps else "—"
    parts.append(_summary_metric("通过率", pass_rate, True))
    parts.append(_summary_metric("耗时", _esc(duration), True))
    parts.append(_summary_metric("开始时间", record.started_at or "—", nowrap=True))
    parts.append("</section>")

    # 失败摘要卡（仅失败时渲染）
    parts.append(_fail_card(steps, sid_of))
    # 契约出入提示卡（有出入时渲染）
    parts.append(_contract_card(record, steps))

    # 主体：左导航 + 右详情
    parts.append('<div class="layout">')
    parts.append('<nav class="nav">')
    parts.append(f'<div class="nav-cap">卷内目录<span class="nav-cap-n">{len(steps)} 步</span></div>')
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
