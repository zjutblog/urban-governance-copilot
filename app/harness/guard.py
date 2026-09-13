"""HarnessGuard：在 agent 运行时强制边界。

负责三件事：
1. 动作白名单校验（某角色不能越权调用）
2. 预算/终止条件校验（步数、重规划次数）
3. 安全等级判定（read 放行 / write 需门控）
"""
from __future__ import annotations

from dataclasses import dataclass

from app.harness.config import HarnessConfig, get_harness_config


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""
    safety: str = "read"


class HarnessGuard:
    def __init__(self, config: HarnessConfig | None = None):
        self.config = config or get_harness_config()

    def check_action(self, agent_role: str, action_type: str) -> GuardResult:
        """校验某角色是否被允许执行某动作。"""
        allowed = self.config.allowed_actions(agent_role)
        if action_type not in allowed:
            return GuardResult(
                ok=False,
                reason=f"action '{action_type}' not in allowlist for role '{agent_role}'",
            )
        return GuardResult(ok=True, safety=self.config.safety_of(action_type))

    def is_write(self, action_type: str) -> bool:
        return self.config.safety_of(action_type) == "write"

    def check_budget(self, steps_used: int, plan_revisions: int) -> GuardResult:
        rt = self.config.runtime
        if steps_used >= rt.max_steps:
            return GuardResult(ok=False, reason="max_steps reached")
        if plan_revisions >= rt.max_revisions:
            return GuardResult(ok=False, reason="max_revisions reached")
        return GuardResult(ok=True)
