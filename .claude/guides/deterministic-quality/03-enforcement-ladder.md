# The Enforcement Ladder — From Probabilistic to Deterministic

How to systematically promote a quality property from documentation (lowest enforcement) to impossible-to-violate API design (highest enforcement). Every quality property starts somewhere on this ladder and should be pushed upward over time.

**Origin**: journal/0052-DISCOVERY-session-productivity-patterns.md, research synthesis from cross-industry SDK analysis and kailash-py/rs source audits.

## The Ladder

```
Rung 6: IMPOSSIBLE API           ← Can't express the wrong thing
Rung 5: TYPE SYSTEM              ← Compiler/type-checker rejects it
Rung 4: RUNTIME VALIDATION       ← Fails fast with clear error
Rung 3: LINTER / CI GATE         ← Caught before merge
Rung 2: RULE (Loud/Linguistic)   ← Agent follows; probabilistic but tested
Rung 1: DOCUMENTATION            ← Ignored under pressure
Rung 0: ORAL TRADITION           ← Not written down at all
```

Each rung is strictly stronger than the one below it. A quality property enforced at Rung 4 is strictly safer than one at Rung 2, because Rung 4 fires even when the rule isn't loaded.

But Rung 2 (rules) is NOT disposable once Rung 4+ exists. The rule carries the WHY — the institutional memory of what failure mode the primitive prevents. Remove the rule and the primitive gets "refactored away" by someone who doesn't know why it's there.

## Case Studies: Climbing the Ladder

### Case 1: Silent Bulk Failure

**Problem**: DataFlow BulkCreate silently swallows 10,663 per-row exceptions.

| Rung | What exists                                                                   | Status                           |
| ---- | ----------------------------------------------------------------------------- | -------------------------------- |
| 0    | Nothing — developers learn by hitting the bug                                 | Before 0052                      |
| 1    | Journal entry documents the failure                                           | 0052-DISCOVERY                   |
| 2    | `rules/observability.md` §5 log triage gate; `rules/zero-tolerance.md` Rule 3 | Current (catches it per-session) |
| 3    | Custom ruff rule flags `except Exception: continue` without logging           | Not yet built                    |
| 4    | `BulkResult.__post_init__` auto-emits WARN when `failed > 0`                  | Not yet built                    |
| 5    | `BulkResult` is `#[must_use]` in Rust (compiler warns if ignored)             | Not yet built                    |
| 6    | `BulkResult` with `failed > 0` cannot be constructed without a logger handle  | Not yet built                    |

