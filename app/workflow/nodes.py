"""工作流节点：Plan-and-Execute 的 Planner / Executor / Re-planner / Quality Gate / Human Review。"""
from __future__ import annotations

import os
import time
from typing import Any

from loguru import logger

from app.agents.analyst import analyze
from app.agents.perception import PerceptionAgent
from app.agents.planner import build_plan
from app.domain.plan import PlanStep
from app.domain.review import HumanReview
from app.harness.guard import HarnessGuard
from app.quality.self_consistency import run_self_consistency_gate
from app.rag.corpus import get_corpus

# ============================================================
# 子动作处理器（Executor 分发）
# ============================================================


def _do_perceive(state: dict, step) -> dict:
    agent = PerceptionAgent()
    content = state["complaint"].content
    result = agent.classify(content)
    if result is None:
        step.result = {"error": "classifier unavailable"}
        step.status = "failed"
        return {"perception": {}}
    step.result = result
    return {"perception": result}


def _do_retrieve(state: dict, step) -> dict:
    corpus = get_corpus()
    retriever = corpus["retriever"]
    # Adaptive Retrieval：使用分析阶段建议的查询（如有），否则用原始诉求
    query = step.args.get("query") or state["complaint"].content
    where = step.args.get("where")
    top_k = int(step.args.get("top_k", 5))
    docs = retriever.search(query, top_k=top_k, where=where)
    step.result = {"count": len(docs), "ids": [d.doc_id for d in docs], "query": query}
    return {"retrieved_documents": docs}


def _do_retrieve_policy(state: dict, step) -> dict:
    """政策检索：Evidence-based 兜底——按诉求内容检索真实法规条款，供 decision 引用真实条款。"""
    from app.rag.policy_corpus import format_policy_evidence, search_policies

    query = step.args.get("query") or state["complaint"].content
    top_k = int(step.args.get("top_k", 6))
    docs = search_policies(query, top_k=top_k)
    step.result = {"count": len(docs), "query": query, "evidence": format_policy_evidence(docs, max_items=top_k)}
    return {"policy_documents": docs}


def _do_analyze(state: dict, step) -> dict:
    result = analyze(state)
    step.result = {"summary": result.summary, "category": result.category, "urgency": result.urgency}
    return {"analysis": result}


def _do_stats(state: dict, step) -> dict:
    corpus = get_corpus()
    rows = corpus["rows"]
    import pandas as pd

    df = pd.DataFrame(rows)
    target = step.args.get("field") or state.get("perception", {}).get("category")
    result: dict[str, Any] = {"total": len(df)}

    if target and "留言领域" in df.columns:
        sub = df[df["留言领域"] == target]
        result["category"] = target
        result["category_count"] = len(sub)
        result["satisfaction_dist"] = sub["满意情况"].value_counts().to_dict()
        result["top_departments"] = sub["回复组织"].value_counts().head(5).to_dict()
    elif "留言领域" in df.columns:
        result["category_dist"] = df["留言领域"].value_counts().head(10).to_dict()
    step.result = result
    return {}


