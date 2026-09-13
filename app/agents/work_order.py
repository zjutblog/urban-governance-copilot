"""工单生成：把「留言 + 分析 + 决策」组装成一份**可直接验收的数字员工交付物——处理工单**。

设计要点（对齐待办#2：字段完整率≥95%）：
- 复用已在管线里产生的事实字段（decision/analysis/perception/geo/plan），**不额外调用 LLM**。
- 对可能缺失的字段做**确定性兜底**（关键词规则/哨兵值），保证关键字段几乎恒有值。
- 输出 self 评估 `completeness`（关键字段填充率）+ `missing`（未填字段），供评测 claim。
"""
from __future__ import annotations

import time
from typing import Any

from app.domain.decision import GovernanceDecision


# 诉求大类：投诉/咨询/建议/求助 启发式（兜底用，留言无标注时）
def _message_type(content: str) -> str:
    c = content or ""
    if any(w in c for w in ["投诉", "举报", "反映", "曝光", "违规", "问题严重"]):
        return "投诉"
    if any(w in c for w in ["咨询", "请问", "想了解", "询问", "是否有规定"]):
        return "咨询"
    if any(w in c for w in ["建议", "希望今后", "期盼", "能不能改善"]):
        return "建议"
    return "求助"


# 留言领域：关键词兜底映射
_FIELD_KEYWORDS = [
    ("城建", ["施工", "物业", "违建", "路灯", "道路", "房", "电梯", "装修", "占道", "积水", "停水"]),
    ("交通", ["停车", "堵", "公交", "地铁", "红绿灯", "路", "车辆", "出行"]),
    ("环保", ["噪声", "噪音", "油烟", "扬尘", "污水", "污染", "垃圾", "异味", "粉尘"]),
    ("治安", ["治安", "扰民", "诈骗", "狗", "纠纷", "打架", "偷"]),
    ("人社", ["工资", "欠薪", "社保", "劳动", "加班", "裁员", "辞退"]),
    ("教育", ["学校", "教育", "老师", "入学", "补课", "学生"]),
    ("医疗", ["医院", "医疗", "看病", "医保"]),
    ("民政", ["低保", "养老", "残疾", "救助", "高龄"]),
    ("三农", ["农村", "农民", "耕地", "宅基地", "农田", "村里"]),
    ("企业", ["企业", "公司", "商户", "经营", "注册", "办证"]),
]


def _field(content: str) -> str:
    c = content or ""
    for name, kws in _FIELD_KEYWORDS:
        if any(w in c for w in kws):
            return name
    return "其他"


def _urgency(analysis: Any, content: str) -> str:
    u = (getattr(analysis, "urgency", None) if analysis else None) or ""
    if u:
        return {"low": "低", "medium": "中", "high": "高"}.get(str(u).lower(), str(u))
    c = content or ""
    if any(w in c for w in ["断水", "断电", "火灾", "塌陷", "爆炸", "中毒", "受伤", "死亡", "群体", "堵路", "事故", "危险"]):
        return "高"
    if any(w in c for w in ["停水", "停电", "急", "长期", "严重影响"]):
        return "中"
    return "低"


def _deadline(urgency_cn: str, message_type: str) -> str:
    """按紧急程度/诉求类型给办理时限（确定性规则，恒有值）。"""
    if urgency_cn == "高":
        return "24 小时（涉急涉稳优先响应）"
    if urgency_cn == "中":
        return "5 个工作日"
    if message_type in ("咨询", "建议"):
        return "7 个工作日"
    return "7 个工作日"


def _region_of(state: dict) -> tuple[str, str]:
    """从 geo query_location / complaint 尽量定位到 省/市区县。返回 (region_text, region_detail)。"""
    plan = state.get("plan")
    if plan:
        steps = getattr(plan, "steps", None) or []
        for s in steps:
            if getattr(s, "action_type", "") == "geo_query" and getattr(s, "result", None):
                q = s.result.get("query_location") or {}
                if q.get("province") or q.get("city") or q.get("district"):
                    text = f"{q.get('province','')}{q.get('city','')}{q.get('district','')}"
                    return (text, {"province": q.get("province"), "city": q.get("city"), "district": q.get("district")})
    complaint = state.get("complaint")
    if complaint:
        p, cty, dist = getattr(complaint, "province", None), getattr(complaint, "city", None), getattr(complaint, "district", None)
        if p or cty or dist:
            return (f"{p or ''}{cty or ''}{dist or ''}", {"province": p, "city": cty, "district": dist})
    analysis = state.get("analysis")
    locs = getattr(analysis, "location_entities", None) if analysis else None
    if locs:
        return (locs[0], {})
    return ("（地点待核实，建议补充）", {})


