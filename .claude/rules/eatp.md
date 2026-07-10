---
priority: 10
scope: path-scoped
paths:
  - "**/trust/**"
  - "**/eatp/**"
---

# EATP SDK Rules

<!-- slot:neutral-body -->

## Scope

These rules apply when working with EATP trust code.

## SDK Conventions

### Dataclasses

- Use `@dataclass` (NOT Pydantic) for all data types
- Every `@dataclass` MUST have `to_dict()` → `Dict[str, Any]` and `@classmethod from_dict()` → Self
- Enums serialize as `.value`, datetimes as `.isoformat()`

**Why:** Missing `to_dict()`/`from_dict()` makes trust records non-serializable, breaking audit logging, wire transfer, and persistence.

### Module Structure

- `from __future__ import annotations` in every module
- `# Copyright <YEAR> <COPYRIGHT_HOLDER>` + `# SPDX-License-Identifier: <SPDX_ID>` header
- `logger = logging.getLogger(__name__)` in every module
- Explicit `__all__` in every module
- `str`-backed `Enum` classes for JSON-friendly serialization

**Why:** Missing `__all__` exposes internal symbols on `import *`, and non-str Enums produce integer values in JSON that downstream consumers cannot interpret.

### Error Handling

- All errors MUST inherit from `TrustError` (in `eatp.exceptions`)
- All errors MUST include `.details: Dict[str, Any]` parameter

**Why:** Non-`TrustError` exceptions bypass trust-layer catch blocks, causing unhandled crashes instead of structured denial.

- Fail-closed: unknown/error states → deny, NEVER silently permit

**Why:** A fail-open default means any bug in trust evaluation silently grants access, turning errors into security bypasses.

### Cryptography

- Ed25519 is the mandatory signing algorithm
- HMAC is optional overlay (HMAC alone is NEVER sufficient for external verification)
- Constant-time comparison via `hmac.compare_digest()` — NEVER use `==` for signature comparison
- AWS KMS uses ECDSA P-256 (Ed25519 not available in KMS) — document the algorithm mismatch

**Why:** Using `==` for signature comparison leaks timing information, enabling attackers to forge valid signatures byte by byte.

### Trust Model

- Monotonic escalation only: AUTO_APPROVED → FLAGGED → HELD → BLOCKED (never downgrade)

**Why:** Allowing trust level downgrades means a compromised component can reset its own restriction, defeating the entire escalation model.

- Bounded collections: `maxlen=10000`, trim oldest 10% at capacity

**Why:** Unbounded collections cause memory exhaustion in long-running trust services, crashing the entire trust plane.

- `None` role = all-access (backward-compatible, no RBAC enforcement)

## MUST: Signed Audit Event Emits BEFORE State Advance; FAILED Path Uses A No-Recurse Helper

Any state-machine transition that emits a signed audit event MUST sign-and-emit the audit row BEFORE advancing the state slot. If signing/emit raises, the transition aborts at the pre-advance position so the next call observes the pre-transition state — never a half-advanced state with no audit row. The FAILED path itself emits an audit event, and that emit MUST go through a dedicated `_advance_to_failed_no_audit`-style helper that bypasses the audit-emit step the parent advance used, preventing infinite recursion when the FAILED path's own audit emit raises.

```python
# DO — emit first, advance second; fail closed at the pre-advance position
self._audit_engine.append(event)   # raises → state slot unchanged
self._phase = Phase.ACTING

# DO NOT — advance first; emit failure leaves (phase=ACTING, no audit row)
self._phase = Phase.ACTING
self._audit_engine.append(event)   # next dispatch observes half-state
```

**BLOCKED rationalizations:** "wrap both in try/except and roll the state back" / "the audit row can be emitted lazily after the transition" / "recursion on the FAILED path is theoretical" / "catch-all handling covers it".

**Why:** Advance-before-emit leaves the runtime half-advanced with a hole in the audit chain — the silent-fallback failure mode (`zero-tolerance.md` Rule 3) at the state-machine surface; the structural defense is ordering + a no-recurse FAILED helper, not catch-all exception handling. Generalizes to every state-machine + audit-chain pairing: trust executor, agent lifecycle loops, governance envelope cascades, transaction phases.

