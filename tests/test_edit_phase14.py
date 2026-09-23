def payload():
    return {
        "customer_id": "cust-dining",
        "text": "dining culture event",
        "city": "Rome",
        "date": "2026-10-02",
        "timezone": "Europe/Rome",
        "start_time": "17:00",
        "end_time": "23:00",
        "card_id": "card-a",
    }


def make_plan(client):
    response = client.post("/api/v1/outings/plan", json=payload())
    assert response.status_code == 200, response.text
    return response.json()


def test_remove_stop_preserves_plan_and_marks_revalidation(client):
    plan = make_plan(client)
    stop = plan["alternatives"][0]["stops"][0]["entity"]["entity_id"]
    response = client.post(
        f"/api/v1/outings/{plan['outing_id']}/edit",
        json={"customer_id": "cust-dining", "operation": "REMOVE_STOP", "stop_id": stop},
    )
    assert response.status_code == 200
    edited = response.json()
    assert edited["status"] == "PARTIAL"
    assert stop not in [s["entity"]["entity_id"] for s in edited["alternatives"][0]["stops"]]
    assert any("fresh route" in warning for warning in edited["warnings"])


def test_change_budget_and_duration(client):
    plan = make_plan(client)
    rid = plan["outing_id"]
    response = client.post(
        f"/api/v1/outings/{rid}/edit",
        json={"customer_id": "cust-dining", "operation": "CHANGE_BUDGET", "budget": "25", "currency": "EUR"},
    )
    assert response.status_code == 200 and response.json()["search_plan"]["budget"] == "25"
    response = client.post(
        f"/api/v1/outings/{rid}/edit",
        json={"customer_id": "cust-dining", "operation": "CHANGE_DURATION", "visit_minutes": 30},
    )
    assert response.status_code == 200 and response.json()["status"] == "PARTIAL"


def test_change_category_filters_stops(client):
    plan = make_plan(client)
    rid = plan["outing_id"]
    response = client.post(
        f"/api/v1/outings/{rid}/edit",
        json={"customer_id": "cust-dining", "operation": "CHANGE_CATEGORY", "category": "DINING"},
    )
    assert response.status_code == 200
    assert all(s["entity"]["entity_type"] == "DINING" for a in response.json()["alternatives"] for s in a["stops"])


def test_add_and_replace_require_fresh_verified_plan(client):
    plan = make_plan(client)
    rid = plan["outing_id"]
    for operation in ("ADD_STOP", "REPLACE_STOP"):
        response = client.post(
            f"/api/v1/outings/{rid}/edit", json={"customer_id": "cust-dining", "operation": operation}
        )
        assert response.status_code == 422


def test_expired_or_unknown_run(client):
    response = client.post(
        "/api/v1/outings/missing/edit", json={"customer_id": "cust-dining", "operation": "REMOVE_STOP", "stop_id": "x"}
    )
    assert response.status_code == 404


def test_member_consent_required(client):
    customer = client.app.state.repository.customer("cust-dining")
    customer.consent.allowed = False
    client.app.state.repository.save_customer(customer)
    response = client.post(
        "/api/v1/outings/missing/edit", json={"customer_id": "cust-dining", "operation": "REMOVE_STOP", "stop_id": "x"}
    )
    assert response.status_code == 403
