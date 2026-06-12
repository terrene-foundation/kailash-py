# 01 — DataFlow Dependency Verification (ground-truth source check)

> Produced by read-only verification agent. Persisted by orchestrator (agent lacked Write).
> **This is the decisive ground-truth check.** Where it disagrees with `03-scope-reconciliation.md`
> (which inferred from the `(draft)` spec), THIS file's source reads win.

## Key correction: spec citation paths are STALE; the primitives DO exist

The three spec citations point at flat paths that do not exist; the primitives are real at
`dataflow/ml/` subpackage paths and are publicly re-exported from `dataflow/ml/__init__.py`
(`__all__` lines 57-85), so `from dataflow.ml import transform, ml_feature_source, hash` resolves.

| Spec citation                                                | Reality                                                                  |
| ------------------------------------------------------------ | ------------------------------------------------------------------------ |
| `dataflow-ml-integration.md §3.1` → `dataflow/transforms.py` | does not exist → real: `dataflow/ml/_transform.py`                       |
| `§2.1` → `dataflow/ml_integration.py`                        | does not exist → `ml_feature_source` at `dataflow/ml/_feature_source.py` |
| `§4.1` → `dataflow/lineage.py`                               | does not exist → real: `dataflow/ml/_hash.py`                            |

## TRUE / FALSE / UNCLEAR table

| #   | Claim                                                                                               | Verdict                                                | Evidence                                                                                                                                                                                                              |
| --- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `dataflow.transform` exists, real impl                                                              | **TRUE**                                               | `dataflow/ml/_transform.py:51` `def transform(expr, source, *, name, tenant_id=None)`; real body (`source.with_columns(expr.alias(name))` at :118), classification propagation; no `NotImplementedError`              |
| 2   | `dataflow.ml_feature_source` exists; write path?                                                    | **TRUE (exists); READ-ONLY delegation, NO write path** | `dataflow/ml/_feature_source.py:153`; delegates to `feature_group.materialize(...)` (:246-259), returns `polars.LazyFrame`. Materializer owned by the feature-group (kailash-ml side), not DataFlow                   |
| 3   | `dataflow.hash(df)` lineage hashing implemented                                                     | **TRUE**                                               | `dataflow/ml/_hash.py:55`; canonicalizes frame → Arrow IPC → `f"sha256:{hexdigest}"` (:127-128); cross-SDK byte-parity with kailash-rs; no stub                                                                       |
| 4   | ANY compute+persist materialisation primitive in DataFlow a `FeatureStore.materialize()` could wrap | **FALSE**                                              | DataFlow exposes none on the ML bridge. `ml_feature_source` is read/materialize-to-LazyFrame delegator. Generic write path is `@db.model` + `express.create`. **Persistence is the caller's (kailash-ml's) concern.** |
| 5   | kailash-dataflow version                                                                            | **2.11.3**                                             | `packages/kailash-dataflow/pyproject.toml:7`                                                                                                                                                                          |

## Exact signatures (load-bearing)

```python
# dataflow/ml/_transform.py:51
def transform(expr, source, *, name: str, tenant_id: Optional[str] = None) -> "Any"
# dataflow/ml/_feature_source.py:153
def ml_feature_source(feature_group, *, tenant_id=None, point_in_time=None,
                      since=None, until=None, limit=None) -> "Any"
# dataflow/ml/_hash.py:55
def hash(df: Any, *, algorithm: str = "sha256", stable: bool = True) -> str
```

## DECISIVE VERDICT: can `@feature` + `FeatureStore.materialize()` be built NOW?

**YES — NOT blocked on any unshipped DataFlow work.** Pure kailash-ml authoring work.

The dependency direction inverts the brief's framing. `ml_feature_source` is a **duck-typed
delegator**: it consumes any object with `.name` + a callable
`.materialize(*, tenant_id, point_in_time, since, until, limit) -> polars frame`
(`_feature_source.py:77-103`). The compute+persist logic lives on the kailash-ml
`FeatureGroup`/store side, NOT in DataFlow (which takes no hard import dep on kailash-ml,
`_feature_source.py:6-11,83-86`).

Already proven shipped: kailash-ml's internal `SchemaFeatureGroup`
(`features/_schema_feature_group.py:65`) implements exactly that `.materialize(...)` contract
(:97) against a backing DataFlow table, consumed by `FeatureStore.get_features` via
`ml_feature_source` (#1241, READ path). M2 work = add the AUTHORING/WRITE surfaces:

- public `FeatureGroup` (distinct from the internal `SchemaFeatureGroup` read adapter)
- `@feature` decorator → calls shipped `dataflow.transform`
- `FeatureStore.materialize()` → compute+persist via `@db.model`/`express` + lineage via shipped `dataflow.hash`

**`ml-feature-store.md §11.2` "Deferred until DataFlow ships a materialisation primitive" is
STALE/incorrect** — DataFlow already ships `transform`/`ml_feature_source`/`hash`. No missing
DataFlow primitive. The brief (`briefs/01-issue-1302.md`) is accurate; the §11.2 disposition is not.

## Cross-package contract constraint for the M2 plan (not a blocker)

`ml_feature_source` calls `feature_group.materialize(tenant_id=, point_in_time=, since=, until=, limit=)`
(exact 5-kwarg surface) and raises `FeatureSourceError` on `TypeError` (`_feature_source.py:262-269`).
Any public M2 `FeatureGroup.materialize()` **MUST accept all 5 kwargs** to satisfy the binding contract.
The internal `SchemaFeatureGroup.materialize` (`_schema_feature_group.py:97-105`) already matches — the
public class must keep parity.
