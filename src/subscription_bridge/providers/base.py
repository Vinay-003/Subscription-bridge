from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

ProviderCapability = Literal[
    "text_chat",
    "code_reasoning",
    "image_generation",
    "file_upload",
    "vision",
]


@dataclass
class ProviderRequest:
    run_id: str
    prompt: str
    system_prompt: str | None = None
    attachments: list[str] | None = None
    response_format: str = "text"
    require_json: bool = False
    timeout_seconds: int = 300
    metadata: dict[str, Any] | None = None


@dataclass
class ProviderResponse:
    provider: str
    text: str
    raw_text: str
    success: bool
    latency_seconds: float
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ProviderAdapter(ABC):
    name: str = ""
    capabilities: set[ProviderCapability] = set()

    @abstractmethod
    async def create_session(self) -> str:
        ...

    @abstractmethod
    async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
        ...

    @abstractmethod
    async def reset_chat(self, session_id: str) -> None:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @abstractmethod
    async def close_session(self, session_id: str) -> None:
        ...

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            cls.name = cls.__name__.lower().replace("provideradapter", "").replace("adapter", "")
