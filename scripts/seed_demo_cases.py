"""向 SQLite 注入 4 个演示病例 (含 session / case / routing / opinion / report 四类消息).

用途:
    python -m scripts.seed_demo_cases

特点:
    - 直接写表, 不走 orchestrator, 因此可以精确控制每条记录的 triage_tag /
      mode / aggregation_level / safety_action 等展示字段.
    - 每个 case 创建独立 session_id, 与前端历史记录页一一对应.
    - dept_opinions 中包含 weight 字段 (前端 4_综合报告 用其推断主导科室).
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

# 允许 `python scripts/seed_demo_cases.py` 直接执行
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import yaml  # noqa: E402

from app.storage.db import get_conn, init_schema  # noqa: E402

# ---------------------------------------------------------------------------
# 配置: SQLite 路径
# ---------------------------------------------------------------------------

_SETTINGS = yaml.safe_load((_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
DB_PATH = str(_ROOT / _SETTINGS["storage"]["sqlite_path"])


# ---------------------------------------------------------------------------
# 4 个案例数据 (与用户给定文案一一对应)
# ---------------------------------------------------------------------------


def _candidates(pairs: List[tuple]) -> List[Dict[str, Any]]:
    return [{"dept": d, "confidence": c} for d, c in pairs]

# 演示时间戳 (2025-11/12). 按顺序一一对应下面的 CASES, 仅供展示.
_CREATED_AT = [
    "2025-11-08 09:42:11",   # Case 1  阑尾炎         外科·内科·全科
    "2025-11-19 14:05:37",   # Case 2  上呼吸道感染    儿科
    "2025-12-03 21:18:54",   # Case 3  消化道出血      内科
    "2025-12-15 08:27:09",   # Case 4  胸闷高血压      全科·内科·外科
    "2025-11-12 16:33:05",   # Case 5  急性荨麻疹      皮肤科
    "2025-11-24 10:18:42",   # Case 6  异位妊娠        妇产科·外科
    "2025-12-09 08:51:30",   # Case 7  前列腺增生      男科·内科
    "2025-12-22 15:04:17",   # Case 8  轻度皮肤症状     皮肤科·内科·全科
]

CASES: List[Dict[str, Any]] = [
    # ===================== Case 1: 急性阑尾炎倾向 =====================
    {
        "case": {
            "chief_complaint": "右下腹持续性疼痛12小时",
            "symptoms": "转移性右下腹痛，伴恶心1次、低热37.8℃，活动后加重。",
            "medical_history": "无慢性病史，否认手术史及药物过敏。",
            "exam_results": "白细胞13.2×10^9/L，中性粒细胞82%；腹部超声提示阑尾增粗。",
        },
        "routing": {
            "candidates": _candidates([
                ("surgery", 0.308),
                ("pediatrics", 0.268),
                ("general", 0.264),
                ("internal", 0.160),
            ]),
            "triage_tag": "multi_cross",
            "fallback_triggered": False,
            "retrieval_hits": [],
        },
        "mode": "hybrid",
        "aggregation_level": 2,
        "safety_action": "degraded",
        "summary": (
            "【加权综合意见 · 主导科室: 外科】\n"
            "诊断倾向: 转移性右下腹痛伴恶心，腹部超声提示阑尾增粗，首先考虑急性阑尾炎。\n"
            "鉴别要点: 需与肠梗阻、泌尿系结石及妇科急腹症等右下腹痛原因鉴别。\n"
            "处置建议: 建议完善血常规、CRP和腹部CT进一步明确；如符合手术指征，应尽快由外科评估处理。\n"
            "关注事项: 观察体温变化、腹痛范围及腹膜刺激征是否加重。\n"
            "\n【其他科室补充】\n"
            "- [internal w=0.742] 诊断: 急腹症待明确，阑尾炎可能性高; 处置: 建议补液并完善炎症指标。\n"
            "- [general w=0.701] 诊断: 右下腹急腹症待排; 关注: 若疼痛加剧或持续呕吐应及时线下就诊。"
        ),
        "disclaimer": "【免责声明】本报告已对可能引发直接处方或高风险操作的表达做降级处理，仅供就医前信息参考，不构成具体诊疗依据。",
        "dept_opinions": [
            {
                "dept": "surgery",
                "weight": 0.769,
                "self_confidence": "high",
                "diagnosis": "急性阑尾炎可能性大。",
                "differential": "需与肠梗阻、泌尿系结石及妇科急腹症鉴别。",
                "treatment": "建议完善腹部CT；如指征明确，可由外科评估手术。",
                "attention": "关注体温、压痛范围和腹膜刺激征变化。",
            },
            {
                "dept": "internal",
                "weight": 0.742,
                "self_confidence": "high",
                "diagnosis": "急腹症待明确，阑尾炎可能性高。",
                "differential": "注意与胃肠炎和泌尿系结石区分。",
                "treatment": "建议先补液，复查血常规和CRP。",
                "attention": "若出现持续呕吐或高热，应尽快线下处理。",
            },
            {
                "dept": "general",
                "weight": 0.701,
                "self_confidence": "medium",
                "diagnosis": "右下腹急腹症待排。",
                "differential": "可与肠痉挛、肠系膜淋巴结炎等情况区分。",
                "treatment": "建议尽快至具备影像与外科条件的医院就诊。",
                "attention": "疼痛范围扩大或活动受限时需及时复诊。",
            },
        ],
    },
    # ===================== Case 2: 儿童上呼吸道感染 / 急性扁桃体炎倾向 =====================
    {
        "case": {
            "chief_complaint": "发热伴咽痛2天",
            "symptoms": "6岁男童，体温最高39.2℃，伴咽痛、轻咳，食欲下降，无皮疹。",
            "medical_history": "既往体健，无慢性病史。",
            "exam_results": "咽部充血，扁桃体Ⅰ~Ⅱ度肿大；血常规白细胞11.5×10^9/L。",
        },
        "routing": {
            "candidates": _candidates([
                ("pediatrics", 0.621),
                ("internal", 0.173),
                ("general", 0.138),
                ("surgery", 0.068),
            ]),
            "triage_tag": "single_clear",
            "fallback_triggered": False,
            "retrieval_hits": [],
        },
        "mode": "serial",
        "aggregation_level": 1,
        "safety_action": "pass",
        "summary": (
            "【一致性综合意见 · 主导科室: 儿科】\n"
            "诊断倾向: 发热伴咽痛，咽部充血明显，优先考虑急性上呼吸道感染或急性扁桃体炎。\n"
            "鉴别要点: 需与流感、肺炎早期及传染性单核细胞增多症鉴别。\n"
            "处置建议: 建议完善血常规并根据体温变化进行对症处理，必要时复诊评估是否需要进一步检查。\n"
            "关注事项: 若持续高热、精神差或出现呼吸急促，应及时线下就诊。"
        ),
        "disclaimer": "【免责声明】本报告仅供辅助参考，请结合线下医生面诊与检查结果综合判断。",
        "dept_opinions": [
            {
                "dept": "pediatrics",
                "weight": 0.812,
                "self_confidence": "high",
                "diagnosis": "急性上呼吸道感染或急性扁桃体炎可能性大。",
                "differential": "需与流感和肺炎早期鉴别。",
                "treatment": "建议先予对症退热和补液，必要时复诊评估。",
                "attention": "若持续高热、精神萎靡或呼吸急促，应及时就医。",
            },
        ],
    },
    # ===================== Case 3: 上消化道出血 / 消化性溃疡倾向 =====================
    {
        "case": {
            "chief_complaint": "黑便伴上腹痛1天",
            "symptoms": "昨日起黑便2次，上腹隐痛，伴头晕乏力，无呕血。",
            "medical_history": "既往反复反酸、上腹不适，近1周因腰痛间断服用止痛药。",
            "exam_results": "血红蛋白96 g/L，大便隐血阳性，心率102次/分。",
        },
        "routing": {
            "candidates": _candidates([
                ("internal", 0.472),
                ("general", 0.241),
                ("surgery", 0.201),
                ("pediatrics", 0.086),
            ]),
            "triage_tag": "single_clear",
            "fallback_triggered": False,
            "retrieval_hits": [],
        },
        "mode": "serial",
        "aggregation_level": 2,
        "safety_action": "pass",
        "summary": (
            "【加权综合意见 · 主导科室: 内科】\n"
            "诊断倾向: 黑便伴上腹痛和贫血表现，首先考虑上消化道出血，消化性溃疡或胃黏膜损伤可能性较大。\n"
            "鉴别要点: 需与食管胃底静脉曲张破裂、胃癌出血及下消化道出血相鉴别。\n"
            "处置建议: 建议尽快完善血常规复查、凝血功能及胃镜等检查，必要时住院进一步评估。\n"
            "关注事项: 若出现呕血、明显乏力加重或黑便频次增加，应及时急诊就诊。"
        ),
        "disclaimer": "【免责声明】本报告仅供辅助参考，请结合线下医生面诊与检查结果综合判断。",
        "dept_opinions": [
            {
                "dept": "internal",
                "weight": 0.754,
                "self_confidence": "high",
                "diagnosis": "上消化道出血可能性大，考虑消化性溃疡或药物相关胃黏膜损伤。",
                "differential": "需与食管胃底静脉曲张破裂、胃癌出血及下消化道出血区分。",
                "treatment": "建议尽快完善血常规、凝血功能和胃镜评估，必要时住院处理。",
                "attention": "若出现呕血、心慌或乏力加重，应及时急诊就诊。",
            },
        ],
    },
    # ===================== Case 4: 胸闷伴血压明显升高 =====================
    {
        "case": {
            "chief_complaint": "胸闷伴头晕4小时",
            "symptoms": "活动后胸闷，伴头晕和心悸，无明确胸痛，休息后缓解不明显。",
            "medical_history": "高血压病史5年，平时服药不规律。",
            "exam_results": "家庭自测血压180/104 mmHg，心率96次/分。",
        },
        "routing": {
            "candidates": _candidates([
                ("general", 0.286),
                ("internal", 0.274),
                ("surgery", 0.236),
                ("pediatrics", 0.204),
            ]),
            "triage_tag": "ambiguous",
            "fallback_triggered": True,
            "retrieval_hits": [],
        },
        "mode": "parallel",
        "aggregation_level": 3,
        "safety_action": "arbitrated",
        "summary": (
            "【仲裁综合意见 · 主导科室: 全科】\n"
            "诊断倾向: 胸闷伴血压明显升高，需优先排除高血压急症及心血管事件，目前不支持居家观察处理。\n"
            "鉴别要点: 需与急性冠脉综合征、心律失常、焦虑相关过度换气及脑血管事件前驱状态鉴别。\n"
            "处置建议: 建议尽快至有急诊能力的医院完善血压复测、心电图、肌钙蛋白及必要影像检查。\n"
            "关注事项: 若出现持续胸痛、呼吸困难、肢体无力或意识改变，应立即线下急诊就诊。\n"
            "\n【其他科室补充】\n"
            "- [internal w=0.703] 诊断: 需警惕高血压急症; 处置: 尽快完成心电图和心肌损伤标志物检查。\n"
            "- [surgery w=0.412] 诊断: 暂无明确外科急症证据; 关注: 如出现进行性胸背部撕裂样疼痛需警惕大血管问题。"
        ),
        "disclaimer": "【免责声明】本报告已在多科室分歧基础上经仲裁生成，存在一定不确定性，请尽快线下就诊进一步评估。",
        "dept_opinions": [
            {
                "dept": "general",
                "weight": 0.741,
                "self_confidence": "high",
                "diagnosis": "胸闷伴明显血压升高，需首先按高风险心血管症状处理。",
                "differential": "需与急性冠脉综合征、心律失常及焦虑相关症状鉴别。",
                "treatment": "建议立即至急诊完善血压复测、心电图和心肌损伤标志物检查。",
                "attention": "若出现持续胸痛、呼吸困难或神经系统症状应立即就医。",
            },
            {
                "dept": "internal",
                "weight": 0.703,
                "self_confidence": "high",
                "diagnosis": "需警惕高血压急症或心肌缺血。",
                "differential": "需与高血压亚急性升高和非心源性胸闷区分。",
                "treatment": "建议尽快完成心电图、肌钙蛋白和基础生化检查。",
                "attention": "若血压持续升高并伴不适，应及时急诊处理。",
            },
            {
                "dept": "surgery",
                "weight": 0.412,
                "self_confidence": "medium",
                "diagnosis": "当前暂无明确外科急腹症证据。",
                "differential": "如出现突发胸背部剧痛，应警惕主动脉夹层等大血管问题。",
                "treatment": "建议结合影像检查进一步排除大血管急症。",
                "attention": "疼痛性质改变时需立即复评。",
            },
        ],
    },
    # ===================== Case 5: 急性荨麻疹（皮肤科主导）=====================
    {
        "case": {
            "chief_complaint": "身上突然起了很多包，越挠越多",
            "symptoms": "昨晚进食海鲜后约2小时，躯干及四肢出现大片风团，伴剧烈瘙痒，无呼吸困难。",
            "medical_history": "既往有对虾过敏史，近期未用药。",
            "exam_results": "皮肤科查体：躯干四肢散在红色风团，直径1~5 cm，压之褪色，无水疱。",
        },
        "routing": {
            "candidates": _candidates([
                ("dermatology", 0.581),
                ("general", 0.198),
                ("internal", 0.142),
                ("surgery", 0.079),
            ]),
            "triage_tag": "single_clear",
            "fallback_triggered": False,
            "retrieval_hits": [],
        },
        "mode": "serial",
        "aggregation_level": 1,
        "safety_action": "pass",
        "summary": (
            "【一致性综合意见 · 主导科室: 皮肤科】\n"
            "诊断倾向: 进食海鲜后急发风团伴瘙痒，符合急性荨麻疹（食物过敏诱发）。\n"
            "鉴别要点: 需与血管性水肿、药疹及病毒疹鉴别；注意是否合并过敏性休克前驱表现。\n"
            "处置建议: 建议立即停止接触可疑过敏原，口服抗组胺药处理；若出现喉头水肿或低血压需急诊处置。\n"
            "关注事项: 密切观察呼吸道及循环状况，48小时内症状未消退应复诊。"
        ),
        "disclaimer": "【免责声明】本报告仅供辅助参考，请结合线下医生面诊与检查结果综合判断。",
        "dept_opinions": [
            {
                "dept": "dermatology",
                "weight": 0.831,
                "self_confidence": "high",
                "diagnosis": "急性荨麻疹，食物过敏诱发可能性大。",
                "differential": "需与血管性水肿及药物性皮疹鉴别。",
                "treatment": "建议口服第二代抗组胺药，必要时短期使用糖皮质激素。",
                "attention": "若出现口唇水肿、呼吸困难或血压下降，应立即急诊就诊。",
            },
        ],
    },
    # ===================== Case 6: 异位妊娠可能（妇产科主导）=====================
    {
        "case": {
            "chief_complaint": "月经推迟3周，昨天开始右侧小腹一阵一阵地疼",
            "symptoms": "末次月经推迟约21天，昨起右下腹阵发性隐痛，伴少量阴道不规则出血，轻微头晕。",
            "medical_history": "既往月经规律，无手术史，有宫内节育器放置史2年。",
            "exam_results": "尿妊娠试验阳性；血HCG 1240 mIU/mL；阴道超声：宫腔未见妊娠囊，右附件区可疑低回声包块。",
        },
        "routing": {
            "candidates": _candidates([
                ("gynecology", 0.524),
                ("surgery", 0.261),
                ("internal", 0.138),
                ("general", 0.077),
            ]),
            "triage_tag": "multi_cross",
            "fallback_triggered": False,
            "retrieval_hits": [],
        },
        "mode": "hybrid",
        "aggregation_level": 2,
        "safety_action": "degraded",
        "summary": (
            "【加权综合意见 · 主导科室: 妇产科】\n"
            "诊断倾向: 停经伴阳性妊娠试验及右附件低回声包块，需高度警惕异位妊娠（宫外孕）。\n"
            "鉴别要点: 需与黄体破裂、急性阑尾炎及宫内早孕合并附件囊肿鉴别。\n"
            "处置建议: 建议立即至妇产科急诊完善HCG动态监测及超声复查，评估是否需要手术干预。\n"
            "关注事项: 若出现持续腹痛加剧、晕厥或肛门坠胀感，应立即急诊就诊。\n"
            "\n【其他科室补充】\n"
            "- [surgery w=0.614] 诊断: 不除外急腹症，需结合妇产科评估; 关注: 腹膜刺激征阳性时需急诊处理。"
        ),
        "disclaimer": "【免责声明】本报告已对可能引发直接处方或高风险操作的表达做降级处理，仅供就医前信息参考，不构成具体诊疗依据。",
        "dept_opinions": [
            {
                "dept": "gynecology",
                "weight": 0.847,
                "self_confidence": "high",
                "diagnosis": "异位妊娠（宫外孕）可能性大，需紧急评估。",
                "differential": "需与黄体破裂、宫内早孕及急性盆腔炎鉴别。",
                "treatment": "建议立即急诊就诊，完善HCG动态及超声检查，必要时手术。",
                "attention": "一旦出现突发剧痛或休克征象，应立即急诊外科介入。",
            },
            {
                "dept": "surgery",
                "weight": 0.614,
                "self_confidence": "medium",
                "diagnosis": "腹腔内出血不除外，需妇产科明确诊断后联合处理。",
                "differential": "需与急性阑尾炎区分。",
                "treatment": "如确诊宫外孕破裂，需急诊手术。",
                "attention": "腹膜刺激征阳性或血压下降时需立即升级处理。",
            },
        ],
    },
    # ===================== Case 7: 前列腺增生（男科主导）=====================
    {
        "case": {
            "chief_complaint": "尿越来越细，晚上老是要起来上厕所",
            "symptoms": "近半年排尿费力、尿线变细，夜尿3~4次，偶有尿不尽感，无血尿。",
            "medical_history": "65岁男性，既往高血压，规律服用降压药，无糖尿病史。",
            "exam_results": "PSA 3.8 ng/mL；直肠指检：前列腺Ⅱ度增大，质地均匀，无结节；残余尿量约85 mL。",
        },
        "routing": {
            "candidates": _candidates([
                ("andrology", 0.463),
                ("internal", 0.272),
                ("surgery", 0.185),
                ("general", 0.080),
            ]),
            "triage_tag": "single_clear",
            "fallback_triggered": False,
            "retrieval_hits": [],
        },
        "mode": "serial",
        "aggregation_level": 2,
        "safety_action": "pass",
        "summary": (
            "【加权综合意见 · 主导科室: 男科】\n"
            "诊断倾向: 老年男性，下尿路症状（夜尿增多、尿线细、排尿费力）伴前列腺增大，符合良性前列腺增生（BPH）。\n"
            "鉴别要点: 需与前列腺癌（PSA升高需复查）、膀胱过度活动症及尿路感染鉴别。\n"
            "处置建议: 建议完善尿动力学检查；PSA复查排除恶性；可评估α受体阻滞剂治疗。\n"
            "关注事项: 若出现急性尿潴留或血尿，应及时就诊；同时关注降压药对排尿的影响。"
        ),
        "disclaimer": "【免责声明】本报告仅供辅助参考，请结合线下医生面诊与检查结果综合判断。",
        "dept_opinions": [
            {
                "dept": "andrology",
                "weight": 0.793,
                "self_confidence": "high",
                "diagnosis": "良性前列腺增生（BPH）可能性大。",
                "differential": "PSA轻度升高需复查，排除前列腺癌；并与膀胱功能异常鉴别。",
                "treatment": "建议先行生活方式指导，评估是否需要α受体阻滞剂或5α还原酶抑制剂治疗。",
                "attention": "定期复查PSA和残余尿量；若症状快速加重应及时就诊。",
            },
            {
                "dept": "internal",
                "weight": 0.621,
                "self_confidence": "medium",
                "diagnosis": "下尿路症状，BPH最符合目前表现。",
                "differential": "注意当前降压药物是否影响膀胱出口。",
                "treatment": "建议继续规律监测血压，泌尿科就诊评估手术指征。",
                "attention": "若PSA复查明显升高，应尽快完善前列腺穿刺活检评估。",
            },
        ],
    },
    # ===================== Case 8: 轻度皮肤症状（皮肤科主导，多科室交叉 / 并行 / L1 一致）=====================
    {
        "case": {
            "chief_complaint": "面部出现红色皮疹伴轻度瘙痒2天，无发热",
            "symptoms": "2天前无明显诱因出现面部红斑，范围逐渐扩大，伴轻微瘙痒，无渗液，无疼痛，无发热，无畏寒。",
            "medical_history": "既往体健，无慢性病史，无已知药物或食物过敏史。",
            "exam_results": "近期未更换护肤品，无明显接触刺激性物质，无类似病史。",
        },
        "routing": {
            "candidates": _candidates([
                ("dermatology", 0.477),
                ("internal", 0.342),
                ("general", 0.181),
            ]),
            "triage_tag": "multi_cross",
            "fallback_triggered": False,
            "retrieval_hits": [],
        },
        "mode": "hybrid",
        "aggregation_level": 1,
        "safety_action": "pass",
        "summary": (
            "【一致性综合意见 · 主导科室: 皮肤科】\n"
            "诊断倾向: 综合各科室意见，当前情况更倾向于轻度接触性皮炎或过敏性皮肤反应。"
            "结合病程较短、皮损局限于面部、以轻度瘙痒为主且无发热及明显全身不适，"
            "暂未见明确支持系统性感染或其他全身性疾病相关皮肤表现的证据，整体风险较低。\n"
            "鉴别要点: 目前主要需与脂溢性皮炎及早期感染性皮损相鉴别，"
            "同时注意后续是否出现渗液、疼痛、皮疹范围明显扩大或伴随其他系统症状。\n"
            "处置建议: 现阶段建议以避免刺激因素和温和护理为主，保持面部清洁，"
            "减少抓挠及频繁摩擦，避免继续使用可疑刺激性护肤品或自行叠加外用药物。"
            "若红斑或瘙痒持续不缓解，可在医生指导下进行规范的抗炎或抗过敏对症处理。\n"
            "关注事项: 后续除观察皮疹颜色、范围和局部变化外，也应注意是否出现发热、乏力等全身表现。"
            "若出现明显扩散、渗液、肿胀、疼痛加重，或伴发热等症状，应及时进一步就诊评估。\n"
            "\n【其他科室同向意见】\n"
            "- [internal] 倾向局部过敏或轻度炎症反应，系统性疾病可能性低。\n"
            "- [general] 优先采取避免刺激与观察策略，2~3天内无改善建议专科就诊。"
        ),
        "disclaimer": "【免责声明】本报告仅供辅助参考，请结合线下医生面诊与检查结果综合判断。",
        "dept_opinions": [
            {
                "dept": "dermatology",
                "weight": 0.812,
                "self_confidence": "high",
                "diagnosis": "考虑面部接触性皮炎或轻度过敏性皮炎可能性较大。",
                "differential": "需与脂溢性皮炎鉴别，并排除早期感染性皮肤病。",
                "treatment": "避免可疑刺激因素；可外用温和抗炎药物（如低效糖皮质激素）；必要时口服抗过敏药物。",
                "attention": "避免搔抓以防继发感染，密切观察皮疹变化。",
            },
            {
                "dept": "internal",
                "weight": 0.684,
                "self_confidence": "medium",
                "diagnosis": "倾向过敏反应或轻度炎症反应，系统性疾病可能性较低。",
                "differential": "需排除病毒感染早期表现；关注是否伴随其他系统症状。",
                "treatment": "以对症处理为主；必要时口服抗组胺药物；注意观察是否出现发热或全身症状。",
                "attention": "若症状加重或扩散应及时就医，避免自行使用刺激性药物。",
            },
            {
                "dept": "general",
                "weight": 0.602,
                "self_confidence": "medium",
                "diagnosis": "倾向于轻度皮肤过敏或接触性刺激反应。",
                "differential": "结合皮肤科意见优先考虑局部因素，排除环境或饮食诱因。",
                "treatment": "避免刺激源，保持皮肤清洁，症状轻微可先观察。",
                "attention": "若2~3天内无改善建议专科就诊。",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# 写入逻辑
# ---------------------------------------------------------------------------


def _dept_opinion_payload(op: Dict[str, Any]) -> Dict[str, Any]:
    """构造与 DepartmentOpinion 字段对齐的 payload, 额外保留 weight 供前端使用."""
    return {
        "dept": op["dept"],
        "diagnosis": op["diagnosis"],
        "differential": op["differential"],
        "treatment": op["treatment"],
        "attention": op["attention"],
        "self_confidence": op["self_confidence"],
        "inference_meta": {"weight": op["weight"]},
        "weight": op["weight"],
    }


def _insert_case(conn, data: Dict[str, Any], created_at: str) -> str:
    sid = uuid.uuid4().hex
    cid = uuid.uuid4().hex

    # session
    conn.execute(
        "INSERT INTO session (id, created_at, meta) VALUES (?, ?, ?)",
        (sid, created_at, json.dumps({"source": "seed_demo_cases"}, ensure_ascii=False)),
    )

    # case
    case = data["case"]
    conn.execute(
        'INSERT INTO "case" (id, session_id, chief_complaint, symptoms, medical_history, exam_results, created_at) '
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            cid,
            sid,
            case["chief_complaint"],
            case["symptoms"],
            case["medical_history"],
            case["exam_results"],
            created_at,
        ),
    )

    round_ = 1

    # routing message
    routing = data["routing"]
    conn.execute(
        "INSERT INTO message (session_id, round, role, payload_json, inference_meta_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            sid,
            round_,
            "routing",
            json.dumps(routing, ensure_ascii=False),
            json.dumps(
                {
                    "triage_tag": routing["triage_tag"],
                    "fallback_triggered": routing["fallback_triggered"],
                    "n_candidates": len(routing["candidates"]),
                    "n_retrieval_hits": 0,
                },
                ensure_ascii=False,
            ),
            created_at,
        ),
    )

    # opinion messages
    dept_opinions = [_dept_opinion_payload(op) for op in data["dept_opinions"]]
    for op_payload in dept_opinions:
        conn.execute(
            "INSERT INTO message (session_id, round, role, payload_json, inference_meta_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                sid,
                round_,
                "opinion",
                json.dumps(op_payload, ensure_ascii=False),
                json.dumps({"weight": op_payload["weight"]}, ensure_ascii=False),
                created_at,
            ),
        )

    # report message
    report_payload = {
        "summary": data["summary"],
        "dept_opinions": dept_opinions,
        "aggregation_level": data["aggregation_level"],
        "safety_action": data["safety_action"],
        "disclaimer": data["disclaimer"],
    }
    conn.execute(
        "INSERT INTO message (session_id, round, role, payload_json, inference_meta_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            sid,
            round_,
            "report",
            json.dumps(report_payload, ensure_ascii=False),
            json.dumps(
                {
                    "aggregation_level": data["aggregation_level"],
                    "safety_action": data["safety_action"],
                    "mode": data["mode"],
                    "n_opinions": len(dept_opinions),
                },
                ensure_ascii=False,
            ),
            created_at,
        ),
    )

    return sid


def _purge_existing_seed(conn) -> int:
    """删除上一次该脚本插入的 session (meta.source == 'seed_demo_cases'), 以免重复."""
    rows = conn.execute(
        "SELECT id FROM session WHERE json_extract(meta, '$.source') = 'seed_demo_cases'"
    ).fetchall()
    sids = [r["id"] for r in rows]
    for sid in sids:
        conn.execute("DELETE FROM message WHERE session_id = ?", (sid,))
        conn.execute('DELETE FROM "case" WHERE session_id = ?', (sid,))
        conn.execute("DELETE FROM session WHERE id = ?", (sid,))
    return len(sids)


# 把所有"非 seed"会话的时间整体平移到该截止点之前 (含 case / message),
# 以保证 seed (2025-11/12) 排在历史记录顶部.
_NON_SEED_CUTOFF = "2025-10-31 23:00:00"


def _shift_non_seed_before_cutoff(conn, cutoff: str = _NON_SEED_CUTOFF) -> int:
    """对 meta.source != 'seed_demo_cases' 的会话, 将其 created_at 整体减去一个常量,
    使最大 created_at 不晚于 cutoff. 同步更新对应 case / message 的 created_at,
    保留各记录的相对先后顺序.

    返回受影响的 session 数 (0 表示无需平移).
    """
    rows = conn.execute(
        "SELECT id, created_at FROM session "
        "WHERE COALESCE(json_extract(meta, '$.source'), '') != 'seed_demo_cases'"
    ).fetchall()
    if not rows:
        return 0

    # 找当前最大 created_at; 若其已 <= cutoff 则无需平移.
    max_dt = max(r["created_at"] for r in rows if r["created_at"])
    delta_sql_max = conn.execute(
        "SELECT (julianday(?) - julianday(?)) AS d", (cutoff, max_dt)
    ).fetchone()
    delta_days = delta_sql_max["d"]  # cutoff - max_dt, 单位: 天
    if delta_days >= 0:
        return 0  # 已经早于 cutoff, 不动

    # delta_days < 0: 需要把每条记录的 created_at 加上 delta_days 天 (即往前移)
    sids = [r["id"] for r in rows]
    placeholders = ",".join("?" * len(sids))
    params = [delta_days] + sids

    conn.execute(
        f'UPDATE session SET created_at = '
        f"datetime(julianday(created_at) + ?) WHERE id IN ({placeholders})",
        params,
    )
    conn.execute(
        f'UPDATE "case" SET created_at = '
        f"datetime(julianday(created_at) + ?) WHERE session_id IN ({placeholders})",
        params,
    )
    conn.execute(
        f"UPDATE message SET created_at = "
        f"datetime(julianday(created_at) + ?) WHERE session_id IN ({placeholders})",
        params,
    )
    return len(sids)


def main() -> None:
    init_schema(DB_PATH)
    conn = get_conn(DB_PATH)
    purged = _purge_existing_seed(conn)
    if purged:
        print(f"Purged {purged} previous seed session(s).")
    shifted = _shift_non_seed_before_cutoff(conn)
    if shifted:
        print(f"Shifted {shifted} non-seed session(s) to before {_NON_SEED_CUTOFF}.")
    inserted: List[str] = []
    for i, data in enumerate(CASES, start=1):
        created_at = _CREATED_AT[i - 1]
        sid = _insert_case(conn, data, created_at)
        inserted.append(sid)
        print(
            f"[{i}/{len(CASES)}] inserted session={sid} "
            f"created_at={created_at} chief={data['case']['chief_complaint']}"
        )
    print(f"\nDone. {len(inserted)} demo cases inserted into {DB_PATH}.")


if __name__ == "__main__":
    main()
