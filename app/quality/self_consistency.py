"""Self-Consistency 质量门控。

对决策的离散字段做多次采样投票（而非投票自由文本），
一致性高于阈值通过，低于阈值升级人工，中间带批评重写。

协同点：k 条采样共享同一 prompt 前缀，GPU 上 vLLM prefix cache 让边际成本趋近 0。
"""
from __future__ import annotations

from typing import Any, Optional

from loguru import logger

from app.agents.decision import make_decision
from app.harness.config import get_harness_config


def run_self_consistency_gate(state: dict, k: Optional[int] = None) -> dict[str, Any]:
    cfg = get_harness_config().quality_gate
    k = k or cfg.k
    temperature = cfg.temperature
    vote_fields = cfg.vote_fields

    samples = []
    for i in range(k):
        logger.info(f"self-consistency sample {i + 1}/{k}")
        samples.append(make_decision(state, temperature=temperature))

    votes: dict[str, dict[str, Any]] = {}
    for field in vote_fields:
        dist: dict[str, int] = {}
        for s in samples:
            val = str(getattr(s, field, None))
            dist[val] = dist.get(val, 0) + 1
        winner = max(dist, key=dist.get)
        votes[field] = {
            "winner": winner,
            "consistency": dist[winner] / k,
            "distribution": dist,
        }

    overall = round(
        sum(v["consistency"] for v in votes.values()) / max(len(votes), 1), 3
    )

    final = None
    for s in samples:
        if all(str(getattr(s, f, None)) == votes[f]["winner"] for f in vote_fields):
            final = s
            break
    if final is None:
        final = samples[0]

    if overall >= cfg.theta_high:
        route = "pass"
    elif overall >= cfg.theta_low:
        route = "retry"
    else:
        route = "escalate"

    return {
        "k": k,
        "votes": votes,
        "consistency": overall,
        "route": route,
        "decision": final,
        "reasoning_chain": getattr(final, "reasoning_chain", []),
    }
