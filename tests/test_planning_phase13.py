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


def test_json_outing_plan_returns_validated_alternatives(client):
    response = client.post("/api/v1/outings/plan", json=payload())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["search_plan"]["city"] == "Rome"
    assert data["alternatives"]
    assert all(stop["evidence_ids"] for alternative in data["alternatives"] for stop in alternative["stops"])
    assert all(route["synthetic"] for alternative in data["alternatives"] for route in alternative["routes"])
    assert all(len(alternative["stops"]) <= 4 for alternative in data["alternatives"])


def test_plan_rejects_consent(client):
    customer = client.app.state.repository.customer("cust-dining")
    customer.consent.allowed = False
    client.app.state.repository.save_customer(customer)
    response = client.post("/api/v1/outings/plan", json=payload())
    assert response.status_code == 403


def test_plan_rejects_business_customer(client):
    response = client.post("/api/v1/outings/plan", json=payload() | {"customer_id": "biz-merchant"})
    assert response.status_code in {404, 422}


def test_plan_validation_rejects_bad_window(client):
    response = client.post("/api/v1/outings/plan", json=payload() | {"start_time": "23:00", "end_time": "17:00"})
    assert response.status_code == 422
