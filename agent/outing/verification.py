import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from agent.outing.models import FieldEvidence, Location, RealWorldEntity


def evidence(provider, field, value, url, source_type, now, settings, synthetic=False):
    confidence = 0.95 if source_type in {"PLACES_API", "TICKETING_API", "DEMO"} else 0.98
    key = json.dumps([provider, field, value, url], sort_keys=True)
    return FieldEvidence(
        evidence_id=hashlib.sha256(key.encode()).hexdigest()[:20],
        field=field,
        value=value,
        source_type=source_type,
        url=url,
        provider=provider,
        retrieved_at=now,
        expires_at=now + timedelta(seconds=settings.ttl.get(field, settings.ttl["default"])),
        confidence=confidence,
        synthetic=synthetic,
        attribution="Google Maps" if provider == "google_places" else provider,
    )


def valid_fact(field, value):
    try:
        if field in {"name", "address"}:
            return isinstance(value, str) and bool(value.strip())
        if field == "location":
            Location.model_validate(value)
        if field.startswith("schedule."):
            return datetime.fromisoformat(value).tzinfo is not None
        if field == "price":
            amount = Decimal(str(value["amount"]))
            return amount.is_finite() and amount >= 0 and len(value["currency"]) == 3
        if field == "opening_hours":
            if not isinstance(value, list):
                return False
            for period in value:
                for name in ("open", "close"):
                    if name == "close" and name not in period:
                        continue
                    point = period[name]
                    if not (
                        isinstance(point, dict)
                        and 0 <= point["day"] <= 6
                        and 0 <= point.get("hour", 0) <= 23
                        and 0 <= point.get("minute", 0) <= 59
                    ):
                        return False
        return True
    except (ValueError, TypeError, KeyError, InvalidOperation):
        return False


class VerificationService:
    def __init__(self, settings):
        self.settings = settings

    def verify(self, candidate):
        now = self.settings.now()
        facts, scores, freshness, conflicts = {}, {}, {}, {}
        grouped = {}
        for item in candidate.evidence:
            grouped.setdefault(item.field, []).append(item)
        for field, items in grouped.items():
            policy = self.settings.field_source_priority.get(field, self.settings.source_priority)
            fresh = [
                e
                for e in items
                if e.retrieved_at <= now < e.expires_at
                and e.confidence >= 0.8
                and valid_fact(field, e.value)
                and e.source_type in policy
                and (self.settings.demo or not e.synthetic)
            ]
            freshness[field] = "FRESH" if fresh else "STALE" if items else "UNKNOWN"
            if not fresh:
                continue
            priority = max(policy[e.source_type] for e in fresh)
            best = [e for e in fresh if policy[e.source_type] == priority]
            values = {json.dumps(e.value, sort_keys=True) for e in best}
            if len({json.dumps(e.value, sort_keys=True) for e in items}) > 1:
                conflicts[field] = [e.evidence_id for e in items]
            if len(values) != 1:
                continue
            facts[field] = best[0].value
            scores[field] = min(e.confidence for e in best)
        required = {"name", "location", "address"}
        if candidate.category == "EVENT":
            required |= {"schedule.start"}
        status = "UNVERIFIED"
        if required <= facts.keys():
            status = (
                "VERIFIED"
                if (
                    (candidate.category == "EVENT" and "schedule.end" in facts)
                    or (candidate.category != "EVENT" and "opening_hours" in facts)
                )
                else "PARTIALLY_VERIFIED"
            )
        return RealWorldEntity(
            entity_id=candidate.candidate_id,
            entity_type=candidate.category,
            canonical_name=str(facts.get("name", candidate.name)),
            facts=facts,
            sources=candidate.evidence,
            conflicts=conflicts,
            confidence=scores,
            freshness=freshness,
            verification_status=status,
            synthetic=any(e.synthetic for e in candidate.evidence),
        )


def deduplicate(candidates):
    """Only stable provider identities merge; names alone never merge branches or event occurrences."""
    found, fingerprints = {}, {}
    for candidate in candidates:
        key = (candidate.provider, candidate.candidate_id)
        # Cross-provider event merging requires corroborated venue, local date and name.
        # A title alone can never collapse a recurring event or a branch.
        strong = {
            e.field: e.value
            for e in candidate.evidence
            if e.source_type in {"PLACES_API", "TICKETING_API", "OFFICIAL_ORGANIZER", "OFFICIAL_VENUE"}
            and e.confidence >= 0.8
            and valid_fact(e.field, e.value)
        }
        required = {"name", "address", "location", "schedule.start"}
        if candidate.category == "EVENT" and required <= strong.keys():
            fingerprint = (
                re.sub(r"[^a-z0-9]", "", strong["name"].casefold()),
                re.sub(r"[^a-z0-9]", "", strong["address"].casefold()),
                round(strong["location"]["lat"], 5),
                round(strong["location"]["lng"], 5),
                datetime.fromisoformat(strong["schedule.start"]).astimezone(UTC),
            )
            key = fingerprints.setdefault(fingerprint, key)
        if key not in found:
            found[key] = candidate.model_copy(deep=True)
        else:
            previous = found[key]
            ids = {e.evidence_id for e in previous.evidence}
            previous.evidence.extend(e for e in candidate.evidence if e.evidence_id not in ids)
    return list(found.values())
