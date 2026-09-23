import asyncio
import json

import httpx
import pytest
from pydantic import Field

from agent.domain import Model
from agent.llm.adapters import MockLLMAdapter, ResponsesAdapter
from agent.llm.contracts import LLMError, LLMRequest, ModelRoute
from agent.llm.gateway import LLMGateway
from agent.llm.router import ModelRouter
from agent.outing.config import OutingSettings
from agent.outing.providers import Transport
from agent.providers.container import build_gateway


class Output(Model):
    evidence_ids: list[str] = Field(min_length=1)


def request():
    return LLMRequest(
        "recommendation.explanation",
        [{"role": "user", "content": "private input"}],
        Output,
        metadata={"credential": "never-log-this"},
    )


def gateway(handler):
    return LLMGateway(
        ModelRouter({"recommendation.explanation": ModelRoute("mock", "fixture")}),
        {"mock": MockLLMAdapter({"recommendation.explanation": handler})},
    )


async def test_mock_validated_and_logs_safe(caplog):
    caplog.set_level("INFO", logger="llm")
    result = await gateway({"evidence_ids": ["source-1"]}).invoke(request())
    assert result.output.evidence_ids == ["source-1"]
    assert result.route.adapter == "mock" and result.latency_ms >= 0
    assert "private input" not in caplog.text and "never-log-this" not in caplog.text


@pytest.mark.parametrize("output", [{"evidence_ids": []}, {"evidence_ids": ["a"], "invented_amount": 100}, "not-json"])
async def test_gateway_rejects_invalid_output(output):
    with pytest.raises(LLMError, match="structured validation"):
        await gateway(output).invoke(request())


async def test_cancellation_propagates():
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def delayed(req):
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.set()

    task = asyncio.create_task(gateway(delayed).invoke(request()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


def test_enterprise_selection_never_falls_back(settings):
    settings.llm_gateway_mode = "safechain"
    with pytest.raises(ValueError, match="unavailable"):
        build_gateway(settings)
    settings.llm_gateway_mode = "configured"
    settings.llm_routes = {"recommendation.ranking": {"adapter": "safechain"}}
    with pytest.raises(ValueError, match="unavailable"):
        build_gateway(settings)


async def test_mock_mode_does_not_call_transport(settings):
    settings.llm_gateway_mode = "mock"

    def no_network(req):
        pytest.fail("Mock invoked network")

    service = build_gateway(
        settings,
        transport=httpx.MockTransport(no_network),
        mock_handlers={"recommendation.explanation": {"evidence_ids": ["a"]}},
    )
    assert (await service.invoke(request())).route.adapter == "mock"


async def test_responses_adapter_schema_model_and_usage():
    settings = OutingSettings(openai_key="test-key", model="from-configuration")

    def response(req):
        body = json.loads(req.content)
        assert body["model"] == "from-configuration" and body["store"] is False
        assert body["text"]["format"]["strict"] is True
        return httpx.Response(
            200,
            json={
                "output": [{"content": [{"type": "output_text", "text": '{"evidence_ids":["a"]}'}]}],
                "usage": {"input_tokens": 10, "output_tokens": 5, "secret": "omit"},
            },
        )

    transport = Transport(settings, httpx.AsyncClient(transport=httpx.MockTransport(response)))
    service = LLMGateway(
        ModelRouter({"recommendation.explanation": ModelRoute("responses", settings.model)}),
        {"responses": ResponsesAdapter(transport, settings)},
    )
    try:
        result = await service.invoke(request())
        assert result.usage == {"input_tokens": 10, "output_tokens": 5}
    finally:
        await transport.close()


def test_no_model_http_in_business_modules():
    from pathlib import Path

    for filename in ["agent/ai.py", "agent/business/extraction.py", "agent/outing/llm.py"]:
        text = Path(filename).read_text()
        assert "AsyncClient(" not in text and "Authorization" not in text and "/v1/responses" not in text


async def test_responses_rejects_insecure_remote_endpoint_before_network():
    settings = OutingSettings(openai_key="private-key", model="configured", responses_endpoint="http://example.org")

    class NoNetwork:
        async def json(self, *args, **kwargs):
            pytest.fail("Credential sent to insecure endpoint")

    with pytest.raises(LLMError, match="HTTPS"):
        await ResponsesAdapter(NoNetwork(), settings).invoke(request(), ModelRoute("responses", settings.model))


async def test_chat_malformed_envelope_returns_safe_error(settings):
    settings.llm_endpoint = "https://model.example/chat"
    settings.llm_model = "configured"
    settings.llm_api_key = "secret"
    service = build_gateway(settings, transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[])))
    req = LLMRequest("recommendation.ranking", request().messages, Output)
    with pytest.raises(LLMError, match="unavailable"):
        await service.invoke(req)


def test_route_overrides_preserve_other_operations(settings):
    settings.llm_model = "original"
    settings.llm_routes = {"recommendation.ranking": {"model": "override"}}
    service = build_gateway(settings)
    assert service.router.resolve("recommendation.ranking").model == "override"
    assert service.router.resolve("business.goal_extraction").model == "original"
    with pytest.raises(LLMError):
        service.router.resolve("recommendation.ranking", "unavailable-class")
