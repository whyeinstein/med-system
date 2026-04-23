"""Streamlit 入口 (阶段 6, 论文 4.4 系统对外展示)."""
from __future__ import annotations

import streamlit as st

from frontend._shared import (
    get_case,
    get_client,
    get_report,
    latest_report,
    setup_page,
)
from frontend.api_client import BackendError

setup_page("总览", icon="🩺")

client = get_client()
backend_ok = client.health()


# 总览页固定展示一组示例数据 (方便演示 / 截图), 不读取真实 session_state 或历史
_MOCK = {
    "service": {
        "status_label": "系统在线" if backend_ok else "后端离线",
        "status_cls": "ok" if backend_ok else "danger",
    },
}


DEPT_LABEL = {
    "internal": "内科", "surgery": "外科", "pediatrics": "儿科", "general": "全科",
    "gynecology": "妇产科", "oncology": "肿瘤科", "dermatology": "皮肤科", "andrology": "男科",
}


def _fmt_relative(ts: str) -> str:
    """将后竨 created_at (形如 '2025-12-22 15:04:17') 转为友好的相对时间描述."""
    if not ts:
        return ""
    from datetime import datetime
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M")
    dt = None
    for f in fmts:
        try:
            dt = datetime.strptime(ts[:19], f)
            break
        except ValueError:
            continue
    if dt is None:
        return ts
    delta = datetime.now() - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return dt.strftime("%Y-%m-%d %H:%M")
    if secs < 60:
        return f"{secs} 秒前"
    if secs < 3600:
        return f"{secs // 60} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    if secs < 86400 * 7:
        return f"{secs // 86400} 天前"
    return dt.strftime("%Y-%m-%d %H:%M")


@st.cache_data(ttl=15, show_spinner=False)
def _latest_report_card() -> dict | None:
    """从后端拉取最近一条已出报告的会诊, 返回展示所需字段."""
    try:
        sessions = client.list_sessions(limit=10)
    except BackendError:
        return None
    for s in sessions:
        sid = s.get("id")
        if not sid:
            continue
        try:
            msgs = client.list_messages(sid)
        except BackendError:
            continue
        rep_msg = latest_report(msgs)
        if not rep_msg:
            continue
        rep = rep_msg.get("payload") or {}
        # 拉主诉作为标题
        chief = ""
        try:
            case_data = client.get_case(sid)
            chief = (case_data.get("chief_complaint") or "").strip()
        except Exception:  # noqa: BLE001
            pass
        # 从 summary 中提取首条有意义文本
        import re as _re
        raw = rep.get("summary") or ""
        body = ""
        for ln in raw.splitlines():
            ln = ln.strip()
            if not ln or _re.match(r"^【|^#+\s|^-\s*\[", ln):
                continue
            body = _re.sub(r"\s*\(?w=[\d.]+\)?\s*", " ", ln).strip()
            if body:
                break
        depts = [o.get("dept") for o in rep.get("dept_opinions", [])]
        dept_str = " · ".join(DEPT_LABEL.get(d, d) for d in depts if d)
        return {
            "title": (chief or "会诊报告")[:60],
            "summary": (body or "(未提供摘要)")[:80],
            "updated": _fmt_relative(s.get("created_at", "")),
            "depts": dept_str,
        }
    return None


def _current_consultation() -> dict | None:
    """只在"病例已提交但报告尚未产出"时, 视为有正在进行的会诊."""
    case = get_case()
    if not case:
        return None
    if get_report() is not None:
        return None
    chief = (case.get("chief_complaint") or "").strip()
    if not chief:
        return None
    return {"chief": chief, "stage": "进行中"}


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
    case = _current_consultation()
    if case:
        body_html = (
            f'<p style="margin:0; font-family: var(--md-serif); font-size:1.05rem; '
            f'line-height:1.55; color: var(--md-text);">{case["chief"]}</p>'
        )
        meta_html = _meta_row([
            f"<span class='md-tag info' style='padding:2px 8px;'>{case['stage']}</span>",
        ])
    else:
        body_html = (
            '<p style="margin:0; font-family: var(--md-serif); font-size:1.05rem; '
            'line-height:1.55; color: var(--md-text-dim);">暂无正在进行的会诊</p>'
        )
        meta_html = _meta_row(["可在「病例录入」开启新一轮会诊"])
    st.markdown(
        f"""
        <div class="md-card md-card-eq">
            <h3>当前会诊</h3>
            {body_html}
            {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    rep = _latest_report_card()
    if rep:
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
                    {rep['summary']}
                </p>
                {_meta_row([rep['depts'] or '综合结论 · 仅供临床参考'])}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="md-card md-card-eq">
                <h3>最新报告</h3>
                <p style="margin:0; font-family: var(--md-serif); font-size:1.05rem;
                          line-height:1.55; color: var(--md-text-dim);">暂无已生成的会诊报告</p>
                {_meta_row(["完成一次会诊后在此展示"])}
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


