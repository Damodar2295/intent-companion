# Phase 20 release gate

The local release gate covers the consumer, member, small-business and outing journeys, including streamed planning, bounded edits, grounded responses, diagnostics, readiness checks, consent invalidation, provider failures, cancellation and short-lived retention.

The verified local baseline is 301 backend tests and 17 frontend tests, plus Ruff, ESLint, TypeScript compilation, Vite production build, Postman collection execution and JSON validation. The remaining warning is the existing Starlette `BlockingPortal` deprecation from the installed test dependency.

Realtime provider smoke tests still require user-supplied credentials and are intentionally separate from the deterministic CI suite. AMEX value remains explicitly synthetic and illustrative; no bookings, payments, browser-history collection or mailbox integration are enabled.