**Trust Posture Wiring:**

- **Severity:** `halt-and-report` at the /implement gate (reviewer + security-reviewer mechanical sweep on every state-advance + audit-emit call-site pair; structural-signal class per `hook-output-discipline.md` MUST-2).
- **Grace period:** 7 days from rule landing.
- **Cumulative posture impact:** 3× same-rule in 30d → drop 1 posture per `trust-posture.md` MUST-4.
- **Regression-within-grace:** trigger key `audit_after_state_advance` fires emergency downgrade (1 step) per `trust-posture.md` MUST-4.
- **Receipt requirement:** SessionStart hard-gate `[ack: audit-before-state-advance]` IFF `posture.json::pending_verification` includes this rule_id AND the most recent journal entry references trust-executor / agent-lifecycle / envelope-cascade work.
- **Detection mechanism:** gate-level reviewer + security-reviewer mechanical sweep at /implement + /redteam — AST walk for a state-slot write followed by `<audit>.append(` in the SAME function; advance-before-emit ordering = HIGH finding. Phase 2 (deferred): hook detector `.claude/hooks/lib/violation-patterns.js::detectStateAdvanceBeforeAuditEmit`; audit fixtures land with the detector under the violation-patterns detectStateAdvanceBeforeAuditEmit subdir per `cc-artifacts.md` Rule 9.
- **Violation scope:** MUST 1 (emit-before-advance ordering) — structural AST sweep; MUST 2 (no-recurse FAILED helper) — structural AST sweep asserting any `*_to_failed*` function has zero calls to the module's parent audit-emit helper.
- **Origin:** PR #1139 commit e9626a223 (2026-05-22) — pre-fix code advanced the lifecycle `phase` slot before `_audit_engine.append`; an emit failure left (phase=ACTING, no audit row) and the next dispatch raised an opaque error. Post-fix: emit-first, advance-second, plus `_advance_to_failed_no_audit` for the FAILED-path recursion guard.

## MUST: Dual-Surface State Reconciles BOTH Surfaces Atomically Under One Lock; Reconcile On A Stable Id

A state machine whose state spans TWO mutable surfaces (e.g. an in-memory review queue + a persisted store) MUST reconcile BOTH surfaces ATOMICALLY under ONE lock on EVERY transition (expire, resolve, review). A transition that mutates one surface without reconciling the other lets a stale entry on the un-reconciled surface be re-resolved into a monotonic DOWNGRADE — the exact inverse of the monotonic-escalation invariant above (AUTO_APPROVED → … → BLOCKED, never downgrade). Two further invariants hold the reconcile honest:

- **The reconcile key MUST be STABLE.** Keying reconcile on a re-minted / mutable id (e.g. a corrupt-sentinel that mints a fresh id) misses the very entries it must remove. Carry the ORIGINAL id through the transition and reconcile on it.
- **A single-surface entry MUST NOT be evictable by an event on the OTHER surface.** An entry present in ONLY one surface (e.g. a no-timeout hold in the queue but never written to the store) MUST NOT be removed by an event targeting the other surface — a forged / stale store row MUST NOT deny a queue-only entry.

```python
# DO — one lock, both surfaces, reconcile on the ORIGINAL id
async def expire_holds(self, now):
    async with self._lock:                              # ONE lock spans both surfaces
        for h in self._store.due(now):
            orig_id = h.id                              # stable key captured BEFORE any re-mint
            self._store.mark_blocked(orig_id)
            self._review_queue.discard(orig_id)         # queue reconciled in the SAME critical section
        # a queue-only entry (never in _store) is untouched here — no store event evicts it

# DO NOT — mutate one surface, leave the other stale; reconcile on a re-minted id
async def expire_holds(self, now):
    for h in self._store.due(now):
        self._store.mark_blocked(h.id)                  # store advanced to BLOCKED
    # review_queue NOT reconciled → a lingering queue entry re-resolves the
    # already-BLOCKED hold back to AUTO_APPROVED (monotonic downgrade), and a
    # corrupt-sentinel remint means discard(h.id) would miss it anyway
```

**BLOCKED rationalizations:**

