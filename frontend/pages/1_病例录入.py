"""病例录入. 提交后由协调器编排整条会诊流水线."""
from __future__ import annotations

import uuid

import streamlit as st

from frontend._shared import get_client, set_case, set_report, set_session_id, setup_page
from frontend.api_client import BackendError

setup_page("病例录入", icon="📝")

st.markdown(
    """
    <div class="md-card">
      <h3>录入病例并发起会诊</h3>
      <p style="color: var(--md-text-dim);">
        提交后系统将自动完成 智能分诊 → 多科室并行/串行/混合会诊 → 三级综合 → 安全审查.
        过程通常需要数秒, 期间请勿刷新页面.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

PRESETS = {
    "(空白)": {"chief_complaint": "", "symptoms": "", "medical_history": "", "exam_results": ""},
    "阑尾炎疑似": {
        "chief_complaint": "右下腹持续性疼痛 12 小时",
        "symptoms": "转移性右下腹痛, 伴恶心呕吐, 低热 37.8℃, 麦氏点压痛阳性",
        "medical_history": "无慢性病史, 否认手术史",
        "exam_results": "白细胞 13.2×10⁹/L, 中性粒细胞 82%; 腹部超声提示阑尾增粗",
    },
    "儿童高热": {
        "chief_complaint": "5 岁患儿反复高热 3 天",
        "symptoms": "体温最高 39.6℃, 伴咽痛、轻咳, 食欲下降, 无皮疹",
        "medical_history": "既往体健, 未接种当年流感疫苗",
        "exam_results": "咽部充血, 双肺呼吸音清; 血常规白细胞 11.5×10⁹/L",
    },
    "高血压复诊": {
        "chief_complaint": "头晕乏力 1 周",
        "symptoms": "晨起头部胀痛, 偶有视物模糊, 无胸痛",
        "medical_history": "高血压病史 8 年, 服用氨氯地平 5mg/日",
        "exam_results": "诊室血压 162/98 mmHg, 心率 78 次/分, 心电图未见异常",
    },
}

with st.form("case_form", clear_on_submit=False):
    preset = st.selectbox("示例病例", list(PRESETS.keys()), index=1)
    p = PRESETS[preset]

    chief = st.text_input("主诉 *", value=p["chief_complaint"])
    symptoms = st.text_area("症状描述 *", value=p["symptoms"], height=100)
    history = st.text_area("既往史", value=p["medical_history"], height=80)
    exams = st.text_area("检查结果", value=p["exam_results"], height=80)

    submitted = st.form_submit_button("发起会诊", type="primary", use_container_width=True)

if submitted:
    if not chief.strip() or not symptoms.strip():
        st.error("主诉与症状描述为必填项.")
        st.stop()

    case_payload = {
        "case_id": f"case-{uuid.uuid4().hex[:8]}",
        "chief_complaint": chief.strip(),
        "symptoms": symptoms.strip(),
        "medical_history": history.strip(),
        "exam_results": exams.strip(),
    }
    client = get_client()

    with st.spinner("创建会诊会话…"):
        try:
            sid = client.create_session()
        except BackendError as e:
            st.error(f"会话创建失败: {e}")
            st.stop()
    set_session_id(sid)
    set_case(case_payload)

    with st.spinner("多科室会诊推理中, 请稍候…"):
        try:
            report = client.consultation(sid, case_payload)
        except BackendError as e:
            st.error(f"会诊失败: {e}")
            st.stop()
    set_report(report)

    level = report.get("aggregation_level")
    action = report.get("safety_action")
    action_label = {"pass": "通过", "arbitrated": "仲裁", "degraded": "降级"}.get(action, action)
    st.success(f"会诊完成 · 综合层级 L{level} · 安全审查 {action_label}")
    st.markdown(
        '<div class="md-card"><h3>下一步</h3>'
        '<p style="color: var(--md-text-dim);">'
        '请在左侧依次查看 <b>分诊结果</b> · <b>各科室意见</b> · <b>综合报告</b>.'
        '</p></div>',
        unsafe_allow_html=True,
    )
