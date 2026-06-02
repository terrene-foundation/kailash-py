# #643 Analysis Findings — FeatureStore canonical surface (2026-06-02)

Method: 3 parallel investigators (deprecation mechanism / wiring-test infra / caller map)

- adversarial red-team, then orchestrator re-verified every load-bearing claim against
  source/PyPI directly (investigators erred — red-team caught a phantom `packages/kailash-ml/specs/`
  path; orchestrator independently confirmed the PyPI-publish + method-surface facts).

## Headline: the issue's framing is STALE — step 1 already shipped

| Issue claim (2026-04-30)                       | Verified reality (2026-06-02)                                                                                                                                                                            | Evidence                                                                                                        |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Bridge release (DeprecationWarning) is pending | **SHIPPED in PyPI 1.7.2** (2026-05-06)                                                                                                                                                                   | CHANGELOG:30 "FeatureStore deprecation-warning bridge (#643)"; commit `9e186e743`; `pip index` shows 1.7.2 live |
| Warning injection needs implementing           | **Live** at `__init__.py:676-690` (PEP-562 `__getattr__`, `name=="FeatureStore"` guard, `DeprecationWarning` stacklevel=2, fires on access only — never at import)                                       | direct source read                                                                                              |
| Wiring test needs adding                       | **Exists**: `tests/integration/test_feature_store_wiring.py` (599 lines, real SQLite DataFlow, 15 facade-manager-detection assertions) + Postgres companion `tests/regression/test_feature_store_e2e.py` | direct source read                                                                                              |
| Package at 1.1.1; bump to 1.2.0                | Package at **1.7.4**; any bridge bump would be 1.8.0 — but bridge already shipped, so no release pending                                                                                                 | pyproject + `_version.py`                                                                                       |
| Docs need canonical-form update                | README/MIGRATION/CHANGELOG **done**; 4 skill examples still legacy                                                                                                                                       | grep sweep                                                                                                      |

## The real picture: canonical surface is read-only BY DESIGN

`kailash_ml.features.FeatureStore` is **not** an incomplete clone of legacy — it is a deliberate
read-only retrieval facade per spec §1.2 ("What FeatureStore Does NOT Do in 1.0+"). Surfaces:

- **Canonical** (`features/store.py`): `get_features` + `cache_key_for_row` + `invalidation_pattern` + 2 properties. **1 operation.**
- **Legacy** (`engines/feature_store.py`): `initialize`, `register_features`, `compute`, `store`, `get_features`, `get_training_set`, `get_features_lazy`, `list_schemas`. **8 operations.**

The 1.0+ architecture moved materialization/write OUT of FeatureStore (to DataFlow models + the
`dataflow.ml.ml_feature_source` polars binding). The spec is internally consistent; it does NOT
over-claim the canonical method surface.

## CONFIRMED functional gap (the real remaining value): canonical `get_features` is non-functional

`get_features` (`store.py:197`) calls `ml_feature_source(schema, ...)` passing a `FeatureSchema`.
The binding (`_feature_source.py:99-103`) hard-requires a callable `.materialize(...)` on its
`feature_group` argument. `FeatureSchema` has `to_dict`/`from_dict`/`field_names`/`with_features`
— **no `.materialize`**. So `get_features` against any backend raises `FeatureSourceError`
(re-wrapped as `FeatureStoreError`). **The canonical surface's sole operation does not complete
end-to-end.** This is the spec-vs-source gap that actually matters — far larger than the
import-resolution drift the issue focused on. It also blocks any future 2.0.0 cutover.

## Implications for the issue's step 1 / step 3

- **Step 1 (bridge):** DONE + SHIPPED (1.7.2). No release pending.
- **Step 1 docs (4 skill files):** CANNOT be mechanically migrated to canonical — they demonstrate
  the legacy write workflow (`register_features`/`store`/`initialize`) which the canonical surface
  does not have, and the canonical read path (`get_features`) is itself broken. Interim = deprecation
  banner on legacy examples; true fix waits on the functional gap.
- **Step 3 (2.0.0 cutover):** BLOCKED — not a switch-flip. Requires (a) the `get_features` functional
  gap fixed, (b) a documented write-path migration story (legacy callers using `register_features`/
  `store` must move to DataFlow models + binding), (c) feature-parity decisions on `get_training_set`/
  `get_features_lazy`/`list_schemas`.

## Fixed this session (unblocked, owned per zero-tolerance Rule 1)

- `specs/ml-feature-store.md:3` + `specs/ml-automl.md:3`: phantom-verified version citation
  ("1.1.1, verified at \_version.py" while `_version.py`=1.7.4) → dated-snapshot form (1.7.4, 2026-06-02).
  spec-accuracy MUST-1 (phantom-verified citation) closed.

## Remaining dispositions (need decision — see journal/0001 + tasks)

1. The `get_features` `.materialize` functional gap — file + scope a fix (3 candidate fixes; design-ambiguous).
2. 4 skill examples — banner-now vs wait-for-functional-fix; 3 are loom-synced (edit-then-/sync).
3. Stale skip-comment `test_feature_store_e2e.py:68-72` (claims binding unwired; it resolves via Path 2 — the real blocker is the `.materialize` mismatch the comment never mentions).
4. Update #643 to reflect bridge-shipped reality.
