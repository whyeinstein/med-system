"""历史记录. 用临床字段(主诉摘要/时间/层级/安全)替代 session_id."""
from __future__ import annotations

from typing import Dict

import streamlit as st

from frontend._shared import get_client, latest_report, set_case, set_report, set_session_id, setup_page
from frontend.api_client import BackendError

setup_page("历史记录", icon="🗂️")

client = get_client()

try:
    sessions = client.list_sessions(limit=100)
except BackendError as e:
    st.error(str(e))
    st.stop()

DEPT_LABEL = {
    "internal": "内科", "surgery": "外科", "pediatrics": "儿科", "general": "全科",
    "gynecology": "妇产科", "oncology": "肿瘤科", "dermatology": "皮肤科", "andrology": "男科",
}
LEVEL_LABEL = {1: "L1 一致", 2: "L2 加权", 3: "L3 仲裁"}
ACTION_LABEL = {"pass": "通过", "arbitrated": "仲裁", "degraded": "降级"}
ACTION_TAG = {"pass": "ok", "arbitrated": "info", "degraded": "warn"}


@st.cache_data(ttl=30, show_spinner=False)
def _enrich(sid: str) -> Dict:
    try:
        msgs = client.list_messages(sid)
    except BackendError:
        return {}
    rep_msg = latest_report(msgs)
    rep = rep_msg["payload"] if rep_msg else {}

    # 优先用主诉作为摘要标题，fallback 才从 summary 提取
    chief = ""
    try:
        case_data = client.get_case(sid)
        chief = (case_data.get("chief_complaint") or "").strip()
    except Exception:  # noqa: BLE001
        pass

    if chief:
        summary = chief[:80]
    else:
        # 从 summary 里跳过调试头 (【...】行 / ### 行)，取第一条有意义的文本
        import re as _re
        raw = rep.get("summary") or ""
        summary = ""
        for ln in raw.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if _re.match(r"^【|^#+\s", ln):
                continue
            # 去掉 w=... 权重标记
            ln = _re.sub(r"\s*\(?w=[\d.]+\)?\s*", " ", ln).strip()
            if ln:
                summary = ln[:80]
                break
        summary = summary or "(尚未产出报告)"

    return {
        "summary": summary,
        "level": rep.get("aggregation_level"),
        "safety": rep.get("safety_action"),
        "depts": [o.get("dept") for o in rep.get("dept_opinions", [])],
    }


st.markdown(
    f"""
    <div class="md-card">
      <h3>会话档案</h3>
      <div class="md-kv">
        <div class="item"><div class="label">近期会诊</div>
            <div class="value">{len(sessions)}</div></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not sessions:
    st.info("尚无任何会诊记录, 请先在 [病例录入] 页提交一次会诊.")
    st.stop()

# 删除确认 state
if "confirm_delete" not in st.session_state:
    st.session_state["confirm_delete"] = None

for s in sessions:
    sid = s["id"]
    created = s.get("created_at", "")
    info = _enrich(sid)
    summary = info.get("summary") or "(尚未产出报告)"
    level = info.get("level")
    level_label = LEVEL_LABEL.get(level or 0, "—")
    safety = info.get("safety")
    safety_label = ACTION_LABEL.get(safety or "", "—")
    safety_cls = ACTION_TAG.get(safety or "", "info")
    depts = " · ".join(DEPT_LABEL.get(d, d) for d in (info.get("depts") or []))

    st.markdown(
        f"""
        <div class="md-card" style="padding:18px 22px;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:18px;">
            <div style="flex:1;">
              <div style="font-size:.68rem; letter-spacing:.18em; text-transform:uppercase;
                           color: var(--md-text-faint); margin-bottom:4px;">主诉</div>
              <div style="font-family: var(--md-serif); font-size:1.08rem; color: var(--md-text);
                           line-height:1.55;">
                {summary}
              </div>
              <div style="margin-top:6px; color: var(--md-text-faint); font-size:.78rem; letter-spacing:.06em;">
                {created} &nbsp;·&nbsp; 参与科室 {depts or '—'}
              </div>
            </div>
            <div style="text-align:right; min-width:180px;">
              <span class="md-tag info">{level_label}</span>
              &nbsp;<span class="md-tag {safety_cls}">{safety_label}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    btn_cols = st.columns([2, 2, 14])
    with btn_cols[0]:
        if st.button("载入会诊", key=f"load_{sid}"):
            set_session_id(sid)
            try:
                case_data = client.get_case(sid)
                set_case(case_data)
            except Exception:  # noqa: BLE001
                pass
            try:
                msgs = client.list_messages(sid)
                from frontend._shared import latest_report  # noqa: PLC0415
                rep_msg = latest_report(msgs)
                if rep_msg:
                    set_report(rep_msg["payload"])
            except Exception:  # noqa: BLE001
                pass
            st.success("已切换到该会话, 可前往「综合报告」查看综合结论与各科室意见.")
    with btn_cols[1]:
        if st.session_state["confirm_delete"] == sid:
            if st.button("确认删除", key=f"del_confirm_{sid}"):
                try:
                    client.delete_session(sid)
                    _enrich.clear()
                except BackendError as e:
                    st.error(str(e))
                st.session_state["confirm_delete"] = None
                st.rerun()
        else:
            if st.button("删除记录", key=f"del_{sid}"):
                st.session_state["confirm_delete"] = sid
                st.rerun()

    st.write("")

