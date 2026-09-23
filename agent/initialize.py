"""Application lifetime: config → storage → seed → factory → ready → close."""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from dotenv import load_dotenv
from fastapi import FastAPI

from agent.business.extraction import DeterministicExtractor, LLMGoalExtractor
from agent.business.service import BusinessService
from agent.business.store import ExtensionStore
from agent.customer_context import CustomerService
from agent.factory import GraphFactory
from agent.intent_service import IntentService
from agent.outing.config import OutingSettings
from agent.outing.providers import Transport
from agent.outing.service import OutingService
from agent.providers.container import build_gateway, build_intent_extractor, build_outing
from agent.repositories import SQLiteRepository
from agent.retrieval.composition import build_ingestion
from config.settings import ROOT, Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(ROOT / ".env", override=False)
    settings = app.state.injected_settings or Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    repository = SQLiteRepository(settings.database_path)
    try:
        repository.seed(settings.fixture_dir)
        app.state.ingestion = build_ingestion(settings)
        from agent.retrieval.hybrid import HybridRetriever
        from agent.retrieval.testing import TestRerankerAdapter

        reranker = TestRerankerAdapter() if settings.reranker_mode == "test_hash" else None
        app.state.retriever = HybridRetriever(
            app.state.ingestion.store, app.state.ingestion.embeddings, settings, reranker
        )
        from agent.context.service import ContextBuilder

        app.state.context_builder = ContextBuilder()
        app.state.settings = settings
        app.state.repository = repository
        outing_settings = OutingSettings.from_env()
        outing_http = Transport(outing_settings)
        app.state.outing_http = outing_http
        gateway = build_gateway(settings, outing_settings, outing_http)
        app.state.llm_gateway = gateway
        app.state.intents = IntentService(repository, settings)
        from agent.search.service import SearchPlanner, planner_mode

        app.state.search_planner = SearchPlanner(
            repository,
            settings,
            gateway,
            app.state.intents,
            planner_mode(settings, outing_settings),
            now=(lambda: datetime.now(UTC)) if outing_settings.realtime else settings.now,
        )
        from agent.tools.composition import build_tools
        from agent.tools.service import ToolOrchestrator

        app.state.tool_orchestrator = ToolOrchestrator(
            repository,
            app.state.search_planner,
            build_tools(repository, outing_settings, outing_http),
            settings,
            "demo" if outing_settings.demo else "realtime",
        )
        app.state.intent_extractor = build_intent_extractor(settings, gateway)
        app.state.companion = GraphFactory.create(repository, settings, gateway=gateway)
        app.state.extensions = ExtensionStore(repository, settings)
        app.state.business = BusinessService(app.state.extensions, settings, app.state.companion.ai)
        app.state.goal_extractor = (
            LLMGoalExtractor(settings, gateway=gateway) if settings.ai_provider == "llm" else DeterministicExtractor()
        )
        app.state.customers = CustomerService(repository)
        app.state.outing = OutingService(
            repository, outing_settings, build_outing(repository, outing_settings, gateway, outing_http)
        )
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        if hasattr(app.state, "outing"):
            await app.state.outing.close()
        elif hasattr(app.state, "outing_http"):
            await app.state.outing_http.close()
        if hasattr(app.state, "ingestion"):
            app.state.ingestion.store.close()
        repository.close()
