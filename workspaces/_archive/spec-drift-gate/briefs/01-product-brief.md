# Spec Drift Gate — Product Brief

**Date:** 2026-04-26
**Origin:** Wave 5 portfolio audit (38 HIGHs surfaced) + Wave 6.5 spec realignment (PR #639) demonstrated that spec-vs-code drift compounds invisibly until an active audit catches it. Goal: replace the audit-after-the-fact loop with a prevent-at-insertion loop.

## Vision

Every "is implemented" assertion in `specs/*.md` is mechanically verified against the source tree at PR time. New drift fails CI. The Wave 5 → Wave 6.5 cycle (audit, find 13 spec/code contradictions per shard, re-spec) becomes structurally impossible.

## Problem statement

Three repeating drift patterns observed in Wave 5 + Wave 6.5:

1. **Overstated specs** — spec describes capability not built. v1 `ml-automl.md` invited `from kailash_ml import Ensemble; Ensemble.from_leaderboard(...)` — the class exists at `engines/ensemble.py:611` but is not exported and the classmethod doesn't exist. Users following spec hit `ImportError`.
2. **Fabricated typed exceptions** — spec asserts `try/except FeatureGroupNotFoundError` is supported. Round 1 of `ml-feature-store.md` v2 inherited this; reviewer caught 5 fabricated classes. Downstream code following the spec gets `NameError`.
3. **Stale anchors** — spec references workspace artifacts (`W31 31b`), draft-stage predecessors (`ml-feature-store-draft.md`), or moved file paths. Cross-references rot silently.

Today's defenses (`/redteam`, code review, periodic audits) are agent-driven and run only when an audit cycle is convened. The audit cost is high (Wave 5 = 7 shards × 3 waves = ~10-20 session-equivalents; Wave 6.5 added ~3 sessions for the re-spec). Drift accumulates between audits.

## Solution sketch

A **mechanical drift gate** running in pre-commit + CI that performs the same sweeps the audit shards ran:

- **Symbol existence** — every `class X` / `def Y` / `@decorator` / `Exception` cited in a spec MUST exist at the cited path.
- **Test file existence** — every test file enumerated in a spec MUST exist on disk (not just in a `tests/foo/` directory description).
- **Public surface alignment** — every symbol cited as exported MUST appear in the package's `__all__`.
- **Cross-spec sibling consistency** — when one spec is edited, mechanical sweep on every `specs/<sibling>*.md` for stale references to the edited spec's surface (per `rules/specs-authority.md` § 5b — full-sibling re-derivation).
- **Workspace-artifact leak detection** — `grep -E '(W3[0-9] [0-9]+|workspaces/)' specs/` returns zero matches in shipped specs (workspace history doesn't leak into authoritative content).

Optional second tier (deferred): machine-readable annex per spec MUST clause (`<!-- mech: class:kailash_ml.automl.AutoMLEngine -->`) that the gate consumes as structured input. Defer until the gate proves itself on a few specs.

## Tech stack / environment

- **Language:** Python (matches existing kailash-py tooling).
- **Hooks:** existing `.pre-commit-config.yaml` extended with a new `spec-drift-gate` hook.
- **CI:** new GitHub Actions job under `.github/workflows/`. Per `rules/git.md` § Pre-FIRST-Push CI Parity — local pre-commit run gives parity with CI before push.
- **Reuse:** `skills/spec-compliance/SKILL.md` already documents the verification protocol; the gate is the executable form of that skill.

## Constraints

- **Do NOT introduce a new test framework or new code-analysis dependency** — use stdlib `ast`, `grep`/`ripgrep`, `pathlib`. The gate must run in <30s on the full `specs/` set.
- **Do NOT block velocity for >2 weeks** — existing 36-HIGH backlog gets a one-time grace window via a `.spec-drift-baseline.json` (or equivalent) snapshot; new violations introduced after the baseline are blocking.
- **Do NOT auto-mutate specs** — the gate reports + blocks; agents fix.
- **Respect `feedback_no_auto_cicd.md`** — present the workflow file as a proposed addition; do not auto-merge a new GH Actions job without user review of cost implications.
- **Cross-SDK alignment** — kailash-py first; design with kailash-rs in mind so the same gate ports across.

## Users

- **Framework specialists** (dataflow, nexus, kaizen, ml, pact, align) — receive a clear pre-commit failure when their spec edit breaks an assertion.
- **Reviewers** — see the gate's CI status check on every PR; no need to re-run audit sweeps manually.
- **Future contributors** — see the gate's failure messages as structured guidance ("class X cited at specs/ml-foo.md:42 not found in src/kailash/ml/foo.py — add the class, fix the cite, or move to deferred section").

## Success criteria

1. **Coverage:** every `class.*Error|class \w+Engine|class \w+Store|class \w+Manager|def [a-z]\w+` mentioned in a spec is verified.
2. **False positive rate:** <5% — spec prose mentioning a class informally (e.g., "imagine a `FooEngine` class...") MUST NOT trigger the gate. Use a marker convention or context grep.
3. **Performance:** <30s wall clock on the full `specs/` set on a developer laptop.
4. **One-time baseline:** the existing 36-HIGH backlog passes via baseline snapshot; only new violations block.
5. **CI integration:** PR fails at the spec-drift-gate job when a spec is edited to introduce drift; passes when the spec is realigned.
6. **Demonstrable on real PR:** simulate Wave 6.5's CRIT-1 failure (the 5 fabricated `FeatureGroupNotFoundError` classes in round 1 of the FeatureStore draft) — gate must catch it.

## Out of scope

- **Rewriting prose** — gate verifies mechanical assertions, not narrative quality.
- **Cross-SDK Python↔Rust drift detection** — design for it; ship in this workspace only the kailash-py side.
- **Spec generation from code** — different workstream; this gate keeps drift OUT of human-authored specs.
- **Replacing /redteam** — /redteam still runs for plan-vs-implementation alignment; the gate covers spec-vs-code drift specifically.

## Acceptance criteria for this workspace cycle

- [ ] `scripts/spec_drift_gate.py` (or equivalent location) implementing the four sweeps in § "Solution sketch"
- [ ] `.pre-commit-config.yaml` entry running it on `specs/**.md` changes
- [ ] `.github/workflows/spec-drift-gate.yml` (proposed; user reviews before merge)
- [ ] `.spec-drift-baseline.json` capturing the 36-HIGH backlog as known-pre-existing
- [ ] One-spec prototype validating the sweep design (likely `ml-automl.md` since v2 is fresh)
- [ ] Documentation: a new section in `skills/spec-compliance/SKILL.md` linking to the executable form
- [ ] Tier 1 + Tier 2 tests for the gate itself (deterministic fixtures + real `specs/` sweep)
- [ ] Demonstration: a deliberately-broken spec edit fails CI; the realignment passes

## Related work

- **PR #639** — Wave 6.5 spec realignment (the trigger for this work)
- **Issue #640** — Wave 6 follow-ups (7 items the spec realignment surfaced)
- **`workspaces/portfolio-spec-audit/04-validate/W5-E2-findings.md`** — the audit shard whose mechanical sweeps the gate productionizes
- **`skills/spec-compliance/SKILL.md`** — the protocol-level documentation the gate executes
- **`rules/specs-authority.md`** § 5, § 5b, § 5c — the rule basis the gate enforces mechanically
- **`rules/orphan-detection.md`** + **`rules/facade-manager-detection.md`** — sibling rule families addressing the same drift class at the source level

## Open questions for the analyst

1. Where does the gate live — `scripts/`, `tools/`, a new `meta/` directory? Existing `scripts/` already has hooks; reuse or new location?
2. Marker convention for "informal class mention" exclusion — backticks-only? An explicit `<!-- spec-drift-gate:ignore -->` comment? Verify against existing spec prose to pick the lowest-noise option.
3. Baseline format — JSON, YAML, plain text? Whatever is simplest to diff in PR review.
4. CI matrix — does the gate run only on `specs/**.md` changes, or every PR? (Cheap enough to run every PR if <30s.)
5. Cross-SDK design — does the gate read a config that points at the package source tree, so the same script runs against `kailash-rs/`? Or duplicate per-SDK?
