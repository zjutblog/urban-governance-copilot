"""Runner：端到端运行多智能体工作流。

用法：
  python main.py "小区附近晚上施工噪音很大，希望有关部门处理"
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

from loguru import logger

from app.domain.complaint import Complaint
from app.storage.memory import MemoryStore
from app.storage.trace_store import TraceStore
from app.workflow.graph import build_graph
from app.workflow.state import GovernanceState


def initial_state(complaint: Complaint, memory: list[str]) -> GovernanceState:
    return GovernanceState(
        complaint=complaint,
        perception={},
        analysis=None,
        retrieved_documents=[],
        plan=None,
        current_step_id=0,
        plan_revisions=0,
        decision=None,
        gate_result={},
        review=None,
        current_step="start",
        next_action=None,
        steps_used=0,
        trace=[],
        tool_calls=[],
        errors=[],
        evaluation=None,
        memory_context=memory,
    )


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "小区附近晚上施工噪音很大，希望有关部门处理"

    complaint = Complaint(
        complaint_id=str(uuid.uuid4())[:8],
        content=text,
        province="浙江省",
        city="杭州市",
        field="环境",
    )

    memory_store = MemoryStore()
    memory = memory_store.get_memories("demo_user")

    graph = build_graph()
    state = initial_state(complaint, memory)

    t0 = time.time()
    logger.info("running workflow...")
    result = graph.invoke(dict(state))
    elapsed = time.time() - t0

    # 落库 trace
    trace_store = TraceStore()
    run_id = complaint.complaint_id
    trace_store.log_run(
        run_id,
        complaint.complaint_id,
        json.dumps(result["plan"].model_dump() if result.get("plan") else {}, ensure_ascii=False, default=str),
        complaint_text=text,
    )
    gr = result.get("gate_result") or {}
    trace_store.update_run(run_id, "done", result.get("steps_used", 0), gr.get("consistency", 0.0), gr.get("route", ""))

    # 落库每步轨迹事件
    for ev in result.get("trace", []):
        trace_store.log_step(
            run_id,
            ev.get("node", ""),
            ev.get("action", ""),
            json.dumps({k: v for k, v in ev.items() if k not in ("node", "action")}, ensure_ascii=False, default=str),
            "",
            ev.get("latency_ms", 0.0),
        )
    # 落库门控结果
    if gr:
        trace_store.log_gate(
            run_id,
            gr.get("consistency", 0.0),
            json.dumps(gr.get("votes", {}), ensure_ascii=False, default=str),
            gr.get("route", ""),
            json.dumps(result["decision"].model_dump() if result.get("decision") else {}, ensure_ascii=False, default=str),
            json.dumps(gr.get("reasoning_chain", []), ensure_ascii=False, default=str),
        )

    # 打印结果
    print("=" * 60)
    print("运行完成，耗时 %.1fs" % elapsed)
    print("=" * 60)
    print("[计划]")
    if result.get("plan"):
        for s in result["plan"].steps:
            print(f"  {s.step_id}. {s.action_type} [{s.status}] {s.objective}")
    print("[感知]")
    print("  ", json.dumps(result.get("perception", {}), ensure_ascii=False))
    print("[分析]")
    if result.get("analysis"):
        a = result["analysis"]
        print(f"   类别={a.category} 紧急度={a.urgency} 部门={a.predicted_department} (conf={a.department_confidence})")
        print(f"   摘要={a.summary}")
        print(f"   依据={a.reasoning_summary}")
    print("[检索]")
    print("  ", f"{len(result.get('retrieved_documents', []))} 条相关案例")
    print("[质量门控]")
    print("  ", json.dumps({k: gr.get(k) for k in ("consistency", "route", "k", "votes")}, ensure_ascii=False, default=str))
    print("[决策]")
    if result.get("decision"):
        d = result["decision"]
        print(f"   责任部门={d.responsible_department}")
        print(f"   建议措施={d.recommended_action}")
        print(f"   回复建议={d.generated_reply}")
        rc = getattr(d, "reasoning_chain", None) or []
        if rc:
            print("   推理链:")
            for i, step in enumerate(rc, 1):
                print(f"     {i}. {step}")
    print("[轨迹]")
    for ev in result.get("trace", []):
        print(f"   {ev['node']:12s} {ev['action']:16s} {ev.get('latency_ms', 0):.0f}ms")
    if result.get("errors"):
        print("[错误]", result["errors"])
    if result.get("review"):
        print("[人工审核]", result["review"].review_status)

    # 写记忆（与 service.run_pipeline 一致，CLI/Web 行为统一）
    if result.get("decision"):
        d = result["decision"]
        summary = (
            f"用户曾反映：{text[:80]}；归口：{d.responsible_department or '未知'}；"
            f"建议：{(d.recommended_action or '')[:80]}"
        )
        memory_store.add_memory("demo_user", "case", summary, importance=0.8)

    trace_store.close()
    memory_store.close()
    print("=" * 60)
    print("trace 已落库 data/trace.db")


if __name__ == "__main__":
    main()
