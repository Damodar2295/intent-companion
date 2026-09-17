"""Transparent, configurable signal aggregation. Confidence is a heuristic, not a probability."""

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from agent.domain import CustomerContext, Evidence, IntentContext, IntentSignal
from agent.repositories import Abstain, NotFound, Repository
from config.settings import Settings


class IntentEngine:
    def __init__(self, repository: Repository, settings: Settings):
        self.repository = repository
        self.settings = settings

    def validate_signal(self, customer: CustomerContext, signal: IntentSignal) -> None:
        if signal.customer_id != customer.customer_id:
            raise NotFound("Unknown signal for this customer")
        if not customer.consent.allowed or not signal.consent.allowed:
            raise Abstain("Personalization consent is missing or withdrawn.")
        if not signal.context.destination:
            raise Abstain("A destination is required before detecting travel intent.")
        if signal.context.destination != "Rome":
            raise Abstain("This synthetic MVP supports Rome only.")
        now = self.settings.now()
        if signal.timestamp > now:
            raise Abstain("Future-dated signals cannot be used.")
        if signal.timestamp + timedelta(days=self.settings.signal_ttl_days) <= now:
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
        unique = {s.event_id: s for s in signals}
        for signal in unique.values():
            self.validate_signal(customer, signal)
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
                    fact=f"Permissioned {signal.event_type.replace('_', ' ')} for Rome.",
                    weight=weight,
                )
            )
        preferences = set(customer.stated_preferences)
        for signal in unique.values():
            preferences.update(signal.context.preferences)
        preferences -= set(customer.suppressed_preferences)
        expires = min(
            [s.timestamp + timedelta(days=self.settings.signal_ttl_days) for s in unique.values()]
            + [datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)]
        )
        return IntentContext(
            intent_id=intent_id or f"intent-{uuid4().hex}",
            customer_id=customer.customer_id,
            destination="Rome",
            start_date=start,
            end_date=end,
            purpose=purpose,
            preferences=sorted(preferences),
            lifecycle_stage=customer.lifecycle_stage,
            intent_stage="booked"
            if "travel_booking" in seen_types
            else "planning"
            if confidence >= 0.4
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
