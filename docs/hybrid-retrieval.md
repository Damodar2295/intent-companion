# Phase 7: hybrid retrieval

`POST /api/v1/retrieval/search` queries the existing typed SQLite retrieval index. It is a retrieval/debug endpoint, not a recommendation or eligibility endpoint. The runtime never reads seed JSON files.

The pipeline applies hard metadata predicates before returning lexical or semantic candidates: market, source type, city, category, segment, document type, product IDs, freshness and validity date. It then runs FTS5 lexical search and, when an embedding adapter is configured, exact cosine semantic search concurrently. The channels are merged by reciprocal rank fusion:

`RRF(record) = Σ 1 / (rrf_k + channel_rank)`

Raw BM25 and cosine scores are preserved separately and are never added. Canonical record IDs deduplicate the channels. Conflicting representations of one ID are suppressed. `top_k` and `candidate_k` are bounded by the request schema; later reranking is intentionally absent until Phase 8.

The response contains `READY`, `EMPTY`, `PARTIAL` or `ERROR`, the retrieval mode, typed hits, warnings and optional debug details. Debug data includes channel status, timings, hard filters, candidate counts, RRF constant and conflict count. Safe logs contain timing and channel state only; no customer ID, query, coordinates, provider body or credentials. A failed semantic branch can leave a lexical-only partial result. Disabled embeddings are reported explicitly. Test-hash embeddings are labeled test quality; the existing OpenAI adapter is used only when explicitly configured.

Request consent and the customer profile are checked before and after retrieval. Preference/consent context changes return 409/403. Precise coordinates and card identifiers are not sent to the retrieval service. Hits retain source metadata and synthetic labels but do not prove eligibility, availability, savings or recommendation acceptance.

Configuration:

- `RETRIEVAL_RRF_K=60`
- `RETRIEVAL_TIMEOUT_SECONDS=10`
- `RETRIEVAL_CONCURRENCY=4`

The existing `/infrastructure/index` endpoint remains read-only. Ingestion and index statistics are unchanged. No reranker, business validation, cache or customer-specific vector index is introduced in this phase.

All external behavior is tested with SQLite/test-vector doubles; no live provider or embedding request was made for this phase.
