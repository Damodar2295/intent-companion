# Phase 3 — persistent ingestion

This phase adds normalization, record-specific searchable text, embedding generation through an injected interface, atomic vector/metadata upserts, document versions and index statistics. Customer retrieval stays on its existing SQLite repositories. Hybrid retrieval and reranking are not activated.

## Infrastructure decision and limits

The local Python environment provides SQLite FTS5 but no configured SafeChain/BGE embedding service or approved vector database client. `SQLiteVectorStore` implements the existing VectorStore contract using persistent SQLite tables, FTS5 lexical search and exact cosine scans over stored vectors. This is a local vector retrieval layer; it is not an ANN index or a claim of enterprise-scale performance. No runtime dependency was added.

`EMBEDDING_MODE=disabled` is the default. Ingestion returns an actionable error in this mode; startup never embeds automatically. `EMBEDDING_MODE=openai` now selects a real OpenAI embedding adapter using the existing OPENAI_API_KEY and an explicitly configured EMBEDDING_MODEL. Explicit `test_hash` mode uses the Phase 1 deterministic hashed-token adapter. Its vectors are NOT semantic embeddings, scores are labeled `test_hash_cosine`, and index statistics report `semantic_quality_verified: false`. No semantic-quality or reranker-lift claim is made. Unsupported embedding modes fail configuration without substituting test vectors.

An approved enterprise EmbeddingService can be injected into IngestionService alongside an IngestionStore. The latter extends VectorStore with fingerprints and statistics. An enterprise store must atomically publish a batch, enforce a single embedding space/dimension, maintain content versions and support deletion. Use an embedding-space identifier that includes the model revision and dimensions. Register concrete adapters at composition; no SafeChain internals, model endpoints or credentials are invented here. Non-synthetic provider storage needs an explicit retention/policy implementation before expanding the current synthetic-only storage guard.

## Input and normalization

`seed_documents` validates the Phase 2 catalog and knowledge bundle before generating documents for cards, benefits, offers, rewards, merchants, places, events and AMEX experiences. Customers and intent signals are not indexed. JSON is read only by the ingestion CLI; runtime index reads query SQLite.

Each typed record is one standalone document, limited to 16,000 characters. These small structured records do not need arbitrary text chunking. Conditions, product applicability and values remain together. Unicode NFKC and whitespace normalization produce labeled search text rather than embedding raw JSON. Event keys include their original event IDs, so recurring events and same-name venues remain separate. Descriptive linked product and venue names are resolved from the validated input.

Metadata retains applicable source IDs, synthetic labels, completeness, market, category, city, product/merchant/venue/event relationships, validity, freshness, monetary values, currencies and explicit relationship evidence. Knowledge sources retain their original retrieval/verification/expiry timestamps and attribution. Existing catalog verification is date-granular and labeled as such; ingestion never refreshes verification timestamps or invents a provider retrieval time. Catalog expiry is the earlier of the configured catalog TTL or the exclusive validity end; experience expiry also respects validity end. Unknown fields stay unknown. Freshness metadata is not evidence that a record is currently usable: later retrieval must apply time/eligibility checks.

## Persistence and versioning

- Default: additive `retrieval_documents`, `retrieval_config` and `retrieval_fts` tables in DATABASE_PATH. RETRIEVAL_DATABASE_PATH optionally isolates the index. Existing catalog/preferences tables are untouched.
- A deterministic content hash includes normalized text, metadata, normalization version and a source-record hash. Provenance or source changes therefore invalidate the fingerprint even when visible text is unchanged.
- Unchanged records skip embedding and keep their version. Changed records increment their persisted document_version; the current version is retained, not a historical archive.
- Embeddings are generated in batches of 64, within a 60-second async deadline, before a single atomic publish. Cancellation or embedding failure before publish leaves the index unchanged. SQL failures roll back both documents and FTS changes.
- Finite, nonzero vectors, consistent dimensions and a fixed embedding space are required. Use a new database when changing the embedding model/revision/dimensions; vectors are never silently mixed.
- At most 10,000 records are accepted per run. Ingestion is an upsert, not an authoritative sync: records omitted from a later input are not deleted. Explicit VectorStore.delete removes both vectors and FTS rows. Synthetic expired records can remain for testing; no live Places/page payload cache is introduced.
- API diagnostics expose counts and adapter labels, not database paths, raw source text, credentials or customer details.

## Run locally

From the application root, choose a local index and opt into test embeddings explicitly:

```sh
.venv/bin/python -m scripts.ingest_catalog \
  --database /tmp/intent-companion-phase3.sqlite3 \
  --embedding-mode test_hash
```

The supplied fixtures produce **44 documents**: 3 cards, 9 benefits, 6 offers, 6 rewards, 8 merchants, 3 places, 6 events and 3 experiences. A repeat run reports 44 unchanged and zero newly embedded. This corpus validates infrastructure, not semantic retrieval quality. `--directory` accepts another validated seed directory. No provider network calls are made.

