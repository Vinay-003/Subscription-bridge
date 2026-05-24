from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from subscription_bridge.core.plan import AgentMode


@dataclass
class Task:
    text: str
    workspace: str = "."
    provider: str = "fake"
    max_steps: int = 10
    metadata: dict[str, Any] = field(default_factory=dict)
    mode: AgentMode = AgentMode.ACT
