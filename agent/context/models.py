from typing import Literal

from pydantic import Field

from agent.domain import Consent, Model


class ContextMessage(Model):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=12000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    priority: int = Field(default=0, ge=0, le=100)


class ContextRequest(Model):
    customer_id: str = Field(min_length=1, max_length=100)
    consent: Consent = Field(default_factory=Consent)
    messages: list[ContextMessage] = Field(min_length=1, max_length=100)
    evidence: list[ContextMessage] = Field(default_factory=list, max_length=200)
    token_budget: int = Field(default=1800, ge=128, le=12000)
    preserve_last_messages: int = Field(default=4, ge=1, le=20)
    debug: bool = False


class ContextResponse(Model):
    status: Literal["READY", "PARTIAL", "ERROR"]
    messages: list[ContextMessage]
    estimated_tokens: int
    token_budget: int
    diagnostics: dict[str, int | float | str] | None = None
    warnings: list[str] = Field(default_factory=list)