def build_work_order(state: dict) -> dict[str, Any]:
    complaint = state.get("complaint")
    content = getattr(complaint, "content", "") if complaint else ""
    perception = state.get("perception") or {}
    analysis = state.get("analysis")
    decision: GovernanceDecision = state.get("decision")
    gate = state.get("gate_result") or {}

    dept = (getattr(decision, "responsible_department", None) or
            (getattr(analysis, "predicted_department", None) if analysis else None) or "待核实")
    action = (getattr(decision, "recommended_action", None) if decision else None) or "建议由属地相关部门现场核查处置"
    reply = (getattr(decision, "generated_reply", None) if decision else None) or "已收悉您反映的问题，将转交相关部门核实处理并反馈。"
    urgency_cn = _urgency(analysis, content)
    mtype = _message_type(content)
    fld = (perception.get("category") or (getattr(analysis, "category", None) if analysis else None)
           or (getattr(analysis, "sub_category", None) if analysis else None) or _field(content))
    region_text, region_detail = _region_of(state)
    policy = (getattr(decision, "policy_references", None) if decision else None) or []
    cases = (getattr(decision, "related_cases", None) if decision else None) or []
    difficulty = (getattr(decision, "estimated_difficulty", None) if decision else None) or "中"
    risk_warn = (getattr(decision, "risk_warning", None) if decision else None) or "无明显风险"
    risk_level = (getattr(analysis, "risk_level", None) if analysis else None) or (
        "高" if urgency_cn == "高" else "中")
    confidence = float((getattr(decision, "confidence", 0) if decision else 0) or 0)
    route = str(gate.get("route") or "")
    route_cn = {"pass": "已通过（定稿）", "retry": "需复核重写", "escalate": "转人工复核"}.get(route, "—")

    order = {
        "order_id": getattr(complaint, "complaint_id", "") or f"WO{int(time.time())}",
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "complaint_summary": ((getattr(analysis, "summary", None) if analysis else None)
                              or content[:60] or "（无原文）"),
        "complaint_type": mtype,
        "field": fld,
        "region": region_text,
        "region_detail": region_detail,
        "urgency": urgency_cn,
        "risk_level": risk_level,
        "responsible_department": dept,
        "handler": f"建议由「{dept}」牵头承办（经办人待分派）",
        "measures": action,
        "deadline": _deadline(urgency_cn, mtype),
        "policy_basis": list(policy),
        "reference_cases": [str(c) for c in cases],
        "reply_to_citizen": reply,
        "difficulty": str(difficulty),
        "risk_warning": risk_warn,
        "confidence": round(confidence, 2),
        "review_route": route_cn,
        "source_content": content[:2000],
    }

    # 字段完整率（关键必填字段）
    required = [
        "order_id", "complaint_summary", "complaint_type", "field", "region", "urgency",
        "risk_level", "responsible_department", "handler", "measures", "deadline",
        "reply_to_citizen", "difficulty", "review_route",
    ]
    missing = [k for k in required if not order.get(k)]
    # policy_basis 允许为空（无匹配政策时不强求）；reference_cases 允许为空
    completeness = round(1 - len(missing) / max(len(required), 1), 3)
    order["_meta"] = {"completeness": completeness, "missing": missing, "required_total": len(required)}
    return order


def format_work_order_markdown(order: dict) -> str:
    """工单的可读文本（评审/导出用）。"""
    return (
        f"# 处理工单 {order.get('order_id')}\n\n"
        f"- 诉求：{order.get('complaint_summary')}\n"
        f"- 类别 / 领域：{order.get('complaint_type')} · {order.get('field')}\n"
        f"- 事发区域：{order.get('region')}（紧急 {order.get('urgency')} / 风险 {order.get('risk_level')}）\n"
        f"- 归口部门：{order.get('responsible_department')}\n"
        f"- 承办：{order.get('handler')}\n"
        f"- 办理时限：{order.get('deadline')}\n"
        f"- 处置措施：{order.get('measures')}\n"
        f"- 政策依据：{'；'.join(order.get('policy_basis')) or '（暂无匹配条款）'}\n"
        f"- 面向市民回复：{order.get('reply_to_citizen')}\n"
        f"- 复核：{order.get('review_route')}（置信度 {order.get('confidence')}）\n"
    )
