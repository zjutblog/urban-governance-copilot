"""服务层：把 multi-agent pipeline 封装成可复用的函数，供 CLI / API / SSE 流式调用。

- run_pipeline：一次性返回结果（CLI 用 + Web 轮询后端）
- stream_pipeline：逐步 yield SSE 事件（Web 流式思维链）
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from loguru import logger

from app.domain.complaint import Complaint
from app.storage.memory import MemoryStore
from app.storage.trace_store import TraceStore
from app.workflow.graph import build_graph
from app.workflow.state import GovernanceState


def _dump(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    return obj


def _make_state(text: str, user_id: str, memory_store: MemoryStore, llm_config: dict | None = None):
    complaint = Complaint(complaint_id=str(uuid.uuid4())[:8], content=text)
    memory = memory_store.get_memories(user_id)
    state = GovernanceState(
        complaint=complaint,
        perception={},
        analysis=None,
        retrieved_documents=[],
        policy_documents=[],
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
        llm_config=llm_config or {},
    )
    return complaint, state


def _extract_result(result: dict, run_id: str, elapsed: float) -> dict[str, Any]:
    from app.agents.work_order import build_work_order

    geo = None
    plan = result.get("plan")
    if plan:
        for s in plan.steps:
            if s.action_type == "geo_query" and s.result:
                geo = s.result
                break
    gr = result.get("gate_result") or {}
    return {
        "run_id": run_id,
        "elapsed": round(elapsed, 1),
        "plan": _dump(result.get("plan")),
        "perception": _dump(result.get("perception")),
        "analysis": _dump(result.get("analysis")),
        "retrieved": [_dump(d) for d in (result.get("retrieved_documents") or [])][:5],
        "policy": [_dump(d) for d in (result.get("policy_documents") or [])][:6],
        "decision": _dump(result.get("decision")),
        "gate": _dump(gr),
        "geo": geo,
        "work_order": build_work_order(result),
        "trace": _dump(result.get("trace")),
        "errors": result.get("errors") or [],
        "review": _dump(result.get("review")),
    }


def _write_trace(result: dict, run_id: str, text: str, memory_store: MemoryStore, elapsed: float, user_id: str):
    """落库 trace + 写记忆（多轮上下文）。"""
    trace_store = TraceStore()
    complaint_id = ""
    if result.get("complaint"):
        cid = getattr(result["complaint"], "complaint_id", None)
        complaint_id = cid or ""
    trace_store.log_run(run_id, complaint_id, json.dumps(_dump(result.get("plan")), ensure_ascii=False), complaint_text=text)
    gr = result.get("gate_result") or {}
    trace_store.update_run(run_id, "done", result.get("steps_used", 0), gr.get("consistency", 0.0), gr.get("route", ""))
    for ev in result.get("trace", []):
        trace_store.log_step(
            run_id,
            ev.get("node", ""),
            ev.get("action", ""),
            json.dumps({k: v for k, v in ev.items() if k not in ("node", "action")}, ensure_ascii=False, default=str),
            "",
            ev.get("latency_ms", 0.0),
        )
    if gr:
        trace_store.log_gate(
            run_id,
            gr.get("consistency", 0.0),
            json.dumps(gr.get("votes", {}), ensure_ascii=False, default=str),
            gr.get("route", ""),
            json.dumps(_dump(result.get("decision")), ensure_ascii=False),
            json.dumps(gr.get("reasoning_chain", []), ensure_ascii=False),
        )
    trace_store.close()

    # 写记忆（与 CLI/Web 一致）
    if result.get("decision"):
        d = result["decision"]
        summary = (
            f"用户曾反映：{text[:80]}；归口：{d.responsible_department or '未知'}；"
            f"建议：{(d.recommended_action or '')[:80]}"
        )
        memory_store.add_memory(user_id, "case", summary, importance=0.8)


def refresh_pipeline(run_id: str, llm_config: dict | None = None) -> dict[str, Any]:
    """结合留言更新重答：原留言 + 过去生成的决策 + 新增更新 拼成 prompt，单次 LLM 调用。

    需要时点击按钮才触发，不点不产生任何 LLM 成本。
    """
    from app.agents.decision import _DecisionWithCoT
    from app.llm.client import get_llm
    from app.rag.corpus import get_corpus

    store = TraceStore()
    try:
        run = store.get_run(run_id)
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        updates = store.list_updates(run_id)
        old_text = (run.get("complaint_text") or "").strip()
        if not old_text:
            raise ValueError("该历史记录未存原始留言，无法重答（旧数据请重新跑一次）")
        if not updates:
            return {"run_id": run_id, "refreshed": False, "note": "该留言暂无更新"}

        new_texts = [u["content"] for u in updates]
        combined = old_text + "\n" + "\n".join(new_texts)

        # 证据兜底：按"原留言+更新"再检索一次，防编造（与决策 agent 同一防幻觉约定）
        docs = get_corpus()["retriever"].search(combined, top_k=5)
        case_lines = []
        for d in docs:
            dept = d.metadata.get("department", "") or "（未知部门）"
            case_lines.append(f"- [案例{d.doc_id}] 部门:{dept} | {d.content[:160]}")
        cases = "\n".join(case_lines) or "（无历史案例）"
        valid_ids = ", ".join(d.doc_id for d in docs) or "（无）"
        dept_options = "、".join(
            sorted({d.metadata.get("department", "") for d in docs if d.metadata.get("department")})
        ) or "（无）"

        # 政策检索：Evidence-based，只允许引用真实条款
        from app.rag.policy_corpus import format_policy_evidence, search_policies

        policy_docs = search_policies(combined, top_k=6)
        policy_evidence = format_policy_evidence(policy_docs, max_items=6) if policy_docs else "（未检索到相关法规条款）"
        valid_policy_refs = "、".join(f"《{d.metadata.get('title', '')}》{d.metadata.get('article_no', '')}" for d in policy_docs) or "（无）"

        old_decision_txt = ""
        raw = store.latest_decision(run_id)
        if raw:
            try:
                old_decision_txt = json.dumps(json.loads(raw), ensure_ascii=False)[:1200]
            except Exception:  # noqa: BLE001
                old_decision_txt = str(raw)[:800]

        upd_txt = "\n".join(f"{i}. {t}" for i, t in enumerate(new_texts, 1))
        
        # 智能部门匹配：基于留言内容关键词
        dept_hint = ""
        combined_content = old_text + " " + " ".join(new_texts)
        keyword_dept_hints = [
            ("施工", "住建"), ("噪音", "城管执法"), ("污水", "水务"), ("供水", "水务"),
            ("路灯", "住建"), ("道路", "住建"), ("交通", "交通"), ("堵车", "交通"),
            ("教育", "教育体育"), ("学校", "教育体育"), ("医疗", "卫生健康"), ("医院", "卫生健康"),
            ("物业", "物业房产"), ("供暖", "能源"), ("供电", "能源"), ("燃气", "能源"),
            ("环保", "生态环境"), ("污染", "生态环境"), ("垃圾", "城管执法"),
        ]
        for keyword, dept_name in keyword_dept_hints:
            if keyword in combined_content:
                dept_hint = f"（提示：根据留言关键词，可能归口到「{dept_name}」部门）"
                break
        
        prompt = f"""你之前处理过一条群众留言并给出了治理决策。现在该留言有了**新的补充情况**，请结合更新重新给出决策与回复。

