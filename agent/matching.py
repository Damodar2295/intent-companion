"""Retrieve structured candidates, then filter before any model sees them."""

from dataclasses import dataclass
from datetime import timedelta

from agent.domain import (
    Benefit,
    CardProduct,
    CatalogItem,
    CustomerContext,
    Evidence,
    IntentContext,
    MembershipRewardOpportunity,
    Merchant,
    Offer,
    Recommendation,
)
from agent.repositories import Abstain, Repository
from config.settings import Settings


@dataclass
class MatchResult:
    recommendations: list[Recommendation]
    items: dict[str, CatalogItem]
    retrieved_count: int
    excluded_count: int


class MatchingEngine:
    def __init__(self, repository: Repository, settings: Settings):
        self.repository = repository
        self.settings = settings

    def fresh(self, item: CatalogItem, intent: IntentContext) -> bool:
        today = self.settings.now().date()
        return bool(
            item.source
            and item.valid_from <= today <= item.valid_to
            and item.valid_from <= intent.start_date <= intent.end_date <= item.valid_to
            and today - timedelta(days=self.settings.catalog_ttl_days) <= item.last_verified <= today
        )

    def match(self, customer: CustomerContext, intent: IntentContext) -> MatchResult:
        catalog = self.repository.catalog(customer.market, customer.segment, intent.destination)
        all_cards = {i.product_id for i in catalog if isinstance(i, CardProduct)}
        if customer.lifecycle_stage == "member" and (
            not customer.existing_cards or set(customer.existing_cards) - all_cards
        ):
            raise Abstain("A held card is unknown or unavailable for this market.")
        if customer.lifecycle_stage == "prospect" and customer.existing_cards:
            raise Abstain("The prospect profile must not contain held cards.")
        fresh = {i.item_id: i for i in catalog if self.fresh(i, intent)}
        cards = {
            i.product_id: i
            for i in fresh.values()
            if isinstance(i, CardProduct)
            and (customer.lifecycle_stage == "prospect" or i.product_id in customer.existing_cards)
        }
        if not cards:
            raise Abstain("No verified card product is available for this scenario.")
        preferences = set(intent.preferences)
        result = []
        selected_items = {}
        for item in fresh.values():
            matching_preferences = preferences.intersection(item.tags)
            if item.kind != "card" and item.tags and not matching_preferences:
                continue
            dependencies: list[CatalogItem] = []
            if isinstance(item, (CardProduct, Benefit, MembershipRewardOpportunity)):
                product_ids = [item.product_id] if item.product_id in cards else []
            elif isinstance(item, Offer):
                merchant = fresh.get(item.merchant_id)
                if (
                    not isinstance(merchant, Merchant)
                    or merchant.city != intent.destination
                    or item.location != intent.destination
                ):
                    continue
                product_ids = sorted(set(item.eligible_products) & set(cards) & set(merchant.accepting_products))
                dependencies.append(merchant)
            else:
                if item.city != intent.destination:
                    continue
                product_ids = sorted(set(item.accepting_products) & set(cards))
            if not product_ids:
                continue
            dependencies.extend(cards[p] for p in product_ids)
            sources = {i.item_id: i for i in [item, *dependencies]}
            evidence = [
                Evidence(
                    evidence_id=f"intent:{intent.intent_id}",
                    type="intent",
                    source_id=intent.intent_id,
                    fact=f"Rome trip, {intent.start_date.isoformat()} to {intent.end_date.isoformat()}.",
                )
            ]
            evidence += [
                Evidence(
                    evidence_id=f"preference:{p}",
                    type="preference",
                    source_id=p,
                    fact=f"Matches your active preference: {p}.",
                )
                for p in sorted(matching_preferences)
            ]
            evidence += [
                Evidence(
                    evidence_id=f"catalog:{i.item_id}",
                    type="catalog",
                    source_id=i.item_id,
                    fact=f"{i.title}. Source {i.source}; verified {i.last_verified}; {i.catalog_version}.",
                )
                for i in sources.values()
            ]
            rule = (
                "Held-card applicability checked against the synthetic catalog."
                if customer.lifecycle_stage == "member"
                else "Contextual product illustration only; not a credit eligibility assessment."
            )
            evidence.append(
                Evidence(
                    evidence_id=f"rule:{item.item_id}",
                    type="rule",
                    source_id=item.item_id,
                    fact=f"{rule} Market, location, trip validity and freshness checks passed.",
                )
            )
            explanation = (
                "Selected for " + ", ".join(sorted(matching_preferences)) + ". "
                if matching_preferences
                else "Relevant to your Rome travel context. "
            ) + rule
            result.append(
                Recommendation(
                    recommendation_id=f"rec:{item.item_id}",
                    recommendation_type=item.kind,
                    title=item.title,
                    description=item.description,
                    category=item.category,
                    product_ids=product_ids,
                    relevance_score=round(min(1, 0.2 + 0.3 * len(matching_preferences)), 2),
                    evidence=evidence,
                    source_ids=sorted(sources),
                    conditions=item.conditions,
                    explanation=explanation,
                )
            )
            selected_items[item.item_id] = item
        if not any(r.recommendation_type != "card" for r in result):
            raise Abstain("No verified recommendation is available for this scenario.")
        return MatchResult(result, selected_items, len(catalog), len(catalog) - len(result))
