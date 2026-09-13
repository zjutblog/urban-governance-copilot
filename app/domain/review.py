from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HumanReview(BaseModel):
    """
    人工审核结果

    用于 Human-in-the-loop 流程。
    """

    # =========================
    # 审核状态
    # =========================

    approved: bool = Field(
        default=False,
        description="是否通过审核"
    )


    review_status: str = Field(
        default="pending",
        description="""
        审核状态:
        pending  待审核
        approved 已通过
        rejected 已拒绝
        """
    )


    # =========================
    # 审核人员
    # =========================

    reviewer_id: Optional[str] = Field(
        default=None,
        description="审核人员ID"
    )


    reviewer_role: Optional[str] = Field(
        default=None,
        description="审核角色，例如管理员、部门人员"
    )


    # =========================
    # 审核意见
    # =========================

    feedback: Optional[str] = Field(
        default=None,
        description="人工反馈意见"
    )


    modification_suggestion: Optional[str] = Field(
        default=None,
        description="修改建议"
    )


    # =========================
    # 质量评价
    # =========================

    quality_score: Optional[float] = Field(
        default=None,
        description="人工评价Agent输出质量"
    )


    error_type: Optional[str] = Field(
        default=None,
        description="""
        错误类型:
        retrieval_error
        reasoning_error
        generation_error
        classification_error
        """
    )


    # =========================
    # 时间
    # =========================

    review_time: Optional[datetime] = Field(
        default=None,
        description="审核时间"
    )