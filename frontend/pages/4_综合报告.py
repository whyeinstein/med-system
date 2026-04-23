"""综合报告. 唯一主结果页: 摘要 + 结构化综合结论 + 各科室意见 + 免责声明.

summary 由 aggregator 拼装, 包含 L1 一致 / L2 加权 / L3 仲裁三种格式; 本页做轻量规则
解析, 把它还原成"诊断倾向 / 鉴别要点 / 处置建议 / 关注事项 + 其他科室补充"四段式
结构, 不再原样展示带有调试痕迹的原始字符串.
"""
from __future__ import annotations

import html
import re
from typing import Dict, List

import streamlit as st

from frontend._shared import (
    get_client,
    get_report,
    latest_report,
    render_department_opinions,
    render_session_banner,
    require_session_or_stop,
    setup_page,
)
from frontend.api_client import BackendError

setup_page("综合报告", icon="📋")
render_session_banner()

sid = require_session_or_stop()
client = get_client()

try:
    messages = client.list_messages(sid)
except BackendError as e:
    st.error(str(e))
    st.stop()

report = get_report()
if not report:
    msg = latest_report(messages)
    if msg is None:
        st.info("当前会话尚未产出综合报告.")
        st.stop()
    report = msg["payload"]

routing = None  # 过程信息已移至「分诊详情」页, 本页仅作最终结果页

DEPT_LABEL = {"internal": "内科", "surgery": "外科", "pediatrics": "儿科", "general": "全科"}
MERGE_LABEL = {1: "一致融合", 2: "加权融合", 3: "仲裁裁定"}

level = report.get("aggregation_level", 0)
action = report.get("safety_action", "pass")
n_dept = len(report.get("dept_opinions", []))

# ======================== summary 解析 ========================

_NOISE_LINES = {
    "high", "medium", "low",
    "根据提供的信息，我们可以得出以下结论：",
    "根据提供的信息，我们可以得出以下结论:",
    "根据提供的信息, 我们可以得出以下结论:",
}
_FIELD_ALIASES = {
    "诊断": "diagnosis", "诊断倾向": "diagnosis", "初步诊断": "diagnosis",
    "鉴别": "differential", "鉴别要点": "differential", "鉴别诊断": "differential",
    "处置": "treatment", "处置建议": "treatment", "治疗建议": "treatment",
    "关注": "attention", "关注事项": "attention", "注意事项": "attention",
}


