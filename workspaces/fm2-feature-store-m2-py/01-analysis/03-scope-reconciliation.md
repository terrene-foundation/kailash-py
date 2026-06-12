# 03 — Scope Reconciliation: Issue #1302 AC vs `specs/ml-feature-store.md` §11

> Produced by read-only analysis agent (scope-reconciliation mission). Persisted by
> orchestrator (agent lacked Write). **CAVEAT:** this agent's conflict findings for
> AC#1/#3 (`@feature` / `materialize`) rest on the assumption that the DataFlow
> materialisation primitive is unshipped. That assumption is verified independently by
> `01-dataflow-dependency-verification.md` — read that FIRST; if `dataflow.transform`
> ships as a real implementation, CONFLICT-1/3 dissolve.

Brief "absent surface" claims verified against source: no `@feature`, no public
`FeatureGroup`, no `FeatureStore.materialize`, none of the six M2 typed exceptions in
`errors.py`, no `erase_tenant`. All accurate.

## Headline split

Of the 8 acceptance criteria: **0 unconditionally BUILD-NOW**, **4 CONDITIONALLY-DEFER**
(spec §11 names an unmet precondition), **1 ADR-OUT**, **3 derived/meta** gated by the
above. This workstream is NOT "build all 8 surfaces" — it is "build the unblocked subset
(near-empty today) + ADR the rest" — _pending DataFlow-dependency confirmation_.

## Reconciliation table

| #   | Issue AC                          | Spec §11            | Verbatim blocking condition                                                                                                                                              | Classification                                                                           |
| --- | --------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| 1   | `@feature` decorator              | §11.2               | "Defer **until DataFlow ships a materialisation primitive that the FeatureStore can wrap**."                                                                             | CONDITIONALLY-DEFER                                                                      |
| 2   | public `FeatureGroup` class       | §11.1               | "Re-introduce **if and only if a downstream Engine surfaces a need that `FeatureSchema + ml_feature_source(...)` cannot express**."                                      | CONDITIONALLY-DEFER                                                                      |
| 3   | `FeatureStore.materialize()`      | §11.2 + §4.1 MUST-5 | Materialisation-primitive deferral + DB-side windowed as-of needs "a DataFlow aggregation primitive not yet exposed without raw SQL"                                     | CONDITIONALLY-DEFER                                                                      |
| 4   | online-store adapter (**or ADR**) | §11.4               | "**Defer.** … when the FeatureStore lands a registry-backed online surface, GDPR erasure plumbs through that path."                                                      | ADR-OUT (issue already hedged)                                                           |
| 5   | M2 typed exceptions               | §11.7               | "Each will land in `errors.py` **at the same PR that lands the corresponding surface**… Until then, downstream code MUST NOT `try/except` against any of these classes." | CONDITIONALLY-DEFER (coupled to #1–#4; orphan classes = `zero-tolerance.md` Rule 2 stub) |
| 6   | Tier-2 tests per surface          | derived             | inherits disposition of whichever surfaces build                                                                                                                         | GATED                                                                                    |
| 7   | spec graduated; #693 closed       | see below           | §13: "the `@feature`/`FeatureGroup` clauses **MUST be revisited**"                                                                                                       | GATED — but NOT on building all M2 surfaces                                              |
| 8   | §11 items → shipped               | derived             | moving an unshipped item = `spec-accuracy.md` Rule 1/5 violation                                                                                                         | GATED                                                                                    |

## Conflicts (issue "implement" vs spec "defer until X")

- **CONFLICT-1 (AC#1 `@feature`):** §11.2 defers until DataFlow ships a materialisation primitive. `dataflow.transform(...)` (the helper `@feature` would consume) is specified only in a `(draft)` spec whose §13 marks it M2-deferred. **→ confirm against source (agent 01).**
- **CONFLICT-2 (AC#2 `FeatureGroup`):** §11.1 gates on a demonstrated downstream-Engine need the current surface can't express. None cited; the internal `SchemaFeatureGroup` adapter (#1241) already bridges schema→binding, evidence the current surface DOES express the need.
- **CONFLICT-3 (AC#3 `materialize()`):** same DataFlow-primitive precondition; §4.1 MUST-5 says DB-side as-of needs an aggregation primitive "not yet exposed without raw SQL." Building against raw SQL → `framework-first.md` + `zero-tolerance.md` Rule 4 violation. **→ confirm against source (agent 01).**
- **CONFLICT-4 (AC#5 typed exceptions):** §11.7 lands them only with their surface. Landing now = six orphan classes = `zero-tolerance.md` Rule 2 stub.

## What #693 graduation ACTUALLY requires

Graduating `dataflow-ml-integration.md` from `(draft)` does **NOT** require building all M2
surfaces. §13's operative clause is "MUST be **revisited**" (≠ "implemented"). The `ml_feature_source`
binding (§2) is already shipped + consumed (#1241) — that half is graduation-ready. Per
`spec-accuracy.md` Rule 1/5, graduation requires the spec to describe only shipped reality:
the §2.5/§3 `@feature`/`FeatureGroup` clauses must either (a) move to a bounded `## Out of scope`
section pointing at the M2 deferral, or (b) be rewritten to describe the shipped
`ml_feature_source` + `SchemaFeatureGroup` path. **#693 closes by correcting the draft spec to
match shipped reality, NOT by building M2 author/online surfaces.**

## Recommended workstream shape (for the `/todos` gate) — PENDING agent-01 confirmation

1. **Write the ADR** deferring M2 author-side + online surfaces per §11.1/§11.2/§11.4/§11.7 (unmet preconditions as of kailash-ml 2.0.1). Resolves AC#4 explicitly; covers #1/#2/#3/#5.
2. **Graduate `dataflow-ml-integration.md`**: correct §2.5/§3 to shipped reality, bound deferred surfaces in `## Out of scope` → closes AC#7, #693.
3. **AC#1/#2/#3/#5 → CONDITIONALLY-DEFER** with value-anchors citing the unmet §11 preconditions; future session re-validates when DataFlow ships the materialisation primitive.
4. **AC#6/#8** resolve trivially: no new surfaces ship → no new Tier-2 tests, no §11 items move.

**Implications:** converts a multi-surface implementation into a ~1-session spec-accuracy + ADR
workstream; keeps the codebase honest (no orphan exceptions, no raw-SQL workarounds). **Con:** the
issue's literal AC checklist shows 4 items "deferred via ADR" not "implemented" — user confirms at
`/todos` gate. **Pro:** aligns with `spec-accuracy.md`, `framework-first.md`, `zero-tolerance.md`
Rule 2/4; alternative (build all 8) ships speculative surfaces against unshipped DataFlow primitives.
