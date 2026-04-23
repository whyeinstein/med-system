"""分诊详情. 过程页: 展示候选科室、置信度分布、由分诊触发的会诊模式. 最终结论以综合报告为准."""
from __future__ import annotations

import streamlit as st

from frontend._shared import (
    get_client,
    latest_report,
    latest_routing,
    render_session_banner,
    require_session_or_stop,
    setup_page,
)
from frontend.api_client import BackendError

setup_page("分诊详情", icon="🧭")
render_session_banner()

st.caption(
    "本页展示分诊环节的候选科室、置信度分布与触发的会诊模式, 用于过程追溯; "
    "最终诊疗结论请以「综合报告」为准."
)

sid = require_session_or_stop()
client = get_client()

try:
    messages = client.list_messages(sid)
except BackendError as e:
    st.error(str(e))
    st.stop()

routing_msg = latest_routing(messages)
if routing_msg is None:
    st.info("当前会话尚未产出分诊结果.")
    st.stop()

routing = routing_msg["payload"]

TRIAGE_LABEL = {
    "single_clear": ("单一明确", "ok"),
    "multi_cross":  ("多科室交叉", "info"),
    "ambiguous":    ("情况复杂", "warn"),
}
DEPT_LABEL = {"internal": "内科", "surgery": "外科", "pediatrics": "儿科", "general": "全科"}
MODE_LABEL = {"parallel": "并行会诊", "serial": "串行会诊", "hybrid": "混合会诊"}

triage = routing.get("triage_tag", "—")
triage_label, triage_cls = TRIAGE_LABEL.get(triage, (triage, "info"))
fallback = bool(routing.get("fallback_triggered", False))
candidates = routing.get("candidates", [])
top_dept = candidates[0]["dept"] if candidates else "—"

# 会诊模式取自最近一次 report 的 inference_meta.mode
report_msg = latest_report(messages)
mode_code = ""
if report_msg:
    mode_code = (report_msg.get("inference_meta") or {}).get("mode", "") or ""
mode_label = MODE_LABEL.get(mode_code, "尚未确定")
mode_cls = "ok" if mode_code else "info"

# 兜底状态: 触发时高亮 warn, 未触发只做轻量徽标
if fallback:
    fallback_badge = '<span class="md-tag warn" style="margin-left:8px;">已触发兜底</span>'
else:
    fallback_badge = (
        '<span style="margin-left:8px; color: var(--md-text-faint); font-size:.78rem;">'
        '兜底未触发</span>'
    )

# ---------------- 分诊概览 ----------------

st.markdown(
    f"""
    <div class="md-card">
      <h3>分诊概览</h3>
      <div class="md-kv">
        <div class="item"><div class="label">分诊判定</div>
            <div class="value">
              <span class="md-tag {triage_cls}">{triage_label}</span>{fallback_badge}
            </div></div>
        <div class="item"><div class="label">首选科室</div>
            <div class="value">{DEPT_LABEL.get(top_dept, top_dept)}</div></div>
        <div class="item"><div class="label">候选科室数</div>
            <div class="value">{len(candidates)} 个</div></div>
        <div class="item"><div class="label">会诊模式</div>
            <div class="value"><span class="md-tag {mode_cls}">{mode_label}</span></div></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------- 置信度分布 (与分诊概览合并展示) ----------------

if candidates:
    top1_conf = candidates[0]["confidence"] if len(candidates) >= 1 else 0

    # 进度条颜色: top1 深绿 / top2 中绿 / 其他浅绿; 文字颜色统一用主题色
    BAR_COLORS = ["#1f4d46", "#4a8c82", "#c8deda"]

    bars_html = ""
    for rank, c in enumerate(candidates):
        pct = c["confidence"] * 100
        dept_label = DEPT_LABEL.get(c["dept"], c["dept"])
        bar_color = BAR_COLORS[min(rank, 2)]
        bars_html += f"""
        <div style="margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:baseline;">
            <span style="font-family: var(--md-serif); font-size:1.05rem;
                         color: var(--md-text);">{dept_label}</span>
            <span style="color: var(--md-text-dim); font-variant-numeric: tabular-nums;
                         font-size:.9rem;">{pct:.1f}%</span>
          </div>
          <div class="md-bar">
            <span style="width:{pct:.1f}%; background:{bar_color};"></span>
          </div>
        </div>
        """

    top1_label = DEPT_LABEL.get(candidates[0]["dept"], candidates[0]["dept"])

    st.markdown(
        f"""
        <div class="md-card">
          <h3>科室置信度分布</h3>
          <div style="display:flex; gap:28px; margin: 4px 0 18px; flex-wrap:wrap;">
            <div>
              <div style="font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
                           color: var(--md-text-faint); margin-bottom:3px;">TOP 1</div>
              <div style="font-family: var(--md-serif); font-size:1.05rem;
                           color: var(--md-text);">{top1_label}</div>
            </div>
            <div>
              <div style="font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
                           color: var(--md-text-faint); margin-bottom:3px;">分布特征</div>
              <div style="font-family: var(--md-serif); font-size:1.05rem;
                           color: var(--md-text);">{triage_label}</div>
            </div>
          </div>
          {bars_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown('<div class="md-card"><h3>科室置信度分布</h3><p>无候选.</p></div>',
                unsafe_allow_html=True)


