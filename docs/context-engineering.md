# Phase 9: context engineering

`POST /api/v1/context/build` builds a bounded context package from explicitly supplied messages and evidence. It is deterministic and does not call an LLM. The endpoint is intended for later grounded explanation/planning stages; existing response generation is unchanged.

Context construction keeps system messages, recent conversation turns and evidence explicitly referenced by message `evidence_ids`. Unreferenced evidence is excluded. Duplicate messages are removed. If the estimated token budget is exceeded, lower-priority non-system messages are pruned first; an oversized system message is deterministically truncated only as a final fallback. The estimate is a conservative word-based approximation and is reported as an estimate, not provider token accounting.

Request limits are 100 messages, 200 evidence records, 12,000 characters per message and a 128–12,000 token budget. `preserve_last_messages` controls the recent-turn window. Diagnostics include input/output counts, dropped messages, estimated input/output tokens and compression ratio when `debug` is true. No raw customer profile, card data or hidden catalog is added by the builder.

Consent and preference context are checked before and after construction. Withdrawal returns 403; changed context returns 409. The output status is READY or PARTIAL (when pruning/truncation warnings exist). This phase performs no retrieval, reranking, eligibility, savings or final prose generation. It does not claim that estimates equal model tokenizer usage.

The future LLM/context caller should pass the returned messages through the existing `LLMGateway`; provider adapters remain outside this package. No conversation persistence or semantic cache is introduced in this phase.
