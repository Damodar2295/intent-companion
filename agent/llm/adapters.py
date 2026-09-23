"""Only this module contains model wire protocols and model authentication."""

import inspect
from urllib.parse import urlparse

import httpx

from agent.llm.contracts import AdapterOutput, LLMError
from agent.outing.providers import ProviderError


def strict_schema(model):
    schema = model.model_json_schema()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            node.pop("default", None)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return schema


class MockLLMAdapter:
    """Explicit operation fixtures; no network and no automatic production fallback."""

    def __init__(self, handlers=None):
        self.handlers = dict(handlers or {})

    async def invoke(self, request, route):
        handler = self.handlers.get(request.operation)
        if handler is None:
            raise LLMError("No mock fixture configured for this operation")
        content = handler(request) if callable(handler) else handler
        if inspect.isawaitable(content):
            content = await content
        return AdapterOutput(content=content)


class ChatCompletionsAdapter:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    async def invoke(self, request, route):
        s = self.settings
        if not (s.llm_endpoint and route.model and s.llm_api_key):
            raise LLMError("LLM configuration is incomplete; deterministic fallback is available")
        url = urlparse(s.llm_endpoint)
        if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}):
            raise LLMError("LLM endpoint must use HTTPS or localhost")
        try:
            async with httpx.AsyncClient(timeout=s.llm_timeout, transport=self.transport, trust_env=False) as client:
                response = await client.post(
                    s.llm_endpoint,
                    headers={"Authorization": f"Bearer {s.llm_api_key}"},
                    json={
                        "model": route.model,
                        "messages": request.messages,
                        "response_format": {"type": "json_object"},
                        "store": False,
                    },
                )
                response.raise_for_status()
                body = response.json()
                usage = body.get("usage", {})
                return AdapterOutput(
                    content=body["choices"][0]["message"]["content"],
                    usage={
                        "input_tokens": usage.get("prompt_tokens", 0),
                        "output_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise LLMError("LLM unavailable or output failed validation") from None


class ResponsesAdapter:
    def __init__(self, transport, settings):
        self.http, self.settings = transport, settings

    async def invoke(self, request, route):
        if not self.settings.openai_key or not route.model:
            raise LLMError("Configure OPENAI_API_KEY and OPENAI_MODEL to plan live outings")
        url = urlparse(self.settings.responses_endpoint)
        if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}):
            raise LLMError("LLM endpoint must use HTTPS or localhost")
        try:
            response = await self.http.json(
                "openai",
                "POST",
                self.settings.responses_endpoint,
                headers={"Authorization": f"Bearer {self.settings.openai_key}"},
                json={
                    "model": route.model,
                    "store": False,
                    "max_output_tokens": 1800,
                    "input": request.messages,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": request.response_schema.__name__,
                            "strict": True,
                            "schema": strict_schema(request.response_schema),
                        }
                    },
                },
            )
            content = "".join(
                part["text"]
                for item in response.get("output", [])
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            return AdapterOutput(content=content, usage=response.get("usage", {}))
        except (ProviderError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise LLMError("LLM unavailable or output failed validation") from None
