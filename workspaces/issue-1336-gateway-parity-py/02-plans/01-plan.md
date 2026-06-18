# #1336 Gateway HTTP-Middleware Parity — Plan (APPROVED 2026-06-16)

Gate: brief-claim verification done (`01-analysis/00-brief-claim-verification.md`).
Net scope: 3 narrow gaps + 2 preset stubs. All HTTP work Nexus-domain →
nexus-specialist. Session-TTL is core `kailash.channels`.

## Brief corrections

See `journal/0001-DECISION-brief-corrections.md`. Clusters 1 (rate-limit) & 4
(CSP) are ALREADY-PRESENT — no new capability; only preset auto-wiring residue.

## Shards → PRs

**PR 1 (Nexus package)** — Shards A + B + D bundled (shared Nexus app-wiring surface):

- **A — Exception→HTTP canonical envelope** (#1346): `{error:{code,message,...}}`
  envelope helper + consumer `register_exception(exc_type, status)` hook wired into
  the Nexus app; retire/migrate legacy hardcoded 404 (`api/workflow_api.py:201`).
- **B — Per-request metrics middleware** (#1347): one `BaseHTTPMiddleware` timing
  each request → existing `get_metrics_registry().increment`/`record_timer` labeled
  by method/path/status; surfaces on existing `/metrics`.
- **D — Preset wiring** (#1345 + #1348 residue): replace rate-limit preset stub
  (`nexus/presets.py:181` returns None) so `public`/`saas` auto-attach the built
  `RateLimitMiddleware`; thread custom CSP through `NexusConfig` into the
  security-headers preset factory (`presets.py:140`).

**PR 2 (core kailash.channels)** — Shard C:

- **C — Session TTL** (#1349): add `remaining_ttl()` accessor on `CrossChannelSession`;
  wire sliding-TTL-on-access (store window `ttl` so `touch()`/`SessionManager.get_session`
  re-slides `expires_at`). `channels/session.py`.

PR 1 and PR 2 are fully independent (different packages, no shared files) → parallel
worktree-isolated agents.

## Gates

Each PR: reviewer + security-reviewer (MUST at /implement). #1336 AC marked per-item
(2 already-present w/ citation, 3 closed w/ API). Release via /release after merges.

## Invariants (PR1 bundle): error-envelope shape · exception registration · metrics

labels · preset auto-attach · CSP passthrough = 5. Within budget.
