"""Streamlit 入口 (阶段 6, 论文 4.4 系统对外展示)."""
from __future__ import annotations

import streamlit as st

from frontend._shared import clear_session, get_case, get_client, get_report, setup_page

setup_page("总览", icon="🩺")

client = get_client()
backend_ok = client.health()

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    badge = (
        '<span class="md-tag ok">系统在线</span>'
        if backend_ok
        else '<span class="md-tag danger">后端离线</span>'
    )
    st.markdown(
        f"""
        <div class="md-card">
            <h3>服务状态</h3>
            <div>{badge}</div>
            <p style="margin-top:10px; color: var(--md-text-dim); font-size:.85rem;">
                推理内核: MoE-LoRA · 模拟模式
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col2:
    case = get_case() or {}
    chief = case.get("chief_complaint") or "尚无活跃会诊"
    st.markdown(
        f"""
        <div class="md-card">
            <h3>当前会诊</h3>
            <p style="margin:0; font-family: var(--md-serif); font-size:1.05rem;">
                {chief}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col3:
    report = get_report()
    if report:
        level = report.get("aggregation_level", "—")
        action = report.get("safety_action", "—")
        action_label = {"pass": "通过", "arbitrated": "仲裁", "degraded": "降级"}.get(action, action)
        body = (
            f'<span class="md-tag info">L{level}</span> '
            f'&nbsp;<span class="md-tag ok">{action_label}</span>'
        )
    else:
        body = '<span class="md-tag warn">尚无报告</span>'
    st.markdown(
        f"""
        <div class="md-card">
            <h3>最新报告</h3>
            <div style="padding-top:4px;">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="md-card">
      <h3>关于本系统</h3>
      <p class="md-summary" style="font-size:1rem; line-height:1.85;">
        本系统将一例待诊病例分发到 <b>内科 / 外科 / 儿科 / 全科</b> 四位科室智能体,
        让它们独立给出诊断倾向、鉴别要点、处置建议与关注事项;
        随后由系统沿 一致性 → 加权融合 → 仲裁 三级路径合成共识,
        并由安全审查模块替换风险表述、追加免责声明, 最终产出一份完整的会诊报告.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="md-card">
      <h3>会诊流程</h3>
      <div class="md-kv">
        <div class="item"><div class="label">第一步</div><div class="value">病例录入</div></div>
        <div class="item"><div class="label">第二步</div><div class="value">智能分诊</div></div>
        <div class="item"><div class="label">第三步</div><div class="value">多科室会诊</div></div>
        <div class="item"><div class="label">第四步</div><div class="value">三级综合</div></div>
        <div class="item"><div class="label">第五步</div><div class="value">安全审查</div></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("会话管理"):
    st.write("清空当前会话上下文不会影响后端已存档的历史记录.")
    if st.button("清空当前会话上下文"):
        clear_session()
        st.success("已清空, 请到 [病例录入] 页重新发起会诊.")
        st.rerun()
