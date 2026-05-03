# DECISION — Issue #774: Normalize at constructor boundary, not per-site guards

**Date**: 2026-05-01
**Author**: Claude Opus 4.7 (1M context) — `/autonomize` cycle
**Type**: DECISION

## Context

Issue #774 surfaced an `AttributeError` in `dataflow/core/nodes.py:837`:

```
declared = self.model_fields.get(field_name, {}).get("type")
# AttributeError: type object 'str' has no attribute 'get'
```

`NodeGenerator.generate_*_nodes` is typed `fields: Dict[str, Any]` and accepted both shapes:

- **Dict-form** (canonical, produced by `@db.model` at `engine.py:1858`): `{"name": {"type": str, "required": True}}`
- **Bare-type form** (used by direct callers, e.g., `tests/unit/core/test_auto_generated_bulk_parameter_mapping.py:23`): `{"name": str}`

Every downstream lookup (`nodes.py:835`, `:166`, `:89`, `:429`, `:768`, `:878`, `:1031`) assumed dict-form. Bare-type input crashed at the first `.get("type")` chain.

## Issue's acceptance criteria offered two paths

1. **Per-site guards**: `isinstance(spec, dict)` check before every `.get("type")`
2. **Boundary normalization**: normalize the input once at the call boundary upstream of `validate_inputs`

## Decision: Boundary normalization

Picked path 2 (`_normalize_field_specs()` at `DataFlowNode.__init__`) plus defense-in-depth on module-level helpers (`_coerce_record_id`, `convert_datetime_fields`).

## Why boundary over per-site

- **Single source of truth.** `self.model_fields` is canonical dict-form everywhere downstream regardless of caller-supplied shape. Future contributors writing new lookups don't have to remember the dual-shape contract.
- **Lower invariant cost.** 1 normalization at constructor → all 7 lookup sites (`get_parameters` create/update, validate_inputs bulk-data guard, datetime-conversion helper, etc.) operate on a single shape. Per-site guards = 7 invariants to maintain.
- **Aligns with existing rule patterns.** `rules/security.md` § Multi-Site Kwarg Plumbing mandates same-PR sweep when a security-relevant kwarg is plumbed; the same principle generalizes — fix once at the boundary, not N times at consumers.
- **Defense-in-depth retained.** Module-level helpers (`_coerce_record_id`, `convert_datetime_fields`) accept `model_fields` from external callers that bypass the constructor; these still need their own `isinstance` guards.

## Cross-SDK disposition

Per `rules/cross-sdk-inspection.md` Rule 3a (Structural API-Divergence), kailash-rs uses `Vec<FieldDef>` with `FieldType` enum (`crates/kailash-dataflow/src/model.rs:587`, `:842`). The compiler structurally rejects passing a bare `FieldType` where a `FieldDef` struct is required. Bug class is unreachable. No upstream issue filed.

The Python-side regression test pins the contract: `test_normalize_field_specs_accepts_both_shapes` confirms both shapes converge to canonical dict-form. If a future refactor narrows the contract, the test fails loudly.

## What landed

- PR #775 (code fix): `9676a1ef` — boundary normalizer + defense-in-depth guards + 4 regression tests (Tier 1 unit, structural-invariant, Tier 2 real-Postgres round-trip)
- PR #776 (release prep): `release/v2.7.5` metadata-only branch
- Tag `dataflow-v2.7.5` → publish-pypi.yml run `25215840937` success
- PyPI `kailash-dataflow==2.7.5` installable from clean venv; `_normalize_field_specs` + `NodeGenerator` import clean
- PR #777: deployment record at `deploy/deployments/2026-05-01-dataflow-v2.7.5.md`

## What did NOT land

- `kailash-coc-claude-py/pyproject.toml` pin bump (`kailash-dataflow>=2.7.3 → >=2.7.5`) — working-tree edit only; commits stay with user per envelope (USE template = no commits on user's behalf).
- 4 unrelated `test_model_registry_runtime_injection.py` failures — predate this session per stash test, tied to in-flight commit `87287952 wip(MED-S5): drop eager runtime=self.runtime in subsystem instantiation`. Different bug class. Recorded in deployment record + flagged for next session.
