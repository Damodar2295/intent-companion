from fastapi import APIRouter


def provider_routes(app):
    router = APIRouter(prefix="/api/v1/providers", tags=["Providers v1"])

    @router.get("/capabilities")
    async def provider_capabilities():
        settings = app.state.outing.settings
        return {
            "mode": "demo" if settings.demo else "realtime",
            "providers": {
                "web_discovery": {
                    "provider": "brave",
                    "configured": settings.demo or bool(settings.search_key),
                    "role": "discovery_only",
                },
                "events": {
                    "provider": "ticketmaster",
                    "configured": settings.demo or bool(settings.event_key),
                    "role": "structured_event_discovery",
                },
                "places": {
                    "provider": "google_places",
                    "configured": settings.demo or bool(settings.places_key),
                    "role": "places_and_coordinates",
                },
                "routing": {
                    "provider": "google_routes",
                    "configured": settings.demo or bool(settings.routing_key),
                    "role": "travel_estimates",
                },
                "amex_experiences": {
                    "provider": "synthetic_catalog",
                    "configured": False,
                    "role": "unavailable_inventory",
                },
            },
            "freshness_seconds": dict(settings.ttl),
            "source_priority": dict(settings.source_priority),
            "storage_policy": "Provider payloads are not persistently cached by this capability endpoint.",
            "secrets_exposed": False,
        }

    return router