To inspect that index through the running application, configure `RETRIEVAL_DATABASE_PATH` to the same path before startup. `EMBEDDING_MODE` may remain disabled when only reading statistics. Alternatively omit `--database` to use the application's configured storage; the CLI reads process environment variables through Settings.from_env. It does not load a .env file automatically.

## API / Postman

`GET /api/infrastructure/index` (also `/infrastructure/index`) returns:

```json
{
  "backend": "sqlite-exact-cosine-fts5",
  "records": 44,
  "by_type": {"card": 3, "benefit": 9, "offer": 6, "reward": 6, "merchant": 8, "place": 3, "event": 6, "experience": 3},
  "embedding_space": {"name": "test-hash-v1:64", "dimensions": 64},
  "embedding_mode": "disabled",
  "semantic_quality_verified": false,
  "scope": "synthetic-ingestion-only",
  "customer_retrieval_enabled": false
}
```

The response also includes last_updated_at (index write time, not source verification time). Empty indexes report zero records and null embedding_space. Storage errors return a safe 503. The Postman Infrastructure folder verifies this endpoint. Ingestion is an operator CLI operation; there is no unauthenticated HTTP file-reading or mutation endpoint.

## Verification

`tests/test_ingestion.py` covers persistence/reopen, repeat-run idempotence, changed-document versions, reference-preserving search text, filters, deletion, invalid vectors, model-space mismatches, disabled mode, non-synthetic rejection, cancellation, embedding failure, database rollback and API statistics/errors. Existing Postman scripts run against isolated storage. Mocked transports cover the real adapter protocol, response ordering, malformed vectors, missing configuration, access failures, retries and cancellation. See the real-embedding section below for live-smoke instructions; no enterprise database is claimed.


## Real OpenAI embeddings (Phase 3 extension)

OpenAIEmbeddingAdapter implements the same EmbeddingService interface and uses HTTPX, with no new SDK dependency. Model selection stays in configuration. It follows the [official embeddings API guide](https://developers.openai.com/api/docs/guides/embeddings): text input, configured model, float vectors and optional output dimensions. A working example model is `text-embedding-3-small`; availability still depends on the configured account.

```sh
# OPENAI_API_KEY must already be set in the process environment; do not put it in source control.
EMBEDDING_MODEL=text-embedding-3-small .venv/bin/python -m scripts.ingest_catalog \
  --database var/openai-embeddings.sqlite3 --embedding-mode openai
```

Use a separate index from test_hash. The persisted embedding-space identifier binds the provider endpoint fingerprint, configured model and requested dimensions; mismatched indexes fail before embedding. Model responses must name the configured model and contain exactly one indexed, finite, nonzero vector for every input. Out-of-order rows are reordered by index. Unknown/rejected configurations and failed authentication never fall back to fake vectors. Existing vectors are retained on failure.

Requests are bounded to 16 texts per HTTP batch, two concurrent requests per adapter, configurable per-request timeout and at most two transient retries. Empty inputs or documents over 8192 UTF-8 bytes fail explicitly without truncation. The byte bound is conservative and does not claim exact token counting. The existing 60-second ingestion deadline still applies. Provider response bodies, source texts and credentials are excluded from adapter logs; available token usage and timing are logged.

To point application diagnostics at the resulting index, configure:

```dotenv
EMBEDDING_MODE=openai
EMBEDDING_MODEL=text-embedding-3-small
RETRIEVAL_DATABASE_PATH=var/openai-embeddings.sqlite3
```

`EMBEDDING_DIMENSIONS` applies only to test_hash. `EMBEDDING_OUTPUT_DIMENSIONS` is optional for real models that support the API dimensions parameter; omit it for native model dimensions. `EMBEDDING_ENDPOINT` and `EMBEDDING_TIMEOUT_SECONDS` are also configurable. Neither API key nor endpoint credentials are stored in the index. `embedding_kind: model` distinguishes model vectors from test vectors, while `semantic_quality_verified` remains false until corpus evaluation is performed. Actual embeddings do not by themselves establish recommendation quality or activate hybrid customer retrieval.

Live-smoke verification completed on 2026-09-23 after explicit user approval to send the synthetic catalog to OpenAI. The configured `text-embedding-3-small` endpoint generated and persisted all 44 documents in `var/openai-embeddings.sqlite3`, each with 1,536 finite, nonzero vector values. All document versions remain 1. Vector norms range from 0.999524 to 1.000450; cosine retrieval normalizes them during scoring.

Three real query embeddings verified filtered retrieval: the restaurant-savings query ranked Dining credit first, the gallery query ranked Gallery admission credit first, and the Rome event query returned the two distinct recurring Rome events. Repeat ingestion skipped all 44 documents with zero embedding calls. The read-only index API independently returned 44 model records and 1,536 dimensions. Detailed scores and checks are in the local `var/embedding-verification.json` report.

This is a live integration smoke test, not calibrated quality evaluation. `semantic_quality_verified` remains false and customer retrieval remains unchanged. The index and report are local ignored artifacts; no credentials are stored in them.
