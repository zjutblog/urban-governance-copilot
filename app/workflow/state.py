"""全局状态：所有 agent 节点共享的 LangGraph state。"""
from __future__ import annotations

from typing import Any, Optional, TypedDict

from app.domain.analysis import ComplaintAnalysis
from app.domain.complaint import Complaint
from app.domain.decision import GovernanceDecision
from app.domain.document import Document
from app.domain.plan import Plan
from app.domain.review import HumanReview


class GovernanceState(TypedDict, total=False):
    # ===== 原始输入 =====
    complaint: Complaint

    # ===== 感知层（本地小模型）=====
    perception: dict[str, Any]          # {category, category_confidence, ...}

    # ===== LLM 分析 =====
    analysis: Optional[ComplaintAnalysis]

    # ===== 检索结果 =====
    retrieved_documents: list[Document]
    policy_documents: list[Document]    # 政策法规检索结果（Evidence-based 引用真实条款）

    # ===== 计划 =====
    plan: Optional[Plan]
    current_step_id: int                # 当前待执行 step_id
    plan_revisions: int                 # 已重规划次数

    # ===== 决策 =====
    decision: Optional[GovernanceDecision]

    # ===== 质量门控 =====
    gate_result: dict[str, Any]         # {consistency, votes, route, ...}

    # ===== 人工审核 =====
    review: Optional[HumanReview]

    # ===== 工作流控制 =====
    current_step: str
    next_action: Optional[str]
    steps_used: int                     # 已消耗步数（预算）

    # ===== 轨迹（结构化事件流）=====
    trace: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    errors: list[str]

    # ===== 评估 =====
    evaluation: Optional[dict[str, Any]]

    # ===== 记忆上下文 =====
    memory_context: list[str]

    # ===== 请求级 LLM 配置 =====
    llm_config: dict[str, Any]          # {api_key?, base_url?, model?} 仅本次运行生效，不写全局
