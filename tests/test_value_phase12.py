import pytest

from agent.outing.demo import Demo
from agent.outing.models import OutingRequest
from agent.outing.verification import VerificationService


@pytest.mark.asyncio
async def test_preview_labels_synthetic_value(client):
    settings = client.app.state.outing.settings
    demo = Demo(settings)
    request = OutingRequest(customer_id="cust-dining", text="dining", city="Rome", date="2026-10-02", card_id="card-a")
    plan = await demo.interpret(request, [])
    candidate = (await demo.search(plan))[0]
    entity = VerificationService(settings).verify(candidate)
    response = client.post(
        "/api/v1/value/preview",
        json={
            "customer_id": "cust-dining",
            "consent": {"allowed": True},
            "entity": entity.model_dump(mode="json"),
            "card_id": "card-a",
            "date": "2026-10-02",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["label"] == "Demo / illustrative AMEX value"
    assert data["eligibility_evaluated"] is False and data["points_separate"] is True
    assert all(match["label"] == "Demo / illustrative AMEX value" for match in data["matches"])


@pytest.mark.asyncio
async def test_event_never_gets_merchant_match(client):
    settings = client.app.state.outing.settings
    demo = Demo(settings)
    request = OutingRequest(customer_id="cust-dining", text="event", city="Rome", date="2026-10-02", card_id="card-a")
    plan = await demo.interpret(request, [])
    event = next(c for c in await demo.search(plan) if c.category == "EVENT")
    entity = VerificationService(settings).verify(event)
    response = client.post(
        "/api/v1/value/preview",
        json={
            "customer_id": "cust-dining",
            "consent": {"allowed": True},
            "entity": entity.model_dump(mode="json"),
            "card_id": "card-a",
            "date": "2026-10-02",
        },
    )
    assert response.status_code == 200 and response.json()["merchant"]["status"] == "NO_MATCH"


def test_member_cannot_preview_unheld_card(client):
    response = client.post(
        "/api/v1/value/preview",
        json={
            "customer_id": "cust-dining",
            "consent": {"allowed": True},
            "entity": {
                "entity_id": "x",
                "entity_type": "DINING",
                "canonical_name": "x",
                "facts": {},
                "sources": [],
                "conflicts": {},
                "confidence": {},
                "freshness": {},
                "verification_status": "UNVERIFIED",
                "relationships": [],
                "merchant": {},
                "amex_matches": [],
                "synthetic": True,
            },
            "card_id": "not-held",
            "date": "2026-10-02",
        },
    )
    assert response.status_code == 403
