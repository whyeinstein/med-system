"""各科室意见. 仅展示临床字段."""
from __future__ import annotations

import streamlit as st

from frontend._shared import (
    confidence_tag,
    get_client,
    messages_by_role,
    render_session_banner,
    require_session_or_stop,
    setup_page,
)
from frontend.api_client import BackendError

setup_page("各科室意见", icon="🧠")
render_session_banner()

sid = require_session_or_stop()
client = get_client()

try:
    messages = client.list_messages(sid)
except BackendError as e:
    st.error(str(e))
    st.stop()

opinions = messages_by_role(messages, "opinion")
if not opinions:
    st.info("当前会话尚未产出科室意见.")
    st.stop()

DEPT_LABEL = {"internal": "内科", "surgery": "外科", "pediatrics": "儿科", "general": "全科"}

n_total = len(opinions)
n_high = sum(1 for o in opinions if o["payload"].get("self_confidence") == "high")
n_med = sum(1 for o in opinions if o["payload"].get("self_confidence") == "medium")
n_low = sum(1 for o in opinions if o["payload"].get("self_confidence") == "low")

st.markdown(
    f"""
    <div class="md-card">
      <h3>会诊矩阵</h3>
      <div class="md-kv">
        <div class="item"><div class="label">参与科室</div><div class="value">{n_total}</div></div>
        <div class="item"><div class="label">高置信</div><div class="value">{n_high}</div></div>
        <div class="item"><div class="label">中置信</div><div class="value">{n_med}</div></div>
        <div class="item"><div class="label">低置信</div><div class="value">{n_low}</div></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tabs = st.tabs([DEPT_LABEL.get(o["payload"].get("dept", "?"), "?") for o in opinions])

for tab, msg in zip(tabs, opinions):
    with tab:
        op = msg["payload"]
        dept_label = DEPT_LABEL.get(op.get("dept", ""), op.get("dept", "—"))

        st.markdown(
            f"""
            <div class="md-card md-opinion">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <h3 style="margin:0; border:none; padding:0;">{dept_label} · 科室意见</h3>
                <div>{confidence_tag(op.get('self_confidence', 'medium'))}</div>
              </div>
              <hr style="margin: 14px 0;">
              <h4>诊断倾向</h4><p>{op.get('diagnosis', '—')}</p>
              <h4>鉴别要点</h4><p>{op.get('differential', '—')}</p>
              <h4>处置建议</h4><p>{op.get('treatment', '—')}</p>
              <h4>关注事项</h4><p>{op.get('attention', '—')}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
