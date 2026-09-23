from datetime import datetime
from typing import Literal

from pydantic import Field

from agent.domain import CatalogItem, Model
from agent.outing.models import DiscoveryCandidate
from agent.search.models import SearchPlanResponse


class ToolTrace(Model):
    tool: str
    sequence: int
    status: Literal[
        "QUEUED", "RUNNING", "SUCCEEDED", "EMPTY", "FAILED", "UNAVAILABLE", "TIMED_OUT", "CANCELLED", "SKIPPED"
    ]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: float = 0
    queue_ms: float = 0
    result_count: int = 0
    truncated: bool = False
    message: str = ""


class ToolOutput(Model):
    tool: str
    candidates: list[DiscoveryCandidate] = Field(default_factory=list)
    catalog: list[CatalogItem] = Field(default_factory=list)
    usage: Literal["DISCOVERY_ONLY", "ILLUSTRATIVE_CATALOG_NOT_ELIGIBILITY"]


class ExecutionResult(Model):
    run_id: str
    status: Literal["READY", "EMPTY", "PARTIAL", "ERROR", "CLARIFICATION_REQUIRED"]
    mode: Literal["demo", "realtime"]
    planning: SearchPlanResponse | None = None
    outputs: list[ToolOutput] = Field(default_factory=list)
    trace: list[ToolTrace] = Field(default_factory=list)
    deferred: dict[str, str] = Field(default_factory=dict)
    message: str = "Discovery records are not verified recommendations. Catalog records are illustrative, not eligibility or savings."