**Climb plan**: 2 → 3 (linter) → 4 (runtime auto-WARN) → 5 (Rust #[must_use]). Each rung makes the previous one a backstop rather than the primary enforcement.

### Case 2: Accidental Full-Table Deletion

**Problem**: `express.delete("User")` with no filter deletes all rows.

| Rung | What exists                                                                                             | Status                            |
| ---- | ------------------------------------------------------------------------------------------------------- | --------------------------------- |
| 2    | `rules/dataflow-identifier-safety.md` §4 mandates `force_drop=True` on DROP                             | Current (covers DROP, not DELETE) |
| 4    | `drop_model(force_drop=False)` raises `DropRefusedError`                                                | Current for DROP                  |
| 6    | `express.delete()` requires mandatory `filter` param; `admin.purge(confirm_purge=True)` for full delete | Not yet built                     |

**Climb plan**: Extend Rung 4 to cover DELETE (mandatory filter), then Rung 6 (separate method for purge). The rule at Rung 2 stays as the institutional memory.

### Case 3: Raw SQL Injection

**Problem**: Raw SQL via multiple entry points, no naming convention.

| Rung | What exists                                                                                                             | Status                  |
| ---- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| 2    | `rules/security.md` mandates parameterized queries; `rules/dataflow-identifier-safety.md` mandates `quote_identifier()` | Current                 |
| 3    | Not yet — no linter rule for raw SQL detection                                                                          | Not yet built           |
| 4    | `quote_identifier()` validates + quotes; `IdentifierError` on invalid input                                             | Current for identifiers |
| 6    | `unsafe_raw()` as sole entry point; name is grep-able; `reason` parameter required                                      | Not yet built           |

**Climb plan**: 2+4 → 3 (linter flags non-parameterized queries) → 6 (`unsafe_raw()` sole escape hatch).

### Case 4: Cross-SDK Semantic Divergence

**Problem**: kailash-rs `ProductMode::Parameterized` is a stub; kailash-py has full implementation.

| Rung | What exists                                                                  | Status                |
| ---- | ---------------------------------------------------------------------------- | --------------------- |
| 2    | `rules/cross-sdk-inspection.md` mandates inspection on every issue           | Current               |
| 3    | `loom/scripts/check-manifest-parity.sh` checks artifact sync, not API parity | Current (wrong scope) |
| 3    | CI parity check on every PR                                                  | Not yet built         |
| 4    | Parity test suites in `tests/parity/` that fail when behavior diverges       | Not yet built         |

**Climb plan**: 2+3 (manifest) → 3 (API surface diff tool) → 4 (behavioral parity tests). The rule at Rung 2 stays because tooling can't catch behavioral divergence that isn't tested.

### Case 5: Gate-Level Reviews Skipped

**Problem**: Review agents phrased as "recommended" — skipped 6/6 times under pressure.

| Rung | What exists                                                                      | Status        |
| ---- | -------------------------------------------------------------------------------- | ------------- |
| 1    | `rules/agents.md` gate table says "recommended"                                  | Current       |
| 2    | Upgraded to MUST at specific gates with BLOCKED responses                        | Proposed      |
| 3    | Hook that blocks commit if reviewer agent hasn't run since last /implement       | Not yet built |
| 4    | /implement command auto-spawns reviewer in background; commit gate checks result | Not yet built |

**Climb plan**: 1 → 2 (upgrade to MUST) → 3 (pre-commit hook) → 4 (auto-spawn + gate). The hook at Rung 3 is the key jump — it makes the review unavoidable without manual skipping.

## How to Decide Which Rung to Target

Not every quality property needs Rung 6. The decision depends on:

| Factor                  | Push higher                                   | Stay lower                           |
| ----------------------- | --------------------------------------------- | ------------------------------------ |
| **Failure cost**        | Data loss, security breach, silent corruption | Cosmetic, recoverable, low-frequency |
| **Failure frequency**   | Fires in 50%+ of sessions                     | Rare edge case                       |
| **Enforcement cost**    | Cheap (add `#[must_use]`, add a flag)         | Expensive (redesign API surface)     |
| **False positive risk** | Low (the check is precise)                    | High (would block valid code)        |

**Rule of thumb**: If the same rule fires in 3+ sessions on the same pattern, it's time to promote the pattern to a code primitive (Rung 4+). The rule has proven its value; now make it automatic.

## The Rule ↔ Primitive Lifecycle

```
1. DISCOVERY: Session hits a failure; journal entry created
   ↓
2. RULE: Zero-tolerance / domain rule authored (Rung 2)
   Rule fires in sessions; agent behavior improves
   ↓
3. PATTERN RECOGNITION: Same rule fires 3+ times on same code pattern
   ↓
4. PRIMITIVE: Code change makes the pattern enforced (Rung 4-6)
   GitHub issue filed; code ships in next release
   ↓
5. BACKSTOP: Rule stays as institutional memory of WHY
   Primitive handles enforcement; rule explains the failure mode
   If primitive is ever removed, rule catches the regression
```

**The rule is never deleted.** It transitions from "primary enforcement" to "backstop + institutional memory." This is why rules carry `Why:` lines — the Why is the only artifact that survives if the primitive is removed.

## Inventory: Current Rung for Key Properties

| Property                       | Current rung                  | Target rung              | Gap                      |
| ------------------------------ | ----------------------------- | ------------------------ | ------------------------ |
| Silent bulk failure logging    | 2 (rule)                      | 4 (BulkResult auto-WARN) | GH issue filed           |
| SQL injection prevention       | 2+4 (rule + quote_identifier) | 6 (unsafe_raw sole path) | Needs design             |
| Accidental DROP                | 4 (force_drop flag)           | 4 (sufficient)           | —                        |
| Accidental DELETE-all          | 0 (nothing)                   | 6 (mandatory filter)     | Needs design             |
| Cross-SDK divergence           | 2 (rule)                      | 3+4 (CI + parity tests)  | GH issue filed           |
| Gate-level reviews             | 1 (recommended)               | 3 (hook)                 | Needs rule upgrade first |
| Pool exhaustion                | 0 (nothing)                   | 4 (circuit breaker)      | Needs design             |
| Config mutation                | 2 (implicit)                  | 5 (frozen=True)          | Low effort               |
| Input validation at boundaries | 0 (nothing)                   | 4 (express validates)    | Needs design             |
| Structured return types        | 0 (nothing)                   | 5 (TypedDict/dataclass)  | Needs migration          |
| Correlation ID propagation     | 2 (rule)                      | 4 (contextvars auto)     | Needs design             |
| Public enum evolution          | 0 (nothing)                   | 5 (#[non_exhaustive])    | Low effort               |

## Cross-References

- `01-rule-authoring-principles.md` — how to author rules at Rung 2
- `02-session-architecture.md` — the 4-layer loading model that makes rules scale
- `04-type-system-enforcement.md` — patterns for Rung 5 (type system)
- `05-runtime-safety-defaults.md` — patterns for Rung 4 (runtime validation)
- `06-observability-primitives.md` — patterns for Rung 4 (auto-telemetry)
- `07-destructive-operation-gates.md` — patterns for Rung 4-6 (explicit confirmation)
- `08-cross-sdk-parity.md` — patterns for Rung 3-4 (CI + parity tests)
- `rules/rule-authoring.md` — the meta-rule for Rung 2 authoring
- `rules/zero-tolerance.md` — the canonical Rung 2 rule
