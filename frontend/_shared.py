"""前端各页面共用的工具函数 / 样式片段 / session_state 访问.

约定:
- 任何页面都不直接访问后端, 必须经 ``api_client.ApiClient``.
- 任何页面都不直接读 ``st.session_state['xxx']`` 拼写, 走本模块的 getter.
- 全站使用同一套 CSS 主题 (industrial / clinical) , 通过 ``inject_theme`` 注入.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import streamlit as st

from frontend.api_client import ApiClient

# ---------------- 主题 ----------------

_THEME_CSS = """
<style>
  /* ===== Editorial / Clinical 浅色主题 ===== */
  :root {
    --md-bg: #f8f6f1;
    --md-bg-2: #efece4;
    --md-panel: #ffffff;
    --md-panel-2: #f3efe6;
    --md-line: #e4ddcd;
    --md-line-strong: #c9bfa8;
    --md-text: #1d2825;
    --md-text-dim: #6a6356;
    --md-text-faint: #9c9582;
    --md-accent: #1f4d46;        /* 墨绿 主色 */
    --md-accent-2: #2c7569;      /* 浅墨绿 */
    --md-accent-warm: #8a6d3b;   /* 暖棕 */
    --md-danger: #b8443a;
    --md-ok: #3f7a5a;
    --md-serif: 'Iowan Old Style','Noto Serif SC','Source Han Serif SC','Georgia',serif;
    --md-sans: -apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
  }
  html, body, [class*="css"], .stApp, .stMarkdown, .stText {
    color: var(--md-text); font-family: var(--md-sans);
  }
  .stApp {
    background:
      radial-gradient(1200px 600px at 90% -10%, rgba(31,77,70,.06), transparent 60%),
      radial-gradient(900px 500px at -10% 110%, rgba(138,109,59,.06), transparent 60%),
      var(--md-bg);
  }
  /* 让 Streamlit 默认控件适配浅色 */
  .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
    background: var(--md-panel) !important; color: var(--md-text) !important;
    border: 1px solid var(--md-line) !important; border-radius: 6px !important;
  }
  .stButton > button {
    border-radius: 4px; border: 1px solid var(--md-accent);
    background: var(--md-accent); color: #fdfaf2;
    font-weight: 500; letter-spacing: .04em; padding: .55rem 1.2rem;
    transition: background .18s ease, transform .18s ease;
  }
  .stButton > button:hover { background: var(--md-accent-2); border-color: var(--md-accent-2); }
  .stButton > button:active { transform: translateY(1px); }
  .stExpander { border: 1px solid var(--md-line) !important; border-radius: 6px !important;
                background: var(--md-panel) !important; }
  .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--md-line); }
  .stTabs [data-baseweb="tab"] {
    background: transparent; color: var(--md-text-dim);
    border: none; border-bottom: 2px solid transparent;
    padding: 8px 14px; font-weight: 500; letter-spacing: .06em;
  }
  .stTabs [aria-selected="true"] { color: var(--md-accent); border-bottom-color: var(--md-accent); }
  hr { border-color: var(--md-line) !important; }
  code, pre { background: var(--md-panel-2) !important; color: var(--md-text) !important;
              border: 1px solid var(--md-line); border-radius: 4px; }

  /* ===== 顶部品牌条 (editorial 报刊感) ===== */
  .md-brand {
    display: flex; align-items: flex-end; justify-content: space-between;
    padding: 28px 28px 18px; margin: -1.2rem -1rem 1.6rem -1rem;
    border-bottom: 1.5px solid var(--md-line-strong);
    background:
      linear-gradient(180deg, #fbf9f3 0%, var(--md-bg) 100%);
  }
  .md-brand .left { display: flex; align-items: center; gap: 18px; }
  .md-brand .mark {
    width: 44px; height: 44px; border-radius: 0;
    background: var(--md-accent);
    position: relative;
    box-shadow: 4px 4px 0 var(--md-accent-warm);
  }
  .md-brand .mark::after {
    content: ""; position: absolute; inset: 14px;
    border: 2px solid #fbf9f3; border-radius: 0;
  }
  .md-brand h1 {
    margin: 0; font-family: var(--md-serif); font-weight: 600;
    font-size: 1.55rem; letter-spacing: -.01em; color: var(--md-text);
    line-height: 1.1;
  }
  .md-brand .sub {
    color: var(--md-text-dim); font-size: .78rem;
    letter-spacing: .24em; text-transform: uppercase; margin-top: 4px;
  }
  .md-brand .meta {
    text-align: right; color: var(--md-text-faint); font-size: .72rem;
    letter-spacing: .18em; text-transform: uppercase;
    border-left: 1px solid var(--md-line); padding-left: 18px;
  }
  .md-brand .meta strong { display: block; color: var(--md-accent); font-size: .9rem;
                          letter-spacing: .12em; margin-bottom: 2px; font-weight: 600; }

  /* ===== 通用卡片 ===== */
  .md-card {
    background: var(--md-panel);
    border: 1px solid var(--md-line);
    border-radius: 4px;
    padding: 22px 24px;
    margin-bottom: 16px;
    box-shadow: 0 1px 0 rgba(31,77,70,.04);
  }
  /* 同一行中需要等高的卡片: 主页顶部三列 */
  .md-card-eq {
    min-height: 220px;
    height: 100%;
    display: flex; flex-direction: column;
    margin-bottom: 0;
  }
  /* 使 columns 内部的 markdown 容器 也填满高度, 以开启等高 */
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    display: flex;
  }
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {
    width: 100%;
  }
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] .stMarkdown,
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] .stMarkdown > div {
    height: 100%;
  }
  .md-card h3 {
    margin: 0 0 14px; font-family: var(--md-serif); font-weight: 600;
    font-size: 1.05rem; color: var(--md-text); letter-spacing: -.005em;
    padding-bottom: 8px; border-bottom: 1px solid var(--md-line);
  }
  .md-card p { color: var(--md-text); line-height: 1.7; }

  /* ===== KV 指标条 ===== */
  .md-kv { display: flex; gap: 0; flex-wrap: wrap;
           border: 1px solid var(--md-line); border-radius: 4px; overflow: hidden;
           background: var(--md-panel); }
  .md-kv .item {
    flex: 1 1 140px; padding: 14px 18px;
    border-right: 1px solid var(--md-line);
    background: var(--md-panel);
  }
  .md-kv .item:last-child { border-right: none; }
  .md-kv .label {
    font-size: .68rem; color: var(--md-text-faint);
    text-transform: uppercase; letter-spacing: .18em; font-weight: 500;
  }
  .md-kv .value {
    font-family: var(--md-serif); font-size: 1.35rem; color: var(--md-text);
    margin-top: 6px; font-variant-numeric: tabular-nums; line-height: 1.2;
  }

  /* ===== 标签 (印章感) ===== */
  .md-tag {
    display: inline-block; padding: 3px 10px; border-radius: 2px;
    font-size: .7rem; letter-spacing: .14em; text-transform: uppercase;
    font-weight: 600; border: 1px solid currentColor;
  }
  .md-tag.ok      { color: var(--md-ok);          background: rgba(63,122,90,.08); }
  .md-tag.warn    { color: var(--md-accent-warm); background: rgba(138,109,59,.08); }
  .md-tag.danger  { color: var(--md-danger);      background: rgba(184,68,58,.08); }
  .md-tag.info    { color: var(--md-accent);      background: rgba(31,77,70,.08); }

  /* ===== 进度条 ===== */
  .md-bar { height: 4px; background: var(--md-bg-2); border-radius: 0; overflow: hidden; margin-top: 6px; }
  .md-bar > span { display: block; height: 100%;
                   background: linear-gradient(90deg, var(--md-accent), var(--md-accent-2)); }

  /* ===== 五字段意见块 ===== */
  .md-opinion h4 {
    margin: 14px 0 4px; font-family: var(--md-serif); font-weight: 600;
    color: var(--md-accent); letter-spacing: .02em; font-size: .88rem;
    text-transform: uppercase; letter-spacing: .14em;
  }
  .md-opinion h4::before { content: "— "; color: var(--md-accent-warm); }
  .md-opinion p  { margin: 0 0 6px; line-height: 1.7; color: var(--md-text); }

  /* ===== 免责声明 ===== */
  .md-disclaimer {
    border-left: 3px solid var(--md-accent-warm);
    padding: 14px 18px; background: rgba(138,109,59,.06);
    color: var(--md-text-dim); font-size: .9rem; line-height: 1.7;
    font-family: var(--md-serif); font-style: italic;
  }

  /* ===== 综合结论正文 (editorial) ===== */
  .md-summary {
    font-family: var(--md-serif); font-size: 1.08rem; line-height: 1.85;
    color: var(--md-text); white-space: pre-wrap;
    column-gap: 32px;
  }
  .md-summary::first-letter {
    font-size: 2.6rem; float: left; line-height: 1; padding: 4px 8px 0 0;
    color: var(--md-accent); font-weight: 700;
  }

  /* ===== 时间线 ===== */
  .md-timeline-item {
    display: flex; gap: 14px; padding: 10px 14px;
    border-left: 2px solid var(--md-line); margin-left: 6px;
  }
  .md-timeline-item .role {
    font-size: .68rem; letter-spacing: .18em; text-transform: uppercase;
    color: var(--md-text-faint); min-width: 70px;
  }
  .md-timeline-item .body { color: var(--md-text); flex: 1; line-height: 1.55; }

  /* ===== 隐藏 Streamlit 自带的 'Made with Streamlit' ===== */
  footer { visibility: hidden; }

  /* ===== 隐藏顶部右侧 Deploy 按钮 / 三点菜单, 但保留 sidebar 折叠按钮 ===== */
  [data-testid="stDecoration"],
  [data-testid="stStatusWidget"],
  [data-testid="stAppDeployButton"],
  [data-testid="stToolbarActions"],
  header [data-testid="stMainMenu"],
  #MainMenu { display: none !important; }
  /* 保留顶部 header 占位 (内含 sidebar 展开按钮), 仅做透明化 */
  header[data-testid="stHeader"] {
    background: transparent !important;
    box-shadow: none !important;
  }
  /* 折叠后用于重新展开的浮动按钮: 务必保留 */
  [data-testid="stSidebarCollapsedControl"],
  [data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
  }

  /* ===== 侧边栏: 与右侧主内容统一的 editorial 浅色主题 ===== */
  [data-testid="stSidebar"] {
    background:
      linear-gradient(180deg, #fbf9f3 0%, var(--md-bg) 100%) !important;
    border-right: 1px solid var(--md-line-strong) !important;
  }
  [data-testid="stSidebar"] > div:first-child {
    background: transparent !important;
  }
  /* 侧边栏内文字 / 标题 / 链接 (避免覆盖 Material Symbols 图标字体) */
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] span,
  [data-testid="stSidebar"] div,
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] a,
  [data-testid="stSidebar"] li {
    color: var(--md-text);
    font-family: var(--md-sans);
  }
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 {
    font-family: var(--md-serif);
    color: var(--md-text);
    letter-spacing: -.005em;
  }
  /* 关键: 不要覆盖图标字体, 否则 'keyboard_double_arrow_left' 等会显示成文字 */
  [data-testid="stSidebar"] [class*="icon"],
  [data-testid="stSidebar"] [data-testid*="Icon"],
  [data-testid="stSidebar"] svg,
  [data-testid="stSidebarCollapseButton"] *,
  [data-testid="stSidebarCollapsedControl"] *,
  [data-testid="collapsedControl"] *,
  .material-symbols-rounded,
  .material-symbols-outlined,
  .material-icons,
  span[translate="no"] {
    font-family: 'Material Symbols Rounded','Material Symbols Outlined','Material Icons' !important;
  }
  /* 多页导航链接 */
  [data-testid="stSidebarNav"] {
    padding-top: 8px;
    border-bottom: 1px solid var(--md-line);
    margin-bottom: 12px;
  }
  [data-testid="stSidebarNav"] ul { padding: 0 8px; }
  [data-testid="stSidebarNav"] a {
    border-radius: 4px;
    margin: 2px 0;
    padding: 6px 12px !important;
    color: var(--md-text-dim) !important;
    font-weight: 500;
    letter-spacing: .02em;
    transition: background .15s ease, color .15s ease;
  }
  [data-testid="stSidebarNav"] a:hover {
    background: rgba(31,77,70,.06) !important;
    color: var(--md-accent) !important;
  }
  [data-testid="stSidebarNav"] a[aria-current="page"],
  [data-testid="stSidebarNav"] a.active {
    background: rgba(31,77,70,.10) !important;
    color: var(--md-accent) !important;
    border-left: 2px solid var(--md-accent);
  }
  [data-testid="stSidebarNav"] span { color: inherit !important; }
  /* 把入口页 app -> 总览 (Streamlit 多页导航默认显示文件名) */
  [data-testid="stSidebarNav"] ul li:first-child a span { display: none !important; }
  [data-testid="stSidebarNav"] ul li:first-child a::after {
    content: "总览";
    font-family: var(--md-sans);
    font-weight: 500;
    color: inherit;
  }
  /* 侧边栏内的控件外观对齐 */
  [data-testid="stSidebar"] .stTextInput input,
  [data-testid="stSidebar"] .stTextArea textarea,
  [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div {
    background: var(--md-panel) !important;
    border: 1px solid var(--md-line) !important;
    color: var(--md-text) !important;
  }
  [data-testid="stSidebar"] hr { border-color: var(--md-line) !important; }
  /* 折叠/展开按钮: 保持可见, 仅微调配色 */
  [data-testid="stSidebarCollapseButton"],
  [data-testid="stSidebarCollapsedControl"],
  [data-testid="collapsedControl"],
  [data-testid="stBaseButton-headerNoPadding"] {
    color: var(--md-accent) !important;
    background: transparent !important;
  }
  [data-testid="stSidebarCollapseButton"] svg,
  [data-testid="stSidebarCollapsedControl"] svg,
  [data-testid="collapsedControl"] svg {
    fill: var(--md-accent) !important;
    color: var(--md-accent) !important;
  }
</style>
"""


def setup_page(title: str, icon: str = "🩺") -> None:
    """统一页面初始化: 设置页签、注入主题、显示品牌条."""
    st.set_page_config(page_title=f"{title} · 多智能体医疗会诊", page_icon=icon, layout="wide")
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="md-brand">
            <div class="left">
                <div class="mark"></div>
                <div>
                    <h1>多智能体医疗会诊</h1>
                    <div class="sub">Multi-Agent Medical Consultation</div>
                </div>
            </div>
            <div class="meta">
                <strong>{title}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )



# ---------------- session_state 访问 ----------------

_S_CLIENT = "_api_client"
_S_SESSION_ID = "session_id"
_S_CASE = "current_case"
_S_REPORT = "current_report"


def get_client() -> ApiClient:
    if _S_CLIENT not in st.session_state:
        st.session_state[_S_CLIENT] = ApiClient()
    return st.session_state[_S_CLIENT]


def get_session_id() -> Optional[str]:
    return st.session_state.get(_S_SESSION_ID)


def set_session_id(sid: str) -> None:
    st.session_state[_S_SESSION_ID] = sid


def clear_session() -> None:
    for k in (_S_SESSION_ID, _S_CASE, _S_REPORT):
        st.session_state.pop(k, None)


def get_case() -> Optional[Dict[str, Any]]:
    return st.session_state.get(_S_CASE)


def set_case(case: Dict[str, Any]) -> None:
    st.session_state[_S_CASE] = case


def get_report() -> Optional[Dict[str, Any]]:
    return st.session_state.get(_S_REPORT)


def set_report(report: Dict[str, Any]) -> None:
    st.session_state[_S_REPORT] = report


# ---------------- 数据查找 ----------------


def messages_by_role(messages: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
    return [m for m in messages if m.get("role") == role]


def latest_routing(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rs = messages_by_role(messages, "routing")
    return rs[-1] if rs else None


def latest_report(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rs = messages_by_role(messages, "report")
    return rs[-1] if rs else None


# ---------------- 渲染辅助 ----------------


def require_session_or_stop() -> str:
    sid = get_session_id()
    if not sid:
        st.warning("当前无活跃会话, 请先在 [病例录入] 页提交一次会诊.")
        st.stop()
    return sid  # type: ignore[return-value]


def render_session_banner() -> None:
    """页面顶部展示当前会诊的临床状态摘要 (不暴露 session_id / case_id)."""
    case = get_case() or {}
    chief = case.get("chief_complaint") or "尚未提交病例"
    report = get_report() or {}
    safety = report.get("safety_action")
    level = report.get("aggregation_level")

    if level:
        level_label = {1: "L1 · 一致融合", 2: "L2 · 加权融合", 3: "L3 · 仲裁裁定"}.get(level, f"L{level}")
    else:
        level_label = "—"
    safety_label = {"pass": "通过", "arbitrated": "仲裁", "degraded": "降级"}.get(safety or "", "—")

    st.markdown(
        f"""
        <div class="md-card">
          <div class="md-kv">
            <div class="item"><div class="label">当前主诉</div>
                <div class="value" style="font-size:1.05rem;">{chief}</div></div>
            <div class="item"><div class="label">综合层级</div>
                <div class="value">{level_label}</div></div>
            <div class="item"><div class="label">安全审查</div>
                <div class="value">{safety_label}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def confidence_tag(conf_level: str) -> str:
    cls = {"high": "ok", "medium": "info", "low": "warn"}.get(conf_level, "info")
    label = {"high": "高 置信", "medium": "中 置信", "low": "低 置信"}.get(conf_level, conf_level)
    return f'<span class="md-tag {cls}">{label}</span>'


def safety_tag(action: str) -> str:
    cls = {"pass": "ok", "arbitrated": "info", "degraded": "warn"}.get(action, "info")
    label = {"pass": "通过", "arbitrated": "仲裁", "degraded": "降级"}.get(action, action)
    return f'<span class="md-tag {cls}">{label}</span>'


def pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
