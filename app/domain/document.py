from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Document(BaseModel):
    """
    知识库文档对象

    所有进入RAG系统的数据统一转换成Document。
    """


    # =========================
    # 文档基本信息
    # =========================

    doc_id: str = Field(
        description="文档唯一ID"
    )


    content: str = Field(
        description="文档正文内容"
    )


    title: Optional[str] = Field(
        default=None,
        description="文档标题"
    )


    source: str = Field(
        description="数据来源"
    )


    doc_type: str = Field(
        description="""
        文档类型:

        complaint
        reply
        policy
        case
        knowledge
        """
    )


    # =========================
    # Metadata
    # =========================

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="检索过滤信息"
    )


    # =========================
    # 时间信息
    # =========================

    created_time: Optional[datetime] = None


    update_time: Optional[datetime] = None


    # =========================
    # 向量信息
    # =========================

    embedding_id: Optional[str] = Field(
        default=None,
        description="向量数据库中的ID"
    )


    # =========================
    # 质量信息
    # =========================

    quality_score: Optional[float] = Field(
        default=None,
        description="知识质量评分"
    )


    usage_count: int = Field(
        default=0,
        description="被Agent使用次数"
    )