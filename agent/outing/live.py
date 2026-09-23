from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from agent.outing.models import DiscoveryCandidate, RouteLeg
from agent.outing.providers import ProviderError
from agent.outing.verification import evidence


class Places:
    fields = "id,displayName,formattedAddress,location,businessStatus,websiteUri,regularOpeningHours,googleMapsUri"

    def __init__(self, http, settings):
        self.http, self.settings = http, settings

    def candidate(self, place, category):
        if not isinstance(place.get("id"), str):
            raise ProviderError("Place identity missing")
        url = place.get("googleMapsUri", "https://maps.google.com/")
        fields = {
            "name": place.get("displayName", {}).get("text"),
            "address": place.get("formattedAddress"),
            "place_id": place["id"],
            "business_status": place.get("businessStatus"),
            "website": place.get("websiteUri"),
        }
        loc = place.get("location", {})
        if "latitude" in loc and "longitude" in loc:
            fields["location"] = {"lat": loc["latitude"], "lng": loc["longitude"]}
        hours = place.get("regularOpeningHours", {}).get("periods")
        if hours:
            fields["opening_hours"] = hours
        ev = [
            evidence("google_places", k, v, url, "PLACES_API", self.settings.now(), self.settings)
            for k, v in fields.items()
            if v is not None
        ]
        return DiscoveryCandidate(
            candidate_id="google:" + place["id"],
            name=fields["name"] or "Place",
            category=category,
            provider="google_places",
            url=url,
            evidence=ev,
            official_urls=[fields["website"]] if fields.get("website") else [],
        )

    async def get_details(self, place_id, category):
        from urllib.parse import quote

        raw = await self.http.json(
            "google_places",
            "GET",
            "https://places.googleapis.com/v1/places/" + quote(place_id, safe=""),
            headers={"X-Goog-Api-Key": self.settings.places_key, "X-Goog-FieldMask": self.fields},
        )
        return self.candidate(raw, category)

    async def search(self, plan):
        if not self.settings.places_key:
            raise ProviderError("Places is not configured; location verification is limited")
        results = []
        names = {
            "DINING": "restaurants",
            "SHOPPING": "shops",
            "CULTURE": "museums",
            "ATTRACTION": "attractions",
            "EXPERIENCE": "things to do",
        }
        for category in plan.categories:
            if category == "EVENT":
                continue
            raw = await self.http.json(
                "google_places",
                "POST",
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "X-Goog-Api-Key": self.settings.places_key,
                    "X-Goog-FieldMask": ",".join("places." + f for f in self.fields.split(",")),
                },
                json={"textQuery": f"{names[category]} in {plan.city}", "pageSize": 5},
            )
            for item in raw.get("places", []):
                results.append(self.candidate(item, category))
        return results


class Events:
    def __init__(self, http, settings):
        self.http, self.settings = http, settings

    async def search(self, plan):
        if "EVENT" not in plan.categories and "CULTURE" not in plan.categories:
            return []
        if not self.settings.event_key:
            raise ProviderError("Event search is not configured")
        start = datetime.combine(plan.date, plan.start_time, ZoneInfo(plan.timezone)).astimezone(UTC)
        end = datetime.combine(plan.date, plan.end_time, ZoneInfo(plan.timezone)).astimezone(UTC)
        raw = await self.http.json(
            "ticketmaster",
            "GET",
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params={
                "apikey": self.settings.event_key,
                "city": plan.city,
                "size": 10,
                "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        results = []
        for event in raw.get("_embedded", {}).get("events", []):
            venues = event.get("_embedded", {}).get("venues", [])
            if not venues:
                continue
            venue = venues[0]
            loc = venue.get("location", {})
            dates = event.get("dates", {})
            fields = {
                "name": event.get("name"),
                "schedule.start": dates.get("start", {}).get("dateTime"),
                "schedule.end": dates.get("end", {}).get("dateTime"),
                "event_status": dates.get("status", {}).get("code"),
                "address": venue.get("address", {}).get("line1"),
                "venue_id": venue.get("id"),
                "ticket_url": event.get("url"),
            }
            if loc.get("latitude") and loc.get("longitude"):
                fields["location"] = {"lat": float(loc["latitude"]), "lng": float(loc["longitude"])}
            prices = event.get("priceRanges", [])
            if prices:
                fields["price"] = {
                    "amount": prices[0].get("min"),
                    "currency": prices[0].get("currency"),
                    "kind": "advertised_from",
                }
            url = event.get("url", "https://www.ticketmaster.com/")
            results.append(
                DiscoveryCandidate(
                    candidate_id="ticketmaster:" + event["id"],
                    name=event["name"],
                    category="EVENT",
                    provider="ticketmaster",
                    url=url,
                    evidence=[
                        evidence("ticketmaster", k, v, url, "TICKETING_API", self.settings.now(), self.settings)
                        for k, v in fields.items()
                        if v is not None
                    ],
                )
            )
        return results


class Brave:
    def __init__(self, http, settings):
        self.http, self.settings = http, settings

    async def search(self, plan):
        if not self.settings.search_key:
            raise ProviderError("Web discovery is not configured")
        raw = await self.http.json(
            "brave",
            "GET",
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": self.settings.search_key},
            params={"q": f"{plan.city} {plan.date} exhibitions events things to do", "count": 5},
        )
        # Intentionally no evidence: snippets cannot establish venue facts.
        return [
            DiscoveryCandidate(
                candidate_id="web:" + item["url"],
                name=item["title"],
                category="EVENT",
                provider="brave",
                url=item["url"],
            )
            for item in raw.get("web", {}).get("results", [])
        ]


class Routes:
    def __init__(self, http, settings):
        self.http, self.settings = http, settings

    async def route(self, origin, destination, departure, mode, origin_id, destination_id):
        if not self.settings.routing_key:
            raise ProviderError("Travel times are unavailable: routing is not configured")

        def point(loc):
            return {"location": {"latLng": {"latitude": loc.lat, "longitude": loc.lng}}}

        body = {"origin": point(origin), "destination": point(destination), "travelMode": mode}
        if mode == "TRANSIT" or (mode == "DRIVE" and departure > self.settings.now()):
            body["departureTime"] = departure.astimezone(UTC).isoformat()

        async def fetch():
            raw = await self.http.json(
                "google_routes",
                "POST",
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                headers={
                    "X-Goog-Api-Key": self.settings.routing_key,
                    "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
                },
                json=body,
            )
            try:
                route = raw["routes"][0]
                now = self.settings.now()
                return RouteLeg(
                    origin_id=origin_id,
                    destination_id=destination_id,
                    duration_seconds=round(float(route["duration"].removesuffix("s"))),
                    distance_meters=route["distanceMeters"],
                    provider="google_routes",
                    retrieved_at=now,
                    expires_at=now + timedelta(seconds=300),
                )
            except (KeyError, IndexError, ValueError, TypeError):
                raise ProviderError("No validated route returned") from None

        result = await self.http.cached("route", body, 300, fetch)
        return result.model_copy(update={"origin_id": origin_id, "destination_id": destination_id})
