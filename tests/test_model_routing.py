import pytest

from agent.llm.contracts import ModelRoute
from agent.llm.router import OPERATIONS, ModelRouter
from agent.providers.container import build_gateway


def test_router_describe_is_safe(settings):
    gateway = build_gateway(settings)
    data = gateway.router.describe()
    assert set(data) == set(OPERATIONS)
    assert all(set(item) == {"adapter", "model_class", "model_configured"} for item in data.values())
    assert "api_key" not in str(data).lower() and "endpoint" not in str(data).lower()


def test_route_capability_mismatch_rejected():
    routes = {"recommendation.ranking": ModelRoute("mock", "fixture", "lightweight")}
    with pytest.raises(ValueError, match="model class"):
        ModelRouter(routes)


def test_partial_test_router_remains_supported():
    router = ModelRouter({"recommendation.ranking": ModelRoute("mock", "fixture", "standard")})
    assert router.resolve("recommendation.ranking").adapter == "mock"


def test_unknown_operation_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        ModelRouter({"unknown": ModelRoute("mock", "fixture")})


def test_mock_gateway_routes_every_operation_to_mock(settings):
    settings.llm_gateway_mode = "mock"
    gateway = build_gateway(settings)
    assert all(route.adapter == "mock" for route in gateway.router.routes.values())


def test_unavailable_adapter_never_falls_back(settings):
    settings.llm_routes = {"recommendation.ranking": {"adapter": "safechain"}}
    with pytest.raises(ValueError, match="unavailable"):
        build_gateway(settings)


def test_routes_endpoint_hides_configuration(client):
    response = client.get("/api/v1/llm/routes")
    assert response.status_code == 200
    body = response.json()
    assert body["secrets_exposed"] is False
    assert "api_key" not in str(body).lower()
    assert "endpoint" not in str(body).lower()
    assert "search.requirements_generation" in body["operations"]
