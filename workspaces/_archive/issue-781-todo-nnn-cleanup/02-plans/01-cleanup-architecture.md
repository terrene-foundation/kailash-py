# Architecture Plan — Issue #781 TODO-NNN Cleanup

**Workspace:** `issue-781-todo-nnn-cleanup`
**Phase:** /analyze → ready for /todos approval
**Base:** `main @ dab10c5d` (2026-05-03)
**Brief:** `briefs/01-issue-781.md`

## Goal

Bring production source code into compliance with `rules/zero-tolerance.md` Rule 2 (no `TODO/FIXME/HACK/STUB/XXX` markers in production code) and Rule 6 (iterative TODOs permitted only when actively tracked). Land a CI gate that prevents future ratchet.

Success = `grep -rnE 'TODO-[0-9]+' src/ packages/*/src/ | grep -vE ':\s*///|:\s*//!|/build/'` returns zero hits OR every remaining hit has a same-line tracker link, AND a CI check fails the build on any new untracked `TODO-NNN` introduced into production source.

## Brief corrections

The brief was authored against an earlier tree state and uses a narrow regex. Three claims are corrected here so downstream phases inherit ground truth (per `rules/agents.md` MUST "Parallel Brief-Claim Verification"):

1. **Counts (DRIFTED → updated to current main)**

   | Metric                          | Brief | Current | Source       |
   | ------------------------------- | ----: | ------: | ------------ |
   | Marker hits (production source) |   244 |     254 | journal/0001 |
   | Distinct files                  |   118 |     111 | journal/0001 |
   | Distinct tracker IDs            |    98 |      56 | journal/0001 |

2. **Detection regex (NARROW → wider)**

   The brief's regex `TODO-(0[0-9]+|1[0-9]+|2[0-9]+)` requires ≥2 digits AND first digit 0/1/2 — it leaks the 300+ band (≥6 distinct IDs). Plan adopts the wider canonical form `TODO-[0-9]+`, which captures 56 distinct IDs (50 narrow + 6 in the 300+ band).

3. **`(GOV-NNN)` precedent (FALSE → replaced)**

   The brief proposes `(V<release>-NNN)` "matching the existing (GOV-NNN) convention". `(GOV-NNN)` does not exist in the codebase (zero hits). Real parenthetical precedents in production source: `(DF-NNN)` × 91, `(CARE-NNN)` × 50, `(ADR-NNN)` × 32, `(BP-NNN)` × 9. Plan replaces the `(V<release>-NNN)` proposal with an evidence-grounded convention — see § Class disposition rules.

4. **Taxonomy refinement (3-class → 4-class with 1a/1b sub-distinction)**

   Brief's three classes hold (30/30 sample classifiable, 0 unknowns), but Class 1 has two distinct syntactic shapes the brief conflates. Plan splits Class 1 into 1a (header banner) and 1b (provenance line). Different rename mechanics per class — see below.

## Refined taxonomy + disposition rules

Sample distribution (n=30, uniform across 254 hits): ~73% Class 1 / ~3% Class 2 / ~20% Class 3 / ~7% ambiguous Class-1/2 boundary. Extrapolated to full set: ~186 Class 1 (1a + 1b) / 8 Class 2 / 51 Class 3 / 9 ambiguous.

### Class 1a — header banner for shipped code

**Shape:** `# === <Topic> (v<X.Y.Z>, TODO-NNN) ===` or `# === <Topic> (TODO-NNN) ===`
**Example:** `runtime/local.py:770` — `# === Coordinated Shutdown (v0.12.0, TODO-015) ===`
**Disposition:** Replace `TODO-NNN` with `SHIPPED-vX.Y.Z` if a version is paired, else drop the parenthetical entirely. The section divider stays; the tracker tag goes.

```python
# Before
# === Coordinated Shutdown (v0.12.0, TODO-015) ===

# After
# === Coordinated Shutdown (SHIPPED-v0.12.0) ===
```

### Class 1b — module/class docstring provenance

**Shape:** `Module Foo - TODO-NNN Phase X` or `Created: <date> (Phase 3, Day 2, TODO-NNN)` in module docstrings.
**Examples:**

- `packages/kaizen-agents/.../patterns/ensemble.py:39` — `Created: 2025-10-27 (Phase 3, Day 2, TODO-174)`
- `packages/kailash-dataflow/.../mitigation_strategy_engine.py:3` — `Mitigation Strategy Engine... — TODO-140 Phase 2`

**Disposition:** Strip `TODO-NNN Phase X` references entirely. Module docstrings should describe what the module does, not which workstream produced it. Provenance belongs in `git log` and CHANGELOG, not in source. If specific provenance is load-bearing (e.g., links to an ADR), convert to `(ADR-NNN)` if an ADR exists, else delete.

