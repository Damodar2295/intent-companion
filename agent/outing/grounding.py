"""Grounded customer response assembly for completed outing plans."""

from pydantic import Field

from agent.domain import Model
from agent.outing.models import OutingPlan


class GroundedStop(Model):
    entity_id: str
    name: str
    explanation: str
    evidence_ids: list[str] = Field(min_length=1)


class GroundedResponse(Model):
    outing_id: str
    status: str
    summary: str
    stops: list[GroundedStop]
    warnings: list[str]
    evidence_ids: list[str]


def build_response(plan: OutingPlan) -> GroundedResponse:
    """Project only evidence-backed stop fields; never invents facts or values."""
    stops = []
    evidence = []
    for alternative in plan.alternatives:
        for stop in alternative.stops:
            if not stop.evidence_ids:
                continue
            stops.append(
                GroundedStop(
                    entity_id=stop.entity.entity_id,
                    name=stop.entity.canonical_name,
                    explanation=stop.explanation,
                    evidence_ids=list(dict.fromkeys(stop.evidence_ids)),
                )
            )
            evidence.extend(stop.evidence_ids)
        if stops:
            break
    summary = "Here is a sourced outing plan." if stops else "No sourced stops are available yet."
    return GroundedResponse(
        outing_id=plan.outing_id,
        status=plan.status,
        summary=summary,
        stops=stops,
        warnings=list(dict.fromkeys(plan.warnings)),
        evidence_ids=list(dict.fromkeys(evidence)),
    )
