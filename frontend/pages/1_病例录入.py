"""病例录入. 极简问诊式: 顶部两行引导, 一个 selectbox 示例入口, 两个主输入区, 一个折叠详细区, 一个主按钮."""
from __future__ import annotations

import uuid

import streamlit as st

from frontend._shared import get_client, set_case, set_report, set_session_id, setup_page
from frontend.api_client import BackendError

setup_page("病例录入", icon="📝")

# ---------------- 预设 (示例病例) ----------------

PRESETS = {
    "示例病例": {"chief": "", "supp": "", "history": "", "exams": ""},
    "阑尾炎疑似": {
        "chief": "右下腹持续性疼痛 12 小时",
        "supp": "转移性右下腹痛, 伴恶心呕吐, 低热 37.8℃, 麦氏点压痛阳性",
        "history": "无慢性病史, 否认手术史",
        "exams": "白细胞 13.2×10⁹/L, 中性粒细胞 82%; 腹部超声提示阑尾增粗",
    },
    "儿童高热": {
        "chief": "5 岁患儿反复高热 3 天",
        "supp": "体温最高 39.6℃, 伴咽痛、轻咳, 食欲下降, 无皮疹",
        "history": "既往体健, 未接种当年流感疫苗",
        "exams": "咽部充血, 双肺呼吸音清; 血常规白细胞 11.5×10⁹/L",
    },
    "高血压复诊": {
        "chief": "头晕乏力 1 周, 晨起明显",
        "supp": "晨起头部胀痛, 偶有视物模糊, 无胸痛",
        "history": "高血压病史 8 年, 服用氨氯地平 5mg/日",
        "exams": "诊室血压 162/98 mmHg, 心率 78 次/分, 心电图未见异常",
    },
}

for k in ("ci_chief", "ci_supp", "ci_history", "ci_exams"):
    st.session_state.setdefault(k, "")
st.session_state.setdefault("ci_preset_last", "示例病例")


# ---------------- 顶部: 引导文字 (左) + 示例病例 (右) ----------------

top_l, top_r = st.columns([4, 1])

with top_l:
    st.markdown(
        """
        <div style="margin: 4px 0 0;">
          <h3 style="margin:0 0 4px; font-family: var(--md-serif); font-weight:600;
                     font-size:1.05rem; color: var(--md-text); letter-spacing:-.005em;
                     border:none; padding-bottom:0;">
            录入本次病例信息
          </h3>
          <p style="margin:0; color: var(--md-text-dim); font-size:.82rem; line-height:1.6;">
            填写主诉与补充病情即可提交; 既往史与检查结果按需补充. 系统会自动完成分诊与多科室会诊.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with top_r:
    preset_choice = st.selectbox(
        "示例病例",
        list(PRESETS.keys()),
        index=list(PRESETS.keys()).index(st.session_state["ci_preset_last"]),
        key="ci_preset_select",
        label_visibility="collapsed",
    )
    if preset_choice != st.session_state["ci_preset_last"]:
        p = PRESETS[preset_choice]
        st.session_state["ci_chief"] = p["chief"]
        st.session_state["ci_supp"] = p["supp"]
        st.session_state["ci_history"] = p["history"]
        st.session_state["ci_exams"] = p["exams"]
        st.session_state["ci_preset_last"] = preset_choice
        st.rerun()

st.markdown(
    "<div style='border-top:1px solid var(--md-line); margin: 14px 0 18px;'></div>",
    unsafe_allow_html=True,
)

# ---------------- 主输入区 1: 主诉 ----------------

st.markdown(
    """
    <div style="margin: 4px 0 4px;">
      <div style="font-family: var(--md-serif); font-size:1.05rem; color: var(--md-text);">
        主要不适
      </div>
      <div style="color: var(--md-text-faint); font-size:.72rem;
                  letter-spacing:.18em; text-transform:uppercase; margin-top:2px;">
        主诉
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.text_area(
    "主诉",
    key="ci_chief",
    height=80,
    placeholder="例如: 右下腹持续疼痛 12 小时",
    label_visibility="collapsed",
)

# ---------------- 主输入区 2: 补充病情 ----------------

st.markdown(
    """
    <div style="margin: 18px 0 4px;">
      <div style="font-family: var(--md-serif); font-size:1.05rem; color: var(--md-text);">
        补充症状和相关情况
      </div>
      <div style="color: var(--md-text-faint); font-size:.72rem;
                  letter-spacing:.18em; text-transform:uppercase; margin-top:2px;">
        症状表现 · 持续时间 · 诱因
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.text_area(
    "补充病情",
    key="ci_supp",
    height=160,
    placeholder="例如: 伴恶心、低热, 活动后加重, 夜间疼痛明显",
    label_visibility="collapsed",
)

# ---------------- 可选展开区 ----------------

with st.expander("补充详细信息 (可选)"):
    st.text_area(
        "既往病史 / 长期用药",
        key="ci_history",
        height=90,
        placeholder="例如: 高血压 8 年, 长期服用氨氯地平; 否认药物过敏",
    )
    st.text_area(
        "化验、影像或体征结果",
        key="ci_exams",
        height=90,
        placeholder="例如: 白细胞 13.2×10⁹/L; 腹部超声提示阑尾增粗",
    )

# ---------------- 主按钮 ----------------

st.write("")
btn_cols = st.columns([1, 2, 1])
with btn_cols[1]:
    submitted = st.button(
        "开始会诊",
        type="primary",
        use_container_width=True,
        key="submit_consult",
    )
    st.markdown(
        """
        <p style="margin: 6px 0 0; text-align:center; color: var(--md-text-faint);
                  font-size:.78rem;">
          提交后系统将自动完成分诊、会诊综合与安全审查.
        </p>
        """,
        unsafe_allow_html=True,
    )

# ---------------- 提交逻辑 ----------------

if submitted:
    chief = (st.session_state["ci_chief"] or "").strip()
    supp = (st.session_state["ci_supp"] or "").strip()
    history = (st.session_state["ci_history"] or "").strip()
    exams = (st.session_state["ci_exams"] or "").strip()

    if not chief or not supp:
        st.error("请至少填写「主诉」与「补充病情」, 系统才能进行会诊.")
        st.stop()

    case_payload = {
        "case_id": f"case-{uuid.uuid4().hex[:8]}",
        "chief_complaint": chief,
        "symptoms": supp,
        "medical_history": history,
        "exam_results": exams,
    }
    client = get_client()

    with st.spinner("已接收病例信息, 正在创建会诊会话…"):
        try:
            sid = client.create_session()
        except BackendError as e:
            st.error(f"会话创建失败: {e}")
            st.stop()
    set_session_id(sid)
    set_case(case_payload)

    with st.spinner("正在组织多科室会诊, 请稍候…"):
        try:
            report = client.consultation(sid, case_payload)
        except BackendError as e:
            st.error(f"会诊失败: {e}")
            st.stop()
    set_report(report)

    st.success("已完成会诊, 请前往「综合报告」查看综合结论与各科室意见.")
    st.caption("如需查看候选科室与置信度等过程信息, 可前往「分诊详情」.")
