"""Provider contracts and bounded transport. Credentials and query text never enter logs."""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Protocol

import httpx

from agent.outing.models import DiscoveryCandidate, Location, OutingRequest, RouteLeg, SearchPlan

log = logging.getLogger("outing")


class ProviderError(Exception):
    pass


class LLMProvider(Protocol):
    async def interpret(self, request: OutingRequest, preferences: list[str]) -> SearchPlan: ...
    async def explain(self, facts: list[dict]) -> dict[str, str]: ...


class SearchProvider(Protocol):
    async def search(self, plan: SearchPlan) -> list[DiscoveryCandidate]: ...


class PlaceProvider(Protocol):
    async def search(self, plan: SearchPlan) -> list[DiscoveryCandidate]: ...
    async def get_details(self, place_id: str, category: str) -> DiscoveryCandidate: ...


class EventProvider(Protocol):
    async def search(self, plan: SearchPlan) -> list[DiscoveryCandidate]: ...


class RoutingProvider(Protocol):
    async def route(
        self,
        origin: Location,
        destination: Location,
        departure: datetime,
        mode: str,
        origin_id: str,
        destination_id: str,
    ) -> RouteLeg: ...


class Transport:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.provider_timeout, trust_env=False)
        self.semaphore = asyncio.Semaphore(4)
        self.cache = {}  # interpretation/route only; no Places or raw page cache

    async def close(self):
        await self.client.aclose()

    async def json(self, provider, method, url, **kwargs):
        started = time.monotonic()
        for attempt in range(3):
            try:
                async with self.semaphore:
                    response = await self.client.request(method, url, **kwargs)
                if (response.status_code == 429 or response.status_code >= 500) and attempt < 2:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                response.raise_for_status()
                result = response.json()
                log.info(
                    json.dumps(
                        {
                            "provider": provider,
                            "latency_ms": round((time.monotonic() - started) * 1000),
                            "success": True,
                            "retry_count": attempt,
                            "cache_hit": False,
                        }
                    )
                )
                return result
            except (httpx.HTTPError, ValueError) as exc:
                if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)) and attempt < 2:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                log.warning(json.dumps({"provider": provider, "success": False, "retry_count": attempt}))
                raise ProviderError(f"{provider} is unavailable") from None
        raise ProviderError(f"{provider} is unavailable")

    async def cached(self, namespace, key, ttl, call):
        hashed = hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()
        k = (namespace, hashed)
        now = time.monotonic()
        self.cache = {key: val for key, val in self.cache.items() if val[0] > now}
        if k in self.cache:
            log.info(json.dumps({"provider": namespace, "cache_hit": True}))
            return self.cache[k][1]
        result = await call()
        if len(self.cache) >= 128:
            self.cache.pop(next(iter(self.cache)))
        self.cache[k] = (now + ttl, result)
        return result
