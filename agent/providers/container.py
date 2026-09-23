"""Composition root: only this boundary selects concrete provider implementations."""

from dataclasses import dataclass

from agent.llm.adapters import ChatCompletionsAdapter, MockLLMAdapter, ResponsesAdapter
from agent.llm.contracts import ModelRoute
from agent.llm.gateway import LLMGateway
from agent.llm.router import OPERATIONS, ModelRouter


def build_gateway(settings, outing_settings=None, http=None, transport=None, mock_handlers=None):
    mode = settings.llm_gateway_mode
    if mode not in {"configured", "mock"}:
        raise ValueError("Selected enterprise LLM adapter is unavailable; supply an internal adapter at composition")
    routes = {name: ModelRoute("chat", settings.llm_model, capability) for name, capability in OPERATIONS.items()}
    adapters = {"chat": ChatCompletionsAdapter(settings, transport), "mock": MockLLMAdapter(mock_handlers)}
    if outing_settings is not None:
        for name in ("search.plan_generation", "search.requirements_generation", "recommendation.explanation"):
            routes[name] = ModelRoute("responses", outing_settings.model, OPERATIONS[name])
        adapters["responses"] = ResponsesAdapter(http, outing_settings)
    from agent.search.service import OPERATION, mock_plan, planner_mode

    if planner_mode(settings, outing_settings) == "mock":
        routes[OPERATION] = ModelRoute("mock", "fixture", "lightweight")
        adapters["mock"].handlers.setdefault(OPERATION, mock_plan)
    for operation, override in settings.llm_routes.items():
        if operation not in routes or set(override) - {"adapter", "model", "model_class"}:
            raise ValueError("Invalid operation route configuration")
        current = routes[operation]
        routes[operation] = ModelRoute(
            override.get("adapter", current.adapter),
            override.get("model", current.model),
            override.get("model_class", current.model_class),
        )
        if routes[operation].adapter not in adapters:
            raise ValueError("Selected model adapter is unavailable; no implicit fallback")
    if settings.intent_extraction_mode == "mock":
        from agent.intent_extraction import quote_candidates

        routes["intent.entity_extraction"] = ModelRoute("mock", "fixture", "lightweight")
        adapters["mock"].handlers.setdefault(
            "intent.entity_extraction", lambda req: quote_candidates(req.messages[-1]["content"]).model_dump()
        )
    if mode == "mock":
        routes = {key: ModelRoute("mock", "mock", route.model_class) for key, route in routes.items()}
    if (routes[OPERATION].adapter == "mock") != (planner_mode(settings, outing_settings) == "mock"):
        raise ValueError("Search operation route contradicts SEARCH_PLAN_MODE; select mock or llm explicitly")
    return LLMGateway(ModelRouter(routes), adapters, outing_settings.price_table if outing_settings else None)


@dataclass
class OutingDependencies:
    llm: object
    discovery: list
    router: object
    http: object
    catalog: object
    experiences: object


def build_outing(repository, settings, gateway=None, http=None):
    from agent.outing.demo import Demo
    from agent.outing.live import Brave, Events, Places, Routes
    from agent.outing.llm import OutingLanguageService
    from agent.outing.providers import Transport
    from agent.providers.catalog import SQLiteCatalogProvider, UnavailableAmexExperienceProvider
    from config.settings import Settings

    http = http or Transport(settings)
    gateway = gateway or build_gateway(Settings(), settings, http)
    demo = Demo(settings)
    return OutingDependencies(
        demo if settings.demo else OutingLanguageService(http, settings, gateway),
        [demo] if settings.demo else [Places(http, settings), Events(http, settings), Brave(http, settings)],
        demo if settings.demo else Routes(http, settings),
        http,
        SQLiteCatalogProvider(repository),
        UnavailableAmexExperienceProvider(),
    )


def build_intent_extractor(settings, gateway):
    from agent.intent_extraction import IntentExtractor

    if settings.intent_extraction_mode == "deterministic":
        return IntentExtractor()
    return IntentExtractor(gateway, settings.intent_extraction_mode)
