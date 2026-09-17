import pytest


def test_health_and_openapi(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["demo_mode"] is True
    assert response.headers["x-request-id"].startswith("req-")
    paths = client.get("/openapi.json").json()["paths"]
    assert all(p in paths for p in ["/signals", "/intents/detect", "/companion", "/scenarios"])


@pytest.mark.parametrize("prefix", ["", "/api"])
def test_end_to_end_scenarios(client, prefix):
    for scenario in client.get(prefix + "/scenarios").json():
        data = client.post(
            prefix + "/intents/detect",
            json={"customer_id": scenario["customer_id"], "signal_ids": scenario["signal_ids"]},
        ).json()
        response = client.post(
            prefix + "/companion",
            json={"customer_id": scenario["customer_id"], "intent_id": data["intent"]["intent_id"]},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ready"


def test_unknown_ids_and_ownership(client):
    assert client.get("/customers/unknown").status_code == 404
    assert client.post("/intents/detect", json={"customer_id": "unknown"}).status_code == 404
    assert client.post("/companion", json={"customer_id": "cust-dining", "intent_id": "unknown"}).status_code == 404
    intent = client.post("/intents/detect", json={"customer_id": "cust-dining"}).json()["intent"]
    assert (
        client.post("/companion", json={"customer_id": "cust-stay", "intent_id": intent["intent_id"]}).status_code
        == 404
    )


def test_preferences_api(client):
    client.post("/customers/cust-dining/preferences/remove", json={"preference": "fine dining"}).raise_for_status()
    prefs = client.get("/customers/cust-dining/preferences").json()
    assert prefs["preferences"] == ["museums"]
    assert prefs["suppressed_preferences"] == ["fine dining"]
    client.put("/customers/cust-dining/preferences", json={"preferences": ["shopping"]}).raise_for_status()
    result = client.post("/intents/detect", json={"customer_id": "cust-dining"}).json()
    assert result["intent"]["preferences"] == ["shopping"]
    assert (
        client.put("/customers/cust-dining/preferences", json={"preferences": ["protected characteristic"]}).status_code
        == 422
    )


def test_consent_withdrawal(client):
    intent = client.post("/intents/detect", json={"customer_id": "cust-dining"}).json()["intent"]
    client.put(
        "/customers/cust-dining/consent", json={"allowed": False, "purpose": "personalization"}
    ).raise_for_status()
    assert client.post("/intents/detect", json={"customer_id": "cust-dining"}).json()["status"] == "abstained"
    response = client.post("/companion", json={"customer_id": "cust-dining", "intent_id": intent["intent_id"]})
    assert response.json()["status"] == "abstained"
    assert not response.json()["recommended_cards"]


def test_ingest_rejects_missing_consent_and_duplicate_conflicts(client):
    signal = client.app.state.repository.signals("cust-dining")[0].model_dump(mode="json")
    assert client.post("/signals", json=signal).json()["status"] == "duplicate"
    signal["source"] = "changed"
    assert client.post("/signals", json=signal).status_code == 409
    signal["event_id"] = "new-event"
    signal.pop("consent")
    assert client.post("/signals", json=signal).status_code == 422
    assert "new-event" not in {s.event_id for s in client.app.state.repository.signals("cust-dining")}


def test_unexpected_exception_is_redacted(client, monkeypatch):
    def bad(*args):
        raise RuntimeError("password=do-not-expose")

    monkeypatch.setattr(client.app.state.repository, "customer", bad)
    response = client.get("/customers/cust-dining")
    assert response.status_code == 500
    assert "password" not in response.text
