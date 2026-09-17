"""SQLite repository boundary; structured columns are used for catalog retrieval."""

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Protocol

from agent.domain import CATALOG_ADAPTER, CatalogItem, CompanionExperience, CustomerContext, IntentContext, IntentSignal
from config.settings import ROOT


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Abstain(Exception):
    """A valid request lacks trustworthy evidence. Its reason is safe to expose."""


class Repository(Protocol):
    def customer(self, customer_id: str) -> CustomerContext: ...
    def save_customer(self, customer: CustomerContext) -> None: ...
    def signals(self, customer_id: str, ids: list[str] | None = None) -> list[IntentSignal]: ...
    def add_signal(self, signal: IntentSignal) -> bool: ...
    def intent(self, intent_id: str) -> IntentContext: ...
    def save_intent(self, intent: IntentContext) -> None: ...
    def catalog(self, market: str, segment: str, destination: str) -> list[CatalogItem]: ...
    def audit(self, experience: CompanionExperience) -> None: ...


class SQLiteRepository:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.db:
            self.db.executescript("""
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS customers (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS signal_customer ON signals(customer_id);
                CREATE TABLE IF NOT EXISTS intents (
                    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS catalog (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, market TEXT NOT NULL,
                    segment TEXT NOT NULL, geography TEXT NOT NULL, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS catalog_lookup ON catalog(market, segment, geography, kind);
                CREATE TABLE IF NOT EXISTS experiences (
                    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, generated_at TEXT NOT NULL, data TEXT NOT NULL);
            """)

    def seed(self) -> None:
        """Version flag prevents reseeding from resurrecting edits on subsequent starts."""
        with self.lock, self.db:
            if self.db.execute("SELECT value FROM metadata WHERE key='seed_version'").fetchone():
                return
            for obj in json.loads((ROOT / "data/customers.json").read_text()):
                customer = CustomerContext.model_validate(obj)
                self.db.execute(
                    "INSERT INTO customers VALUES (?, ?)", (customer.customer_id, customer.model_dump_json())
                )
            for obj in json.loads((ROOT / "data/signals.json").read_text()):
                signal = IntentSignal.model_validate(obj)
                self.db.execute(
                    "INSERT INTO signals VALUES (?, ?, ?)",
                    (signal.event_id, signal.customer_id, signal.model_dump_json()),
                )
            for filename in ("cards", "benefits", "offers", "rewards", "merchants"):
                for obj in json.loads((ROOT / f"data/{filename}.json").read_text()):
                    item = CATALOG_ADAPTER.validate_python(obj)
                    self.db.execute(
                        "INSERT INTO catalog VALUES (?, ?, ?, ?, ?, ?)",
                        (item.item_id, item.kind, item.market, item.segment, item.geography, item.model_dump_json()),
                    )
            self.db.execute("INSERT INTO metadata VALUES ('seed_version', 'synthetic-v1')")

    def customer(self, customer_id: str) -> CustomerContext:
        with self.lock:
            row = self.db.execute("SELECT data FROM customers WHERE id=?", (customer_id,)).fetchone()
        if row is None:
            raise NotFound("Unknown customer")
        return CustomerContext.model_validate_json(row["data"])

    def save_customer(self, customer: CustomerContext) -> None:
        with self.lock, self.db:
            cursor = self.db.execute(
                "UPDATE customers SET data=? WHERE id=?", (customer.model_dump_json(), customer.customer_id)
            )
            if not cursor.rowcount:
                raise NotFound("Unknown customer")

    def signals(self, customer_id: str, ids: list[str] | None = None) -> list[IntentSignal]:
        with self.lock:
            rows = self.db.execute(
                "SELECT data FROM signals WHERE customer_id=? ORDER BY id", (customer_id,)
            ).fetchall()
        result = [IntentSignal.model_validate_json(r["data"]) for r in rows]
        if ids is not None:
            result = [s for s in result if s.event_id in ids]
            if set(ids) != {s.event_id for s in result}:
                raise NotFound("Unknown signal for this customer")
        return result

    def add_signal(self, signal: IntentSignal) -> bool:
        self.customer(signal.customer_id)
        with self.lock, self.db:
            row = self.db.execute("SELECT data FROM signals WHERE id=?", (signal.event_id,)).fetchone()
            if row:
                if IntentSignal.model_validate_json(row["data"]) != signal:
                    raise Conflict("Event ID already exists with different content")
                return False
            self.db.execute(
                "INSERT INTO signals VALUES (?, ?, ?)", (signal.event_id, signal.customer_id, signal.model_dump_json())
            )
        return True

    def intent(self, intent_id: str) -> IntentContext:
        with self.lock:
            row = self.db.execute("SELECT data FROM intents WHERE id=?", (intent_id,)).fetchone()
        if row is None:
            raise NotFound("Unknown intent")
        return IntentContext.model_validate_json(row["data"])

    def save_intent(self, intent: IntentContext) -> None:
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO intents VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (intent.intent_id, intent.customer_id, intent.model_dump_json()),
            )

    def catalog(self, market: str, segment: str, destination: str) -> list[CatalogItem]:
        with self.lock:
            rows = self.db.execute(
                "SELECT data FROM catalog WHERE market=? AND segment=? AND geography IN (?, 'global') ORDER BY id",
                (market, segment, destination),
            ).fetchall()
        return [CATALOG_ADAPTER.validate_json(r["data"]) for r in rows]

    def audit(self, experience: CompanionExperience) -> None:
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO experiences VALUES (?, ?, ?, ?)",
                (
                    experience.experience_id,
                    experience.customer_id,
                    experience.generated_at.isoformat(),
                    experience.model_dump_json(),
                ),
            )

    def close(self) -> None:
        self.db.close()
