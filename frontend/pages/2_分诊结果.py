"""分诊结果. 仅展示临床友好字段."""
from __future__ import annotations

import streamlit as st

from frontend._shared import (
    get_client,
    latest_routing,
    render_session_banner,
    require_session_or_stop,
    setup_page,
)
from frontend.api_client import BackendError

setup_page("分诊结果", icon="🧭")
render_session_banner()

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

triage = routing.get("triage_tag", "—")
triage_label, triage_cls = TRIAGE_LABEL.get(triage, (triage, "info"))
fallback = routing.get("fallback_triggered", False)
fallback_html = (
    '<span class="md-tag warn">已触发兜底</span>' if fallback else '<span class="md-tag ok">正常</span>'
)
candidates = routing.get("candidates", [])
top_dept = candidates[0]["dept"] if candidates else "—"

st.markdown(
    f"""
    <div class="md-card">
      <h3>分诊概览</h3>
      <div class="md-kv">
        <div class="item"><div class="label">分诊判定</div>
            <div class="value"><span class="md-tag {triage_cls}">{triage_label}</span></div></div>
        <div class="item"><div class="label">兜底状态</div><div class="value">{fallback_html}</div></div>
        <div class="item"><div class="label">候选科室</div>
            <div class="value">{len(candidates)} 个</div></div>
        <div class="item"><div class="label">首选科室</div>
            <div class="value">{DEPT_LABEL.get(top_dept, top_dept)}</div></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="md-card"><h3>科室置信度分布</h3>', unsafe_allow_html=True)
if candidates:
    max_conf = max((c["confidence"] for c in candidates), default=1.0) or 1.0
    for c in candidates:
        pct = c["confidence"] * 100
        bar_pct = (c["confidence"] / max_conf) * 100 if max_conf > 0 else 0
        dept_label = DEPT_LABEL.get(c["dept"], c["dept"])
        st.markdown(
            f"""
            <div style="margin-bottom:14px;">
              <div style="display:flex; justify-content:space-between; align-items:baseline;">
                <span style="font-family: var(--md-serif); font-size:1.05rem;">{dept_label}</span>
                <span style="color: var(--md-accent); font-variant-numeric: tabular-nums;">{pct:.1f}%</span>
              </div>
              <div class="md-bar"><span style="width:{bar_pct:.1f}%"></span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.write("无候选.")
st.markdown("</div>", unsafe_allow_html=True)
