"""Decimal math and conservative aggregation, entirely outside the AI boundary."""

from decimal import ROUND_HALF_UP, Decimal

from agent.domain import (
    Benefit,
    CatalogItem,
    MembershipRewardOpportunity,
    Offer,
    Recommendation,
    ValueBreakdown,
    ValueSummary,
)


def calculate(item: CatalogItem, product_id: str) -> ValueBreakdown | None:
    if isinstance(item, (Benefit, Offer)):
        if item.value_type == "experiential":
            return None
        if item.value_amount is None or item.currency is None:
            return None
        amount = item.value_amount
        rule = "mock_catalog_fixed_amount"
        value_type = "savings"
    elif isinstance(item, MembershipRewardOpportunity):
        if item.value_per_point is None or item.currency is None:
            return None
        amount = Decimal(item.points) * item.value_per_point
        rule = f"{item.points} mock points × {item.value_per_point} {item.currency}/point"
        value_type = "rewards"
    else:
        return None
    return ValueBreakdown(
        source_id=item.item_id,
        product_id=product_id,
        value_type=value_type,
        amount=amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        currency=item.currency,
        calculation_rule=rule,
        assumptions=item.conditions,
    )


class ValueCalculationService:
    def apply(
        self, recommendations: list[Recommendation], items: dict[str, CatalogItem]
    ) -> tuple[list[Recommendation], list[ValueSummary]]:
        valid = []
        by_product: dict[str, list[ValueBreakdown]] = {}
        for rec in recommendations:
            item = items[rec.recommendation_id.removeprefix("rec:")]
            requires_value = (
                isinstance(item, (Offer, MembershipRewardOpportunity))
                or isinstance(item, Benefit)
                and item.value_type == "savings"
            )
            rec.value = [value for p in rec.product_ids if (value := calculate(item, p)) is not None]
            # A monetary claim without a verifiable calculation is excluded, not displayed as zero.
            if requires_value and not rec.value:
                continue
            valid.append(rec)
            if item.kind == "card":
                by_product.setdefault(item.product_id, [])
            for value in rec.value:
                by_product.setdefault(value.product_id, []).append(value)
        summaries = []
        for product_id, values in sorted(by_product.items()):
            winners: dict[tuple[str, str], ValueBreakdown] = {}
            for value in values:
                item = items[value.source_id]
                if not item.stackable or not item.stacking_group:
                    value.exclusion_reason = "Stacking is unspecified; shown separately, excluded from total."
                    continue
                key = (value.currency, item.stacking_group)
                current = winners.get(key)
                if current is None or value.amount > current.amount:
                    winners[key] = value
            totals: dict[str, Decimal] = {}
            for value in values:
                item = items[value.source_id]
                if winners.get((value.currency, item.stacking_group)) is value:
                    value.included_in_total = True
                    totals[value.currency] = totals.get(value.currency, Decimal(0)) + value.amount
                elif value.exclusion_reason is None:
                    value.exclusion_reason = (
                        f"Alternative within {item.stacking_group}; only the highest value is counted."
                    )
            summaries.append(ValueSummary(product_id=product_id, totals_by_currency=totals, breakdown=values))
        return valid, summaries