【原留言】{old_text}

【过去生成的决策】（供参考，可沿用合理部分）
{old_decision_txt or '（无）'}

【新增的留言更新】（重点！必须逐条回应）
{upd_txt}

【历史案例】（责任部门唯一事实来源，禁止编造）
{cases}
可参考的案例ID：{valid_ids}
案例中出现过的责任部门：{dept_options}

【政策法规依据】（真实条款，仅限引用，禁止另编法规）
{policy_evidence}
可引用的政策条款（格式：《标题》第X条）：{valid_policy_refs}
{dept_hint}

要求：
1. responsible_department 必须从"案例中出现过的责任部门"中选择（若有提示，优先考虑提示部门）
2. related_cases 从"可参考的案例ID"中选，最多3个
3. generated_reply 80字以内，只写程序性表述，**必须体现对新增情况的回应**（如"已注意到您补充的情况"）
4. policy_references **必须从"可引用的政策条款"中选取**与诉求相关的真实条款（格式《标题》第X条），最多2条；若均不相关则留空，**禁止编造法规**
5. reasoning_chain 最多3步，说明"更新如何改变了判断"

请以 JSON 格式输出字段。
"""
        decision = get_llm(0.2, llm_config).with_structured_output(_DecisionWithCoT, method="json_mode").invoke(prompt)

        # 政策引用溯源校验：剔除不在检索结果里的编造引用
        from app.agents.decision import _is_valid_policy_ref

        fake_policy = [p for p in decision.policy_references if not _is_valid_policy_ref(p, policy_docs)]
        if fake_policy:
            decision.policy_references = [p for p in decision.policy_references if _is_valid_policy_ref(p, policy_docs)]
            decision.risk_warning = (decision.risk_warning or "") + f"；【已剔除编造/不可溯源的政策引用】{fake_policy}"

        store.log_step(
            run_id, "refresh", "refresh",
            json.dumps({"updates": new_texts}, ensure_ascii=False),
            json.dumps(decision.model_dump(), ensure_ascii=False),
            0.0,
        )
        store.set_refreshed(run_id)
        return {
            "run_id": run_id,
            "refreshed": True,
            "updates_used": len(updates),
            "decision": _dump(decision),
            "evidence": [{"doc_id": d.doc_id, "content": d.content[:140]} for d in docs],
        }
    finally:
        store.close()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def run_pipeline(text: str, user_id: str = "demo_user", llm_config: dict | None = None) -> dict[str, Any]:
    memory_store = MemoryStore()
    complaint, state = _make_state(text, user_id, memory_store, llm_config)
    graph = build_graph()
    t0 = time.time()
    result = graph.invoke(dict(state))
    elapsed = time.time() - t0
    run_id = complaint.complaint_id
    _write_trace(result, run_id, text, memory_store, elapsed, user_id)
    memory_store.close()
    return _extract_result(result, run_id, elapsed)


def stream_pipeline(text: str, user_id: str = "demo_user", llm_config: dict | None = None):
    """逐步生成 SSE 事件。每个 yield 是一段 SSE 帧。"""
    memory_store = MemoryStore()
    complaint, state = _make_state(text, user_id, memory_store, llm_config)
    graph = build_graph()
    full: dict[str, Any] = {}
    t0 = time.time()
    try:
        prev_plan = None
        for chunk in graph.stream(dict(state), stream_mode="updates"):
            for node, upd in chunk.items():
                full.update(upd)
                # 推送节点级事件（提取最新 trace 条目）
                trace = upd.get("trace") or []
                if trace:
                    last = trace[-1]
                    yield _sse({
                        "type": "step",
                        "node": last.get("node", node),
                        "action": last.get("action", ""),
                        "latency_ms": last.get("latency_ms", 0),
                    })
                # 计划生成后推送一次 plan（前端展示执行计划）
                if node == "plan" and full.get("plan"):
                    yield _sse({"type": "plan", "plan": _dump(full["plan"])})
                # geo 完成后推送地图
                if "geo" in upd and node.endswith("geo"):
                    pass
        run_id = complaint.complaint_id
        elapsed = time.time() - t0
        _write_trace(full, run_id, text, memory_store, elapsed, user_id)
        yield _sse({"type": "result", "run_id": run_id, "elapsed": round(elapsed, 1), "result": _extract_result(full, run_id, elapsed)})
    finally:
        memory_store.close()
