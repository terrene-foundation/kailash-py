---
type: DECISION
date: 2026-05-04
author: co-authored
project: dataflow-engine-pyright-cleanup
topic: Split S4 (typed-require helpers) into T7a (Build) + T7b (Wire) per /todos red-team
phase: todos
tags:
  [
    sharding,
    build-wire-separator,
    autonomous-execution-rule-1,
    autonomous-execution-rule-2,
    red-team-correction,
  ]
---

# DECISION: Split S4 (typed-require helpers) into T7a (Build) + T7b (Wire)

**Surfaced by:** /todos red-team review

## Decision

S4 (`typed-require helpers`) — originally a single shard combining "add 4 helpers + 4 helper tests + retrofit 13 W2 call sites" — is split into two shards:

- **T7a (Build, Wave 3a):** Add 4 typed-require helpers + 4 direct unit tests. NO call sites retrofitted. Helper API contract ratified in this journal entry's sibling `journal/0004-DECISION-typed-require-helper-naming.md` (created during T7a implementation; placeholder-named here).
- **T7b (Wire, Wave 3b):** Retrofit the 13 W2 call sites to use the helpers. Mechanical-stamp work; depends on T7a being merged first.

## Why

Two reasons cited in the /todos red-team report:

1. **Per-site invariant count breaches ≤10 ceiling.** `rules/autonomous-execution.md` MUST Rule 1 caps invariants at ≤10 per shard. The reviewer correctly noted that the 13 retrofit sites IS the invariant count when sized by site-wise correctness — even though each retrofit is mechanically identical, each site must be verified to use the right helper for its backing-object type. Splitting Build (4 helpers = 4 invariants) from Wire (13 mechanical retrofits per Rule 2 boilerplate sizing) keeps both shards within budget.

2. **Build/Wire separator from /todos workflow.** The /todos workflow explicitly mandates: "Build vs Wire is a separate todo." A "build the helper" todo is complete when the helper exists + is tested. A "wire the call sites" todo is complete when no direct-access call site remains. These are NOT the same task and the original S4 collapsed them.

## Sequencing implication

The 4-wave structure now reads:

- Wave 1A (parallel): T1, T2, T4
- Wave 1B (parallel): T5
- Wave 2: T3
- Wave 3: T6 (cross-package ClassVar declarations)
- Wave 3a: T7a (Build helpers + tests, depends on T6 for typed declarations on dependency types)
- Wave 3b: T7b (Wire 13 retrofits, depends on T7a)
- Wave 4: T8 (regression gate, depends on all preceding shards merged)

Total shards: 9 (was 8). Total waves: 5 (was 4) when counting 3a + 3b separately, OR 4 if 3a + 3b are treated as a single wave's sequential pair.

## What this unlocks / blocks

**Unlocks:**

- T7a can land independently: helpers exist + tested, even if T7b is delayed.
- The Build-then-Wire pattern becomes a precedent for future cleanups that introduce helpers + retrofit call sites.

**Blocks:**

- T7b cannot launch until T7a's commit is on `main` (T7b's verification grep references `_require_*` helpers that must exist).

## For Discussion

- Does splitting T7 add meaningful overhead vs the safety it provides? (Answer: marginal — both shards are small; the split costs one extra PR cycle but converts a ≤10-invariant ceiling violation into compliance.)
- If a future helper family is discovered during T7a implementation (e.g. a 5th `_require_*` candidate surfaces from reading L293 context), does T7a absorb it or does a T7c land later? (Recommendation: absorb in T7a IF total helper count stays ≤6; otherwise file as T7c.)
