"""Plan 领域模型：Plan-and-Execute 的计划步骤。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# 封闭的动作类型枚举 —— 计划从"菜单"里选，而非自由生成
VALID_ACTIONS = {
    "perceive",   # 本地感知模型：分类 + 实体（省 token）
    "analyze",    # LLM 分析：总结/紧急度/关键词/部门预测
    "retrieve",   # 混合检索历史案例
    "stats",      # 数据统计（pandas 聚合）
    "geo_query",  # 空间分析（shapely buffer/距离/空间关系）
    "mcp_call",   # MCP 工具调用（RDMA_v2 的 geotools/gis_data/model_tools）
    "decide",     # 生成治理决策 + 回复建议
}


class PlanStep(BaseModel):
    step_id: int
    action_type: str = Field(description=f"动作类型，∈ {sorted(VALID_ACTIONS)}")
    objective: str = Field(default="", description="该步目标（给 Executor 参考）")
    args: dict[str, Any] = Field(default_factory=dict, description="步骤参数")
    depends_on: list[int] = Field(default_factory=list, description="依赖的 step_id")

    # 运行时填充
    status: str = Field(default="pending", description="pending|running|done|failed|skipped")
    result: Optional[dict[str, Any]] = Field(default=None, description="执行结果")


class Plan(BaseModel):
    summary: str = Field(default="", description="计划摘要")
    steps: list[PlanStep] = Field(default_factory=list)

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "pending"]

    def get(self, step_id: int) -> Optional[PlanStep]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None
