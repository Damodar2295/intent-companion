"""Persist only nonsensitive run metadata; provider facts are short-lived memory only."""

import asyncio
from datetime import timedelta


class RunStore:
    def __init__(self, repository, settings):
        self.repository, self.settings = repository, settings
        self.results = {}
        self.timers = {}
        with repository.lock, repository.db:
            repository.db.execute("""CREATE TABLE IF NOT EXISTS outing_runs (
                id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, status TEXT NOT NULL,
                generated_at TEXT NOT NULL, expires_at TEXT NOT NULL)""")

    def evict(self, run_id):
        self.results.pop(run_id, None)
        handle = self.timers.pop(run_id, None)
        if handle:
            handle.cancel()
        with self.repository.lock, self.repository.db:
            self.repository.db.execute("DELETE FROM outing_runs WHERE id=?", (run_id,))

    def close(self):
        for handle in self.timers.values():
            handle.cancel()
        self.timers.clear()
        self.results.clear()

    def purge(self):
        now = self.settings.now()
        self.results = {key: val for key, val in self.results.items() if val[1].expires_at > now}
        with self.repository.lock, self.repository.db:
            self.repository.db.execute("DELETE FROM outing_runs WHERE expires_at <= ?", (now.isoformat(),))

    def save(self, customer_id, result, context):
        self.purge()
        # Never retain precise origin coordinates, even in a saved in-memory run.
        saved = result.model_copy(deep=True)
        if saved.search_plan:
            saved.search_plan.user_location = None
        saved.expires_at = min(saved.expires_at, self.settings.now() + timedelta(minutes=5))
        if len(self.results) >= 100:
            self.evict(next(iter(self.results)))
        expiries = [
            e.expires_at
            for a in saved.alternatives
            for s in a.stops
            for e in s.entity.sources
            if e.evidence_id in s.evidence_ids
        ]
        expiries += [r.expires_at for a in saved.alternatives for r in a.routes]
        expiries += [m.expires_at for a in saved.alternatives for s in a.stops for m in s.entity.amex_matches]
        saved.expires_at = min([saved.expires_at, *expiries])
        result.expires_at = saved.expires_at
        self.results[saved.outing_id] = (customer_id, saved, context)
        self.timers[saved.outing_id] = asyncio.get_running_loop().call_later(
            max(0, (saved.expires_at - self.settings.now()).total_seconds()), self.evict, saved.outing_id
        )
        with self.repository.lock, self.repository.db:
            self.repository.db.execute(
                "INSERT OR REPLACE INTO outing_runs VALUES (?,?,?,?,?)",
                (
                    saved.outing_id,
                    customer_id,
                    saved.status,
                    saved.generated_at.isoformat(),
                    saved.expires_at.isoformat(),
                ),
            )

    def get(self, run_id):
        self.purge()
        row = self.results.get(run_id)
        if not row:
            return None
        customer = self.repository.customer(row[0])
        if not customer.consent.allowed or context_version(customer) != row[2]:
            self.evict(run_id)
            return None
        return row[1]

    def diagnostics(self, run_id):
        result = self.get(run_id)
        if result is None:
            return None
        evidence = sum(len(stop.evidence_ids) for alt in result.alternatives for stop in alt.stops)
        return {
            "outing_id": result.outing_id,
            "status": result.status,
            "mode": result.mode,
            "alternative_count": len(result.alternatives),
            "stop_count": sum(len(alt.stops) for alt in result.alternatives),
            "evidence_reference_count": evidence,
            "warning_count": len(result.warnings),
            "expires_at": result.expires_at,
        }


def context_version(customer):
    return (tuple(customer.stated_preferences), tuple(customer.suppressed_preferences), customer.consent.allowed)
