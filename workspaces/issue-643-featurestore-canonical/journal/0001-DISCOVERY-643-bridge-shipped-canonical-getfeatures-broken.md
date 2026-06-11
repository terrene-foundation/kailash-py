# DISCOVERY — #643 step-1 bridge already shipped; canonical get_features is non-functional

**Date:** 2026-06-02
**Phase:** /analyze (issue-643-featurestore-canonical)
**Type:** DISCOVERY

## What we expected vs what is true

The prior-session ledger flagged #643 as "HIGH, actionable — breaking-change deprecation cycle."
That framing was stale. Direct verification (source + PyPI + CHANGELOG, not the 2026-04-30 issue body):

1. **The #643 step-1 bridge SHIPPED in kailash-ml 1.7.2 (2026-05-06).** The `DeprecationWarning`
   on legacy `from kailash_ml import FeatureStore` is live at `__init__.py:676-690` (commit
   `9e186e743`); CHANGELOG:30 titles 1.7.2 "FeatureStore deprecation-warning bridge (#643)";
   1.7.2 is published on PyPI. No release is pending for the warning.
2. **The canonical wiring test exists** (`tests/integration/test_feature_store_wiring.py`, real
   SQLite DataFlow) + a Postgres companion (`tests/regression/test_feature_store_e2e.py`).
3. **The canonical `kailash_ml.features.FeatureStore` is read-only BY DESIGN** (spec §1.2), not an
   incomplete clone — 1 operation (`get_features`) vs legacy's 8. The 1.0+ design moved writes to
   DataFlow models + the `ml_feature_source` binding. Spec is internally consistent (no over-claim).

## The real gap (CONFIRMED, load-bearing)

`get_features` (`store.py:197`) passes a `FeatureSchema` to `ml_feature_source`; the binding
(`_feature_source.py:99-103`) hard-requires a callable `.materialize(...)`, which `FeatureSchema`
does not have. **The canonical surface's only operation raises `FeatureSourceError` against any
backend** — non-functional end-to-end. This is the spec-vs-source gap that matters and the real
blocker for the eventual 2.0.0 cutover (which is therefore NOT a switch-flip).

## Receipts (durable, per verify-resource-existence MUST-4)

- `__init__.py:676-690` (warning live); commit `9e186e743`.
- `packages/kailash-ml/CHANGELOG.md:30` (1.7.2 = #643 bridge); `pip index versions kailash-ml` → 1.7.2 published.
- Method-surface grep: canonical `features/store.py` (1 op) vs legacy `engines/feature_store.py` (8 ops).
- `_feature_source.py:99-103` (`.materialize` requirement) vs `features/schema.py` method list (no `.materialize`).
- Workflow run `wf_d9aff027-2c2` (3 investigators + red-team); orchestrator re-verified all load-bearing claims.

## Disposition

- **Fixed this session:** spec phantom-verified version citation in `ml-feature-store.md:3` +
  `ml-automl.md:3` (both claimed "1.1.1 verified-at-\_version.py"; `_version.py`=1.7.4) → dated snapshot.
  spec-accuracy MUST-1 closed. zero-tolerance Rule 1 (found-it-own-it) + Rule 1a (scanner symmetry,
  both sibling specs fixed).
- **Surfaced for user decision:** the `get_features` `.materialize` functional gap (file + scope fix);
  4 skill examples (banner vs wait); #643 status update. Forest re-ranked — #643's headline value
  already delivered; the functional gap is the genuine remaining FeatureStore work.

## Meta-lesson (codify candidate)

A ledger entry that says "HIGH, actionable" is the PRIOR session's belief, not current truth. The
issue was ~90% shipped a month before being flagged "actionable." Verifying the issue's load-bearing
claims against PyPI + source (≈6 commands) before committing to a "bridge release cycle" prevented
re-implementing an already-published warning and a redundant test. Mirrors value-prioritization
MUST-3 (re-validate deferred items) + zero-tolerance Rule 1c (post-context-boundary claims unprovable).

---

## FOLLOW-UP DISCOVERY (2026-06-03, post-1.7.5 release) — no-timestamp path skips latest-per-entity dedup

The published-wheel end-to-end walk (build-repo-release-discipline Rule 2 + user-flow-validation) caught a semantic bug the unit/integration/regression gates missed: `get_features(schema)` with NO timestamp returned ALL rows including duplicate entities (`u1` twice) instead of the latest row per entity. The `get_features` contract (store.py docstring) states "When timestamp is None the latest values are returned." The adapter's as-of dedup was gated on `point_in_time is not None`, so the no-timestamp "latest" case skipped dedup.

Root of the test gap: every happy-path test used ONE row per entity, so dedup-vs-no-dedup was unobservable. The published-wheel walk used 2 rows for `u1` and exposed it.

Fix (1.7.6): dedup-to-latest-per-entity whenever `timestamp_column` exists (both the timestamp-given as-of case AND the no-timestamp latest case); the window filter (`ts <= T`) still applies only when `point_in_time` is given. Tests strengthened to use multiple rows per entity.

1.7.5 (on PyPI) is correct for the timestamp-given case + single-row-per-entity tables; 1.7.6 supersedes it for the no-timestamp multi-row case.
