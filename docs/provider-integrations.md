# Phase 11: provider integrations

Phase 11 formalizes the existing provider adapters and exposes `GET /api/v1/providers/capabilities`. The endpoint reports configured capabilities, source precedence and freshness policy without credentials or provider payloads.

Realtime adapters are Brave web discovery, Ticketmaster structured events, Google Places (New) and Google Routes. Web results remain discovery-only and create no verified facts. Places and Ticketmaster records carry field evidence; `VerificationService` applies source precedence, field validation, freshness limits and conflict suppression. Google-derived attribution is retained. Routes are short-lived travel estimates and are only created from explicit coordinates; missing routing configuration yields a provider error rather than fabricated durations. The synthetic demo adapters are labeled synthetic and are never used as a realtime fallback.

Provider HTTP uses the existing bounded transport with timeout, semaphore and transient retry handling. Payloads are not added to persistent customer storage. Official-page fetching remains restricted to configured hosts and is separately verified. AMEX experience inventory remains unavailable rather than invented; merchant/value matching belongs to Phase 12.

This phase does not attach offers, calculate eligibility, rank candidates, build itineraries or make live-inventory claims. Tests cover capability disclosure, synthetic labeling and expired field suppression. No credential-enabled provider request was made.
