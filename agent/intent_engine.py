"""Transparent, configurable signal aggregation. Confidence is a heuristic, not a probability."""

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from agent.domain import CustomerContext, Evidence, IntentContext, IntentSignal
from agent.repositories import Abstain, Conflict, NotFound, Repository
from config.settings import Settings


class IntentEngine:
    def __init__(self, repository: Repository, settings: Settings):
        self.repository = repository
        self.settings = settings

    def validate_destination(self, destination):
        if not destination:
            raise Abstain("A destination is required before detecting travel intent.")
        if destination != "Rome":
            raise Abstain("This synthetic MVP supports Rome only.")

    def classify(self, signals):
        return "travel"

    def is_booked(self, intent_type, seen_types):
        return "travel_booking" in seen_types

    def signal_expiry(self, signal):
        days = self.settings.signal_ttl_overrides.get(signal.event_type, self.settings.signal_ttl_days)
        return signal.timestamp + timedelta(days=days)

    def validate_signal(self, customer: CustomerContext, signal: IntentSignal) -> None:
        if signal.customer_id != customer.customer_id:
            raise NotFound("Unknown signal for this customer")
        if not customer.consent.allowed or not signal.consent.allowed:
            raise Abstain("Personalization consent is missing or withdrawn.")
        self.validate_destination(signal.context.destination)
        now = self.settings.now()
        if signal.timestamp > now:
            raise Abstain("Future-dated signals cannot be used.")
        if self.signal_expiry(signal) <= now:
            raise Abstain("The signal has expired.")
        if signal.context.end_date and signal.context.end_date < now.date():
            raise Abstain("The trip has ended.")

    def derive(
        self, customer: CustomerContext, signals: list[IntentSignal], intent_id: str | None = None
    ) -> IntentContext:
        if not customer.consent.allowed:
            raise Abstain("Personalization consent is missing or withdrawn.")
        if not signals:
            raise Abstain("No permissioned travel signals are available.")
        unique = {}
        for signal in signals:
            if signal.event_id in unique and unique[signal.event_id] != signal:
                raise Conflict("Event ID appears with conflicting signal content")
            unique[signal.event_id] = signal
        for signal in unique.values():
            self.validate_signal(customer, signal)
        destinations = {s.context.destination for s in unique.values()}
        if len(destinations) != 1:
            raise Abstain("Signals from different destinations cannot be merged.")
        destination = next(iter(destinations))
        intent_type = self.classify(list(unique.values()))
        complete = {
            (s.context.start_date, s.context.end_date, s.context.purpose)
            for s in unique.values()
            if s.context.start_date and s.context.end_date
        }
        if len(complete) != 1:
            raise Abstain("Select signals for one trip with complete, consistent dates and purpose.")
        start, end, purpose = next(iter(complete))
        for signal in unique.values():
            context = signal.context
            if (
                (context.start_date and context.start_date != start)
                or (context.end_date and context.end_date != end)
                or context.purpose != purpose
            ):
                raise Abstain("Signals from incompatible trips cannot be merged.")
        evidence = []
        seen_types = set()
        confidence = 0.0
        # Stable order ensures the same signal receives each type's contribution.
        for signal in sorted(unique.values(), key=lambda s: (s.timestamp, s.event_id)):
            weight = 0.0 if signal.event_type in seen_types else self.settings.weights[signal.event_type]
            seen_types.add(signal.event_type)
            confidence += weight
            evidence.append(
                Evidence(
                    evidence_id=f"signal:{signal.event_id}",
                    type="signal",
                    source_id=signal.event_id,
                    fact=f"Permissioned {signal.event_type.replace('_', ' ')} for {destination}.",
                    weight=weight,
                )
            )
        preferences = set(customer.stated_preferences)
        for signal in unique.values():
            preferences.update(signal.context.preferences)
        preferences -= set(customer.suppressed_preferences)
        expires = min(
            [self.signal_expiry(s) for s in unique.values()]
            + [datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)]
        )
        return IntentContext(
            intent_id=intent_id or f"intent-{uuid4().hex}",
            customer_id=customer.customer_id,
            destination=destination,
            intent_type=intent_type,
            start_date=start,
            end_date=end,
            purpose=purpose,
            preferences=sorted(preferences),
            lifecycle_stage=customer.lifecycle_stage,
            intent_stage="booked"
            if self.is_booked(intent_type, seen_types)
            else "planning"
            if confidence >= self.settings.intent_planning_threshold
            else "exploring",
            confidence=round(min(1, confidence), 4),
            evidence=evidence,
            signal_ids=sorted(unique),
            created_at=self.settings.now(),
            expires_at=expires,
        )

    def detect(self, customer_id: str, signal_ids: list[str] | None = None) -> IntentContext:
        customer = self.repository.customer(customer_id)
        intent = self.derive(customer, self.repository.signals(customer_id, signal_ids))
        self.repository.save_intent(intent)
        return intent

    def refresh(self, customer: CustomerContext, intent: IntentContext) -> IntentContext:
        if intent.customer_id != customer.customer_id:
            raise NotFound("Unknown intent for this customer")
        if intent.expires_at <= self.settings.now():
            raise Abstain("The intent has expired. Supply fresh signals.")
        refreshed = self.derive(
            customer, self.repository.signals(customer.customer_id, intent.signal_ids), intent.intent_id
        )
        refreshed.created_at = intent.created_at
        refreshed.expires_at = min(refreshed.expires_at, intent.expires_at)
        return refreshed
