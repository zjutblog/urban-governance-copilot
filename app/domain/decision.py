from typing import Optional

from pydantic import BaseModel, Field


class GovernanceDecision(BaseModel):
    """
    城市治理决策结果

    综合:
    - 历史案例
    - 法规知识
    - Agent推理
    """

    recommended_action: str = Field(
        description="建议采取的治理措施"
    )


    related_cases: list[str] = Field(
        default_factory=list,
        description="参考历史案例ID"
    )


    policy_references: list[str] = Field(
        default_factory=list,
        description="相关政策法规"
    )


    responsible_department: Optional[str] = None


    estimated_difficulty: Optional[str] = None


    risk_warning: Optional[str] = None


    generated_reply: Optional[str] = Field(
        default=None,
        description="面向市民的回复建议"
    )


    confidence: float = 0.0