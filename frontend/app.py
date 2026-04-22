"""Streamlit 入口 (阶段 6, 论文 4.4 系统对外展示)."""
from __future__ import annotations

import streamlit as st

from frontend._shared import get_client, setup_page

setup_page("总览", icon="🩺")

client = get_client()
backend_ok = client.health()


# 总览页固定展示一组示例数据 (方便演示 / 截图), 不读取真实 session_state 或历史
_MOCK = {
    "service": {
        "status_label": "系统在线" if backend_ok else "后端离线",
        "status_cls": "ok" if backend_ok else "danger",
    },
    "case": {
        "chief": "6 岁男童, 发热 2 天, 伴咽喉痛和乏力",
        "stage": "进行中",
        "mode": "并行会诊",
        "depts": "儿科 · 内科 · 通用科",
    },
    "report": {
        "title": "老年人胸闷伴肩背不适 · 会诊报告",
        "level_label": "多科共识",
        "safety_label": "安全可发",
        "safety_cls": "ok",
        "updated": "5 分钟前",
        "summary": "综合多科意见, 建议尽快完善心电图与心肌酶检查以排除心脸问题, 同时关注血压与休息状态.",
    },
}


def _meta_row(items):
    """渲染卡片底部的辅助标签行 (label · label · label)."""
    parts = []
    for it in items:
        parts.append(
            f'<span style="color: var(--md-text-dim); font-family: var(--md-sans);">{it}</span>'
        )
    sep = '<span style="color: var(--md-line-strong); margin: 0 8px;">·</span>'
    return (
        '<div style="margin-top:auto; padding-top:14px; '
        'border-top:1px solid var(--md-line); '
        'font-size:.78rem; letter-spacing:.04em;">'
        + sep.join(parts)
        + "</div>"
    )


col1, col2, col3 = st.columns([0.7, 1.15, 1.15])

with col1:
    svc = _MOCK["service"]
    dot_color = "var(--md-ok)" if svc["status_cls"] == "ok" else "var(--md-danger)"
    st.markdown(
        f"""
        <div class="md-card md-card-eq">
            <h3>服务状态</h3>
            <div style="display:flex; align-items:center; gap:10px; margin: 4px 0 0;">
                <span style="width:10px; height:10px; border-radius:50%; background:{dot_color};
                             box-shadow:0 0 0 4px rgba(63,122,90,.12);"></span>
                <span style="font-family: var(--md-serif); font-size:1.15rem; color: var(--md-text);">
                    {svc['status_label']}
                </span>
            </div>
            {_meta_row(["后端服务 · 运行中"])}
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    case = _MOCK["case"]
    st.markdown(
        f"""
        <div class="md-card md-card-eq">
            <h3>当前会诊</h3>
            <p style="margin:0; font-family: var(--md-serif); font-size:1.05rem; line-height:1.55; color: var(--md-text);">
                {case['chief']}
            </p>
            {_meta_row([
                f"<span class='md-tag info' style='padding:2px 8px;'>{case['stage']}</span>",
                case['mode'],
                case['depts'],
            ])}
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    rep = _MOCK["report"]
    summary = rep["summary"].strip().split("\n")[0][:80]
    st.markdown(
        f"""
        <div class="md-card md-card-eq">
            <h3>最新报告</h3>
            <div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin: 0 0 8px;">
                <p style="margin:0; font-family: var(--md-serif); font-size:1.05rem;
                          color: var(--md-text); line-height:1.4;">
                    {rep['title']}
                </p>
                <span style="color: var(--md-text-faint); font-size:.78rem;
                             letter-spacing:.06em; white-space:nowrap;">{rep['updated']}</span>
            </div>
            <p style="margin:0; font-family: var(--md-serif); font-size:.92rem;
                      line-height:1.65; color: var(--md-text-dim);">
                {summary}
            </p>
            {_meta_row(["综合结论 · 仅供临床参考"])}
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="md-card" style="margin-top: 28px;">
      <h3>系统简介</h3>
      <p class="md-summary" style="font-size:1rem; line-height:1.85;">
        本系统面向多科室协同会诊场景, 接收病例后会自动完成信息梳理、智能分诊与多科室分析,
        在保留各方意见的同时形成共识结论, 并经安全审查后输出一份结构清晰、可供参考的会诊报告.
        全流程强调多视角协同分析、过程可追溯可解释与输出风险可控, 为临床提供可靠的辅助诊疗意见.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)


