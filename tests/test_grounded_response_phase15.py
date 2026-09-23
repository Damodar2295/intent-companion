from datetime import UTC, datetime, timedelta

from agent.outing.grounding import build_response
from agent.outing.models import OutingPlan


def test_grounded_response_projects_only_evidence_backed_stops():
    plan = OutingPlan(
        outing_id="run-1",
        status="READY",
        mode="demo",
        generated_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        warnings=["route needs refresh", "route needs refresh"],
    )
    response = build_response(plan)
    assert response.summary == "No sourced stops are available yet."
    assert response.stops == []
    assert response.warnings == ["route needs refresh"]
