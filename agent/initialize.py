"""Application lifetime: config → storage → seed → factory → ready → close."""

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from agent.customer_context import CustomerService
from agent.factory import GraphFactory
from agent.repositories import SQLiteRepository
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
        repository.seed()
        app.state.settings = settings
        app.state.repository = repository
        app.state.companion = GraphFactory.create(repository, settings)
        app.state.customers = CustomerService(repository)
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        repository.close()
