# Architecture and implementation decisions

This adapts the copied FastAPI / React / LangGraph boilerplate into a modular monolith. The original reference project is untouched. CRM, autonomous tool loops, embedding retrieval, enterprise deployment templates and their unrelated tests are removed from the copied app. Its application initialization, factory and graph boundaries remain.

Runtime: Python 3.11+, FastAPI, Pydantic v2, LangGraph fixed workflow, SQLite; React 19 + TypeScript + Vite. SQLite replaces vector retrieval because the authoritative synthetic catalog is structured. No live product facts, financial decisions, external submissions or customer data are used.

Implementation order: contracts and seed fixtures → repositories → consent and intent → catalog matching and value calculation → guarded AI adapter and graph → API and frontend → tests and documentation.

The graph runs guard → retrieve/filter → calculate → rank → compose. There are no agent loops or side-effectful model tools. Detection is a separately callable service before experience generation. A stored intent is revalidated against current consent, signal expiry and preference suppression at activation time.

Domain models live in agent/domain.py. Services in agent/intent_engine.py, customer_context.py, matching.py and value_calculation.py depend on repository interfaces. agent/ai.py owns optional transport and validates model choices. agent/orchestration.py carries evidence through the graph. agent/main.py exposes thin routes; initialize.py and factory.py construct and close dependencies.

Catalog facts, acceptance, rule outcomes and Decimal value calculations never come from the LLM. Only existing candidate and evidence IDs can cross back from that boundary. Deterministic rendering supplies all factual wording. Unavailable or invalid AI returns the same safe deterministic experience, labeled with a fallback reason.

SQLite stores customers, signals, intents, typed catalog records and audit experiences. JSON fixtures under data are versioned synthetic sources; startup inserts once and never overwrites preferences. Evidence snapshots remain auditable after catalog edits. No request/profile bodies or model secrets are logged. This is a localhost-only single-user demo, not an authenticated multi-tenant service.
