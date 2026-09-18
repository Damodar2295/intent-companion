"""Versioned additive extension storage shares the existing SQLite transaction boundary."""

import json
from typing import Protocol

from pydantic import ValidationError

from agent.business.models import BusinessContext, BusinessFixtures, BusinessIntentContext, BusinessSignal
from agent.repositories import Conflict, NotFound


class RecordStore(Protocol):
    def get(self, kind: str, key: str) -> dict: ...
    def all(self, kind: str) -> list[dict]: ...
    def put(self, kind: str, key: str, data: dict) -> None: ...


class ExtensionStore:
    def __init__(self, repository, settings):
        self.repository = repository
        self.settings = settings
        with repository.lock, repository.db:
            repository.db.execute(
                "CREATE TABLE IF NOT EXISTS extension_records (kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id))"
            )
            repository.db.execute("INSERT OR IGNORE INTO metadata VALUES ('schema_version', '2')")
        path = settings.fixture_dir / "business.json"
        try:
            fixtures = BusinessFixtures.model_validate_json(path.read_text())
        except (ValidationError, ValueError) as exc:
            raise ValueError(f"Invalid fixture {path.name}: {exc}") from exc
        self.scenarios = fixtures.scenarios
        groups = {
            "business": fixtures.businesses,
            "product": fixtures.products,
            "supplier": fixtures.suppliers,
            "opportunity": fixtures.opportunities,
            "business_signal": fixtures.signals,
        }
        keys = {"business": "business_id", "business_signal": "event_id"}
        with repository.lock, repository.db:
            if not repository.db.execute("SELECT value FROM metadata WHERE key='business_seed_v1'").fetchone():
                for kind, records in groups.items():
                    for record in records:
                        key = getattr(record, keys.get(kind, "item_id"))
                        repository.db.execute(
                            "INSERT OR IGNORE INTO extension_records VALUES (?,?,?)",
                            (kind, key, record.model_dump_json()),
                        )
                repository.db.execute("INSERT INTO metadata VALUES ('business_seed_v1', '1')")

    def get(self, kind, key):
        with self.repository.lock:
            row = self.repository.db.execute(
                "SELECT data FROM extension_records WHERE kind=? AND id=?", (kind, key)
            ).fetchone()
        if row is None:
            raise NotFound(f"Unknown {kind.replace('_', ' ')}")
        return json.loads(row[0])

    def all(self, kind):
        with self.repository.lock:
            return [
                json.loads(row[0])
                for row in self.repository.db.execute(
                    "SELECT data FROM extension_records WHERE kind=? ORDER BY id", (kind,)
                )
            ]

    def put(self, kind, key, data):
        with self.repository.lock, self.repository.db:
            self.repository.db.execute(
                "INSERT INTO extension_records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data",
                (kind, key, json.dumps(data)),
            )

    def business(self, key):
        return BusinessContext.model_validate(self.get("business", key))

    def intent(self, key):
        return BusinessIntentContext.model_validate(self.get("business_intent", key))

    def add_signal(self, signal: BusinessSignal):
        with self.repository.lock, self.repository.db:
            try:
                previous = BusinessSignal.model_validate(self.get("business_signal", signal.event_id))
            except NotFound:
                self.put("business_signal", signal.event_id, signal.model_dump(mode="json"))
                return True
            if previous != signal:
                raise Conflict("Event ID already exists with different content")
            return False
