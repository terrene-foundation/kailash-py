# DISCOVERY — Wave 1 (Authoring + Registry) convergence + learning delta

**Date:** 2026-06-12
**Phase:** /implement → inter-wave gate G1/G2 (wave-loop)
**Type:** DISCOVERY (convergence receipt + claim-vs-found delta)

## Convergence receipt (wave-loop MUST-5 — durable external receipt)

Wave 1 (Shards A + E) reached **2 consecutive clean redteam rounds** = converged.

- **Round 1** (reviewer task `a42adb0077bbd9027`, security-reviewer `a0f0bf3976f010428`):
  both APPROVE, zero CRIT/HIGH. Findings: 3 MED + 2 LOW.
- **Fixes** committed `6368c6e5c` (Wave-1 round-1 dispositions).
- **Round 2** (reviewer task `a0dd1bf58c9c0e952`, security-reviewer `acc140d1c22407fec`):
  both APPROVE — round clean (convergence candidate), all 3 round-1 findings RESOLVED,
  zero new CRIT/HIGH/MED. Code-reviewer re-ran the suite: 18 passed, pyright clean.

Commits on `feat/fm2-wave1-authoring-registry`: `bcb8a2c65` (A), `373415e42` (E), `6368c6e5c` (fixes).

## Claim-vs-found delta (the learning — lightweight per wave-loop G2, NOT a full /codify)

1. **Environment was broken pre-implementation** (not a Wave-1 code defect, but it gated all
   validation): `kailash-ml` resolved to a stale 0.9.0 wheel (no `features` module) and
   `kailash-dataflow` was editable-installed pointing at a **deleted worktree**
   (`.claude/worktrees/agent-a1af342e8bb6627eb/...`). Repaired by `pip install -e` from the
   canonical `packages/*/src` paths. → matches the session-notes "installed wheels lag source" trap.
   **Forward:** any future ml/dataflow session MUST verify `import dataflow` + `from kailash_ml.features import FeatureGroup` resolve to source before trusting test runs.

2. **Round-1 findings, all same-class (Wave-1 surface), fixed in-session:**
   - Orphan `__all__`: 3 exceptions were in the package re-export but absent from the CANONICAL
     `src/kailash/ml/errors.py::__all__` + tree (orphan-detection Rule 6). **Forward:** Shards B/C/F
     land their new exceptions in the canonical module's `__all__` + tree, not just the re-export.
   - SQLite-only immutability marker: a `_DB_*_MARKER` string matched only SQLite text; Postgres/MySQL
     re-raised the raw driver error. DataFlow surfaces NO typed integrity exception → dialect-aware
     marker tuple is the correct FM2-scoped fix. **Forward:** any code translating DB errors by string
     MUST cover all 3 dialects. (Cross-SDK / DataFlow follow-up: a typed `DataFlowIntegrityError` would
     let consumers catch a class — out of FM2 scope.)
   - Default `express.list` limit=100 silently caps version-history scans. **Forward:** any
     correctness-bearing scan passes an explicit `limit`.

3. **Pre-existing, out of FM2 scope (flagged, not fixed):** `tests/integration/rl/test_rl_align_cross_sdk_wiring.py`
   ImportError (test last touched `41a217dc1`, predates session) — a missing kailash-align editable
   dep. Not in the FM2 blast radius; surfaced for a future env/align session.

## Spec/todo amendments for later waves (G3)

- `specs/ml-feature-store.md §11.1/§11.3` already moved Deferred→shipped first-instance (Shards A/E).
- Wave 2 Shard B (`FeatureStore.materialize`): compose a `FeatureMaterialiser` taking the DataFlow
  instance (facade-manager Rule 3); land its typed exceptions in canonical `errors.py::__all__`+tree
  (learning #2). No signature drift from Wave 1 to amend.

## Re-value-rank (G4)

Unchanged: Wave 2 (materialize + GDPR) HIGH, depends on Wave 1 (now landed on branch). Wave 3
(online + spec graduation) next. Deferred Surface G (DB-side as-of) value-anchor re-validated:
still genuinely DataFlow-gated (no window/aggregation primitive shipped in 2.11.3) — no change.
