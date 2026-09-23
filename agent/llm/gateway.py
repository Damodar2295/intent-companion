import json
import logging
import time

from agent.llm.contracts import LLMError, LLMRequest, LLMResult


class LLMGateway:
    def __init__(self, router, adapters, price_table=None):
        self.router, self.adapters = router, dict(adapters)
        self.price_table = price_table or {}

    async def invoke(self, request: LLMRequest) -> LLMResult:
        started = time.monotonic()
        route = self.router.resolve(request.operation, request.model_class)
        adapter = self.adapters.get(route.adapter)
        if adapter is None:
            raise LLMError("Selected model adapter is unavailable; no provider fallback was attempted")
        try:
            raw = await adapter.invoke(request, route)
            output = (
                request.response_schema.model_validate_json(raw.content)
                if isinstance(raw.content, str)
                else request.response_schema.model_validate(raw.content)
            )
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("Model output failed structured validation") from None
        latency = round((time.monotonic() - started) * 1000, 2)
        usage = {
            key: value
            for key, value in (raw.usage or {}).items()
            if key in {"input_tokens", "output_tokens", "total_tokens"} and type(value) is int and value >= 0
        }
        prices = self.price_table.get(route.model)
        cost = {}
        if prices and "input_tokens" in usage and "output_tokens" in usage:
            cost["estimated_cost"] = (
                usage["input_tokens"] * prices.get("input_per_million", 0)
                + usage["output_tokens"] * prices.get("output_per_million", 0)
            ) / 1_000_000
        # Do not serialize arbitrary caller metadata, messages, model output or endpoint details.
        logging.getLogger("llm").info(
            json.dumps(
                {
                    "operation": request.operation,
                    "adapter": route.adapter,
                    "model_class": route.model_class,
                    "latency_ms": latency,
                    "tokens": usage,
                    **cost,
                }
            )
        )
        return LLMResult(output=output, route=route, latency_ms=latency, usage=usage)
