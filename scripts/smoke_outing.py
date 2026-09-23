"""Opt-in credential-enabled smoke test. Never runs as part of pytest/CI."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from agent.outing.config import OutingSettings
from agent.outing.models import OutingRequest
from agent.outing.service import OutingService
from agent.repositories import SQLiteRepository
from config.settings import ROOT


async def smoke(day):
    load_dotenv(ROOT / ".env")
    settings = OutingSettings.from_env()
    if settings.demo or not settings.capabilities()["llm"]:
        print("Not run: configure REALTIME_MODE=true, DEMO_MODE=false, OPENAI_API_KEY and OPENAI_MODEL.")
        return 2
    repository = SQLiteRepository(":memory:")
    repository.seed()
    service = OutingService(repository, settings)
    try:
        body = OutingRequest(
            customer_id="cust-dining",
            text="Find an event, dining and shopping in Rome",
            city="Rome",
            date=day,
            timezone="Europe/Rome",
            card_id="card-a",
        )
        events = [event async for event in service.stream(body)]
        result = events[-1].result
        print(
            json.dumps(
                {
                    "status": result.status,
                    "mode": result.mode,
                    "warnings": result.warnings,
                    "source_providers": sorted(
                        {e.provider for a in result.alternatives for s in a.stops for e in s.entity.sources}
                    ),
                    "route_providers": sorted({r.provider for a in result.alternatives for r in a.routes}),
                    "alternatives": len(result.alternatives),
                },
                indent=2,
            )
        )
        return 0 if result.alternatives else 1
    finally:
        await service.close()
        repository.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Destination date YYYY-MM-DD")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(smoke(args.date)))
