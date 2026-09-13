"""证据链聚合：把一次历史运行（trace.db）聚合成可审计的关键证据链。

八环链路：诉求 → 执行计划 → Agent 轨迹 → 检索证据池 → 引用溯源校验
        → 推理链 → 质量门控 → 最终回复。

- 证据池按原始留言本地 BM25 重建（毫秒级、零 LLM 成本）
- 决策引用逐一核对：被引用（在池中）/ 引用异常（不在池中，需人工核实）
- 与决策 agent 的防幻觉约定（_verify_grounding）离线一致，可复盘审计
"""
from __future__ import annotations

import json
from typing import Any, Optional


def _safe_json(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def _snippet(content: str, n: int = 110) -> str:
    text = "".join(ch for ch in (content or "") if "\u4e00" <= ch <= "\u9fa5")
    return text[:n]


def build_evidence_chain(run_id: str) -> dict[str, Any]:
    from app.rag.corpus import get_corpus
    from app.storage.trace_store import TraceStore

    store = TraceStore()
    try:
        run = store.get_run(run_id)
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        step_rows = store.conn.execute(
            "SELECT * FROM steps WHERE run_id=? ORDER BY rowid", (run_id,)
        ).fetchall()
        gate_row = store.conn.execute(
            "SELECT * FROM gate_results WHERE run_id=? ORDER BY rowid DESC LIMIT 1", (run_id,)
        ).fetchone()
    finally:
        store.close()

    gate = dict(gate_row) if gate_row else {}
    complaint_text = (run.get("complaint_text") or "").strip()
    decision = _safe_json(gate.get("decision_json")) or {}

    # ---- 环1：群众诉求 ----

    # ---- 环2：执行计划 ----
    plan_raw = _safe_json(run.get("plan_json"))
    plan_steps = []
    if isinstance(plan_raw, dict) and isinstance(plan_raw.get("steps"), list):
        for s in plan_raw["steps"]:
            if not isinstance(s, dict):
                continue
            plan_steps.append({
                "step_id": s.get("step_id"),
                "action_type": s.get("action_type", ""),
                "objective": (s.get("objective") or "")[:60],
                "status": s.get("status", "pending"),
            })

    # ---- 环3：Agent 执行轨迹 ----
    execution = []
    for r in step_rows:
        extra = _safe_json(r["input_json"])
        if not isinstance(extra, dict):
            extra = {}
        execution.append({
            "node": r["node"] or "",
            "action": r["action_type"] or "",
            "latency_ms": round(r["latency_ms"] or 0),
            "error": r["error"] or "",
            "extra": {k: v for k, v in extra.items() if k != "ts"} or None,
        })

    # ---- 环4：检索证据池（本地重建） ----
    pool = []
    pool_depts: set[str] = set()
    if complaint_text:
        try:
            docs = get_corpus()["retriever"].search(complaint_text, top_k=8)
            for d in docs:
                dept_i = d.metadata.get("department", "") or ""
                if dept_i:
                    pool_depts.add(dept_i)
                pool.append({
                    "doc_id": str(d.doc_id),
                    "department": dept_i,
                    "field": d.metadata.get("field", "") or "",
                    "location": d.metadata.get("location", "") or d.metadata.get("city", "") or "",
                    "snippet": _snippet(d.content),
                    "cited": False,
                })
        except Exception:  # noqa: BLE001
            pass

    # ---- 环5：引用溯源校验（离线复核决策的引用）----
    cited_ids = [str(c) for c in (decision.get("related_cases") or [])]
    citations = []
    warnings: list[str] = []
    pool_by_id = {p["doc_id"]: p for p in pool}
    for cid in cited_ids:
        hit = pool_by_id.get(cid)
        if hit:
            hit["cited"] = True
            citations.append({"case_id": cid, "status": "verified"})
        else:
            citations.append({"case_id": cid, "status": "not_in_pool"})
            warnings.append(f"决策引用案例 {cid} 不在证据池中，请人工核实")

    dept = decision.get("responsible_department") or ""
    dept_in_evidence = bool(dept) and bool(pool_depts) and any(
        dept == k or dept in k or k in dept for k in pool_depts
    )
    if dept and pool_depts and not dept_in_evidence:
        warnings.append(f"责任部门「{dept}」未出现在证据案例中")

    if not pool:
        warnings.append("证据池为空：该记录未存原始留言或检索失败，无法复核引用")

    # 决策自带的风险提示单独展示（属不确定性说明，不算链路断裂）
    risk_note = decision.get("risk_warning") or ""

    # ---- 环6/7/8：推理链、门控、回复 ----
    votes = _safe_json(gate.get("votes_json")) or {}
    consistency = gate.get("consistency")
    if consistency is None:
        consistency = run.get("consistency")

    return {
        "run_id": run_id,
        "created_at": run.get("created_at"),
        "complaint_text": complaint_text,
        "plan": plan_steps,
        "execution": execution,
        "evidence_pool": pool,
        "citations": citations,
        "department_check": {"department": dept, "in_evidence": dept_in_evidence},
        "reasoning_chain": decision.get("reasoning_chain") or [],
        "gate": {
            "consistency": consistency,
            "route": gate.get("route") or run.get("route") or "",
            "votes": votes,
        },
        "decision": {
            "responsible_department": dept,
            "recommended_action": decision.get("recommended_action", ""),
            "confidence": decision.get("confidence", 0),
            "risk_warning": risk_note,
        },
        "generated_reply": decision.get("generated_reply", ""),
        "integrity": {
            "ok": not warnings,
            "warnings": warnings,
        },
    }
