"""General deterministic intent service; legacy Rome detection retains its own boundary."""

from agent.intent_engine import IntentEngine
from agent.repositories import Abstain

SIGNAL_INTENTS = {
    "travel_search": "travel",
    "hotel_search": "travel",
    "travel_booking": "travel",
    "restaurant_search": "dining",
    "restaurant_booking": "dining",
    "event_search": "event",
    "event_booking": "event",
}


class IntentService(IntentEngine):
    def validate_destination(self, destination):
        if not destination or not destination.strip():
            raise Abstain("Provide a destination before detecting intent.")

    def classify(self, signals):
        types = set()
        for signal in signals:
            inferred = SIGNAL_INTENTS.get(signal.event_type)
            declared = signal.context.intent_type
            if inferred and declared and inferred != declared:
                raise Abstain("Declared intent conflicts with the structured signal type.")
            if inferred or declared:
                types.add(inferred or declared)
        if not types:
            raise Abstain("Activity is unclear. Provide context.intent_type or a specific activity signal.")
        # Dining/events can support a trip, but a booking for them does not book the trip.
        if "travel" in types:
            return "travel"
        return next(iter(types)) if len(types) == 1 else "lifestyle"

    def is_booked(self, intent_type, seen_types):
        return {"travel": "travel_booking", "dining": "restaurant_booking", "event": "event_booking"}.get(
            intent_type
        ) in seen_types

    def ingest(self, signal):
        customer = self.repository.customer(signal.customer_id)
        self.validate_signal(customer, signal)
        # Reject conflicting declarations even before persistence; incomplete contexts are accepted for aggregation.
        if signal.context.intent_type and signal.event_type in SIGNAL_INTENTS:
            self.classify([signal])
        return self.repository.add_signal(signal)

    def diagnostics(self, intent):
        return {
            "confidence_method": "sum_unique_signal_type_weights_capped_at_one",
            "confidence_is_probability": False,
            "uncapped_weight_sum": round(sum(e.weight or 0 for e in intent.evidence), 4),
            "planning_threshold": self.settings.intent_planning_threshold,
            "signal_contributions": [{"signal_id": e.source_id, "weight": e.weight} for e in intent.evidence],
            "expiry_policy": "earliest_signal_ttl_or_end_date_exclusive_utc",
            "expires_at": intent.expires_at.isoformat(),
        }
