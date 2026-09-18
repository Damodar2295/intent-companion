import pytest


@pytest.mark.parametrize("customer", ["cust-prospect", "cust-dining", "cust-stay"])
def test_progressive_synthetic_journey(client, customer):
    ids = []
    for index, (event, score, stage) in enumerate(
        [
            ("ad_click", 0.1, "exploring"),
            ("ad_click", 0.1, "exploring"),
            ("travel_search", 0.55, "planning"),
            ("hotel_search", 0.95, "planning"),
            ("travel_booking", 1, "booked"),
        ]
    ):
        event_id = f"replay-{index}"
        response = client.post(
            "/signals",
            json={
                "event_id": event_id,
                "customer_id": customer,
                "source": "synthetic_test",
                "event_type": event,
                "timestamp": f"2026-09-17T10:00:0{index}Z",
                "consent": {"allowed": True},
                "context": {"destination": "Rome", "start_date": "2026-10-10", "end_date": "2026-10-15"},
            },
        )
        assert response.status_code == 200
        ids.append(event_id)
        result = client.post("/intents/detect", json={"customer_id": customer, "signal_ids": ids}).json()
        intent = result["intent"]
        assert intent["confidence"] == score
        assert intent["intent_stage"] == stage
        assert set(intent["signal_ids"]) == set(ids)
    experience = client.post("/companion", json={"customer_id": customer, "intent_id": intent["intent_id"]}).json()
    assert experience["status"] == "ready"
    assert experience["intent"]["intent_stage"] == "booked"
