import json
from datetime import timedelta
from decimal import Decimal

import pytest

from agent.customer_context import CustomerService
from agent.domain import Benefit, MembershipRewardOpportunity
from agent.repositories import NotFound
from agent.value_calculation import calculate


def all_recs(experience):
    return (
        experience.recommended_cards
        + experience.benefits
        + experience.offers
        + experience.rewards
        + experience.merchants
    )


def update_catalog(repository, item_id, **changes):
    row = repository.db.execute("SELECT data FROM catalog WHERE id=?", (item_id,)).fetchone()
    data = json.loads(row[0]) | changes
    with repository.db:
        repository.db.execute("UPDATE catalog SET data=? WHERE id=?", (json.dumps(data), item_id))


async def generate(service, customer="cust-dining"):
    intent = service.intent_engine.detect(customer)
    return await service.run(customer, intent.intent_id)


@pytest.mark.parametrize(
    "customer,card,total",
    [("cust-prospect", "card-a", "60.00"), ("cust-dining", "card-a", "60.00"), ("cust-stay", "card-b", "135.00")],
)
async def test_three_journeys(service, repository, customer, card, total):
    result = await generate(service, customer)
    assert result.status == "ready"
    assert result.provider_mode == "deterministic"
    assert result.recommended_cards[0].product_ids == [card]
    assert result.value_summary[0].totals_by_currency["USD"] == Decimal(total)
    assert repository.db.execute("SELECT COUNT(*) FROM experiences").fetchone()[0] == 1
    held = repository.customer(customer).existing_cards
    if held:
        assert all(set(rec.product_ids) <= set(held) for rec in all_recs(result))
    else:
        assert "Contextually relevant" in result.summary
        for phrase in ["you are approved", "preapproved", "eligible for credit", "guaranteed savings"]:
            assert phrase not in result.summary.lower()


async def test_profiles_meaningfully_differ(service):
    dining, shopping = await generate(service), await generate(service, "cust-stay")
    assert dining.recommended_cards[0].title != shopping.recommended_cards[0].title
    assert {r.recommendation_id for r in dining.benefits}.isdisjoint({r.recommendation_id for r in shopping.benefits})
    assert {r.recommendation_id for r in dining.merchants}.isdisjoint({r.recommendation_id for r in shopping.merchants})


async def test_all_evidence_and_values_resolve(service, repository):
    result = await generate(service)
    catalog = {i.item_id: i for i in repository.catalog("US", "consumer", "Rome")}
    for rec in all_recs(result):
        assert rec.evidence
        assert set(rec.source_ids) <= set(catalog)
        assert any(e.type == "rule" for e in rec.evidence)
        assert any(e.type == "catalog" for e in rec.evidence)
        for value in rec.value:
            assert value.source_id in rec.source_ids
            expected = calculate(catalog[value.source_id], value.product_id)
            assert expected.amount == value.amount
    for summary in result.value_summary:
        counted = [v for v in summary.breakdown if v.included_in_total]
        assert len({v.source_id for v in counted}) == len(counted)
        assert summary.totals_by_currency["USD"] == sum(v.amount for v in counted)


async def test_old_intent_rechecks_removed_preferences(service, repository):
    intent = service.intent_engine.detect("cust-dining")
    before = await service.run("cust-dining", intent.intent_id)
    CustomerService(repository).remove("cust-dining", "fine dining")
    after = await service.run("cust-dining", intent.intent_id)
    assert before.benefits != after.benefits
    assert after.preferences_used == ["museums"]
    assert not any(e.type == "preference" and e.source_id == "fine dining" for r in all_recs(after) for e in r.evidence)
    assert after.value_summary[0].totals_by_currency["USD"] == Decimal("20.00")


@pytest.mark.parametrize("condition", ["consent", "expiry", "unknown_card", "no_matches", "stale_all"])
async def test_safe_abstention(service, repository, settings, condition):
    intent = service.intent_engine.detect("cust-dining")
    customer = repository.customer("cust-dining")
    if condition == "consent":
        customer.consent.allowed = False
        repository.save_customer(customer)
    elif condition == "expiry":
        settings.demo_now = intent.expires_at
    elif condition == "unknown_card":
        customer.existing_cards = ["unknown"]
        repository.save_customer(customer)
    elif condition == "no_matches":
        CustomerService(repository).replace(customer.customer_id, [])
    else:
        for item in repository.catalog("US", "consumer", "Rome"):
            update_catalog(repository, item.item_id, last_verified="2020-01-01")
    result = await service.run(customer.customer_id, intent.intent_id)
    assert result.status == "abstained"
    assert not all_recs(result)
    assert not result.value_summary
    assert not result.preferences_used
    assert result.abstention_reasons


