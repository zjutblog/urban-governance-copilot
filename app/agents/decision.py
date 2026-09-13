"""Decision Agent：综合生成治理决策 + 回复建议（含 CoT + 证据约束）。

防幻觉设计（v2）：
1. 强制从检索案例中选责任部门（不凭空编造）
2. related_cases 必须引用真实案例 ID（后处理校验并剔除伪造引用）
3. policy_references 除非 100% 确定否则留空（法规编造是最危险的幻觉）
4. 回复只写程序性表述，禁止编造未发生的事实
5. 无检索证据时自动兜底检索一次（防 LLM 计划漏掉 retrieve 步骤）
6. 后处理"引用溯源校验"：部门/案例 ID 对不上检索结果 → 降 confidence + 风险警告
"""
from __future__ import annotations

import re
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.domain.decision import GovernanceDecision
from app.llm.client import get_llm
from app.rag.corpus import get_corpus
from app.rag.policy_corpus import format_policy_evidence


class _DecisionWithCoT(GovernanceDecision):
    """在决策基础上追加显式思维链，驱动 trace 可视化。"""
    reasoning_chain: list[str] = Field(default_factory=list, description="可解释推理链（5-8步，展示完整思考过程）")

    @field_validator("reasoning_chain", mode="before")
    @classmethod
    def _split_chain(cls, v):
        # 容错：模型可能输出带编号的字符串而非数组
        if isinstance(v, str):
            return [x.strip() for x in v.split("\n") if x.strip()]
        return v

    @field_validator("related_cases", "policy_references", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        # 容错：LLM 常用空字符串/逗号串/数字列表表示，统一转成字符串列表
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return v

    @field_validator("estimated_difficulty", "responsible_department", "recommended_action",
                     "risk_warning", "generated_reply", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        # 容错：LLM 常把难度/等级输出成数字（如 3）导致 string 校验失败 → 统一转字符串
        if v is None:
            return v
        return str(v)


def _ensure_docs(state: dict) -> dict:
    """兜底：若计划漏掉 retrieve 步骤，决策前补一次检索（BM25，毫秒级）。"""
    docs = state.get("retrieved_documents") or []
    if docs:
        return state
    corpus = get_corpus()
    docs = corpus["retriever"].search(state["complaint"].content, top_k=5)
    new_state = dict(state)
    new_state["retrieved_documents"] = docs
    return new_state


def _ensure_policy_docs(state: dict) -> dict:
    """兜底：若工作流漏掉 retrieve_policy 步骤，决策前补一次政策检索（BM25，毫秒级）。"""
    policy_docs = state.get("policy_documents") or []
    if policy_docs:
        return state
    from app.rag.policy_corpus import search_policies

    new_state = dict(state)
    new_state["policy_documents"] = search_policies(state["complaint"].content, top_k=6)
    return new_state


def _policy_prompt_block(policy_docs: list) -> tuple[str, str]:
    """构造 prompt 政策依据块 + 可引用政策条款列表（仅用检索到的真实条款）。"""
    if not policy_docs:
        return "（未检索到相关法规条款）", "（无）"
    evidence = format_policy_evidence(policy_docs, max_items=6)
    valid_refs = "、".join(f"《{d.metadata.get('title', '')}》{d.metadata.get('article_no', '')}" for d in policy_docs[:6]) or "（无）"
    return evidence, valid_refs


def _decision_prompt(state: dict) -> str:
    complaint = state.get("complaint")
    analysis = state.get("analysis")
    perception = state.get("perception") or {}
    docs = state.get("retrieved_documents") or []
    policy_docs = state.get("policy_documents") or []
    memory = state.get("memory_context") or []

    case_lines = []
    for d in docs[:8]:
        dept = d.metadata.get("department", "") or "（未知部门）"
        case_lines.append(f"- [案例{d.doc_id}] 部门:{dept} | {d.content[:180]}")
    cases = "\n".join(case_lines) or "（无历史案例）"
    case_ids = ", ".join(d.doc_id for d in docs[:8]) or "（无）"
    dept_options = "、".join(
        sorted({d.metadata.get("department", "") for d in docs if d.metadata.get("department")})
    ) or "（无，可自行判断）"
    policy_evidence, valid_policy_refs = _policy_prompt_block(policy_docs)
    mem_txt = "\n".join(f"- {m}" for m in memory) or "（无历史对话）"

    return f"""你是城市治理决策专家。请基于【历史案例】给出治理决策，**严格引用证据，禁止编造**。

【群众诉求】{complaint.content}

【历史对话上下文】（用户之前反映过的事项，若本条是追问，回复需衔接前文）
{mem_txt}

【本地分类】{perception.get('category', '未知')}

【分析结果】{analysis.model_dump() if analysis else '（无）'}

【历史案例】（每条含真实责任部门，是你唯一的事实来源）
{cases}

可参考的案例ID：{case_ids}
案例中出现过的责任部门：{dept_options}

【政策法规依据】（真实条款，仅供引用，**禁止另编法规**）
{policy_evidence}

可引用的政策条款（**仅限从上述列表中引用**，格式：《标题》第X条）：{valid_policy_refs}

字段要求（防幻觉规则）：
1. responsible_department：**必须从"案例中出现过的责任部门"中选择**（可微调为同职能更具体单位，但不得凭空编造不存在的部门）
2. recommended_action：建议措施，应基于案例中的实际处置方式
3. related_cases：**必须填写**本次引用的案例ID（从"可参考的案例ID"中选，至少1个，最多3个）
4. policy_references：**必须从"可引用的政策条款"中选取**与本次诉求最相关的真实条款（格式《标题》第X条，最多3条）；若均不相关则留空，**禁止编造不存在的法规/条款**
5. estimated_difficulty：处置难度
6. risk_warning：风险提示（如有任何不确定处必须写明）
7. generated_reply：面向市民的回复建议（**80字以内**）。**只写程序性、可兑现的表述**（如"已转交相关部门核实处理""将跟进督办并反馈"），**禁止编造具体事实**（不得写"已安排执法人员""已拆除""已处罚"等未发生的事）
8. confidence：0~1，对本次判断的确信度
9. reasoning_chain：**详细推理链（5-8步）**，展示完整思考过程，类似 DeepSeek Harness 风格：
   - 第1步：分析诉求类型和关键信息提取
   - 第2步：判断是否需要空间分析/模型计算
   - 第3步：评估历史案例的参考价值
   - 第4步：确定责任部门的依据
   - 第5步：生成回复的考虑因素
   - 可继续添加更多步骤...

请以 JSON 格式输出上述字段。
"""


def _normalize_ref(s: str) -> str:
    """把《》/空白/括号统一去掉，便于比较政策引用。"""
    return re.sub(r"[《》「」\[\]\s（）()、,，]", "", s or "")


def _is_valid_policy_ref(ref: str, policy_docs: list) -> bool:
    """校验某个政策引用是否指向检索到的真实条款（标题+条款号都能对上）。"""
    if not policy_docs or not ref:
        return False
    nr = _normalize_ref(ref)
    for d in policy_docs:
        title = _normalize_ref(d.metadata.get("title", ""))
        art = _normalize_ref(d.metadata.get("article_no", ""))
        # 标题精确/前缀匹配 + 条款号匹配
        if title and (nr == title or title in nr) and art and art in nr:
            return True
    return False


def _verify_grounding(decision: _DecisionWithCoT, docs: list, policy_docs: list) -> None:
    """引用溯源校验：部门/案例ID/政策条款 必须能在检索结果中找到，否则降置信度并警告。"""
    if not docs:
        decision.confidence = min(decision.confidence, 0.3)
        decision.risk_warning = (decision.risk_warning or "") + "；【无检索证据】置信度已下调，请人工核实"
    else:
        known_depts = {d.metadata.get("department", "") for d in docs if d.metadata.get("department")}
        dept = decision.responsible_department or ""
        if dept and known_depts:
            matched = any(dept == k or dept in k or k in dept for k in known_depts)
            if not matched:
                decision.confidence = min(decision.confidence, 0.4)
                decision.risk_warning = (decision.risk_warning or "") + f"；【引用异常】责任部门'{dept}'不在检索案例中，请人工核实"

        valid_ids = {d.doc_id for d in docs}
        fake = [c for c in decision.related_cases if c not in valid_ids]
        if fake:
            decision.related_cases = [c for c in decision.related_cases if c in valid_ids]
            decision.risk_warning = (decision.risk_warning or "") + f"；【已剔除伪造案例引用】{fake}"
        if not decision.related_cases and docs:
            decision.related_cases = [d.doc_id for d in docs[:1]]

    # 政策条款溯源校验：剔除不在检索结果里的编造引用
    fake_policy = [p for p in decision.policy_references if not _is_valid_policy_ref(p, policy_docs)]
    if fake_policy:
        decision.policy_references = [p for p in decision.policy_references if _is_valid_policy_ref(p, policy_docs)]
        decision.risk_warning = (decision.risk_warning or "") + f"；【已剔除编造/不可溯源的政策引用】{fake_policy}"
    if decision.policy_references and not policy_docs:
        decision.risk_warning = (decision.risk_warning or "") + "；【政策引用无检索支撑，请核实】"


def _fallback_decision(state: dict) -> _DecisionWithCoT:
    """解析失败时的保守兜底：不崩 pipeline，标记风险警告。"""
    analysis = state.get("analysis")
    docs = state.get("retrieved_documents") or []
    complaint = state.get("complaint")
    
    # 策略1: 从分析结果中获取部门
    dept = getattr(analysis, "predicted_department", None) if analysis else None
    
    # 策略2: 基于留言内容关键词智能匹配部门（而非简单取第一个）
    if not dept and complaint:
        content = complaint.content or ""
        # 关键词 -> 部门映射（与 dept_rules.py 保持一致）
        keyword_dept_map = [
            ("施工", "住建"), ("噪音", "城管执法"), ("污水", "水务"), ("供水", "水务"),
            ("路灯", "住建"), ("道路", "住建"), ("交通", "交通"), ("堵车", "交通"),
            ("教育", "教育体育"), ("学校", "教育体育"), ("医疗", "卫生健康"), ("医院", "卫生健康"),
            ("物业", "物业房产"), ("供暖", "能源"), ("供电", "能源"), ("燃气", "能源"),
            ("环保", "生态环境"), ("污染", "生态环境"), ("垃圾", "城管执法"),
            ("治安", "公安司法"), ("诈骗", "公安司法"), ("劳动", "人社"), ("社保", "人社"),
            # 新增：洪水/内涝相关
            ("积水", "水务"), ("内涝", "水务"), ("排水", "水务"), ("防洪", "水务"),
            ("暴雨", "水务"), ("汛期", "水务"), ("洪水", "水务"),
            # 新增：更多常见关键词
            ("停车", "城管执法"), ("违建", "城管执法"), ("占道", "城管执法"),
            ("低保", "民政"), ("残疾", "民政"), ("养老", "民政"),
            ("纳税", "财政税务"), ("发票", "财政税务"),
        ]
        for keyword, dept_name in keyword_dept_map:
            if keyword in content:
                dept = dept_name
                break
    
    # 策略3: 从检索案例中选择出现频率最高的部门（而非第一个）
    if not dept and docs:
        from collections import Counter
        dept_counter = Counter(
            d.metadata.get("department") for d in docs if d.metadata.get("department")
        )
        if dept_counter:
            # 优先选择职能部门（包含"局"、"委"、"办"等），而非行政区划（包含"区"、"县"、"市"）
            dept_candidates = dept_counter.most_common()
            # 按优先级排序：职能部门 > 行政区划
            def dept_priority(d):
                if any(kw in d for kw in ["局", "委", "办", "中心", "大队"]):
                    return 0  # 职能部门优先
                elif any(kw in d for kw in ["区", "县", "市"]):
                    return 1  # 行政区划次之
                return 2
            
            dept_candidates.sort(key=lambda x: dept_priority(x[0]))
            dept = dept_candidates[0][0] if dept_candidates else None

    # 政策引用：从检索到的真实条款中取最相关的前几条（不编造）
    policy_refs = [
        f"《{d.metadata.get('title', '')}》{d.metadata.get('article_no', '')}"
        for d in (state.get("policy_documents") or [])[:3]
    ]

    return _DecisionWithCoT(
        responsible_department=dept or "待人工核实",
        recommended_action="建议由属地相关部门核查处置",
        related_cases=[d.doc_id for d in docs[:2]],
        policy_references=policy_refs,
        generated_reply="已收悉您反映的问题，将转交相关部门核实处理，敬请关注。",
        confidence=0.3 if dept else 0.2,
        risk_warning="【大模型输出异常，已降级为保守建议，请人工核实】" if not dept else "【大模型输出异常，已降级为保守建议】",
        reasoning_chain=[
            "大模型输出解析异常，采用兜底策略",
            f"最终归口部门: {dept or '待人工核实'}",
            "建议人工介入核实",
        ],
    )


def make_decision(state: dict, temperature: float = 0.2) -> _DecisionWithCoT:
    state = _ensure_docs(state)
    state = _ensure_policy_docs(state)
    cfg = state.get("llm_config")
    try:
        decision_llm = get_llm(temperature, cfg).with_structured_output(_DecisionWithCoT, method="json_mode")
        decision = decision_llm.invoke(_decision_prompt(state))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"decision parse failed: {e}; retry at low temp...")
        try:
            decision = get_llm(0.1, cfg).with_structured_output(_DecisionWithCoT, method="json_mode").invoke(_decision_prompt(state))
        except Exception as e2:  # noqa: BLE001
            logger.error(f"decision retry failed, fallback: {e2}")
            decision = _fallback_decision(state)
    _verify_grounding(decision, state.get("retrieved_documents") or [], state.get("policy_documents") or [])
    return decision