def _do_geo_query(state: dict, step) -> dict:
    from collections import Counter

    from app.geo.geocoder import get_geocoder, haversine_km

    corpus = get_corpus()
    rows = corpus["rows"]
    complaint = state["complaint"]
    geo = get_geocoder()

    # 1. 确定查询地点：逐个 geocode 分析出的地点实体，取第一个成功的；
    #    否则退回留言属地/省市组合
    location_text = complaint.content
    analysis = state.get("analysis")
    if analysis and getattr(analysis, "location_entities", None):
        for loc in analysis.location_entities:
            c = geo.geocode(loc)
            if c:
                location_text = loc
                break
    elif complaint.city or complaint.province:
        location_text = f"{complaint.province or ''}{complaint.city or ''}"

    query_loc = geo.geocode(location_text)
    # 兜底：解析失败时尝试从文本中提取 省/市/区/县 名再定位（如"鹤壁市"）
    if not query_loc:
        import re as _re

        m = _re.search(r"[\u4e00-\u9fa5]{2,10}(?:省|市|自治州|地区|盟|区|县)", location_text)
        if m:
            query_loc = geo.geocode(m.group(0))
    if not query_loc:
        step.result = {"note": "无法解析地点", "location_text": location_text}
        return {}

    # 2. 批量 geocode 语料案例（带缓存）
    loc_col = [str(r.get("留言属地") or r.get("省份") or "") for r in rows]
    coords = geo.geocode_batch(loc_col)

    # 3. 缓冲区分析
    qlng, qlat = query_loc["lng"], query_loc["lat"]
    radius_km = float(step.args.get("radius_km", 50))
    nearby = []
    for r, c in zip(rows, coords):
        if c and c.get("lng") is not None:
            d = haversine_km(qlng, qlat, c["lng"], c["lat"])
            if d <= radius_km:
                nearby.append({
                    "doc_id": str(r.get("留言ID", "")),
                    "dist_km": round(d, 1),
                    "category": r.get("留言领域", ""),
                    "location": r.get("留言属地", ""),
                    "lng": c["lng"],
                    "lat": c["lat"],
                })

    cat_dist = dict(Counter(n["category"] for n in nearby if n["category"]).most_common(8))
    step.result = {
        "query_location": query_loc,
        "radius_km": radius_km,
        "nearby_count": len(nearby),
        "nearby_category_dist": cat_dist,
        "nearby_samples": nearby[:10],
    }
    return {}


def _do_decide(state: dict, step) -> dict:
    # 决策由 quality gate 的 self-consistency 采样完成，这里仅作标记
    step.result = {"note": "decision delegated to quality gate"}
    return {}


def _do_mcp_call(state: dict, step) -> dict:
    """调用 RDMA_v2 的 MCP 工具。args: {server?, tool, arguments?}"""
    from app.tools.mcp_bridge import call_mcp_tool

    server = str(step.args.get("server", "geotools"))
    tool = str(step.args.get("tool", ""))
    if not tool:
        step.status = "failed"
        step.result = {"error": "mcp_call 缺少 tool 参数"}
        return {"errors": (state.get("errors") or []) + ["mcp_call missing tool"]}
    res = call_mcp_tool(server, tool, step.args.get("arguments") or {})
    payload = {"server": server, "tool": tool, **res}
    data = res.get("data") or ""
    try:
        import json as _json

        payload["data_parsed"] = _json.loads(data)
    except Exception:  # noqa: BLE001
        pass
    
    # 特殊处理洪水模型结果，提取风险摘要供决策使用
    if server == "model_tools" and tool == "run_model":
        try:
            import json as _json
            parsed = _json.loads(data) if data else {}
            if parsed.get("status") == "completed":
                summary = parsed.get("summary", {})
                risk_points = parsed.get("risk_points", [])
                
                # 洪水模型结果处理
                if "high_risk_count" in summary:
                    high_risk = [r for r in risk_points if r.get("risk_level") == "高"]
                    flood_summary = {
                        "high_risk_count": summary.get("high_risk_count", 0),
                        "medium_risk_count": summary.get("medium_risk_count", 0),
                        "low_risk_count": summary.get("low_risk_count", 0),
                        "total_pipes": summary.get("total_pipes", 0),
                        "overflow_pipe_ratio": summary.get("overflow_pipe_ratio", 0),
                        "max_rainfall_mmh": summary.get("max_rainfall_mmh", 0),
                        "high_risk_points": high_risk[:5],
                    }
                    payload["flood_summary"] = flood_summary
                
                # 交通模型结果处理
                elif "congestion_risk" in summary or "total_roads" in summary:
                    traffic_summary = {
                        "total_roads": summary.get("total_roads", 0),
                        "high_risk_roads": summary.get("high_risk_roads", 0),
                        "medium_risk_roads": summary.get("medium_risk_roads", 0),
                        "low_risk_roads": summary.get("low_risk_roads", 0),
                        "avg_congestion": summary.get("avg_congestion", 0),
                        "peak_congestion": summary.get("peak_congestion", 0),
                    }
                    payload["traffic_summary"] = traffic_summary
                
                # 生活圈模型结果处理
                elif "overall_coverage" in summary or "total_communities" in summary:
                    living_summary = {
                        "total_communities": summary.get("total_communities", 0),
                        "overall_coverage": summary.get("overall_coverage", 0),
                        "facility_coverage": summary.get("facility_coverage", {}),
                        "avg_accessibility": summary.get("avg_accessibility", 0),
                    }
                    payload["living_summary"] = living_summary
                
                step.result = payload
        except Exception:
            pass
    
    step.result = payload
    if not res.get("ok"):
        err = f"mcp_call {server}/{tool} failed: {res.get('error') or res.get('data')}"
        logger.warning(err)
        return {"errors": (state.get("errors") or []) + [err]}
    return {}


