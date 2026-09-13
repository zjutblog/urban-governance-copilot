"""Harness 配置加载。"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "configs",
    "harness.yaml",
)


class RuntimeLimits(BaseModel):
    max_steps: int = 8
    max_revisions: int = 2
    max_wall_time_sec: int = 300
    max_retry_per_step: int = 2


class QualityGateConfig(BaseModel):
    algorithm: str = "self_consistency"
    k: int = 3
    temperature: float = 0.7
    theta_high: float = 0.6
    theta_low: float = 0.4
    max_retries: int = 2
    vote_fields: list[str] = Field(default_factory=lambda: ["responsible_department"])


class PerceptionConfig(BaseModel):
    classifier_model: str = "D:/jupyter_work/event_classifier/best_model"
    enabled: bool = True


class HarnessConfig(BaseModel):
    runtime: RuntimeLimits = Field(default_factory=RuntimeLimits)
    action_safety: dict[str, str] = Field(default_factory=dict)
    action_allowlist: dict[str, list[str]] = Field(default_factory=dict)
    require_human_approval: bool = True
    quality_gate: QualityGateConfig = Field(default_factory=QualityGateConfig)
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)

    def safety_of(self, action_type: str) -> str:
        return self.action_safety.get(action_type, "read")

    def allowed_actions(self, agent_role: str) -> list[str]:
        return self.action_allowlist.get(agent_role, [])


@lru_cache(maxsize=1)
def get_harness_config() -> HarnessConfig:
    raw: dict[str, Any] = {}
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    cfg = HarnessConfig(**raw)
    # 环境变量覆盖（便于 CPU 快速调试 self-consistency 采样数）
    if os.getenv("QUALITY_GATE_K"):
        cfg.quality_gate.k = int(os.getenv("QUALITY_GATE_K"))
    return cfg
