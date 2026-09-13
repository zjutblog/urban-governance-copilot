"""检索元数据：对齐真实 CSV 列名。"""
from __future__ import annotations

from typing import Any


def build_metadata(row: dict[str, Any]) -> dict:
    return {
        "province": row.get("省份"),
        "city": row.get("市对象"),
        "location": row.get("留言属地"),
        "field": row.get("留言领域"),
        "issue_type": row.get("留言类型"),
        "department": row.get("回复组织"),
        "complaint_time": row.get("留言时间"),
        "status": row.get("留言状态"),
        "resolution_score": row.get("解决程度评分"),
        "satisfaction": row.get("满意情况"),
        "attitude_score": row.get("办理态度评分"),
        "speed_score": row.get("办理速度评分"),
    }
