# #1336 Gateway HTTP-Middleware Parity — Brief-Claim Verification

**Date:** 2026-06-16
**Method:** 5 parallel deep-dive verification agents (one per cluster), each
independently re-grepping/importing kailash-py source. Mandated by `agents.md`
(≥3-issue brief) + the standing trap that parity issues are routinely overstated
(#1335 ~5× over; #1337 ~80% already-present).
**Target:** kailash 2.35.0 (issue probed 2.34.2).

## Headline

The issue probed **core `kailash.gateway/channels/middleware/servers`** and
almost entirely **missed the Nexus package** (`packages/kailash-nexus`), which is
where the modern HTTP middleware actually lives. 2 of 5 "gaps" are fully present
in Nexus; 3 are real-but-narrow.

## Verdict matrix

| #   | Cluster (parity ref)            | Issue claim                               | **Verdict**           | Real residue                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| --- | ------------------------------- | ----------------------------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Rate-limit (#1345)              | "confirmed gap — absent"                  | **ALREADY-PRESENT**   | Capability complete in `nexus.auth` + `kailash.trust.rate_limit` (token-bucket + 429 + `X-RateLimit-*`/`Retry-After` + per-route + redis). Only residue: **preset auto-wiring stub** `nexus/presets.py:181` returns `None` + warns "coming in WS02".                                                                                                                                                                                                                                     |
| 2   | Exception→HTTP envelope (#1346) | "does gateway expose a hook?"             | **GAP-REAL**          | No consumer-facing exception→status registration; no canonical error envelope. Errors are scattered inline `raise HTTPException(detail=str(e))`. Only `exception_handler` in-tree is a hardcoded legacy 404 (`api/workflow_api.py:201`).                                                                                                                                                                                                                                                 |
| 3   | Per-request metrics (#1347)     | "is there per-request metrics?"           | **GAP-REAL (narrow)** | `/metrics` + connection-pool + workflow/node execution metrics exist; **no middleware records per-request method/endpoint/status/latency**. Registry's labeled `increment`/`record_timer` + Prometheus exporter already support it — only the recording middleware is absent.                                                                                                                                                                                                            |
| 4   | CSP / security headers (#1348)  | "can consumer feed CSP?"                  | **ALREADY-PRESENT**   | `nexus/middleware/security_headers.py:39` `SecurityHeadersConfig` — full free-form `csp: str` + HSTS/frame/content-type/xss/referrer/permissions toggles + `exclude_paths`, wired via public `add_middleware`. Issue misattributed surface to `kailash.gateway/security.py` (which is **secret management**, not headers). Residue: **preset doesn't thread custom CSP** through `NexusConfig` (`presets.py:140` hardcodes config).                                                      |
| 5   | Session store (#1349)           | "mutation / sliding-TTL / remaining-TTL?" | **PARTIAL**           | `kailash.channels` `CrossChannelSession`/`SessionManager` exist (`channels/session.py:24,190`). **(a) data mutation: PRESENT** (`set_shared_data`, `update_channel_context`). **(b) sliding-TTL: PARTIAL** — `extend_expiry()` exists + idle-mode slides via `touch()`, but explicit-`expires_at` mode does NOT slide on access and `get_session` never auto-extends. **(c) remaining-TTL read: GAP-REAL** — no `remaining_ttl()` accessor, only raw `expires_at` + bool `is_expired()`. |

## Brief corrections (the gate)

1. **"rate-limit NOT FOUND → confirmed gap" is FALSE.** A complete, middleware-grade
   rate limiter exists in Nexus. The issue grepped core dirs only.
2. **"kailash.gateway has a `security` surface" for CSP is FALSE/misattributed.**
   `gateway/security.py` is secrets, not headers. The header capability is fully
   present in `nexus/middleware/security_headers.py`.
3. **The genuine gaps are 3, narrow, and Nexus-shaped:** exception envelope (#1346),
   per-request metrics middleware (#1347), session remaining-TTL + sliding-on-access (#1349).
4. **Two preset auto-wiring stubs** surfaced as collateral (rate-limit preset returns
   `None` "coming in WS02"; CSP not threaded through `NexusConfig`). Zero-tolerance:
   found → owned; they are in-scope for this parity issue (auto-wiring the very
   middleware #1336 is about).

## Placement note (for the plan)

Parity intent is to match the Rust engine, which "routes through `kailash.nexus`".
Rate-limit + security-headers already live in **Nexus middleware**. Recommendation:
new middleware (exception-envelope, per-request metrics) lands in **Nexus**, alongside
the existing two; session-TTL lands in **core `kailash.channels`** (where SessionManager
is); preset wiring lands in **Nexus presets**. → Nexus-domain ⇒ delegate to nexus-specialist.
