from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Complaint(BaseModel):
    """
    城市治理留言领域对象

    对应人民网留言原始数据。
    保存用户真实提交的信息，
    不包含Agent生成内容。
    """

    # =========================
    # 基础信息
    # =========================

    complaint_id: str = Field(
        description="留言唯一ID"
    )

    url: Optional[str] = Field(
        default=None,
        description="原始留言链接"
    )


    # =========================
    # 时间信息
    # =========================

    publish_time: Optional[datetime] = Field(
        default=None,
        description="留言发布时间"
    )


    # =========================
    # 用户留言内容
    # =========================

    title: Optional[str] = Field(
        default=None,
        description="留言标题"
    )


    content: str = Field(
        description="留言正文"
    )


    # =========================
    # 留言分类
    # 原始数据字段
    # =========================

    message_type: Optional[str] = Field(
        default=None,
        description="留言类型，例如投诉、咨询、建议"
    )


    field: Optional[str] = Field(
        default=None,
        description="留言领域，例如交通、环保、住房"
    )


    status: Optional[str] = Field(
        default=None,
        description="办理状态"
    )


    # =========================
    # 地理信息
    # =========================

    province: Optional[str] = Field(
        default=None,
        description="省份"
    )


    city: Optional[str] = Field(
        default=None,
        description="城市"
    )


    district: Optional[str] = Field(
        default=None,
        description="区县"
    )


    # =========================
    # 对象信息
    # =========================

    target: Optional[str] = Field(
        default=None,
        description="留言对象"
    )


    reply_department: Optional[str] = Field(
        default=None,
        description="回复组织或责任部门"
    )


    # =========================
    # 官方处理结果
    # 原始数据中的监督信号
    # =========================

    reply_content: Optional[str] = Field(
        default=None,
        description="官方回复内容"
    )


    reply_time: Optional[datetime] = Field(
        default=None,
        description="回复时间"
    )


    # =========================
    # 用户反馈
    # 用于Agent Evaluation
    # =========================

    satisfaction: Optional[str] = Field(
        default=None,
        description="满意情况"
    )


    solution_score: Optional[float] = Field(
        default=None,
        description="解决程度评分"
    )


    attitude_score: Optional[float] = Field(
        default=None,
        description="办理态度评分"
    )


    speed_score: Optional[float] = Field(
        default=None,
        description="办理速度评分"
    )


    class Config:
        json_schema_extra = {
            "example": {

                "complaint_id": "10001",

                "title": "小区道路停车问题",

                "content":
                    "小区门口长期车辆乱停，影响居民出行",

                "province": "浙江省",

                "city": "杭州市",

                "field": "交通",

                "reply_department":
                    "杭州市公安局交通警察支队"
            }
        }