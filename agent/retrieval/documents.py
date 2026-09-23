"""Typed seed normalization. JSON is ingestion input, never a query-time catalog."""

import hashlib
import json
import unicodedata
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue

from agent.canonical.seeds import KnowledgeSeeds, validate_seed_directory
from agent.domain import CATALOG_ADAPTER, Model

TEXT_VERSION = "typed-search-v1"


def clean(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


class SearchDocument(Model):
    record_id: str = Field(min_length=1, max_length=250)
    document_type: Literal["card", "benefit", "offer", "reward", "merchant", "place", "event", "experience"]
    searchable_text: str = Field(min_length=1, max_length=16000)
    metadata: dict[str, JsonValue]

    def digest(self):
        payload = self.model_dump(mode="json")
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def text(fields):
    # One bounded, standalone document per typed record; preserve conditions with their value.
    return "\n".join(f"{label}: {clean(str(value))}" for label, value in fields if value is not None and value != "")


def seed_documents(directory: Path, catalog_ttl_days: int = 90) -> list[SearchDocument]:
    validate_seed_directory(directory)
    if catalog_ttl_days <= 0:
        raise ValueError("Catalog TTL must be positive")
    catalog = [
        CATALOG_ADAPTER.validate_python(row)
        for name in ("cards", "benefits", "offers", "rewards", "merchants")
        for row in json.loads((directory / f"{name}.json").read_text())
    ]
    products = {item.product_id: item.title for item in catalog if item.kind == "card"}
    merchants = {item.merchant_id: item.name for item in catalog if item.kind == "merchant"}
    docs = []
    for item in catalog:
        product_ids = (
            [item.product_id]
            if hasattr(item, "product_id")
            else getattr(item, "eligible_products", getattr(item, "accepting_products", []))
        )
        verified = datetime.combine(item.last_verified, time.min, UTC)
        expiry = min(
            verified + timedelta(days=catalog_ttl_days),
            datetime.combine(item.valid_to + timedelta(days=1), time.min, UTC),
        )
        metadata = {
            "market": item.market,
            "segment": item.segment,
            "city": item.geography,
            "category": item.category,
            "product_ids": product_ids,
            "merchant_id": getattr(item, "merchant_id", None),
            "valid_from": item.valid_from.isoformat(),
            "valid_to": item.valid_to.isoformat(),
            "verified_at": verified.isoformat(),
            "verification_precision": "date",
            "expires_at": expiry.isoformat(),
            "source_type": item.source_type,
            "source_ids": [item.source],
            "source_version": item.catalog_version,
            "freshness_policy": f"catalog-{catalog_ttl_days}-days-or-validity-end",
            "data_completeness": "PARTIAL",
            "conditions": item.conditions,
            "applicability": getattr(item, "eligibility_rule", getattr(item, "product_rules", None)),
            "text_version": TEXT_VERSION,
            "source_record_hash": hashlib.sha256(item.model_dump_json().encode()).hexdigest(),
        }
        raw = item.model_dump(mode="json")
        for key in (
            "product_id",
            "offer_id",
            "benefit_id",
            "reward_id",
            "subcategory",
            "points",
            "value_amount",
            "value_per_point",
            "currency",
            "stacking_group",
            "stackable",
        ):
            if key in raw:
                metadata[key] = raw[key]
        fields = [
            ("Type", item.kind),
            ("Name", item.title),
            ("Category", item.category),
            ("Location", item.geography),
            ("Description", item.description),
            ("Products", "; ".join(products[p] for p in product_ids)),
            ("Merchant", merchants.get(getattr(item, "merchant_id", None))),
            ("Value", getattr(item, "value_amount", None)),
            ("Currency", getattr(item, "currency", None)),
            ("Points", getattr(item, "points", None)),
            ("Conditions", "; ".join(item.conditions)),
            ("Valid from", item.valid_from),
            ("Valid to", item.valid_to),
            ("Source", "SYNTHETIC — illustrative, not live inventory"),
        ]
        docs.append(
            SearchDocument(
                record_id=f"{item.kind}:{item.item_id}",
                document_type=item.kind,
                searchable_text=text(fields),
                metadata=metadata,
            )
        )
    bundle = KnowledgeSeeds.model_validate_json((directory / "knowledge.json").read_text())
    sources = {s.source_id: s for s in bundle.sources}
    venues = {p.place_id: p for p in bundle.places}
    proofs = {p.evidence_id: p.model_dump(mode="json") for p in bundle.relationship_evidence}
    for kind, rows, identity in (
        ("place", bundle.places, "place_id"),
        ("event", bundle.events, "event_id"),
        ("experience", bundle.experiences, "experience_id"),
    ):
        for item in rows:
            provenance = [sources[key].model_dump(mode="json") for key in item.source_ids]
            metadata = {
                "market": item.market,
                "country": item.country,
                "city": item.city,
                "category": item.category,
                "active": item.active,
                "source_type": item.source_type,
                "source_ids": item.source_ids,
                "sources": provenance,
                "expires_at": min(sources[key].expires_at for key in item.source_ids).isoformat(),
                "data_completeness": item.data_completeness,
                "text_version": TEXT_VERSION,
                "source_record_hash": hashlib.sha256(item.model_dump_json().encode()).hexdigest(),
            }
            fields = [
                ("Type", kind),
                ("Name", item.name),
                ("Category", item.category),
                ("Location", item.city),
                ("Description", item.description),
            ]
            if kind == "place":
                metadata.update(
                    place_id=item.place_id,
                    merchant_id=item.merchant_id,
                    address=item.address,
                    location=item.location.model_dump(mode="json") if item.location else None,
                )
                fields.append(("Address", item.address))
            elif kind == "event":
                metadata.update(
                    event_id=item.event_id,
                    venue_id=item.venue_id,
                    starts_at=item.starts_at.isoformat(),
                    ends_at=item.ends_at.isoformat(),
                    timezone=item.timezone,
                    status=item.status,
                    availability=item.availability,
                    ticket_seller_id=item.ticket_seller_id,
                    price=str(item.price) if item.price is not None else None,
                    currency=item.currency,
                )
                fields.extend(
                    [
                        ("Venue", venues[item.venue_id].name),
                        ("Starts", item.starts_at.isoformat()),
                        ("Ends", item.ends_at.isoformat()),
                        ("Status", item.status),
                        ("Price", item.price),
                        ("Currency", item.currency),
                    ]
                )
            else:
                metadata.update(
                    experience_id=item.experience_id,
                    event_id=item.event_id,
                    venue_id=item.venue_id,
                    product_ids=item.eligible_product_ids,
                    conditions=item.conditions,
                    valid_from=item.valid_from.isoformat(),
                    valid_to=item.valid_to.isoformat(),
                    relationship_evidence=[proofs[key] for key in item.relationship_evidence_ids],
                )
                metadata["expires_at"] = min(
                    item.valid_to, *(sources[key].expires_at for key in item.source_ids)
                ).isoformat()
                fields.extend(
                    [
                        ("Conditions", "; ".join(item.conditions)),
                        ("Products", "; ".join(products[p] for p in item.eligible_product_ids)),
                    ]
                )
            fields.append(("Source", "SYNTHETIC — illustrative, not live inventory"))
            docs.append(
                SearchDocument(
                    record_id=f"{kind}:{getattr(item, identity)}",
                    document_type=kind,
                    searchable_text=text(fields),
                    metadata=metadata,
                )
            )
    return docs