ACTION_HANDLERS = {
    "perceive": _do_perceive,
    "retrieve": _do_retrieve,
    "retrieve_policy": _do_retrieve_policy,
    "analyze": _do_analyze,
    "stats": _do_stats,
    "geo_query": _do_geo_query,
    "mcp_call": _do_mcp_call,
    "decide": _do_decide,
}


def _trace(state: dict, node: str, action: str = "", latency_ms: float = 0.0, extra: dict | None = None) -> list[dict]:
    ev = {"node": node, "action": action, "ts": time.time(), "latency_ms": round(latency_ms, 1)}
    if extra:
        ev.update(extra)
    return (state.get("trace") or []) + [ev]


# ============================================================
# 节点
# ============================================================


def plan_node(state: dict) -> dict:
    t0 = time.time()
    plan = build_plan(state)
    first = plan.pending_steps[0].step_id if plan.pending_steps else None
    logger.info(f"plan produced: {[(s.step_id, s.action_type) for s in plan.steps]}")
    return {
        "plan": plan,
        "current_step_id": first,
        "current_step": "execute",
        "trace": _trace(state, "planner", "plan", (time.time() - t0) * 1000, {"steps": len(plan.steps)}),
    }


def execute_node(state: dict) -> dict:
    guard = HarnessGuard()
    plan = state["plan"]
    step = plan.get(state["current_step_id"])

    if step is None:
        return {"current_step": "gate", "trace": _trace(state, "executor", "noop")}

    # 边界校验：动作白名单
    r = guard.check_action("executor", step.action_type)
    if not r.ok:
        logger.warning(r.reason)
        return {
            "errors": (state.get("errors") or []) + [r.reason],
            "current_step": "replan",
            "trace": _trace(state, "executor", "blocked"),
        }

    handler = ACTION_HANDLERS.get(step.action_type)
    if handler is None:
        step.status = "failed"
        step.result = {"error": f"unknown action {step.action_type}"}
        return {"current_step": "replan", "errors": (state.get("errors") or []) + [f"unknown action {step.action_type}"]}

    t0 = time.time()
    logger.info(f"executing step {step.step_id}: {step.action_type}")
    updates = handler(state, step)
    latency = (time.time() - t0) * 1000
    step.status = step.status if step.status in ("failed",) else "done"
    updates["current_step"] = "replan"
    updates["steps_used"] = state.get("steps_used", 0) + 1
    updates["trace"] = _trace(state, "executor", step.action_type, latency)
    return updates


