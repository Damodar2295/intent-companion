"""Goal-scoped intent inference; evidence origins and repeated-type weights are explicit."""

from datetime import timedelta
from itertools import pairwise
from uuid import uuid4

from agent import feedback
from agent.business.models import BusinessEvidence, BusinessIntentContext, BusinessSignal
from agent.repositories import Abstain, Conflict, NotFound


class BusinessIntentEngine:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def validate(self, customer, signal):
        if customer.business_id != signal.business_id:
            raise NotFound("Unknown signal for this business")
        if not customer.consent.allowed or not signal.consent.allowed:
            raise Abstain("Personalization consent is missing or withdrawn.")
        now = self.settings.now()
        if signal.timestamp > now or signal.timestamp + timedelta(days=self.settings.signal_ttl_days) <= now:
            raise Abstain("Business signal is future-dated or expired.")
        if signal.spend and signal.spend.observed_on > now.date():
            raise Abstain("Spend observation date cannot be in the future.")
        if signal.spend and signal.category != signal.spend.category:
            raise Abstain("Signal and spend categories must agree.")
        if signal.spend and signal.spend.status == "observed" and signal.spend.period_end > now.date():
            raise Abstain("Observed spend cannot cover a future period.")

    def detect(self, business_id, goal_id, ids=None, intent_id=None):
        customer = self.store.business(business_id)
        if not customer.consent.allowed:
            raise Abstain("Personalization consent is missing or withdrawn.")
        candidates = [BusinessSignal.model_validate(s) for s in self.store.all("business_signal")]
        signals = [
            s
            for s in candidates
            if s.business_id == business_id and s.goal_id == goal_id and (ids is None or s.event_id in ids)
        ]
        if ids is not None and set(ids) != {s.event_id for s in signals}:
            raise NotFound("Unknown signal for this business goal")
        if not signals:
            raise Abstain("No permissioned signals for this business goal.")
        if len({s.goal_type for s in signals}) != 1:
            raise Abstain("Conflicting goal types must not be merged.")
        evidence, seen, spends, score = [], set(), {}, 0.0
        for signal in sorted(signals, key=lambda s: (s.timestamp, s.event_id)):
            self.validate(customer, signal)
            weight = 0 if signal.event_type in seen else self.settings.business_weights[signal.event_type]
            seen.add(signal.event_type)
            score += weight
            origin = (
                "declared_goal"
                if signal.event_type == "declared_goal"
                else "scheduled_activity"
                if signal.event_type == "scheduled_payment"
                else "observed_activity"
            )
            evidence.append(
                BusinessEvidence(
                    source_id=signal.event_id,
                    origin=origin,
                    fact=f"{signal.event_type.replace('_', ' ').title()}: {signal.category or signal.goal_type}.",
                    weight=weight,
                )
            )
            if signal.spend:
                old = spends.get(signal.spend.observation_id)
                if old and old != signal.spend:
                    raise Conflict("Conflicting copies of a spend observation")
                spends[signal.spend.observation_id] = signal.spend
        # These inputs are period aggregates, not transaction rows. Overlap is ambiguous.
        for category in {s.category for s in spends.values()}:
            periods = sorted([s for s in spends.values() if s.category == category], key=lambda s: s.period_start)
            if any(a.period_end >= b.period_start for a, b in pairwise(periods)):
                raise Abstain("Overlapping spend periods need clarification before valuation.")
        # Evidence of recurrence requires distinct dates and nonoverlapping observation periods.
        for category in customer.priorities:
            observed = sorted(
                [s for s in spends.values() if s.category == category and s.status == "observed"],
                key=lambda s: s.period_start,
            )
            if (
                len(observed) >= 2
                and len({s.observed_on for s in observed}) >= 2
                and all(a.period_end < b.period_start for a, b in pairwise(observed))
            ):
                evidence.append(
                    BusinessEvidence(
                        source_id=",".join(s.observation_id for s in observed),
                        origin="recurring_pattern",
                        fact=f"Repeated {category} spend across distinct observation periods; not a prediction.",
                    )
                )
        needs = {s.category for s in signals if s.category} & set(customer.priorities)
        intent = BusinessIntentContext(
            intent_id=intent_id or f"bintent-{uuid4().hex}",
            business_id=business_id,
            goal_id=goal_id,
            goal_type=signals[0].goal_type,
            intent_stage="committed" if "scheduled_payment" in seen else "planning" if score >= 0.4 else "exploring",
            confidence=round(min(1, score), 4),
            categories=sorted(needs),
            signal_ids=sorted(s.event_id for s in signals),
            evidence=evidence,
            spend=list(spends.values()),
            created_at=self.settings.now(),
            expires_at=min(s.timestamp + timedelta(days=self.settings.signal_ttl_days) for s in signals),
        )
        intent.confirmation = feedback.status(self.store.repository, feedback.business_key(intent))
        self.store.put("business_intent", intent.intent_id, intent.model_dump(mode="json"))
        return intent

    def refresh(self, customer, intent):
        if customer.business_id != intent.business_id:
            raise NotFound("Unknown intent for this business")
        if intent.expires_at <= self.settings.now():
            raise Abstain("Business intent has expired.")
        return self.detect(customer.business_id, intent.goal_id, intent.signal_ids, intent.intent_id)
