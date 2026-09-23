import asyncio
import json
import logging
import time
from datetime import timedelta
from uuid import uuid4

from agent.outing.models import EntityRelationship, OutingPlan, PipelineEvent
from agent.outing.official import OfficialPages
from agent.outing.persistence import RunStore, context_version
from agent.outing.planning import schedule
from agent.outing.providers import ProviderError
from agent.outing.value import enrich, resolve
from agent.outing.verification import VerificationService, deduplicate


class OutingService:
    def __init__(self, repository, settings, dependencies=None):
        from agent.providers.container import build_outing

        self.repository, self.settings = repository, settings
        providers = dependencies or build_outing(repository, settings)
        self.http, self.llm = providers.http, providers.llm
        self.discovery, self.router = providers.discovery, providers.router
        self.catalog, self.experiences = providers.catalog, providers.experiences
        self.store = RunStore(repository, settings)
        self.verifier = VerificationService(settings)

    async def close(self):
        self.store.close()
        await self.http.close()

    async def stream(self, request):
        run_id, sequence, queue = str(uuid4()), 0, asyncio.Queue()
        now = self.settings.now()
        customer = self.repository.customer(request.customer_id)
        context = context_version(customer)
        result = OutingPlan(
            outing_id=run_id,
            status="PARTIAL",
            mode="demo" if self.settings.demo else "realtime",
            generated_at=now,
            expires_at=now + timedelta(minutes=5),
            hypothetical=customer.lifecycle_stage == "prospect",
        )

        def check_consent():
            current = self.repository.customer(request.customer_id)
            if not current.consent.allowed or context_version(current) != context:
                raise ProviderError("Consent or preferences changed. Start a new outing with your current choices.")

        async def stage(name, message):
            check_consent()
            await queue.put((name, message))

        async def work():
            try:
                async with asyncio.timeout(self.settings.deadline):
                    await stage("PLANNING", "Interpreting your request")
                    if (
                        customer.lifecycle_stage == "member"
                        and request.card_id
                        and request.card_id not in customer.existing_cards
                    ):
                        raise ProviderError("Select a card held by this member")
                    prefs = [p for p in customer.stated_preferences if p not in customer.suppressed_preferences]
                    plan = await self.llm.interpret(request, prefs)
                    # Do not resurrect removed preferences from model output or cached interpretation.
                    plan.preferences = [p for p in plan.preferences if p not in customer.suppressed_preferences]
                    result.search_plan = plan
                    await stage("SEARCHING", "Discovering places and events from configured providers")
                    candidates = []

                    async def discover(provider):
                        try:
                            found = await provider.search(plan)
                            candidates.extend(found)
                        except (ProviderError, ValueError, KeyError, TypeError) as exc:
                            result.warnings.append(
                                str(exc) if isinstance(exc, ProviderError) else "Provider response was invalid"
                            )

                    await asyncio.gather(*(discover(p) for p in self.discovery))
                    await stage("VERIFYING", "Checking field evidence, freshness and distinct identities")
                    if not self.settings.demo and self.settings.official_hosts:
                        try:
                            candidates.extend(await OfficialPages(self.settings).discover(candidates))
                        except (ProviderError, OSError, ValueError):
                            result.warnings.append("An official source could not be verified")
                    entities = [self.verifier.verify(c) for c in deduplicate(candidates)]
                    excluded = sum(e.verification_status == "UNVERIFIED" for e in entities)
                    if excluded:
                        result.warnings.append(
                            f"{excluded} discovery records lacked sufficient verified facts and were excluded"
                        )
                    entities = [e for e in entities if e.verification_status != "UNVERIFIED"]
                    for entity in entities:
                        if entity.facts.get("venue_id"):
                            entity.relationships.append(
                                EntityRelationship(
                                    type="TAKES_PLACE_AT",
                                    target_id="ticketmaster:venue:" + entity.facts["venue_id"],
                                    evidence_ids=[e.evidence_id for e in entity.sources if e.field == "venue_id"],
                                )
                            )
                        if entity.facts.get("ticket_url"):
                            entity.relationships.append(
                                EntityRelationship(
                                    type="TICKETS_SOLD_BY",
                                    target_id="ticketmaster:seller",
                                    evidence_ids=[e.evidence_id for e in entity.sources if e.field == "ticket_url"],
                                )
                            )
                        entity.merchant = resolve(entity, self.settings.merchant_mappings)
                    await stage("ENRICHING", "Evaluating illustrative card value and scheduling reachable stops")
                    catalog = self.catalog.catalog(customer.market, customer.segment, plan.city)
                    for entity in entities:
                        enrich(
                            entity,
                            catalog,
                            request.card_id,
                            request,
                            self.settings.now(),
                            self.settings.catalog_refresh_days,
                        )
                    # Alternatives are committed one-by-one so a late timeout can retain completed work.
                    result.alternatives = await schedule(
                        entities, plan, request, self.router, self.settings, result.warnings, result.alternatives
                    )
                    if not result.alternatives:
                        result.warnings.append(
                            "No feasible, verified stops were found for this destination and time window"
                        )
                    await stage("EXPLAINING", "Preparing explanations from permitted evidence")
                    facts = {
                        s.entity.entity_id: {
                            "entity_id": s.entity.entity_id,
                            "evidence_ids": s.evidence_ids,
                            "facts": s.entity.facts,
                            "score": s.score,
                        }
                        for a in result.alternatives
                        for s in a.stops
                    }
                    if facts:
                        try:
                            explanations = await self.llm.explain(list(facts.values()))
                            for a in result.alternatives:
                                for stop in a.stops:
                                    stop.explanation = explanations[stop.entity.entity_id]
                        except (ProviderError, KeyError):
                            result.warnings.append(
                                "Using deterministic explanations; generated explanations were unavailable"
                            )
                    result.status = "READY" if result.alternatives and not result.warnings else "PARTIAL"
            except asyncio.CancelledError:
                logging.getLogger("outing").info(json.dumps({"run_id": run_id, "cancelled": True}))
                raise
            except TimeoutError:
                result.warnings.append("The run deadline was reached; only completed results are shown")
            except ProviderError as exc:
                result.status = "ERROR"
                result.warnings.append(str(exc))
            except (ValueError, KeyError, TypeError, OSError):
                logging.getLogger("outing").warning("Outing stage failed; provider payload omitted")
                result.status = "ERROR"
                result.warnings.append("The outing could not be completed. Check configuration and try again.")
            finally:
                await queue.put(None)

        task = asyncio.create_task(work())
        last = time.monotonic()
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                sequence += 1
                logging.getLogger("outing").info(
                    json.dumps(
                        {"run_id": run_id, "stage": event[0], "elapsed_ms": round((time.monotonic() - last) * 1000)}
                    )
                )
                last = time.monotonic()
                yield PipelineEvent(
                    run_id=run_id, sequence=sequence, stage=event[0], timestamp=self.settings.now(), message=event[1]
                )
            await task
            try:
                check_consent()
            except ProviderError as exc:
                result.alternatives = []
                result.search_plan = None
                result.status = "ERROR"
                result.warnings = [str(exc)]
            result.warnings = list(dict.fromkeys(result.warnings))
            self.store.save(request.customer_id, result, context)
            yield PipelineEvent(
                run_id=run_id,
                sequence=sequence + 1,
                stage=result.status,
                timestamp=self.settings.now(),
                message="Outing processing complete",
                result=result,
            )
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
