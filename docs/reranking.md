# Phase 8: reranking and thresholding

Phase 8 extends `POST /api/v1/retrieval/search` after Phase 7 fusion. A configured `RerankerService` receives only the bounded, filtered RRF candidates. It returns a separate reranker score and ordering; raw lexical, semantic and RRF scores remain intact. Scores are never summed across incompatible scales.

The local `test_hash` reranker is a deterministic token-overlap test double. It is labeled as such and is not semantic quality evidence. The default `disabled` mode retains fused ordering and marks each result `NOT_RERANKED`. A reranker failure or timeout retains fused results with `PARTIAL` status and a fixed warning; it never becomes a silent acceptance.

`RERANKER_THRESHOLD` (default `0.25`) controls retrieval acceptance only. A result is `ACCEPTED` when its configured reranker score meets the threshold, otherwise `BELOW_THRESHOLD`. With no reranker, no acceptance decision is made. These labels do not establish card eligibility, offer validity, merchant identity, opening status, availability, savings or a customer-facing recommendation. Those deterministic business checks remain later pipeline stages.

Debug output includes reranker state, threshold and per-hit `reranker_score`/`reranker_score_type`, alongside lexical, semantic and RRF diagnostics. It does not expose provider payloads, customer identifiers or raw input. Candidate and result limits remain bounded by Phase 7.

Configuration:

- `RERANKER_MODE=disabled|test_hash`
- `RERANKER_THRESHOLD=0.25`
- `RERANKER_TOP_K=20`

Enterprise reranking is an injection seam through the existing `RerankerService` protocol. No BGE or other private deployment is invented. No live reranker request was made in this phase.
