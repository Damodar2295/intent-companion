"""Bounded rank fusion; raw BM25 and cosine scores are never added."""

import asyncio
import logging
import time

from agent.retrieval.contracts import RetrievalHit, VectorRecord
from agent.retrieval.filters import matches
from agent.retrieval.models import HybridHit, RetrievalResponse


def fuse(lexical, semantic, k, top_k):
    records, ranks, scores, labels, conflicts = {}, {}, {}, {}, set()
    for channel, hits in (("lexical", lexical), ("semantic", semantic)):
        seen = set()
        rank = 0
        for hit in hits:
            identity = hit.record.record_id
            old = records.get(identity)
            if old and (
                old.document_type != hit.record.document_type
                or old.searchable_text != hit.record.searchable_text
                or old.metadata != hit.record.metadata
            ):
                conflicts.add(identity)
            if identity in seen:
                continue
            seen.add(identity)
            rank += 1
            records[identity] = hit.record
            ranks.setdefault(identity, {})[channel] = rank
            scores.setdefault(identity, {})[channel] = hit.score
            labels.setdefault(identity, {})[channel] = hit.score_type
    merged = []
    for identity, record in records.items():
        if identity in conflicts:
            continue
        r = ranks[identity]
        merged.append(
            HybridHit(
                record_id=identity,
                document_type=record.document_type,
                searchable_text=record.searchable_text,
                metadata=record.metadata,
                rrf_score=sum(1 / (k + rank) for rank in r.values()),
                **{f"{name}_rank": r.get(name) for name in ("lexical", "semantic")},
                **{f"{name}_score": scores[identity].get(name) for name in ("lexical", "semantic")},
                **{f"{name}_score_type": labels[identity].get(name) for name in ("lexical", "semantic")},
            )
        )
    return sorted(merged, key=lambda hit: (-hit.rrf_score, hit.record_id))[:top_k], len(conflicts), len(records)


class HybridRetriever:
    def __init__(self, store, embeddings, settings, reranker=None):
        self.store, self.embeddings, self.settings, self.reranker = store, embeddings, settings, reranker
        self.semaphore = asyncio.Semaphore(settings.retrieval_concurrency)

    async def search(self, request, market):
        started = time.monotonic()
        f = request.filters
        filters = {
            "market": market,
            "source_type": "SYNTHETIC",
            "_fresh_at": self.settings.now().isoformat(),
            "_valid_on": str(f.valid_on or self.settings.now().date()),
        }
        for name in ("city", "category", "segment"):
            if getattr(f, name) is not None:
                filters[name] = getattr(f, name)
        if f.document_types:
            filters["_types"] = f.document_types
        if f.product_ids:
            filters["_products"] = f.product_ids
        warnings, timings, states, channels = [], {}, {}, {}
        tasks = []

        async def branch(name):
            begin = time.monotonic()
            try:
                async with self.semaphore:
                    if name == "lexical":
                        hits = await self.store.lexical_search(request.query, filters, request.candidate_k)
                    else:
                        vectors = await self.embeddings.embed([request.query])
                        if len(vectors) != 1:
                            raise ValueError("Invalid query vector count")
                        hits = await self.store.semantic_search(tuple(vectors[0]), filters, request.candidate_k)
                    # Defense in depth for injected stores: never return a record violating the hard filters.
                    channels[name] = [
                        h
                        for h in hits[: request.candidate_k]
                        if matches(h.record.document_type, h.record.metadata, filters)
                    ]
                    states[name] = "SUCCEEDED"
            except asyncio.CancelledError:
                states[name] = "CANCELLED"
                raise
            except Exception:  # noqa: BLE001 — provider isolation; no raw exception or query in diagnostics
                states[name] = "FAILED"
            finally:
                timings[name] = round((time.monotonic() - begin) * 1000, 2)

        try:
            tasks.append(asyncio.create_task(branch("lexical")))
            if self.embeddings is not None:
                tasks.append(asyncio.create_task(branch("semantic")))
            else:
                states["semantic"] = "DISABLED"
            _, pending = await asyncio.wait(tasks, timeout=self.settings.retrieval_timeout)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for name in ("lexical", "semantic"):
                if states.get(name) == "CANCELLED":
                    states[name] = "TIMED_OUT"
                if states.get(name) != "SUCCEEDED":
                    warnings.append(f"{name} retrieval {states.get(name, 'unavailable').lower()}.")
            hits, conflicts, unique = fuse(
                channels.get("lexical", []), channels.get("semantic", []), self.settings.retrieval_rrf_k, request.top_k
            )
            if conflicts:
                warnings.append("Conflicting versions of identical record IDs were suppressed.")
            available = {key for key, state in states.items() if state == "SUCCEEDED"}
            mode = (
                "hybrid"
                if len(available) == 2
                else "lexical_only"
                if "lexical" in available
                else "semantic_only"
                if available
                else "unavailable"
            )
            rerank_state = "DISABLED"
            if self.reranker is not None and hits:
                try:
                    rerank_state = "SUCCEEDED"
                    source = [
                        RetrievalHit(
                            VectorRecord(h.record_id, h.document_type, h.searchable_text, (), h.metadata),
                            h.rrf_score,
                            "rrf",
                        )
                        for h in hits
                    ]
                    reranked = await asyncio.wait_for(
                        self.reranker.rerank(request.query, source, min(request.top_k, self.settings.reranker_top_k)),
                        timeout=self.settings.retrieval_timeout,
                    )
                    by_id = {h.record_id: h for h in hits}
                    hits = []
                    for candidate in reranked:
                        original = by_id.get(candidate.record.record_id)
                        if original is None:
                            continue
                        original.reranker_score = candidate.score
                        original.reranker_score_type = candidate.score_type
                        original.acceptance = (
                            "ACCEPTED" if candidate.score >= self.settings.reranker_threshold else "BELOW_THRESHOLD"
                        )
                        original.acceptance_reason = (
                            "Reranker score meets configured threshold."
                            if original.acceptance == "ACCEPTED"
                            else "Reranker score is below configured threshold."
                        )
                        hits.append(original)
                except TimeoutError:
                    rerank_state = "TIMED_OUT"
                    warnings.append("reranking timed out; fused ordering retained.")
                except Exception:  # noqa: BLE001 — isolate reranker failures without raw provider output
                    rerank_state = "FAILED"
                    warnings.append("reranking failed; fused ordering retained.")
            else:
                for hit in hits:
                    hit.acceptance_reason = "No reranker is configured; no acceptance decision was made."
            status = (
                "PARTIAL"
                if warnings and (hits or available)
                else ("READY" if hits else "EMPTY" if available else "ERROR")
            )
            debug = {
                "rrf_k": self.settings.retrieval_rrf_k,
                "top_k": request.top_k,
                "candidate_k": request.candidate_k,
                "channels": states,
                "latency_ms": timings,
                "returned": len(hits),
                "merged_unique": unique,
                "conflicting_records": conflicts,
                "filtered_lexical_candidates": len(channels.get("lexical", [])),
                "filtered_semantic_candidates": len(channels.get("semantic", [])),
                "reranker": rerank_state,
                "reranker_threshold": self.settings.reranker_threshold,
                "filters": filters,
            }
            return RetrievalResponse(
                status=status,
                mode=mode,
                embedding_kind=self.settings.embedding_mode,
                hits=hits,
                warnings=warnings,
                debug=debug if request.debug else None,
            )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            logging.getLogger("retrieval").info(
                "hybrid_retrieval latency_ms=%.2f channels=%s", (time.monotonic() - started) * 1000, states
            )
