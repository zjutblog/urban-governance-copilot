"""Planner Agent：根据诉求 + 感知结果 + 记忆，产出受约束的执行计划。

计划不是自由文本，而是从封闭动作菜单（perceive/analyze/retrieve/stats/geo_query/decide）
里选步骤，保证 Executor 和 Harness 都能逐步校验。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.plan import VALID_ACTIONS, Plan, PlanStep
from app.llm.client import get_llm


class _PlanSteps(BaseModel):
    plan: list[PlanStep] = Field(description="执行计划步骤列表，3~6 步")


def build_plan(state: dict) -> Plan:
    complaint = state.get("complaint")
    perception = state.get("perception") or {}
    memory = state.get("memory_context") or []

    mem_txt = "\n".join(f"- {m}" for m in memory) or "（无历史记忆）"
    
    # 检测是否涉及洪水/内涝/积水等关键词，提示 planner 推荐使用洪水模型
    content = complaint.content or ""
    flood_keywords = ["洪水", "内涝", "积水", "暴雨", "排水", "防洪", "汛期", "暴雨预警", "城市看海"]
    has_flood = any(kw in content for kw in flood_keywords)
    
    # 检测是否涉及交通/道路问题
    traffic_keywords = ["堵车", "交通", "拥堵", "道路", "出行", "通勤", "车流"]
    has_traffic = any(kw in content for kw in traffic_keywords)
    
    # 检测是否涉及社区/生活配套问题
    living_keywords = ["社区", "生活", "配套", "设施", "医院", "学校", "购物", "便民", "15分钟"]
    has_living = any(kw in content for kw in living_keywords)
    
    flood_hint = ""
    if has_flood:
        flood_hint = """
【洪水模型推荐】检测到留言涉及洪水/内涝相关问题，建议在 mcp_call 步骤中调用洪水模拟模型。
可用洪水模型：run_model (model_name="swmm_simulation")，参数：simulation_duration=24, time_step=5, return_period=10
此模型可模拟城市排水系统在暴雨条件下的表现，生成内涝风险评估结果。
"""
    
    traffic_hint = ""
    if has_traffic:
        traffic_hint = """
【交通模型推荐】检测到留言涉及交通/道路问题，建议在 mcp_call 步骤中调用交通预测模型。
可用交通模型：run_model (model_name="traffic_prediction")，参数：prediction_horizon=60, time_interval=5, include_weather=1
此模型可预测未来交通流量和拥堵风险。
"""
    
    living_hint = ""
    if has_living:
        living_hint = """
【生活圈模型推荐】检测到留言涉及社区/生活配套问题，建议在 mcp_call 步骤中调用15分钟生活圈分析模型。
可用生活圈模型：run_model (model_name="living_area_analysis")，参数：routing_mode=2, contour_threshold=15, contour_type="minutes"
此模型可评估社区15分钟生活圈的设施覆盖情况。
"""
    
    prompt = f"""你是城市治理多智能体系统的 Planner。请为下面这条群众留言制定一个执行计划。

【留言】{complaint.content}

【本地感知结果（已由小模型分类）】{perception or '（未感知）'}

【用户历史记忆】{mem_txt}
{flood_hint}{traffic_hint}{living_hint}

可选动作（只能从下面选，每步必须带 action_type 和 objective）：
- perceive   ：本地模型做事件分类/实体识别（如果感知结果已存在可跳过）
- analyze    ：LLM 分析事件总结、紧急程度、关键词、预测责任部门
- retrieve   ：混合检索相似历史案例（同类事件怎么处理的）
- stats      ：对历史数据做统计（同类事件数量/趋势）
- geo_query  ：空间分析（如果留言有具体地点，做缓冲区/邻近分析）
- mcp_call   ：调用外部 MCP 工具。args 格式：{{"server": "server名", "tool": "工具名", "arguments": {{...}}}}
               可用服务器：
               - geotools: buffer_analysis(缓冲区), coordinate_transform(坐标转换), distance_calculator(距离), spatial_query(空间关系)
               - gis_data: GIS 数据资源查询
               - model_tools: list_models(模型列表), run_model(执行模型)
               可用模型：
               - 洪水模拟：{{"server": "model_tools", "tool": "run_model", "arguments": {{"model_name": "swmm_simulation", "parameters": {{"simulation_duration": 24, "time_step": 5, "return_period": 10}}}}}}
               - 交通预测：{{"server": "model_tools", "tool": "run_model", "arguments": {{"model_name": "traffic_prediction", "parameters": {{"prediction_horizon": 60, "time_step": 5, "include_weather": 1}}}}}}
               - 生活圈分析：{{"server": "model_tools", "tool": "run_model", "arguments": {{"model_name": "living_area_analysis", "parameters": {{"routing_mode": 2, "contour_threshold": 15, "contour_type": "minutes"}}}}}}
               仅在需要专业空间计算或模型分析时选用
- decide     ：综合生成治理决策与回复建议（必须放最后一步）

要求：
1. 3~6 步，step_id 从 1 开始递增。
2. decide 必须最后。
3. 若留言含具体地点，加入 geo_query；否则省略。
4. 若感知结果已有 category，可省略 perceive。
5. 若涉及洪水/内涝/积水问题，在 decide 之前加入 mcp_call 调用洪水模型。
6. 若涉及交通/道路拥堵问题，在 decide 之前加入 mcp_call 调用交通预测模型。
7. 若涉及社区/生活配套问题，在 decide 之前加入 mcp_call 调用生活圈分析模型。
8. 每步 objective 一句话说明目的。

请以 JSON 格式输出，结构：{{"plan": [{{"step_id": 1, "action_type": "analyze", "objective": "...", "args": {{}}, "depends_on": []}}]}}
"""

    planner_llm = get_llm(0.2, state.get("llm_config")).with_structured_output(_PlanSteps, method="json_mode")
    result = planner_llm.invoke(prompt)
    if not result.plan:
        result.plan = _default_plan(perception)

    # 清洗：step_id 重排、status/result 归位、action_type 白名单校验
    # （这些是运行时字段，不允许 LLM 填写，防止污染 pending 判断）
    cleaned: list[PlanStep] = []
    for i, s in enumerate(result.plan, start=1):
        action = s.action_type if s.action_type in VALID_ACTIONS else "analyze"
        cleaned.append(
            PlanStep(
                step_id=i,
                action_type=action,
                objective=s.objective,
                args=s.args,
                depends_on=s.depends_on,
            )
        )
    if cleaned and cleaned[-1].action_type != "decide":
        cleaned.append(
            PlanStep(step_id=len(cleaned) + 1, action_type="decide", objective="生成治理决策与回复")
        )

    plan = Plan(summary=f"针对留言 {complaint.complaint_id} 的 {len(cleaned)} 步计划", steps=cleaned)
    return plan


def _default_plan(perception: dict) -> list[PlanStep]:
    steps = []
    i = 1
    if not perception:
        steps.append(PlanStep(step_id=i, action_type="perceive", objective="本地模型分类")); i += 1
    steps.append(PlanStep(step_id=i, action_type="retrieve", objective="检索相似历史案例")); i += 1
    steps.append(PlanStep(step_id=i, action_type="analyze", objective="分析事件与紧急度")); i += 1
    steps.append(PlanStep(step_id=i, action_type="decide", objective="生成治理决策与回复")); i += 1
    return steps
