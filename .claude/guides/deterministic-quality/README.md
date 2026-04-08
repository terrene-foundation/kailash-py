# Deterministic Quality — From Rules to Primitives

Quality that depends on someone (human or LLM) reading and following a rule is **probabilistic**. Quality enforced by the type system, API design, or framework defaults is **deterministic**. This guide documents both — how to author rules that actually work, how to structure sessions for maximum leverage, and how to systematically promote quality properties from rules into code primitives.

**Origin**: journal/0052-DISCOVERY-session-productivity-patterns.md, validated by subprocess A/B tests.

## The Core Discovery

A 12-hour session shipped 6 workstreams, 15 commits, 6 GitHub issues, and 2 production deploys with **nothing falling on the floor**. The root cause was not raw model capability — it was artifact design. Specifically:

1. **Rules that target the agent's own wording** (linguistic tripwires) flip behavior deterministically. Subprocess test: zero-tolerance.md moved the agent from "scope creep, leave it alone" (0/2) to "fix + regression test + verification" (2/2).

2. **A meta-rule for rule authoring** changes output quality from 2/6 to 6/6 on the Loud/Linguistic/Layered criteria. Subprocess test confirmed.

3. **Session architecture matters more than individual rules.** The 4-layer loading model (session-start → path-scoped → tool-scoped → gate-scoped) is what makes 25+ rules feasible without context crowding.

4. **Rules and code primitives compound.** A rule says WHY; a primitive enforces HOW. Neither replaces the other. The rule survives as institutional memory when the primitive handles enforcement.

## Guide Index

### Part I — CO Artifact Insights (how to make agents sharp)

These are the higher-leverage findings. They apply to every project, every language, every session.

| File                                                               | What it covers                                                                                                                                                                                                           |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [01-rule-authoring-principles.md](01-rule-authoring-principles.md) | **"Loud, Linguistic, Layered"** — the meta-pattern for writing rules that actually change behavior. Includes subprocess test evidence, anti-patterns, and reproduction protocol.                                         |
| [02-session-architecture.md](02-session-architecture.md)           | **The 4-layer loading model** — how CLAUDE.md, path-scoped rules, specialists, and gate reviews compose into sessions where nothing falls on the floor. Includes the throughput multiplier breakdown and ablation table. |
| [03-enforcement-ladder.md](03-enforcement-ladder.md)               | **The promotion lifecycle** — how a quality property climbs from documentation (Rung 1) to impossible API (Rung 6). Includes 5 case studies with current rung and target rung for key properties.                        |

### Part II — Code Primitive Patterns (how to make the SDK deterministic)

These are the implementation patterns. They apply to kailash-py and kailash-rs specifically.

| File                                                                   | Category                                                                                                                       | Applies to             |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ---------------------- |
| [04-type-system-enforcement.md](04-type-system-enforcement.md)         | Compile-time / definition-time safety: `#[non_exhaustive]`, typestate builders, newtypes, `__init_subclass__`, frozen configs  | kailash-rs, kailash-py |
| [05-runtime-safety-defaults.md](05-runtime-safety-defaults.md)         | Pit-of-success API design: input validation, `unsafe_raw()`, pool circuit breaker, UNSET sentinels, mandatory context managers | Both SDKs              |
| [06-observability-primitives.md](06-observability-primitives.md)       | Impossible to be silent: auto-telemetry, BulkResult auto-WARN, silent exception detection, correlation ID propagation          | Both SDKs              |
| [07-destructive-operation-gates.md](07-destructive-operation-gates.md) | Explicit confirmation: `force_drop`, mandatory delete filter, migration dry-run, idempotency keys                              | Both SDKs              |
| [08-cross-sdk-parity.md](08-cross-sdk-parity.md)                       | Keeping py/rs in sync: API surface extraction, parity diff, CI integration, behavioral parity tests                            | Platform               |

## The Rule ↔ Primitive Lifecycle

```
DISCOVERY → RULE (Rung 2) → fires 3+ times → PRIMITIVE (Rung 4-6) → rule stays as backstop
   ↑                                                                       ↑
Journal entry                                                     Institutional memory
captures the                                                      of WHY the primitive
failure mode                                                      exists
```

**The rule is never deleted.** It transitions from primary enforcement to backstop. This is why rules carry `Why:` lines — the Why survives if the primitive is ever removed.

## The Spectrum

```
← More probabilistic                              More deterministic →

Documentation → Rules (MUST) → Linter checks → Runtime validation → Type system → Impossible API
     ↑              ↑                ↑                  ↑                 ↑              ↑
  Ignored       Followed         CI gate         Early failure      Compile error   Can't express
  often         sometimes        catches         with message       before ship     the wrong thing
```

## Current State (2026-04-09)

### kailash-rs

- **Strong**: `#[must_use]` (200+ uses), per-crate error enums, RAII on connections/transactions
- **Gaps**: `#[non_exhaustive]` on public enums, typestate builders, newtype enforcement in bindings, sealed traits for audit types

### kailash-py

- **Strong**: deprecation warnings (73 files), frozen configs (56 files), context managers (30 files)
- **Gaps**: input validation at API boundaries, structured return types (25 files return `Dict[str, Any]`), `__init_subclass__` validation, UNSET sentinels

### Cross-cutting

- Auto-telemetry on public methods: absent
- Pool exhaustion circuit breaker: absent
- `unsafe_raw()` escape hatch: absent
- BulkResult auto-WARN on partial failure: absent (source-verified: `except Exception: continue` with zero logging)

## Relationship to Other Artifacts

- `rules/rule-authoring.md` — the meta-rule for authoring COC rules (tested, validated)
- `rules/zero-tolerance.md` — the canonical Rung 2 rule; primitives make it fire less, not disappear
- `rules/observability.md` — log triage gate; §06 primitives make triage automatic
- `rules/dataflow-identifier-safety.md` — `quote_identifier()` is the canonical Rung 4 primitive
- `rules/cross-sdk-inspection.md` — the rule that caught kailash-rs Parameterized stub; §08 automates it
