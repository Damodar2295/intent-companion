from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel


class LLMError(Exception):
    """Safe error; never includes provider response bodies or credentials."""


@dataclass(frozen=True)
class ModelRoute:
    adapter: str
    model: str
    model_class: str = "standard"


@dataclass(frozen=True)
class LLMRequest:
    operation: str
    messages: list[dict[str, str]]
    response_schema: type[BaseModel]
    model_class: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class AdapterOutput:
    content: str | dict[str, Any]
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class LLMResult:
    output: BaseModel
    route: ModelRoute
    latency_ms: float
    usage: dict[str, int]


class LLMAdapter(Protocol):
    async def invoke(self, request: LLMRequest, route: ModelRoute) -> AdapterOutput: ...


class LLMService(Protocol):
    async def invoke(self, request: LLMRequest) -> LLMResult: ...