def _assess_retrieval_need(state: dict) -> tuple[str, str, str]:
    """Adaptive Retrieval：根据当前信息充分性判断是否需要检索/继续检索。

    返回 (action, query_hint, reason)：
      retrieve  ：尚未检索且信息不足（缺分类/地点/部门置信度低）→ 触发检索
      deepen    ：已检索但案例质量不足（top 案例无部门/领域）→ 换词再检索（限次）
      skip      ：证据充分 → 跳过检索
    """
    analysis = state.get("analysis")
    docs = state.get("retrieved_documents") or []
    perception = state.get("perception") or {}
    has_cat = bool(perception.get("category") or (getattr(analysis, "category", None) if analysis else None))
    has_loc = bool(getattr(analysis, "location_entities", None) if analysis else None)
    dept_conf = getattr(analysis, "department_confidence", 0.0) if analysis else 0.0
    has_dept = bool(getattr(analysis, "predicted_department", None) if analysis else None)

    # 已检索过的 retrieve 次数（含完成的）
    retrieval_runs = sum(1 for s in state.get("plan", None).steps if s.action_type == "retrieve" and s.status == "done") if state.get("plan") else 0

    if not docs:
        if not has_cat or not has_loc or dept_conf < 0.5 or not has_dept:
            q = ""
            if has_loc:
                q = "".join(getattr(analysis, "location_entities", [])[:2])
            elif getattr(analysis, "summary", None):
                q = getattr(analysis, "summary", "")[:60]
            return "retrieve", q, "信息不足（分类/地点/部门置信度低），触发检索"
        return "skip", "", "证据充分，跳过检索"

    # 已检索：评估质量（top 案例是否有部门/领域）
    dept_hit = sum(1 for d in docs[:3] if d.metadata.get("department"))
    if dept_hit >= 1:
        return "skip", "", "检索命中相关案例，证据足够"
    # 初检质量差且尚未深挖过（retrieval_runs<=1 即只做过初检）→ 允许再检索一次
    if retrieval_runs <= 1:
        q = (getattr(analysis, "summary", "") or "").strip()[:60] or (getattr(analysis, "category", "") or "")
        return "deepen", q, "已检索但案例相关性不足，扩大检索"
    return "skip", "", "已检索且重试过，进入决策"


