# 0002 — DECISION: Shard A reclassified ALREADY-PRESENT; Shard B deferred (value-anchored)

**Date:** 2026-06-17
**Trigger:** re-verification during PR1 implementation overturned the cluster-2
verdict — same wrong-namespace overstatement pattern as clusters 1 & 4.

## Correction to 0001 (cluster 2)

**Cluster 2 (exception→HTTP canonical envelope) is ALREADY-PRESENT in Nexus**, not
GAP-REAL. The cluster-2 verification agent probed core `kailash.gateway`/`servers`
and missed the Nexus package's own surface:
- `packages/kailash-nexus/src/nexus/errors.py` — full `NexusError` hierarchy
  (`ValidationError`/`NotFoundError`/`ConflictError`/`UnauthorizedError`/
  `ForbiddenError`/`RateLimitError`/`ServiceUnavailableError`/`BadGatewayError`/
  `TimeoutError`) with `to_response_dict()` → canonical `{"error", "detail"}`.
- `transports/http.py:197 _install_exception_handlers()` registers
  `app.add_exception_handler(NexusError, _handle_nexus_error)`, auto-installed at
  transport startup (`core.py:1099`): typed subclass → declared status + canonical
  body; 5xx detail logged-not-leaked. (Shipped via #937, CLOSED.)

So the `_error_handler_middleware_factory` preset stub was DEAD — the capability
ships via the transport, not a preset. Disposition: removed the stub (zero-tolerance).

## PR1 delivered scope (branch feat/issue-1336-nexus-middleware-parity)

- **Shard D (rate-limit preset wiring, parity #1345):** `_rate_limit_middleware_factory`
  now attaches the built `RateLimitMiddleware`/`RateLimitConfig` from `NexusConfig`.
- **Shard D (CSP passthrough, parity #1348):** `NexusConfig.csp` +
  `security_header_overrides` threaded into the security-headers preset.
- **Shard A cleanup:** removed dead `_error_handler_middleware_factory` (capability
  ships via transport). kailash-nexus 2.9.1 → 2.10.0.

## Shard B (per-request metrics middleware, parity #1347) — DEFERRED

**Value-anchor:** delivers per-request HTTP method/route/status/latency metrics on
the existing Nexus `/metrics` Prometheus endpoint — the #1336 issue's parity #1347
ask. This is a REAL gap confirmed in the Nexus namespace (`metrics.py` exposes only
`session_sync`/`failure_recovery` histograms, no per-request middleware).

**Trade-off named (per value-prioritization MUST-1):** B is higher-effort than D
(a new prometheus-integrated `BaseHTTPMiddleware` with route-template cardinality
control). Deferred NOT for fittability but because the gate-review specialists
(reviewer + security-reviewer) were structurally unavailable this session
(persistent server-side sub-agent rate-limit, 6 consecutive deaths), and a new
metrics middleware touching the prometheus registry genuinely warrants those gates.

**Re-pickup gate (MUST-3):** next session re-validate this value-anchor against
#1336 parity #1347 before resuming; build `RequestMetricsMiddleware` in the Nexus
package + preset factory, with reviewer + security-reviewer gates.

## #1336 AC status after this session
- #1345 rate-limit: ALREADY-PRESENT capability + now preset-auto-wired ✅
- #1346 exception envelope: ALREADY-PRESENT (Nexus errors.py + transport) ✅
- #1347 per-request metrics: REAL gap — Shard B DEFERRED (value-anchored above)
- #1348 CSP: ALREADY-PRESENT capability + now NexusConfig-passthrough ✅
- #1349 session TTL: SHIPPED (PR #1346, kailash 2.36.0) ✅
