"""OpenAI embedding wire adapter. No generative model or customer input is involved."""

import asyncio
import hashlib
import json
import logging
import math
import time
from urllib.parse import urlparse

import httpx


class EmbeddingError(Exception):
    """Safe provider/configuration failure; never includes response bodies or credentials."""


class OpenAIEmbeddingAdapter:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport
        self.semaphore = asyncio.Semaphore(2)
        url = urlparse(settings.embedding_endpoint)
        if (
            (url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}))
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise EmbeddingError(
                "Embedding endpoint must use HTTPS or localhost without URL credentials or query parameters"
            )
        if not settings.embedding_model.strip():
            raise EmbeddingError("Configure EMBEDDING_MODEL before selecting openai embeddings")
        endpoint_id = hashlib.sha256(settings.embedding_endpoint.encode()).hexdigest()[:12]
        dimensions = settings.embedding_output_dimensions or "default"
        self.embedding_space = f"openai:{settings.embedding_model}:{dimensions}:{endpoint_id}"

    async def embed(self, texts):
        if not self.settings.embedding_api_key:
            raise EmbeddingError("Configure OPENAI_API_KEY for openai embeddings")
        if not texts:
            return []
        # Conservative byte bounds avoid silently truncating input without adding a tokenizer dependency.
        if any(not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 8192 for text in texts):
            raise EmbeddingError("Embedding input must be nonblank and at most 8192 UTF-8 bytes per document")
        result = []
        async with httpx.AsyncClient(
            timeout=self.settings.embedding_timeout, transport=self.transport, trust_env=False, follow_redirects=False
        ) as client:
            for offset in range(0, len(texts), 16):
                batch = texts[offset : offset + 16]
                result.extend(await self._batch(client, batch))
        return result

    async def _batch(self, client, texts):
        payload = {"model": self.settings.embedding_model, "input": texts, "encoding_format": "float"}
        if self.settings.embedding_output_dimensions is not None:
            payload["dimensions"] = self.settings.embedding_output_dimensions
        started = time.monotonic()
        for attempt in range(3):
            try:
                async with self.semaphore:
                    response = await client.post(
                        self.settings.embedding_endpoint,
                        headers={"Authorization": f"Bearer {self.settings.embedding_api_key}"},
                        json=payload,
                    )
                if (response.status_code == 429 or response.status_code >= 500) and attempt < 2:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                if response.status_code in {401, 403}:
                    raise EmbeddingError("Embedding access denied; check OPENAI_API_KEY and model permissions")
                if response.status_code == 400:
                    raise EmbeddingError(
                        "Embedding request rejected; check EMBEDDING_MODEL, dimensions and input limits"
                    )
                response.raise_for_status()
                body = response.json()
                vectors = self._validate(body, len(texts))
                usage = body.get("usage", {})
                usage = (
                    {
                        k: v
                        for k, v in usage.items()
                        if k in {"prompt_tokens", "total_tokens"} and type(v) is int and v >= 0
                    }
                    if isinstance(usage, dict)
                    else {}
                )
                logging.getLogger("embeddings").info(
                    json.dumps(
                        {
                            "provider": "openai",
                            "operation": "embedding",
                            "documents": len(texts),
                            "dimensions": len(vectors[0]),
                            "tokens": usage,
                            "retry_count": attempt,
                            "latency_ms": round((time.monotonic() - started) * 1000),
                        }
                    )
                )
                return vectors
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < 2:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                raise EmbeddingError("Embedding provider timed out or is unreachable") from None
            except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
                raise EmbeddingError("Embedding provider unavailable or returned invalid vectors") from None
        raise EmbeddingError("Embedding provider unavailable")

    def _validate(self, body, count):
        rows = body["data"]
        if not isinstance(rows, list) or len(rows) != count:
            raise ValueError("Wrong vector count")
        if body.get("model") != self.settings.embedding_model:
            raise ValueError("Unexpected embedding model")
        if any(type(row.get("index")) is not int for row in rows):
            raise ValueError("Invalid embedding index")
        if {row["index"] for row in rows} != set(range(count)):
            raise ValueError("Missing or duplicate embedding index")
        ordered = sorted(rows, key=lambda row: row["index"])
        dimensions = self.settings.embedding_output_dimensions or len(ordered[0]["embedding"])
        if dimensions < 1:
            raise ValueError("Empty embedding")
        result = []
        for row in ordered:
            vector = row["embedding"]
            if (
                not isinstance(vector, list)
                or len(vector) != dimensions
                or any(type(v) not in {float, int} or not math.isfinite(v) for v in vector)
                or not any(vector)
            ):
                raise ValueError("Invalid embedding")
            result.append(tuple(float(v) for v in vector))
        return result