def replan_node(state: dict) -> dict:
    guard = HarnessGuard()
    budget = guard.check_budget(state.get("steps_used", 0), state.get("plan_revisions", 0))
    if not budget.ok:
        logger.warning(f"budget stop: {budget.reason}")
        return {"current_step": "escalate", "trace": _trace(state, "replanner", "budget_stop")}

    plan = state["plan"]
    pending = plan.pending_steps

    # ===== Adaptive Retrieval：按信息充分性决定检索/跳过/加深 =====
    analysis = state.get("analysis")
    if analysis:
        act, query_hint, reason = _assess_retrieval_need(state)
        if act in ("retrieve", "deepen"):
            has_pending_r = any(s.action_type == "retrieve" and s.status == "pending" for s in plan.steps)
            if not has_pending_r:
                new_step = PlanStep(step_id=0, action_type="retrieve",
                                    objective=f"按需检索相似案例（{reason}）", args={"top_k": 6})
                if query_hint:
                    new_step.args["query"] = query_hint
                insert_at = len(plan.steps)
                for i, s in enumerate(plan.steps):
                    if s.action_type == "decide" and s.status == "pending":
                        insert_at = i
                        break
                plan.steps.insert(insert_at, new_step)
                for idx, s in enumerate(plan.steps, start=1):
                    s.step_id = idx
                logger.info(f"adaptive retrieval: {act} ({reason})")
                return {
                    "current_step_id": new_step.step_id,
                    "current_step": "execute",
                    "trace": _trace(state, "replanner", "adaptive_retrieve", extra={"act": act, "reason": reason}),
                }
        elif act == "skip":
            # 跳过计划中尚未执行的 retrieve（证据充分）
            for s in plan.steps:
                if s.action_type == "retrieve" and s.status == "pending":
                    s.status = "skipped"
                    logger.info(f"adaptive retrieval: skip (证据充分)")
                    break

    # ===== 动态插入 geo_query =====
    # 在首个 pending 的 decide 之前插入空间分析步骤（地图展示兜底，不依赖 LLM 自觉）
    analysis = state.get("analysis")
    locs = getattr(analysis, "location_entities", None) if analysis else None
    if locs:
        has_geo = any(s.action_type == "geo_query" for s in plan.steps)
        if not has_geo:
            new_step = PlanStep(
                step_id=0,
                action_type="geo_query",
                objective="空间分析：定位诉求地点并检索邻近历史案例",
            )
            insert_at = len(plan.steps)
            for i, s in enumerate(plan.steps):
                if s.action_type == "decide" and s.status == "pending":
                    insert_at = i
                    break
            plan.steps.insert(insert_at, new_step)
            for idx, s in enumerate(plan.steps, start=1):
                s.step_id = idx
            logger.info(f"injected geo_query step for locations: {locs[:3]}")
            return {
                "current_step_id": new_step.step_id,
                "current_step": "execute",
                "trace": _trace(state, "replanner", "inject_geo_query", extra={"locations": locs[:3]}),
            }

    # ===== 动态插入 policy retrieval（Evidence-based：决策前总是先检索真实法规条款）=====
    has_policy = any(s.action_type == "retrieve_policy" for s in plan.steps)
    if not has_policy:
        new_step = PlanStep(
            step_id=0,
            action_type="retrieve_policy",
            objective="检索相关政策法规条款（证据支撑决策，引用真实条款）",
        )
        insert_at = len(plan.steps)
        for i, s in enumerate(plan.steps):
            if s.action_type == "decide" and s.status == "pending":
                insert_at = i
                break
        plan.steps.insert(insert_at, new_step)
        for idx, s in enumerate(plan.steps, start=1):
            s.step_id = idx
        logger.info("injected retrieve_policy step before decide")
        return {
            "current_step_id": new_step.step_id,
            "current_step": "execute",
            "trace": _trace(state, "replanner", "inject_retrieve_policy"),
        }

    if pending:
        return {
            "current_step_id": pending[0].step_id,
            "current_step": "execute",
            "trace": _trace(state, "replanner", "advance"),
        }
    return {"current_step": "gate", "trace": _trace(state, "replanner", "complete")}


def quality_gate_node(state: dict) -> dict:
    result = run_self_consistency_gate(state)
    from app.harness.config import get_harness_config

    cfg = get_harness_config().quality_gate
    retries = 0
    while result["route"] == "retry" and retries < cfg.max_retries:
        logger.info(f"gate retry {retries + 1}")
        result = run_self_consistency_gate(state)
        retries += 1
    if result["route"] == "retry":
        result["route"] = "escalate"

    logger.info(f"gate: consistency={result['consistency']} route={result['route']}")

    # 本地微调模型专职改写"面向市民回复"（LOCAL_REPLY=1 启用；失败则保留云端回复）
    try:
        from app.llm.local_reply import local_reply_enabled, refine_reply

        if local_reply_enabled() and result.get("decision") is not None:
            complaint = state.get("complaint")
            result["decision"].generated_reply = refine_reply(
                getattr(complaint, "content", "") or "",
                getattr(result["decision"], "generated_reply", None) or "",
            )
            logger.info("local reply applied (LOCAL_REPLY=1)")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"local reply step skipped: {e}")

    return {
        "gate_result": result,
        "decision": result["decision"],
        "current_step": result["route"],
        "trace": _trace(state, "quality_gate", "self_consistency", extra={
            "consistency": result["consistency"],
            "route": result["route"],
        }),
    }


def human_review_node(state: dict) -> dict:
    review = HumanReview(review_status="pending", reviewer_role="staff")
    return {
        "review": review,
        "current_step": "end",
        "trace": _trace(state, "human_review", "escalate"),
    }
