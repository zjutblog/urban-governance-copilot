"""Plan-and-Execute 图：带循环与终止条件的多智能体工作流。"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.workflow.nodes import (
    execute_node,
    human_review_node,
    plan_node,
    quality_gate_node,
    replan_node,
)
from app.workflow.state import GovernanceState


def route_replan(state: dict) -> str:
    cur = state.get("current_step")
    if cur == "escalate":
        return "escalate"
    if cur == "gate":
        return "gate"
    return "execute"


def route_gate(state: dict) -> str:
    gr = state.get("gate_result") or {}
    route = gr.get("route", "escalate")
    if route == "pass":
        return "pass"
    if route == "retry":
        return "retry"
    return "escalate"


def build_graph():
    workflow = StateGraph(GovernanceState)

    workflow.add_node("plan", plan_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("replan", replan_node)
    workflow.add_node("gate", quality_gate_node)
    workflow.add_node("human_review", human_review_node)

    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "execute")
    workflow.add_edge("execute", "replan")

    workflow.add_conditional_edges(
        "replan",
        route_replan,
        {"execute": "execute", "gate": "gate", "escalate": "human_review"},
    )

    workflow.add_conditional_edges(
        "gate",
        route_gate,
        {"pass": END, "retry": "gate", "escalate": "human_review"},
    )

    workflow.add_edge("human_review", END)

    return workflow.compile()
