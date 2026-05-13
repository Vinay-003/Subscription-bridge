from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunResult:
    success: bool
    answer: str = ""
    error: str = ""
    needs_clarification: bool = False
    question: str = ""
    run_id: str = ""
    steps: int = 0
    max_steps: int = 0
    total_elapsed: float = 0.0
    summary: dict[str, Any] = field(default_factory=dict)
