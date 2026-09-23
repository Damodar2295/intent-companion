from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from agent.outing.models import Alternative, Location, Stop
from agent.outing.providers import ProviderError
from agent.outing.value import aggregate


def is_open(entity, arrival, departure):
    """Google weekly periods. Missing/stale hours return unknown, never confirmed open."""
    if entity.facts.get("business_status") in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"}:
        return False
    periods = entity.facts.get("opening_hours")
    if not periods:
        return None
    day = (arrival.weekday() + 1) % 7
    begin = day * 1440 + arrival.hour * 60 + arrival.minute
    finish = begin + (departure - arrival).total_seconds() / 60
    for period in periods:
        opened, closed = period.get("open", {}), period.get("close")
        if opened.get("day") == 0 and opened.get("hour", 0) == 0 and not closed:
            return True
        if not closed:
            continue
        start = opened.get("day", -10) * 1440 + opened.get("hour", 0) * 60 + opened.get("minute", 0)
        end = closed.get("day", -10) * 1440 + closed.get("hour", 0) * 60 + closed.get("minute", 0)
        if end <= start:
            end += 7 * 1440
        if any(start <= begin + offset and finish + offset <= end for offset in (0, 7 * 1440)):
            return True
    return False


def score(entity, plan, weights, travel_seconds=None):
    name = entity.canonical_name.casefold()
    preferences = any(p.casefold() in name or p.casefold() in entity.entity_type.casefold() for p in plan.preferences)
    signals = {
        "relevance": float(entity.entity_type in plan.categories),
        "preferences": float(preferences),
        "evidence": sum(entity.confidence.values()) / max(len(entity.confidence), 1),
        "travel": 0 if travel_seconds is None else max(0, 1 - travel_seconds / 3600),
        "budget": 0,
        "value": float(any(m.eligible for m in entity.amex_matches)),
    }
    price = entity.facts.get("price")
    if price and plan.budget and price.get("currency") == plan.currency:
        signals["budget"] = float(Decimal(str(price["amount"])) * plan.number_of_people <= plan.budget)
    return round(sum(signals[key] * weight for key, weight in weights.items()), 4)


async def schedule(entities, plan, request, router, settings, warnings, completed=None):
    entities = [
        e
        for e in entities
        if e.verification_status != "UNVERIFIED"
        and e.facts.get("event_status") not in {"cancelled", "canceled", "postponed", "rescheduled"}
    ]
    entities.sort(key=lambda e: (-score(e, plan, settings.weights), e.entity_id))
    # Bound planning calls as well as provider discovery. Each alternative evaluates up to eight candidates.
    entities = entities[:8]
    zone = ZoneInfo(plan.timezone)
    begin = datetime.combine(plan.date, plan.start_time, zone)
    deadline = datetime.combine(plan.date, plan.end_time, zone)
    alternatives, signatures = [], set()
    for offset in range(min(3, len(entities))):
        stops, legs, complete = [], [], True
        cursor, origin, origin_id = begin, plan.user_location, "user-origin"
        spent = Decimal(0)
        remaining = list(entities)
        while remaining and len(stops) < 4:
            options = []
            failed_route = False
            for entity in remaining:
                arrival, leg = cursor, None
                destination = Location.model_validate(entity.facts["location"])
                if origin:
                    try:
                        leg = await router.route(
                            origin, destination, cursor, plan.travel_mode, origin_id, entity.entity_id
                        )
                        arrival += timedelta(seconds=leg.duration_seconds)
                    except ProviderError as exc:
                        warnings.append(str(exc))
                        failed_route = True
                        continue
                departure = arrival + timedelta(minutes=request.visit_minutes)
                wait = 0
                if entity.entity_type == "EVENT":
                    event_start = datetime.fromisoformat(str(entity.facts["schedule.start"])).astimezone(zone)
                    event_end = (
                        datetime.fromisoformat(str(entity.facts["schedule.end"])).astimezone(zone)
                        if "schedule.end" in entity.facts
                        else event_start + timedelta(minutes=request.visit_minutes)
                    )
                    if event_start < arrival or event_end <= event_start:
                        continue
                    wait = (event_start - arrival).total_seconds()
                    arrival, departure = event_start, event_end
                opened = True if entity.entity_type == "EVENT" else is_open(entity, arrival, departure)
                if departure > deadline or opened is False:
                    continue
                price = entity.facts.get("price")
                cost = Decimal(0)
                known_price = bool(price and price.get("currency") == plan.currency and price.get("amount") is not None)
                if known_price:
                    cost = Decimal(str(price["amount"])) * plan.number_of_people
                    if plan.budget and spent + cost > plan.budget:
                        continue
                precise = bool(known_price and price.get("kind") != "advertised_from" and opened is not None)
                if entity.entity_type == "EVENT" and "schedule.end" not in entity.facts:
                    precise = False
                    warnings.append("An event end time is unknown; its visit duration is a planning assumption.")
                strength = score(entity, plan, settings.weights, (leg.duration_seconds if leg else 0) + wait)
                options.append((strength, entity, arrival, departure, leg, cost, precise, opened))
            if not options:
                if failed_route:
                    complete = False
                break
            options.sort(key=lambda row: (-row[0], row[2], row[1].entity_id))
            chosen = options[min(offset, len(options) - 1)] if not stops else options[0]
            strength, entity, arrival, departure, leg, cost, precise, opened = chosen
            if not precise:
                complete = False
                warnings.append(
                    "Prices may be unknown, in another currency, or advertised minimums; total budget feasibility is incomplete."
                )
            if opened is None:
                warnings.append("Some opening hours are unknown. These stops are provisional; confirm with the venue.")
            ids = [
                e.evidence_id
                for e in entity.sources
                if e.field in entity.facts
                and e.value == entity.facts[e.field]
                and e.retrieved_at <= settings.now() < e.expires_at
                and e.confidence >= 0.8
            ]
            stops.append(
                Stop(
                    entity=entity.model_copy(deep=True),
                    arrival=arrival,
                    departure=departure,
                    duration_assumed=entity.entity_type != "EVENT" or "schedule.end" not in entity.facts,
                    explanation="Selected for your requested activity mix.",
                    evidence_ids=ids,
                    score=strength,
                )
            )
            if leg:
                legs.append(leg)
            cursor, origin, origin_id = departure, Location.model_validate(entity.facts["location"]), entity.entity_id
            spent += cost
            remaining.remove(entity)
        signature = tuple(s.entity.entity_id for s in stops)
        if not stops or signature in signatures:
            continue
        signatures.add(signature)
        totals, points = aggregate(stops)
        alternatives.append(
            Alternative(
                stops=stops,
                routes=legs,
                totals_by_currency=totals,
                reward_points=points,
                feasibility="CHECKED" if complete else "INCOMPLETE",
            )
        )
        if completed is not None:
            completed[:] = alternatives
    return alternatives
