"""Reuse configured provider adapters; no synthetic fallback in realtime."""

from agent.tools.service import ToolBinding


def build_tools(repository, settings, http):
    from agent.outing.demo import Demo
    from agent.outing.live import Brave, Events, Places
    from agent.providers.catalog import SQLiteCatalogProvider, UnavailableAmexExperienceProvider

    bindings = {}
    if settings.demo:
        demo = Demo(settings)

        async def places(plan):
            plan.categories = [category for category in plan.categories if category != "EVENT"]
            return await demo.search(plan)

        async def events(plan):
            plan.categories = ["EVENT"]
            return await demo.search(plan)

        # No pretend web search in demo. Existing fixtures cover offline event discovery.
        bindings.update(places=ToolBinding(places, True), events=ToolBinding(events, True))
    else:
        for name, provider, enabled in (
            ("places", Places(http, settings), settings.places_key),
            ("events", Events(http, settings), settings.event_key),
            ("web", Brave(http, settings), settings.search_key),
        ):
            if enabled:
                bindings[name] = ToolBinding(provider.search, True)
    catalog = SQLiteCatalogProvider(repository)
    for name in ("cards", "benefits", "offers", "rewards", "merchants"):
        bindings[name] = ToolBinding(getattr(catalog, name), False)
    bindings["amex_experiences"] = ToolBinding(UnavailableAmexExperienceProvider().search, True)
    return bindings