### Class 2 — active iterative TODO

**Shape:** `# TODO-NNN: <description of unfinished work>` introducing a comment that describes work the file has NOT done.
**Example:** `dataflow/__init__.py:146` — `# TODO-153: Type-Aware Field Processor`
**Disposition:** Per `rules/zero-tolerance.md` Rule 6 (iterative TODOs permitted when actively tracked), each MUST acquire a same-line tracker link. Format: `# TODO-NNN: <description> (tracked: gh#<issue>)` or `(tracked: workspaces/<project>/todos/active/<file>.md)`.

If no tracker exists, the choice is binary: open a tracker AND link, OR delete the comment. "Will track later" is BLOCKED.

### Class 3 — forwarded reference to external tracker

**Shape:** `# Integration with X (TODO-N1, TODO-N2, TODO-N3)` or References blocks like `- TODO-157: Phase 3 Tasks 3S.2-3S.5`. Marker appears mid-comment as a parenthetical cross-reference.
**Example:** `packages/kailash-dataflow/.../staging_environment_manager.py:12` — `Integration with existing migration components (TODO-137,138,140,142)`
**Disposition:** Verify each cited tracker ID is still active. If yes — convert to a tracker link or delete the cross-reference. If no — delete entirely. Cross-references that survive without a live tracker are obsolete trackers (the brief's third class as originally framed).

### Ambiguous Class-1/2 boundary (~9 hits)

**Shape:** `# TODO-NNN: <topic>` precedes either a fully-shipped block (Class 1a in disguise) or actually-unfinished work (Class 2). Pattern-matching cannot disambiguate.
**Disposition:** Per-hit triage during /implement. Heuristic: read the next ~30 lines after the marker. If they implement the topic, it's Class 1a; if they punt or stub, it's Class 2. ~9 hits is bounded; budget ~30 min for the cluster.

### Convention selection — open question for human

Two candidate conventions for Class 1a / 1b "shipped" markers:

- **Option A — `(SHIPPED-vX.Y.Z)`** — explicit, grep-able, no in-tree precedent but no ambiguity. Reads as `# === Coordinated Shutdown (SHIPPED-v0.12.0) ===`. Recommended.
- **Option B — `(ADR-NNN)` reuse** — only viable for hits whose shipped work has a corresponding ADR. Most don't. Falls back to delete-the-tag for the rest.

Recommendation: Option A. Rationale: 254 hits are too many for ADR-by-ADR mapping (no ADR for `Coordinated Shutdown v0.12.0` exists today), and `SHIPPED-` is unambiguous on grep — reviewers immediately see "this isn't pending work".

## Sharding strategy

Per `rules/autonomous-execution.md` Per-Session Capacity Budget (≤500 LOC load-bearing logic / ≤5–10 invariants / ≤3–4 call-graph hops). This is comment-rewrite work — high boilerplate factor — so per-package sharding is the right axis.

| Shard | Package                                                                           | Rough hit count | Rationale                                            |
| ----- | --------------------------------------------------------------------------------- | --------------: | ---------------------------------------------------- |
| S1    | `src/kailash/` (Core SDK)                                                         |             ~25 | runtime/local.py (15) + smaller                      |
| S2    | `packages/kailash-dataflow/`                                                      |             ~30 | migrations cluster + dataflow core                   |
| S3    | `packages/kailash-kaizen/`                                                        |             ~50 | tools/native, execution, autonomy/interrupts         |
| S4    | `packages/kaizen-agents/`                                                         |             ~80 | autonomous/base.py (28) + patterns + adapters        |
| S5    | `packages/kailash-ml/`, `packages/kailash-align/`, `packages/kailash-pact/`, etc. |             ~70 | smaller packages bundled                             |
| S6    | CI gate (closing shard)                                                           |             n/a | pre-commit hook + GH Actions check + regression test |

Each shard hits one importable surface per `rules/autonomous-execution.md` MUST Rule 1. S6 lands LAST so the cleanup-then-gate ratchet holds — landing the gate before cleanup blocks every legitimate PR.

Total: 5 cleanup shards + 1 gate shard. Sized for autonomous execution at ≥3-shards-per-session (no logic, no invariants — pure comment rewrite under feedback loop).

## CI gate placement — open question for human

Three candidates, not mutually exclusive:

- **A. Pre-commit hook (local)** — runs before commit, fast feedback. Risk: bypassable via `--no-verify`; relies on contributor discipline.
- **B. GitHub Actions PR-gate workflow** — non-bypassable, runs on every PR. Higher latency (~30s for grep). Recommended primary.
- **C. Existing `lint`/`pre-commit-ci` workflow extension** — append the regex to existing tooling rather than spinning up a new workflow. Lowest CI cost.

Recommendation: B + C combined. Add the canonical regex check to the existing pre-commit-ci workflow (so it runs both locally and in CI). One file change instead of two.

Acceptance criterion for the gate: a synthetic PR that introduces `# TODO-999: test` to a production source file MUST fail CI; a PR that introduces `# TODO-999: test (tracked: gh#9999)` MUST pass.

## Refined acceptance criteria

Replaces the brief's 6-bullet list with verification-grounded versions:

1. **[ ] Detection regex** — replace narrow `TODO-(0[0-9]+|1[0-9]+|2[0-9]+)` with wider `TODO-[0-9]+` everywhere it appears (this plan, the gate, audit scripts). Captures the 6 missed IDs in the 300+ band.
2. **[ ] Per-shard classification + disposition** — every hit in S1–S5 classified into 1a/1b/2/3/ambiguous, dispositioned per § Class disposition rules. Disposition logged in shard PR body.
3. **[ ] Class 1a/1b → SHIPPED-vX.Y.Z** (or delete if no version pairing) — all header banners + provenance lines rewritten or removed.
4. **[ ] Class 2 → tracker link** — every active iterative TODO has a same-line `(tracked: gh#NNN)` or `(tracked: workspaces/.../active/...)` link, OR is deleted with rationale in the shard PR body.
5. **[ ] Class 3 → triage** — every cross-reference verified live (link added) or obsolete (deleted).
6. **[ ] Canonical grep returns zero** — `grep -rnE 'TODO-[0-9]+' src/ packages/*/src/ | grep -vE ':\s*///|:\s*//!|/build/|tracked:' | wc -l` → `0` (note the `tracked:` exclusion to honor the iterative-TODO exception).
7. **[ ] CI gate lands** — pre-commit-ci workflow (or equivalent) fails on any new untracked `TODO-NNN` in production source, validated against a synthetic test PR.
8. **[ ] Regression test** — a checked-in test (e.g., `tests/regression/test_no_untracked_todo_nnn.py`) runs the canonical grep and asserts zero. Belt-and-suspenders against pre-commit/CI drift.

## Risk register

| Risk                                                                                | Mitigation                                                                                                                                             |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------- |
| Class 1a/2 ambiguous hits dispositioned wrong → silent loss of an active TODO       | Per-hit triage with file context + git blame; quote ambiguity decisions in shard PR body for reviewer                                                  |
| Cleanup PRs touch the same files as in-flight feature work, causing merge conflicts | Branch each shard from current main HEAD just before launch; merge fast (within 1 session); no per-shard worktree pile-up                              |
| CI gate blocks legitimate cleanup PRs (shard PRs themselves carry untracked TODOs)  | Stage S6 (gate) AFTER S1–S5 land. Each cleanup shard PR lands without the gate; the gate's first PR is itself the cleanup that brings the tree to zero |
| Wider regex catches false positives (e.g., string literals containing `TODO-NNN`)   | Manual review of grep output before gate ships; consider tightening regex to `^[^"']\*\b(TODO                                                          | FIXME)-[0-9]+` if literals leak |
| Brief misses Class-4-and-beyond patterns the 30-row sample didn't surface           | Full-tree post-cleanup audit before S6 lands; any new class triggers plan revision and regression test for that shape                                  |

## Open questions for human (gate to /todos)

1. **Convention** — Option A (`SHIPPED-vX.Y.Z`) for Class 1a/1b? Or Option B (`ADR-NNN` reuse where possible, delete otherwise)? Or a third option?
2. **CI gate placement** — Recommendation is B+C (PR-gate via existing pre-commit-ci workflow). Confirm or override.
3. **Class 1b disposition default** — Plan recommends "strip provenance lines entirely". Acceptable, or preserve in some form (e.g., move to CHANGELOG)?
4. **Class 2 fallback** — When no tracker exists for an active iterative TODO, plan recommends "open tracker AND link, OR delete". Confirm — some Class 2 may represent forgotten roadmap items the SDK genuinely should ship.
5. **Sharding granularity** — Per-package (5+1) recommended. Acceptable, or split S4 (kaizen-agents, ~80 hits) into two by sub-module?
6. **Shard ordering** — Smallest first (S1 Core SDK) or largest first (S4 kaizen-agents)? Recommendation: largest first to flush the heaviest convention decisions early; smaller shards inherit the rules.

## Next phase

`/todos` — gate is the human approving this plan. The structural-gate definition in `rules/autonomous-execution.md` puts /todos at "human required". On approval, /todos breaks the 5+1 shards into per-shard todos with explicit class-disposition counts and PR/branch names.
