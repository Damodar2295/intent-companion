"""Fixed tool selection, bounded parallel execution, no recursive/model-directed calls."""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from pydantic import TypeAdapter

from agent.domain import CatalogItem
from agent.outing.models import DiscoveryCandidate
from agent.outing.persistence import context_version
from agent.providers.contracts import CapabilityUnavailable, CatalogQuery
from agent.tools.models import ExecutionResult, ToolOutput, ToolTrace

CANDIDATES = TypeAdapter(list[DiscoveryCandidate])
CATALOG = TypeAdapter(list[CatalogItem])


@dataclass(frozen=True)
class ToolBinding:
    invoke: Callable[..., Awaitable[list]]
    discovery: bool


def select_tools(plan):
    names = []
    if plan.requires_real_world_discovery:
        if set(plan.categories) - {"EVENT"}:
            names.append("places")
        if "EVENT" in plan.categories:
            names.extend(["events", "web"])
        if "EXPERIENCE" in plan.categories and plan.requires_amex_value:
            names.append("amex_experiences")
    if plan.requires_amex_value:
        names.extend(["cards", "benefits", "offers", "rewards"])
        if plan.requires_real_world_discovery:
            names.append("merchants")
    return names


class ToolOrchestrator:
    def __init__(self, repository, planner, bindings, settings, mode):
        self.repository, self.planner, self.bindings = repository, planner, dict(bindings)
        self.settings, self.mode = settings, mode
        # Application-wide limit, not merely a separate allowance for each request.
        self.semaphore = asyncio.Semaphore(settings.tool_concurrency)

    async def execute(self, request):
        result = ExecutionResult(run_id=str(uuid4()), status="ERROR", mode=self.mode)
        customer = self.repository.customer(request.customer_id)
        snapshot = context_version(customer)
        if not request.consent.allowed or not customer.consent.allowed:
            raise HTTPException(403, "Personalization consent is missing or withdrawn.")
        deadline = time.monotonic() + self.settings.tool_run_deadline
        tasks = []
        run_expired = False

        def check_context():
            current = self.repository.customer(request.customer_id)
            if not current.consent.allowed:
                raise HTTPException(403, "Personalization consent was withdrawn during execution.")
            if context_version(current) != snapshot:
                raise HTTPException(409, "Preferences changed during execution; start again.")

        def log(trace):
            logging.getLogger("tools").info(
                json.dumps({"event": "tool_invocation", "run_id": result.run_id, **trace.model_dump(mode="json")})
            )

        planning_trace = ToolTrace(tool="search_plan", sequence=1, status="RUNNING", started_at=datetime.now(UTC))
        result.trace.append(planning_trace)
        started = time.monotonic()
        try:
            try:
                async with asyncio.timeout(max(0, deadline - time.monotonic())):
                    result.planning = await self.planner.plan(request)
                check_context()
                planning_trace.status = "SUCCEEDED"
            except TimeoutError:
                planning_trace.status = "TIMED_OUT"
                planning_trace.message = "Run deadline reached during planning."
                return result
            except asyncio.CancelledError:
                planning_trace.status = "CANCELLED"
                raise
            except Exception:
                planning_trace.status = "FAILED"
                planning_trace.message = "Planning failed."
                raise
            finally:
                planning_trace.finished_at = datetime.now(UTC)
                planning_trace.latency_ms = round((time.monotonic() - started) * 1000, 2)
                log(planning_trace)
            if result.planning.status == "CLARIFICATION_REQUIRED":
                result.status = "CLARIFICATION_REQUIRED"
                return result
            plan = result.planning.search_plan
            if plan.requires_routing:
                result.deferred["routing"] = "Requires verified, ordered stops; not executed during discovery."
            query = CatalogQuery(customer.market, customer.segment, plan.destination or "global")
            names = select_tools(plan)

            async def invoke(name, trace):
                queued = time.monotonic()
                active = None
                try:
                    async with self.semaphore:
                        trace.queue_ms = round((time.monotonic() - queued) * 1000, 2)
                        check_context()
                        active = time.monotonic()
                        trace.started_at, trace.status = datetime.now(UTC), "RUNNING"
                        binding = self.bindings.get(name)
                        if binding is None:
                            raise CapabilityUnavailable()
                        async with asyncio.timeout(self.settings.tool_timeout):
                            raw = await binding.invoke(
                                plan.outing.model_copy(deep=True) if binding.discovery else query
                            )
                        check_context()
                        # Reject invalid results rather than exposing arbitrary provider payloads.
                        rows = (CANDIDATES if binding.discovery else CATALOG).validate_python(raw)
                        trace.truncated = len(rows) > self.settings.tool_result_limit
                        rows = rows[: self.settings.tool_result_limit]
                        trace.result_count = len(rows)
                        trace.status = "SUCCEEDED" if rows else "EMPTY"
                        return ToolOutput(
                            tool=name,
                            candidates=rows if binding.discovery else [],
                            catalog=[] if binding.discovery else rows,
                            usage="DISCOVERY_ONLY" if binding.discovery else "ILLUSTRATIVE_CATALOG_NOT_ELIGIBILITY",
                        )
                except CapabilityUnavailable:
                    trace.status, trace.message = "UNAVAILABLE", "Provider is not configured."
                except TimeoutError:
                    trace.status, trace.message = "TIMED_OUT", "Tool deadline reached."
                except asyncio.CancelledError:
                    trace.status, trace.message = (
                        ("TIMED_OUT", "Run deadline reached.") if run_expired else ("CANCELLED", "Execution cancelled.")
                    )
                    raise
                except HTTPException:
                    trace.status, trace.message = "CANCELLED", "Customer context changed."
                    raise
                except Exception:  # noqa: BLE001 — isolate provider failures with a fixed safe message
                    # Provider exceptions may contain URLs, keys, or customer text: never echo them.
                    trace.status, trace.message = "FAILED", "Provider failed or returned an invalid result."
                finally:
                    trace.finished_at = datetime.now(UTC)
                    if active is not None:
                        trace.latency_ms = round((time.monotonic() - active) * 1000, 2)
                    else:
                        trace.queue_ms = round((time.monotonic() - queued) * 1000, 2)
                    log(trace)
                return None

            for index, name in enumerate(names):
                trace = ToolTrace(tool=name, sequence=index + 2, status="QUEUED")
                result.trace.append(trace)
                if index >= self.settings.tool_max_calls:
                    trace.status, trace.message = "SKIPPED", "Tool invocation budget reached."
                    trace.finished_at = datetime.now(UTC)
                    log(trace)
                else:
                    tasks.append(asyncio.create_task(invoke(name, trace)))
            if tasks:
                done, pending = await asyncio.wait(
                    tasks, timeout=max(0, deadline - time.monotonic()), return_when=asyncio.FIRST_EXCEPTION
                )
                # Consent/context exceptions abort siblings and discard every result.
                for task in done:
                    task.result()
                run_expired = bool(pending)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                result.outputs = [task.result() for task in tasks if not task.cancelled() and task.result() is not None]
            check_context()
            unsuccessful = any(t.status in {"FAILED", "UNAVAILABLE", "TIMED_OUT", "SKIPPED"} for t in result.trace)
            result.status = (
                ("PARTIAL" if result.outputs else "ERROR")
                if unsuccessful
                else ("READY" if any(o.candidates or o.catalog for o in result.outputs) else "EMPTY")
            )
            return result
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
