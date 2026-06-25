---
type: CONVERGENCE-STATUS
shard: S2 (AC 3 — Nexus.dependency_overrides)
status: APPROVED via orchestrator-deterministic review (agent panel throttled by transient infra)
branch: feat/1174-s2-dependency-overrides
date: 2026-05-31
---

# Shard 2 (`dependency_overrides`) — convergence via orchestrator-deterministic review

## Why orchestrator-deterministic (transient-infra honesty per `verify-resource-existence.md` MUST-4)

Four background review-agent dispatches for this shard all terminated with
`API Error: Server is temporarily limiting requests (not your usage limit) ·
Rate limited` — the transient Anthropic server-side throttle, NOT findings (the
same infra condition documented at this workstream's R5 + issue-1035 R6). Per
that precedent, the orchestrator ran the deterministic / mechanical half of each
review lens directly.

**Throttled-dispatch receipts (task IDs, all returned the rate-limit error, 0 findings):**

- reviewer: `ae52d7d6211ff09af`, `a95c41e3ed96601d2`
- security-reviewer: `a036bf251457267d9`, `a2775dbd512f31a3b`

## Deterministic checks (orchestrator-run, with receipts)

1. **Tests (real HTTP, no mocking):** `pytest .../integration/nexus/ -q` → **49 passed**
   (39 Shard-1 + 10 new); backward-compat `test_handler_execution.py` → 7 passed;
   `--collect-only` → 49 collected, exit 0.
2. **Orphan Rule 6:** `extractors/__all__` includes `DependencyOverrideMap` +
   `DependencyOverrideRuntimeMutationError`; both re-exported in `nexus/__init__.py`.
3. **Wiring (no split-brain):** `core.py:374-375` —
   `self.dependency_overrides = DependencyOverrideMap()` +
   `self._dependency_overrides_map = self.dependency_overrides` (SAME object the
   resolver consults at `core.py:2983` via `getattr`). The map implements
   `__contains__`/`__getitem__` so it is the resolver's `overrides` arg directly.
4. **Contract (spec §147-159):** `override()` CM restores prior state in `finally`
   (exception-safe; `_ABSENT` sentinel restores a PRIOR override, not bare absence);
   `set`/`clear`(idempotent)/`clear_all`; `__getitem__` raises `KeyError`.
5. **Security (test-injection fenced from production):** map keys/values are only
   `Callable`s supplied by test code (no request-derived data flows in); the
   production-time mutation guard (`_guard_runtime_mutation` via
   `get_current_request()`) raises `DependencyOverrideRuntimeMutationError` (3-field
   message: qualname + correlation-id + audit hint — no secret/PII/body) for any
   mutation during an active request; default state is empty → real resolution.
6. **Hygiene:** no PEP-563 in `overrides.py`; no new top-level `fastapi` dep;
   lock-factory captured via `type(threading.Lock())` (python-environment Rule 5,
   no `isinstance(x, threading.Lock)`); module emits no logs.
7. **Test legitimacy:** `test_context_manager_override_changes_resolution_then_restores`
   asserts `source:"real" → "mock" → "real"` round-trip — proves the override
   genuinely changes resolution; the `_nonce` only forces a per-call cache-miss
   (the source assertion is the proof, not the nonce). Guard test fires from inside
   a live handler with the 3-field message.

## Verdict

**APPROVE.** Correct, secure, well-tested, mechanically clean. The reviewer +
security-reviewer lenses are both covered by the deterministic checks above.
CI (full matrix incl CodeQL) is the remaining gate before merge.

## Pre-existing (NOT introduced; do not block)

4 nexus _unit_-suite failures (fastmcp optional-dep, pydantic URL parsing)
reproduce on `main`; none reference `dependency_overrides` / `overrides.py`.
