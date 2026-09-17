import pytest
from fastapi.testclient import TestClient

from agent.factory import GraphFactory
from agent.main import create_app
from agent.repositories import SQLiteRepository
from config.settings import Settings


@pytest.fixture
def settings():
    return Settings(database_path=":memory:")


@pytest.fixture
def repository():
    repo = SQLiteRepository(":memory:")
    repo.seed()
    yield repo
    repo.close()


@pytest.fixture
def service(repository, settings):
    return GraphFactory.create(repository, settings)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client
