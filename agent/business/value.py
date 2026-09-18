"""Spend and savings are different measures. Alternatives compete per observation and card."""

from decimal import ROUND_HALF_UP, Decimal

from agent.business.models import BusinessValue


def money(value):
    return value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


def calculate(recommendations, items, intent):
    summary = {
        "observed_spend": Decimal(0),
        "planned_spend": Decimal(0),
        "potential_card_addressable_spend": Decimal(0),
    }
    for observation in intent.spend:
        summary[f"{observation.status}_spend"] += observation.amount
    addressable = set()
    winners = {}
    cap_used = {}
    for rec in recommendations:
        item = items[rec.recommendation_id]
        relevant = [
            s
            for s in intent.spend
            if s.category == item.category and item.valid_from <= s.period_start <= s.period_end <= item.valid_to
        ]
        for spend in relevant:
            if spend.payment_method != "held_card":
                addressable.add(spend.observation_id)
            if item.rule == "informational":
                rec.value_note = "Informational feature only; no monetary value or eligibility decision."
                continue
            if item.rate is None or (item.rule == "points_per_dollar" and item.point_value is None):
                rec.value_note = "Value unavailable: required catalog calculation inputs are missing."
                continue
            if spend.amount < item.minimum_spend:
                rec.value_note = f"Minimum illustrative spend of USD {item.minimum_spend} is not met."
                continue
            points = spend.amount * item.rate if item.rule == "points_per_dollar" else None
            amount = points * item.point_value if points is not None else spend.amount * item.rate
            if item.cap is not None:
                amount = min(amount, item.cap)
            for product in rec.product_ids:
                cap_key = (item.item_id, product)
                capped_amount = amount
                if item.cap is not None:
                    capped_amount = min(amount, max(Decimal(0), item.cap - cap_used.get(cap_key, Decimal(0))))
                    cap_used[cap_key] = cap_used.get(cap_key, Decimal(0)) + capped_amount
                value = BusinessValue(
                    source_id=item.item_id,
                    product_id=product,
                    observation_id=spend.observation_id,
                    amount=money(capped_amount),
                    points=points,
                    value_type="rewards" if points is not None else "savings",
                    calculation_rule=f"{item.rule}: {spend.amount} × {item.rate}"
                    + (f" × {item.point_value} USD/point" if points is not None else "")
                    + (f"; shared cap {item.cap} USD across this goal's observations" if item.cap is not None else ""),
                    period=f"{spend.period_start} to {spend.period_end}",
                    assumptions=[
                        *item.conditions,
                        "Assumes all stated spend qualifies; observed spend is an illustrative equivalent, not a retrospective credit.",
                    ],
                )
                rec.values.append(value)
                if item.stacking_group:
                    key = (product, spend.observation_id, item.stacking_group)
                    if key not in winners or value.amount > winners[key].amount:
                        winners[key] = value
        if not relevant:
            rec.value_note = "No spend input covering this category within catalog validity."
    summary["potential_card_addressable_spend"] = sum(
        (s.amount for s in intent.spend if s.observation_id in addressable), Decimal(0)
    )
    totals = {}
    for rec in recommendations:
        for value in rec.values:
            group = items[value.source_id].stacking_group
            value.included_in_total = winners.get((value.product_id, value.observation_id, group)) is value
            if value.included_in_total:
                product = totals.setdefault(value.product_id, {"savings": Decimal(0), "rewards": Decimal(0)})
                product[value.value_type] += value.amount
            else:
                value.exclusion_reason = (
                    "Alternative for the same spend and stacking group, or stacking is unspecified."
                )
    return summary, totals
