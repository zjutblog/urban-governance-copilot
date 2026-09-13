# -*- coding: utf-8 -*-
"""本地微调模型专职生成"面向市民回复"。

适用场景：主链路（planner/分析/决策）需要 JSON 结构化输出，用云端 DeepSeek；
而微调后的 Qwen3-ugov 只擅长写政务回复 → 定稿后用本地模型改写 generated_reply。

开关：.env 里 LOCAL_REPLY=1 启用（默认 0 关闭）。
依赖：本地模型服务在跑（scripts/serve_local_llm.py），LOCAL_BASE_URL/LOCAL_MODEL 指向它。
"""
import os

from loguru import logger

# 与训练时一致的 system 提示（保持分布一致）
_SYSTEM = (
    "你是「城市治理 Copilot」的政务留言处理助手。请依据群众留言生成一条面向市民的官方回复建议："
    "①话语自然、像真实政府部门回复；②只写程序性、可兑现的表述（如'已转交相关部门核实处理''将跟进督办并反馈'），"
    "禁止编造'已拆除/已处罚/已安排'等未发生事实；③一句话到两三句即可，不冗余。"
)


def local_reply_enabled() -> bool:
    return os.getenv("LOCAL_REPLY", "0").strip() == "1"


def refine_reply(complaint_text: str, fallback: str, timeout: int = 180) -> str:
    """用本地微调模型生成回复；失败则原样返回 fallback（不影响主流程）。"""
    if not local_reply_enabled():
        return fallback
    try:
        from openai import OpenAI

        base = os.getenv("LOCAL_BASE_URL", "http://127.0.0.1:8011/v1")
        model = os.getenv("LOCAL_MODEL", "qwen3-ugov")
        key = os.getenv("LOCAL_API_KEY") or os.getenv("LLM_API_KEY", "")
        client = OpenAI(base_url=base, api_key=key or "local", timeout=timeout)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": (complaint_text or "")[:1000]},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        out = (resp.choices[0].message.content or "").strip()
        # 剥离可能残留的思考段
        if "<think>" in out:
            out = out.split("</think>", 1)[-1].strip()
        return out or fallback
    except Exception as e:  # noqa: BLE001
        logger.warning(f"local reply refine failed, keep cloud reply: {e}")
        return fallback
