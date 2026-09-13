from typing import Optional

from pydantic import BaseModel, Field


class ComplaintAnalysis(BaseModel):
    """
    Agent 对城市治理事件的分析结果

    由 Planner / Analyst Agent 产生。
    """

    # =========================
    # 事件理解
    # =========================

    summary: str = Field(
        description="对留言事件的简短总结"
    )


    category: Optional[str] = Field(
        default=None,
        description="事件类别，例如交通、环保、住房"
    )


    sub_category: Optional[str] = Field(
        default=None,
        description="细分类别"
    )


    keywords: list[str] = Field(
        default_factory=list,
        description="关键实体和关键词"
    )


    # =========================
    # 风险判断
    # =========================

    urgency: Optional[str] = Field(
        default=None,
        description="紧急程度 low/medium/high"
    )


    risk_level: Optional[str] = Field(
        default=None,
        description="风险等级"
    )


    # =========================
    # 部门预测
    # =========================

    predicted_department: Optional[str] = Field(
        default=None,
        description="预测责任部门"
    )


    department_confidence: float = Field(
        default=0.0,
        description="部门预测置信度"
    )


    # =========================
    # 地理理解
    # =========================

    location_entities: list[str] = Field(
        default_factory=list,
        description="文本中识别出的**物理地点**实体（可在地图上定位的），如'太原市小店区'、'幸福小区'"
    )


    time_entities: list[str] = Field(
        default_factory=list,
        description="文本中识别出的时间实体，如'晚上'、'凌晨'、'上周'、'连续三天'"
    )


    action_entities: list[str] = Field(
        default_factory=list,
        description="文本中识别出的行为/事件实体，如'施工'、'停水'、'占道经营'、'协商拆迁补偿'"
    )


    target_entities: list[str] = Field(
        default_factory=list,
        description="文本中识别出的受影响对象/标的物，如'路灯'、'暖气'、'房屋'、'业主'、'学生'"
    )


    # =========================
    # Agent自身判断
    # =========================

    reasoning_summary: Optional[str] = Field(
        default=None,
        description="分析依据摘要"
    )


    confidence: float = Field(
        default=0.0,
        description="整体分析置信度"
    )