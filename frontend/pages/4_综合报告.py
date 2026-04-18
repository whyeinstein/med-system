"""综合报告. 突出综合结论 + 免责声明."""
from __future__ import annotations

import streamlit as st

from frontend._shared import (
    confidence_tag,
    get_client,
    get_report,
    latest_report,
    render_session_banner,
    require_session_or_stop,
    safety_tag,
    setup_page,
)
from frontend.api_client import BackendError

setup_page("综合报告", icon="📋")
render_session_banner()

sid = require_session_or_stop()
client = get_client()

report = get_report()
if not report:
    try:
        msgs = client.list_messages(sid)
    except BackendError as e:
        st.error(str(e))
        st.stop()
    msg = latest_report(msgs)
    if msg is None:
        st.info("当前会话尚未产出综合报告.")
        st.stop()
    report = msg["payload"]

DEPT_LABEL = {"internal": "内科", "surgery": "外科", "pediatrics": "儿科", "general": "全科"}
LEVEL_LABEL = {1: "L1 · 一致融合", 2: "L2 · 加权融合", 3: "L3 · 仲裁裁定"}
level = report.get("aggregation_level", 0)
action = report.get("safety_action", "pass")

st.markdown(
    f"""
    <div class="md-card">
      <h3>综合结论</h3>
      <div class="md-kv">
        <div class="item"><div class="label">综合层级</div>
            <div class="value"><span class="md-tag info">{LEVEL_LABEL.get(level, f"L{level}")}</span></div></div>
        <div class="item"><div class="label">安全审查</div><div class="value">{safety_tag(action)}</div></div>
        <div class="item"><div class="label">参与科室</div>
            <div class="value">{len(report.get('dept_opinions', []))}</div></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

summary = report.get("summary") or "—"
st.markdown(
    f'<div class="md-card"><h3>会诊意见</h3>'
    f'<div class="md-summary">{summary}</div></div>',
    unsafe_allow_html=True,
)

disclaimer = report.get("disclaimer") or ""
if disclaimer:
    st.markdown(
        f'<div class="md-card"><h3>免责声明</h3>'
        f'<div class="md-disclaimer">{disclaimer}</div></div>',
        unsafe_allow_html=True,
    )

opinions = report.get("dept_opinions", [])
if opinions:
    with st.expander(f"参考: 原始科室意见 ({len(opinions)})"):
        for op in opinions:
            dept_label = DEPT_LABEL.get(op.get("dept", ""), op.get("dept", "—"))
            st.markdown(
                f"""
                <div class="md-card md-opinion" style="background: var(--md-panel-2); margin-bottom: 10px;">
                  <div style="display:flex; justify-content:space-between;">
                    <h4 style="margin:0; color: var(--md-accent); border:none; padding:0;">{dept_label}</h4>
                    <div>{confidence_tag(op.get('self_confidence', 'medium'))}</div>
                  </div>
                  <p style="margin-top:10px;"><b>诊断:</b> {op.get('diagnosis', '—')}</p>
                  <p><b>鉴别:</b> {op.get('differential', '—')}</p>
                  <p><b>处置:</b> {op.get('treatment', '—')}</p>
                  <p><b>关注:</b> {op.get('attention', '—')}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
