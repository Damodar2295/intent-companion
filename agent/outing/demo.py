"""Deterministic, visibly fictional adapters; never used as realtime fallback."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agent.outing.models import DiscoveryCandidate, RouteLeg, SearchPlan
from agent.outing.providers import ProviderError
from agent.outing.verification import evidence


class Demo:
    def __init__(self, settings):
        self.settings = settings

    async def interpret(self, request, preferences):
        words = request.text.lower()
        categories = [
            category
            for category, terms in {
                "EVENT": ["event", "party", "concert"],
                "DINING": ["dining", "restaurant", "dinner", "food"],
                "SHOPPING": ["shop"],
                "CULTURE": ["museum", "culture", "gallery"],
                "ATTRACTION": ["explore", "sight"],
                "EXPERIENCE": ["experience"],
            }.items()
            if any(term in words for term in terms)
        ]
        return SearchPlan(
            **request.model_dump(include=set(SearchPlan.model_fields)),
            categories=categories or ["DINING", "CULTURE"],
            preferences=preferences,
        )

    async def search(self, plan):
        if plan.city.casefold().strip() not in {"rome", "roma"}:
            raise ProviderError("The offline demonstration supports Rome. Select realtime mode for other destinations.")
        now = self.settings.now()
        rows = [
            ("dinner", "Terrazza Lume", "DINING", "merchant-01"),
            ("gallery", "Atelier delle Arti", "CULTURE", "merchant-02"),
            ("shop", "Via Illustrativa Boutique", "SHOPPING", None),
            ("concert", "Illustrative Roman Evening Concert", "EVENT", None),
            ("walk", "Illustrative Riverside Walk", "ATTRACTION", None),
        ]
        result = []
        for index, (identity, name, category, merchant) in enumerate(rows):
            if category not in plan.categories:
                continue
            fields = {
                "name": name,
                "address": f"{index + 1} Fictional Demo Street, Rome",
                "location": {"lat": 41.90 + index * 0.001, "lng": 12.48 + index * 0.001},
                "opening_hours": [{"open": {"day": 0, "hour": 0}}],
                "business_status": "OPERATIONAL",
            }
            if merchant:
                fields["demo_merchant_id"] = merchant
            if category == "EVENT":
                start = datetime.combine(plan.date, plan.start_time, ZoneInfo(plan.timezone)) + timedelta(hours=3)
                fields.update(
                    {
                        "schedule.start": start.isoformat(),
                        "schedule.end": (start + timedelta(hours=1)).isoformat(),
                        "event_status": "onsale",
                    }
                )
            url = f"demo:outing/{identity}"
            result.append(
                DiscoveryCandidate(
                    candidate_id=f"demo:{identity}",
                    name=name,
                    category=category,
                    provider="demo",
                    url=url,
                    evidence=[
                        evidence("demo", key, value, url, "DEMO", now, self.settings, True)
                        for key, value in fields.items()
                    ],
                )
            )
        return result

    async def route(self, origin, destination, departure, mode, origin_id, destination_id):
        now = self.settings.now()
        return RouteLeg(
            origin_id=origin_id,
            destination_id=destination_id,
            duration_seconds=600,
            distance_meters=700,
            provider="demo",
            retrieved_at=now,
            expires_at=now + timedelta(minutes=5),
            synthetic=True,
        )

    async def explain(self, facts):
        return {f["entity_id"]: "Selected for your requested activity mix." for f in facts}