@pytest.mark.parametrize(
    "changes",
    [
        {"last_verified": "2020-01-01"},
        {"valid_to": "2026-10-11"},
        {"valid_from": "2026-10-01"},
        {"last_verified": "2026-12-01"},
        {"source": ""},
        {"value_amount": None},
        {"currency": None},
    ],
)
async def test_invalid_catalog_item_excluded(service, repository, changes):
    update_catalog(repository, "benefit-01", **changes)
    result = await generate(service)
    assert "rec:benefit-01" not in {r.recommendation_id for r in result.benefits}


async def test_merchant_dependency_freshness(service, repository):
    update_catalog(repository, "merchant-01", last_verified="2020-01-01")
    result = await generate(service)
    assert "rec:offer-01" not in {r.recommendation_id for r in result.offers}
    assert "rec:merchant-01" not in {r.recommendation_id for r in result.merchants}


async def test_product_dependency_freshness(service, repository):
    update_catalog(repository, "card-a", last_verified="2020-01-01")
    result = await generate(service)
    assert all("card-a" not in rec.product_ids for rec in all_recs(result))


async def test_merchant_acceptance_filter(service, repository):
    update_catalog(repository, "merchant-01", accepting_products=["card-c"])
    result = await generate(service)
    assert "rec:offer-01" not in {r.recommendation_id for r in result.offers}


async def test_market_filter(service, repository):
    customer = repository.customer("cust-dining")
    customer.market = "XX"
    repository.save_customer(customer)
    assert (await generate(service)).status == "abstained"


async def test_intent_ownership(service):
    intent = service.intent_engine.detect("cust-dining")
    with pytest.raises(NotFound):
        await service.run("cust-stay", intent.intent_id)


def test_experiential_not_valued(repository):
    benefit = next(
        i
        for i in repository.catalog("US", "consumer", "Rome")
        if isinstance(i, Benefit) and i.value_type == "experiential"
    )
    assert calculate(benefit, benefit.product_id) is None


def test_decimal_reward_calculation(repository):
    reward = next(i for i in repository.catalog("US", "consumer", "Rome") if isinstance(i, MembershipRewardOpportunity))
    reward.points, reward.value_per_point = 333, Decimal("0.015")
    assert calculate(reward, reward.product_id).amount == Decimal("5.00")


async def test_currency_separation_and_unspecified_stacking(service, repository):
    update_catalog(repository, "benefit-01", currency="EUR")
    update_catalog(repository, "offer-01", stackable=False, stacking_group=None)
    result = await generate(service)
    summary = next(v for v in result.value_summary if v.product_id == "card-a")
    assert summary.totals_by_currency == {"EUR": Decimal("40.00"), "USD": Decimal("50.00")}
    offer = next(v for v in summary.breakdown if v.source_id == "offer-01")
    assert not offer.included_in_total
    assert "unspecified" in offer.exclusion_reason


async def test_signal_revoked_after_detection(service, repository):
    intent = service.intent_engine.detect("cust-dining")
    signal = repository.signals("cust-dining")[0]
    signal.consent.allowed = False
    with repository.db:
        repository.db.execute("UPDATE signals SET data=? WHERE id=?", (signal.model_dump_json(), signal.event_id))
    assert (await service.run("cust-dining", intent.intent_id)).status == "abstained"


async def test_signal_expires_after_detection(service, settings):
    intent = service.intent_engine.detect("cust-dining")
    settings.demo_now += timedelta(days=31)
    assert (await service.run("cust-dining", intent.intent_id)).status == "abstained"


def test_catalog_minimums(repository):
    catalog = repository.catalog("US", "consumer", "Rome")
    for kind, count in {"card": 3, "benefit": 8, "offer": 5, "reward": 5, "merchant": 8}.items():
        assert sum(item.kind == kind for item in catalog) >= count
