# DISCOVERY — `ml-feature-store.md §11.2` deferral premise is stale; DataFlow primitives shipped

**Date:** 2026-06-12
**Phase:** /analyze (FM2 / #1302)
**Type:** DISCOVERY

## Finding

`specs/ml-feature-store.md §11.2` defers the `@feature` decorator + `FeatureStore.materialize()`
"until DataFlow ships a materialisation primitive that the FeatureStore can wrap." A parallel
analysis agent that inferred scope from this disposition concluded the M2 surfaces were blocked and
recommended re-scoping #1302 to a spec-graduation-only workstream.

An independent ground-truth source check (kailash-dataflow 2.11.3) refuted the premise:
`dataflow.transform` (`dataflow/ml/_transform.py:51`), `dataflow.ml_feature_source`
(`dataflow/ml/_feature_source.py:153`), and `dataflow.hash` (`dataflow/ml/_hash.py:55`) all ship as
real implementations and are publicly re-exported from `dataflow/ml/__init__.py`. The spec cites
**stale flat paths** (`dataflow/transforms.py`, `dataflow/ml_integration.py`, `dataflow/lineage.py`)
that never existed at those locations — the primitives live under `dataflow/ml/`.

The compute+persist materialisation logic is the **caller's** concern (kailash-ml side, via
`@db.model`/`express`), not a DataFlow primitive — and the internal `SchemaFeatureGroup` adapter
(#1241) already proves the `.materialize(...)` duck-type contract works. So `@feature`/`materialize`
are buildable now as pure kailash-ml authoring work.

## Why it matters

The stale §11.2 disposition would have mis-scoped the entire workstream — re-scoping a real
~6-surface implementation down to a 1-session spec patch, leaving #1302's acceptance criteria
unmet. This is the "stale state-claim" failure mode (`value-prioritization.md` MUST-2 state-anchor
clause): a forest entry's deferral premise rested on a primitive that had since shipped; only a full
source re-read caught it before a plan committed to the wrong scope.

It also confirms the value of `agents.md` parallel brief-claim verification: the scope agent
inherited the spec's stale framing; the independent source-check agent caught it. One agent alone
would have shipped the wrong scope.

## Action

- Build the M2 surfaces (corrected scope in `01-analysis/04-synthesis-reconciled-scope.md`).
- Correct `ml-feature-store.md §11.2` (stale deferral) + `dataflow-ml-integration.md` stale citation
  paths during the spec-graduation shard (S6), per `spec-accuracy.md`.