def _clean_line(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^#+\s*", "", s)              # 去掉 ### 前缀
    s = re.sub(r"\s*\(?w=\d+\.\d+\)?\s*", " ", s)  # 去掉 w=0.769 / (w=...)
    s = re.sub(r"^\*\*(.+?)\*\*\s*[:：]?\s*", r"\1: ", s)  # **xxx** -> xxx:
    s = s.replace("**", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_kv(line: str) -> tuple[str, str] | None:
    m = re.match(r"^([\u4e00-\u9fa5A-Za-z]{2,8})\s*[:：]\s*(.+)$", line)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def _parse_summary(text: str) -> Dict:
    """把 aggregator 拼出的 summary 解析为结构化 dict.

    返回:
        {
          "diagnosis": str, "differential": str, "treatment": str, "attention": str,
          "other_depts": [{"dept": "internal", "items": ["诊断: ...", "处置: ..."]}],
          "extra": str  # L3 仲裁段中无法对齐到字段的自由文本
        }
    """
    result = {
        "diagnosis": "", "differential": "", "treatment": "", "attention": "",
        "other_depts": [], "extra": "",
    }
    if not text:
        return result

    raw_lines = [ln for ln in text.splitlines()]
    in_others = False
    extra_buf: List[str] = []
    seen_field_lines: Dict[str, set] = {}

    for ln in raw_lines:
        s = _clean_line(ln)
        if not s:
            continue
        # 跳过噪音
        if s in _NOISE_LINES:
            continue
        if s in {"###", "—", "-"}:
            continue

        # block header: 【...】
        m_hdr = re.match(r"^【(.+?)】$", s)
        if m_hdr:
            in_others = "其他科室" in m_hdr.group(1) or "原始意见" in m_hdr.group(1)
            continue

        # other depts: - [dept ...] 诊断: xxx; 处置: xxx; 置信: high
        if in_others or s.startswith("- ["):
            mb = re.match(r"^-\s*\[([A-Za-z]+)(?:\s+w=[\d.]+)?\]\s*(.*)$", s)
            if mb:
                dept_code = mb.group(1)
                rest = mb.group(2)
                items = []
                for chunk in re.split(r"[;；]", rest):
                    c = chunk.strip()
                    if not c or c.lower() in {"high", "medium", "low"}:
                        continue
                    # 去掉末尾的 "置信: high"
                    c = re.sub(r"^置信\s*[:：]\s*\w+\s*$", "", c).strip()
                    if not c:
                        continue
                    items.append(c)
                if items:
                    result["other_depts"].append({"dept": dept_code, "items": items})
                continue

        # 字段行 (诊断: ...)
        kv = _split_kv(s)
        if kv:
            label, value = kv
            field = _FIELD_ALIASES.get(label)
            if field:
                # 去重: 同字段同句不重复
                seen = seen_field_lines.setdefault(field, set())
                if value in seen:
                    continue
                seen.add(value)
                if result[field]:
                    result[field] += "\n" + value
                else:
                    result[field] = value
                continue

        # 其他文本: 收入 extra (L3 仲裁稿/兜底说明)
        if s.startswith("注:") or s.startswith("注："):
            continue  # 模板末尾的"注: 本次会诊..."与免责声明重复, 跳过
        extra_buf.append(s)

    # 去掉相邻重复
    if extra_buf:
        deduped: List[str] = []
        for x in extra_buf:
            if not deduped or deduped[-1] != x:
                deduped.append(x)
        result["extra"] = "\n".join(deduped)
    return result


parsed = _parse_summary(report.get("summary") or "")

# ======================== 综合结论 ========================

merge_label = MERGE_LABEL.get(level, f"L{level}")
top_dept_label = "—"
if report.get("dept_opinions"):
    # 取权重最大的科室作为主导科室 (不依赖分诊路由信息)
    top_op = max(report["dept_opinions"], key=lambda o: o.get("weight", 0) or 0)
    top_dept_label = DEPT_LABEL.get(top_op.get("dept", ""), top_op.get("dept", "—"))

def _format_paragraph(text: str) -> str:
    """把一段长结论按 。/；/; 切分, 用 <br> 提早换行, 显得更像一段话.

    - 保留原标点
    - 过短的子句 (< 6 字) 与上一段合并, 避免出现孤立短行
    - 不同 \n (字段内多条) 仍按段落分隔
    """
    if not text:
        return ""
    paragraphs: List[str] = []
    for raw_para in text.split("\n"):
        para = raw_para.strip()
        if not para:
            continue
        # 在中文句号/分号/英文分号后插入切分点 (保留标点)
        parts = re.split(r"(?<=[。；;])\s*", para)
        merged: List[str] = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if merged and len(p) < 6:
                merged[-1] += p
            else:
                merged.append(p)
        paragraphs.append("<br>".join(html.escape(x) for x in merged))
    return '<div style="margin-bottom:6px;"></div>'.join(paragraphs)


field_blocks: List[str] = []
for key, title in [
    ("diagnosis", "诊断倾向"),
    ("differential", "鉴别要点"),
    ("treatment", "处置建议"),
    ("attention", "关注事项"),
]:
    val = parsed[key].strip()
    if not val:
        continue
    val_html = _format_paragraph(val)
    field_blocks.append(
        f'<div style="margin-bottom:16px;">'
        f'<div style="font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;'
        f' color: var(--md-text-faint); margin-bottom:5px;">{title}</div>'
        f'<div style="font-family: var(--md-serif); font-size:1rem; line-height:1.85;'
        f' color: var(--md-text);">{val_html}</div>'
        f'</div>'
    )

if not field_blocks:
    field_blocks.append('<div style="color: var(--md-text-dim);">暂无结构化结论, 请查看下方各科室意见.</div>')

st.markdown(
    f"""
    <div class="md-card">
      <h3>综合结论</h3>
      <div style="display:flex; gap:28px; margin: 4px 0 20px; flex-wrap:wrap;">
        <div>
          <div style="font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
                       color: var(--md-text-faint); margin-bottom:3px;">综合方式</div>
          <div style="font-family: var(--md-serif); font-size:1.05rem;
                       color: var(--md-text);">{merge_label}</div>
        </div>
        <div>
          <div style="font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
                       color: var(--md-text-faint); margin-bottom:3px;">主导科室</div>
          <div style="font-family: var(--md-serif); font-size:1.05rem;
                       color: var(--md-text);">{top_dept_label}</div>
        </div>
      </div>
      {''.join(field_blocks)}
    </div>
    """,
    unsafe_allow_html=True,
)

# ======================== 各科室意见 (补充详情, 默认收起) ========================

with st.expander("各科室意见 · 详情", expanded=False):
    render_department_opinions(report.get("dept_opinions", []) or [])

# ======================== 免责声明 ========================

disclaimer = report.get("disclaimer") or ""
if disclaimer:
    st.markdown(
        f'<div class="md-card"><h3>免责声明</h3>'
        f'<div class="md-disclaimer">{disclaimer}</div></div>',
        unsafe_allow_html=True,
    )
