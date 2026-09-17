import json

import httpx
import pytest

from agent.ai import DeterministicAI, LLMRankingAI
from agent.customer_context import CustomerService
from agent.factory import GraphFactory


@pytest.fixture
def recommendations(service, repository):
    intent = service.intent_engine.detect("cust-dining")
    matches = service.matching.match(repository.customer("cust-dining"), intent)
    return service.value_service.apply(matches.recommendations, matches.items)[0]


@pytest.mark.parametrize(
    "failure",
    ["http", "timeout", "json", "invented_id", "unsupported_claim", "bad_evidence", "duplicates", "missing_candidate"],
)
async def test_model_failure_falls_back(settings, recommendations, failure):
    settings.ai_provider = "llm"
    settings.llm_endpoint = "https://model.example.invalid/v1/chat/completions"
    settings.llm_model = "test-model"
    settings.llm_api_key = "test-not-a-secret"
    choices = [
        {"recommendation_id": r.recommendation_id, "evidence_ids": [r.evidence[-1].evidence_id]}
        for r in recommendations
    ]
    output = {"choices": choices}
    if failure == "invented_id":
        choices[0]["recommendation_id"] = "invented-card"
    if failure == "unsupported_claim":
        output["description"] = "You are approved and receive a million dollars."
    if failure == "bad_evidence":
        choices[0]["evidence_ids"] = ["made-up-fact"]
    if failure == "duplicates":
        choices.append(choices[0])
    if failure == "missing_candidate":
        choices.pop()

    def respond(request):
        if failure == "http":
            return httpx.Response(500, json={"secret": "provider-internal"})
        if failure == "timeout":
            raise httpx.ReadTimeout("provider-internal")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "broken" if failure == "json" else json.dumps(output)}}]}
        )

    provider = LLMRankingAI(settings, httpx.MockTransport(respond))
    result = await provider.rank_recommendations(recommendations, ["fine dining"])
    expected = await DeterministicAI().rank_recommendations(recommendations, ["fine dining"])
    assert result.mode == "deterministic"
    assert result.recommendations == expected.recommendations
    assert result.fallback_reason
    assert "provider-internal" not in result.fallback_reason


async def test_valid_model_can_only_reorder(settings, recommendations):
    settings.llm_endpoint, settings.llm_model, settings.llm_api_key = (
        "https://model.example.invalid/chat",
        "test",
        "test",
    )
    snapshots = [r.model_dump() for r in recommendations]

    def respond(request):
        body = json.loads(request.content)
        data = json.loads(body["messages"][1]["content"])
        assert "customer_id" not in data
        assert "cust-dining" not in request.content.decode()
        assert body["store"] is False
        choices = [
            {"recommendation_id": c["recommendation_id"], "evidence_ids": [c["evidence_ids"][0]]}
            for c in reversed(data["candidates"])
        ]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"choices": choices})}}]})

    result = await LLMRankingAI(settings, httpx.MockTransport(respond)).rank_recommendations(
        recommendations, ["fine dining"]
    )
    assert result.mode == "llm"
    assert [r.model_dump() for r in result.recommendations] == list(reversed(snapshots))


async def test_missing_model_configuration(settings, recommendations):
    result = await LLMRankingAI(settings).rank_recommendations(recommendations, [])
    assert result.mode == "deterministic"
    assert "incomplete" in result.fallback_reason


async def test_consent_change_during_ai_abstains(repository, settings):
    class ChangingAI:
        async def rank_recommendations(self, recommendations, preferences):
            customer = repository.customer("cust-dining")
            customer.consent.allowed = False
            repository.save_customer(customer)
            return await DeterministicAI().rank_recommendations(recommendations, preferences)

    service = GraphFactory.create(repository, settings, ChangingAI())
    intent = service.intent_engine.detect("cust-dining")
    experience = await service.run("cust-dining", intent.intent_id)
    assert experience.status == "abstained"
    assert not experience.recommended_cards


async def test_preference_change_during_ai_abstains(repository, settings):
    class ChangingAI:
        async def rank_recommendations(self, recommendations, preferences):
            CustomerService(repository).remove("cust-dining", "fine dining")
            return await DeterministicAI().rank_recommendations(recommendations, preferences)

    service = GraphFactory.create(repository, settings, ChangingAI())
    intent = service.intent_engine.detect("cust-dining")
    assert (await service.run("cust-dining", intent.intent_id)).status == "abstained"
