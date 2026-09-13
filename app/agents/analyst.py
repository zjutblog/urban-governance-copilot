"""Analyst Agent：LLM 分析，产出 ComplaintAnalysis。"""
from __future__ import annotations

from app.domain.analysis import ComplaintAnalysis
from app.llm.client import get_llm


def analyze(state: dict) -> ComplaintAnalysis:
    complaint = state.get("complaint")
    perception = state.get("perception") or {}
    docs = state.get("retrieved_documents") or []
    memory = state.get("memory_context") or []

    cases = "\n".join(f"- {d.content[:200]}" for d in docs[:3]) or "（无检索结果）"
    mem_txt = "\n".join(f"- {m}" for m in memory) or "（无历史对话）"

    prompt = f"""你是城市治理分析专家。分析下面群众留言。

【留言】{complaint.content}

【历史对话上下文】（用户之前反映过的事项，**可能与本条相关，若是追问请结合**）
{mem_txt}

【本地分类参考】{perception.get('category', '未知')}（置信度 {perception.get('category_confidence', 0):.2f}）

【相似历史案例】{cases}

【实体抽取规则】（重点：区分"地点"和"其他成分"，**"和/与/跟"连接的并列成分不一定是地点**）
- location_entities：只有**真正的物理地点**（可在地图上定位），如"太原市小店区""南中环路口""幸福小区""滨江路"
- time_entities：时间表述，如"晚上""凌晨""上周""连续三天"
- action_entities：行为/事件，如"施工""停水""占道经营""协商拆迁补偿"
- target_entities：受影响的对象/标的，如"路灯""暖气""房屋""业主""学生"

【示例1】"我家在太原市小店区幸福小区，小区附近晚上施工噪音很大"
→ location=["太原市小店区幸福小区","小区附近"]，time=["晚上"]，action=["施工"]，target=["噪音"]

【示例2 - 倒装句】"开发商在滨江路和业主协商拆迁补偿"
→ location=["滨江路"]，time=[]，action=["协商拆迁补偿"]，target=["业主"]
（"和业主"的"业主"是对象不是地点！只有"滨江路"是地点）

【示例3】"幸福小区门口和地下车库的灯不亮"
→ location=["幸福小区门口","地下车库"]，time=[]，action=["灯不亮"]，target=["灯"]
（"和"连接的是两个地点，此处都是地点）

【示例4】"小区楼下和晚上有人跳广场舞噪音大"
→ location=["小区楼下"]，time=["晚上"]，action=["跳广场舞"]，target=["噪音"]
（"和晚上"的"晚上"是时间不是地点！）

请输出：
1. summary：事件简短总结
2. category / sub_category：类别
3. urgency：紧急程度（必须为 low / medium / high 之一）
4. risk_level：风险等级
5. keywords：关键词列表
6. predicted_department：预测责任部门
7. department_confidence：部门预测置信度 0~1
8. location_entities / time_entities / action_entities / target_entities：按上述规则抽取
9. reasoning_summary：分析依据（可解释思维链）
10. confidence：整体置信度 0~1

请以 JSON 格式输出上述字段。
"""

    analysis_llm = get_llm(0.2, state.get("llm_config")).with_structured_output(ComplaintAnalysis, method="json_mode")
    return analysis_llm.invoke(prompt)