- "The store is the source of truth; the queue is just a cache" (a stale queue entry still re-resolves a terminal state — both surfaces are authoritative until reconciled)
- "Reconcile the queue in a follow-up pass after the store write" (the un-reconciled window is where the downgrade lands; it MUST be one critical section)
- "The corrupt-sentinel mints a clean id, that's safer" (a fresh id misses the entry the reconcile must remove — carry the original)
- "A store row targeting this id is enough to evict the queue entry" (a queue-only entry has no store row; a forged store row must not deny it)
- "Two locks, one per surface, is finer-grained" (an interleave between the two locks is exactly the un-reconciled window)

**Why:** When a lifecycle's state lives on two mutable surfaces, a transition that advances one surface and leaves the other stale creates a re-resolution window — a lingering queue entry re-approves an already-expired-and-BLOCKED hold, a monotonic DOWNGRADE that defeats the escalation model. Atomic dual-surface reconcile under one lock, keyed on a stable id, with single-surface entries fenced from cross-surface eviction, is the structural defense; this generalizes the audit-before-state-advance clause above from the single-surface case to the two-surface case.

**Trust Posture Wiring:**

- **Severity:** `halt-and-report` at gate-review (security-reviewer + reviewer at `/implement` + `/redteam`: for any state machine spanning two mutable surfaces, confirm every transition reconciles BOTH under one lock, keys reconcile on a stable id, and fences single-surface entries from cross-surface eviction); `advisory` at the hook layer (the dual-surface-atomicity property is judgment-bearing over the transition's critical section, not a structural tool-call signal, per `hook-output-discipline.md` MUST-2).
- **Grace period:** 7 days from rule landing (2026-07-10 → 2026-07-17).
- **Cumulative posture impact:** same-class violations (a dual-surface transition that mutates one surface without reconciling the other, reconciles on a re-minted id, or evicts a single-surface entry via a cross-surface event) contribute to `trust-posture.md` MUST Rule 4 cumulative-window math (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** a same-class violation within the 7-day grace window routes through the GENERIC `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated per-clause trigger key (a dual-surface-reconcile property is review-layer-only and judgment-bearing; minting a key would drag `trust-posture.md`, a self-referential-codify allowlist file, into a self-ref edit, and the universal `regression_within_grace` trigger already covers it). Named deviation from the canonical key-per-clause shape, recorded here per `trust-posture.md` Rule 8 — the same no-dedicated-key disposition `security.md` § Enforcement-Surface Parity and `git.md` § CI-check/merge took.
- **Receipt requirement:** SessionStart soft-gate `[ack: eatp]` IFF `posture.json::pending_verification` includes this rule_id.
- **Detection mechanism:** Phase 1 (manual, gate-review) — for any state machine whose state spans two mutable surfaces (in-memory queue + persisted store, or equivalent), AST-walk each transition (expire / resolve / review) and confirm both surfaces mutate inside ONE lock's critical section, the reconcile key is the original (non-re-minted) id, and single-surface entries are fenced from cross-surface eviction; run by security-reviewer + reviewer at `/implement` + `/redteam`. Phase 2 (deferred per `trust-posture.md` § Two-Phase Rollout, after ≥3 real sessions exercise Phase 1) — no hook detector; audit fixtures land with the Phase-2 detector at `.claude/audit-fixtures/eatp-dual-surface-reconcile/` per `cc-artifacts.md` Rule 9.
- **Violation scope:** this clause (dual-surface atomic reconcile + stable reconcile key + single-surface-entry eviction fence) ONLY; the pre-existing grandfathered `eatp.md` sections stay exempt until each is itself `/codify`-touched (the clause-scoped precedent set by `rule-authoring.md`'s own Wiring section + `security.md` / `git.md`).
- **Origin:** kailash-py #1510 BH2 legs 2-3 (2026-07-10, PR #1657, kailash 2.46.0). Four adversarial `/redteam` rounds closed a CRITICAL (`expire_holds` mutated the store without reconciling the review queue → a BLOCKED→AUTO_APPROVED resurrection) plus a HIGH (reconcile keyed on the corrupt-sentinel's fresh id missed the original) plus a forged-store-row denial of a queue-only entry. Generalizes the audit-before-state-advance clause above to the two-surface case.

<!-- /slot:neutral-body -->
