"""案例文档构建：把原始行映射成 Document。字段对齐真实 CSV schema。"""
from __future__ import annotations

from app.domain.document import Document
from app.rag.metadata import build_metadata


def _clean_id(v) -> str:
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def build_case_document(row: dict) -> Document:
    # LLM 抽取的结构化字段（labeled_1200.csv 自带），有则并入文档文本，提升检索质量
    extra = ""
    if row.get("demand") or row.get("event_type"):
        extra = f"""结构化诉求：{row.get('demand', '')}

事件类型：{row.get('event_type', '')}（{row.get('event_category', '')}）

紧急程度：{row.get('urgency', '')}

"""
    content = f"""{extra}群众留言：{row.get("留言内容", "")}

官方回复：{row.get("回复内容", "")}

回复组织：{row.get("回复组织", "")}

留言领域：{row.get("留言领域", "")}

留言类型：{row.get("留言类型", "")}
"""

    metadata = build_metadata(row)
    quality_score = calculate_quality(row)

    return Document(
        doc_id=_clean_id(row.get("留言ID", "")),
        title=row.get("留言主题"),
        content=content,
        source="city_complaint_dataset",
        doc_type="historical_case",
        metadata=metadata,
        quality_score=quality_score,
    )


def calculate_quality(row: dict) -> float:
    """用真实监督信号（评分/满意度）给历史案例打分，作为检索时的知识质量先验。"""
    score = 0.0
    try:
        resolution = float(row.get("解决程度评分") or 0)
        score += min(resolution / 5.0, 1.0) * 0.4  # 解决程度 0~5
    except (TypeError, ValueError):
        pass

    satisfaction = str(row.get("满意情况") or "")
    if satisfaction == "满意":
        score += 0.3
    elif satisfaction == "不满意":
        score += 0.0

    if row.get("回复内容"):
        score += 0.3

    return round(score, 3)
