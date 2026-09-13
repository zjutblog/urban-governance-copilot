"""LLM 客户端 —— OpenAI 兼容接口抽象。

默认接 DeepSeek 云端 API（秒级）；改 .env 可切回本地 Ollama / vLLM / 其他云端。

配置解析优先级：请求级 cfg > .env。cfg 随 GovernanceState.llm_config 在
pipeline 内逐节点传递，不写任何进程级全局变量——多用户并发时各自的
api_key/base_url/model 互不干扰（修复原 set_llm_config 全局覆盖问题）。
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

# 默认云端 DeepSeek；如需本地 Ollama，把 .env 改成 http://localhost:11434/v1 + qwen3:8b
_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-chat"


def _base_url() -> str:
    return os.getenv("LLM_BASE_URL", _DEFAULT_BASE_URL)


def _model() -> str:
    return os.getenv("LLM_MODEL", _DEFAULT_MODEL)


def resolve_llm_config(cfg: dict | None = None) -> dict:
    """合并请求级配置与 .env：cfg 中非空字段优先，缺失字段回落 .env。

    支持「双线」：
      LLM_MODE=cloud  → 云端（默认 DeepSeek：LLM_BASE_URL / LLM_MODEL / LLM_API_KEY）
      LLM_MODE=local  → 本地 Qwen（LOCAL_BASE_URL 默认 http://localhost:11434/v1，
                       LOCAL_MODEL 默认 qwen3:0.6b，可指向微调后导入 Ollama 的 tag）
    请求级 cfg 若显式带 base_url/model 则总是生效；只带 api_key 时按 mode 决定 backend 再覆盖 key。
    """
    cfg = cfg or {}
    mode = os.getenv("LLM_MODE", "cloud").strip().lower()
    explicit_url = bool(cfg.get("base_url") or cfg.get("model"))

    if mode == "local" and not explicit_url:
        base = os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1")
        model = os.getenv("LOCAL_MODEL", "qwen3:0.6b")
        api_key = cfg.get("api_key") or os.getenv("LOCAL_API_KEY") or os.getenv("LLM_API_KEY", "")
    else:
        base = cfg.get("base_url") or _base_url()
        model = cfg.get("model") or _model()
        api_key = cfg.get("api_key") or os.getenv("LLM_API_KEY", "")
    return {"api_key": api_key, "base_url": base, "model": model}


def get_llm(temperature: float = 0.2, cfg: dict | None = None) -> ChatOpenAI:
    """按需创建 LLM 实例（不缓存）。cfg 为请求级配置（取自 state.llm_config）。"""
    c = resolve_llm_config(cfg)
    return ChatOpenAI(
        base_url=c["base_url"],
        api_key=c["api_key"],
        model=c["model"],
        temperature=temperature,
        timeout=120,
    )
