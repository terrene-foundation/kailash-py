---
type: CONVERGENCE-STATUS
shard: S4 (AC 5 register_sse + AC 6 register_websocket callback overload)
status: CONVERGED — reviewer + security-reviewer APPROVE (0 CRIT/0 HIGH outstanding)
branch: feat/1174-s4-sse-websocket
date: 2026-05-31
---

# Shard 4 (SSE + WebSocket callback) — convergence

## Round history (durable receipts)

| Round | reviewer                                                                                      | security-reviewer                                                                  |
| ----- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| R1    | APPROVE_WITH_FIXES (task `abeae9ef451478377`) — 1 MED: 3 WS-security MUSTs had no direct test | APPROVE_WITH_FIXES (task `a6d046bc3bd25c380`) — HIGH-1, HIGH-2, MEDIUM-1, MEDIUM-2 |
| R2    | (covered by R2-security confirming the new tests are genuine)                                 | **APPROVE** (task `a8dbce3f3e5bef308`) — all R1 findings resolved, no new issue    |

## R1 findings → dispositions (all applied)

- **HIGH-1 (security)** — SSE subscribe rate-limit (MUST-5) was dead code (`getattr(nexus.auth,"rate_limit")` always None). **Fixed** (commit `f230f33a9`): wired to the real `nexus._rate_limit` int, per-client-IP 60s sliding window keyed on `request.client.host` (ASGI peer, not a spoofable header), HTTP 429 + `RATE_LIMITED` envelope before the handshake. R2-security confirmed parity with the established `core.py::rate_limited_func`.
- **HIGH-2 (security)** — `slow_consumer_timeout` (MUST-4) was an accepted-but-unused kwarg. **Fixed** (`f230f33a9`): `_sse_stream` now bounds each `queue.get()` wait by `min(keepalive, remaining slow-consumer budget)`, returns (cancels producer + releases per-subscription state) when no flush succeeds within the timeout — distinct from keepalive (which emits-and-continues).
- **MEDIUM-1 (security)** — WS origin/subprotocol/auth checks run post-upgrade (the `websockets.serve()` upgrades before the handler), not pre-upgrade. The boundary holds (socket rejected before `on_connect`); the docstrings overstated "pre-upgrade HTTP 401/403". **Fixed** (commit `b9798793c`): docstrings + workspace spec corrected to "post-upgrade, pre-`on_connect`, WS close 1008". True pre-upgrade `process_request` rejection filed as a Follow-up.
- **MEDIUM-2 (security)** — accepted WS subprotocol not echoed (RFC 6455 §4.2.2). Implementation is reject-only; **docstrings/spec corrected** to state reject-only validation; `select_subprotocol` echo filed as a Follow-up (shares MEDIUM-1's `serve()` rewiring root).
- **MEDIUM (reviewer)** — 3 WS-security MUSTs had zero direct tests. **Fixed**: new `test_register_websocket_security.py` (subprotocol→1002, frame-cap→1009, handshake-auth→1008 with status-in-reason + `on_connect`/`on_disconnect` did-not-fire) + 2 SSE tests (rate-limit→429-before-handshake, slow-consumer→close). R2-security confirmed genuine (real WS/SSE, structural assertions).

## Verification (orchestrator-run)

- Full gate set (new SSE/WS + security + existing `test_sse_streaming`/`test_websocket_message_handlers`/`test_websocket_unicast`): **104 passed**.
- `--collect-only` across the package: **2428 collected, 0 errors**.
- HIGH fixes deterministically verified as real wiring (not fake): `nexus._rate_limit` enforced + `slow_consumer_timeout` actually read.

## Follow-ups (filed, NOT blockers — out of shard budget; boundary holds)

1. WS true pre-upgrade rejection via `websockets` `process_request` (real HTTP 401/403 instead of post-upgrade WS-1008).
2. WS `select_subprotocol` echo (RFC 6455 §4.2.2 negotiate-and-confirm).
3. Typed-status HTTP mapping on `/workflows/{name}/execute` (carried from Shard 1 — gateway collapses `NexusHandlerError` to generic 500).

## Verdict

**CONVERGED — APPROVE.** CI (full matrix incl CodeQL) is the remaining gate before merge.
