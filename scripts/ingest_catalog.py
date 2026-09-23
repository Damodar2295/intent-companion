"""Explicit local ingestion: python -m scripts.ingest_catalog --help."""

import argparse
import asyncio
import json
from pathlib import Path

from agent.retrieval.composition import build_ingestion
from agent.retrieval.documents import seed_documents
from config.settings import ROOT, Settings


async def run(args):
    settings = Settings.from_env()
    if args.database:
        settings.retrieval_database_path = args.database
    if args.embedding_mode:
        settings.embedding_mode = args.embedding_mode
    service = build_ingestion(settings)
    try:
        documents = seed_documents(args.directory, settings.catalog_ttl_days)
        print(json.dumps(await service.ingest(documents), indent=2))
    finally:
        service.store.close()


def main():
    parser = argparse.ArgumentParser(
        description="Ingest validated synthetic catalogs into a persistent local vector/FTS index"
    )
    parser.add_argument("--directory", type=Path, default=ROOT / "data")
    parser.add_argument(
        "--database", help="SQLite index path; defaults to configured retrieval database or application database"
    )
    parser.add_argument(
        "--embedding-mode", choices=["disabled", "test_hash", "openai"], help="Explicit embedding provider choice"
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
