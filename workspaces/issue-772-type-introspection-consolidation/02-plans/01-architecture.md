# #772 — Consolidate parallel type-introspection helpers (DataFlow core)

Status: design COMPLETE + verified against source (kailash-dataflow 2.11.2). Single shard.
Verification receipt: forest-verify workflow `wf_4450995c-dab` verdict for #772 + direct source reads
(type_processor.py:49-93/127-130/335-345, nodes.py:153-172/357-445) this session.

## Root cause (verified, empirically confirmed)

Three+ helpers each independently implement the **two-spelling Optional/Union unwrap**
(`origin is Union or origin is types.UnionType` → extract non-`None` args → recurse). When a new
type-form appears, EVERY copy must be patched independently — the maintenance tax #772 predicted.

**The prediction FIRED:** commit `d66fb0090` (#1228, PEP 604 `T | None`, 2026-06-01) patched the
UnionType spelling into `_normalize_type_annotation` (nodes.py), `_normalize_id_type` (nodes.py),
AND `_resolve_type` (type_processor.py) — plus engine.py / schema.py / model_validator.py /
fk_aware_model_integration.py. The exact "patch the Nth site instead of consolidate" anti-pattern
the issue exists to prevent. #1207 was the prior instance. This is no longer speculative.

### The four drift-prone sites (in-scope)

| Site                                                         | File:line                   | Post-detection policy (MUST preserve)                                                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------------------------ | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TypeAwareFieldProcessor._resolve_type`                      | `type_processor.py:49-93`   | single non-None → recurse; **multi-type union → return annotation as-is**; non-union generic → `get_origin`; else annotation. Returns isinstance-usable type.                                                                                                                                                                                                               |
| `TypeAwareFieldProcessor.validate_field` (union-passthrough) | `type_processor.py:127-130` | if resolved type is still a (multi-type) union → pass value through unchanged.                                                                                                                                                                                                                                                                                              |
| `NodeGenerator._normalize_type_annotation`                   | `nodes.py:357-445`          | union → recurse on **first** non-None (Optional, single-union, multi-union all collapse to first); `Union[None]` → `str`; container generic → base type (list/dict/tuple/set); other generic → origin; regular type → itself; datetime/date/time/Decimal → themselves; **fallback `str`**. Optional-detection preserved SEPARATELY (get_parameters reads `required=False`). |
| `_normalize_id_type`                                         | `nodes.py:153-172`          | union → recurse on first non-None; no non-None → `str`; isinstance(type) → itself; else `str`.                                                                                                                                                                                                                                                                              |

**Semantic divergence to PRESERVE (do NOT unify):** `_resolve_type` returns multi-type unions
(`str | int`) AS-IS; the other two recurse on the first non-None arg. The consolidation centralizes
only the DETECTION + non-None extraction; each caller keeps its own post-detection policy.

## Chosen design — single detection primitive, callers keep policy

New module `packages/kailash-dataflow/src/dataflow/core/type_introspection.py`:

```python
import types
import typing
from typing import Any, Union, get_args, get_origin

def union_non_none_args(annotation: Any) -> list | None:
    """Two-spelling Optional/Union detection — the SINGLE place a new union
    spelling is handled (issue #772; #1207/#1228 PEP-604 drift is the evidence).
    Returns the list of non-None args if `annotation` is a Union/Optional in
    EITHER spelling (typing.Union / Optional[T] OR PEP 604 `T | None`), else None.
    A multi-type union with no None returns all its args (caller decides policy).
    """
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return [a for a in get_args(annotation) if a is not type(None)]
    return None

def strip_annotated(annotation: Any) -> Any:
    """Annotated[T, ...] -> T (single layer). Verified 3.12: get_origin is
    typing.Annotated, get_args[0] is the wrapped type. Non-Annotated passes through.
    This is the issue's named next-drift example (typing.Annotated) handled in ONE place."""
    if get_origin(annotation) is typing.Annotated:
        return get_args(annotation)[0]
    return annotation
```

Each site:

- `_resolve_type`: `strip_annotated` first; `union_non_none_args` → len==1 recurse / else return annotation; non-union → `get_origin` or annotation. (behavior-preserving + Annotated now stripped)
- `_normalize_type_annotation`: `strip_annotated` first; `union_non_none_args` → non-empty recurse on `[0]` / empty → `str`; then the existing container-base + special-type + `str`-fallback block (drop the now-redundant standalone `types.UnionType` block + the `__origin__ is Union` branch — both subsumed by the shared helper).
- `_normalize_id_type`: `strip_annotated` first; `union_non_none_args` → non-empty recurse / empty → `str`; isinstance → itself; else `str`.
- `validate_field`: replace the inline `_origin is Union or _origin is types.UnionType` check with `union_non_none_args(expected_type) is not None`.

## Invariants (5) — all must hold post-refactor

1. `_resolve_type` returns isinstance-usable types AND multi-type union → annotation as-is.
2. `_normalize_type_annotation` base-container mapping + Optional → inner (required=False preserved) + `str` fallback.
3. `_normalize_id_type` `str` fallback on unknown.
4. `validate_field` passes multi-type unions through unchanged.
5. Two-spelling union detection exists in EXACTLY ONE place (structural-invariant test).

## Tests (Tier-1 deterministic + structural invariant; Tier-2 node-gen wiring)

New `packages/kailash-dataflow/tests/.../test_type_introspection.py` (or unit dir):

- `union_non_none_args`: Optional[int]→[int]; int|None→[int]; str|int→[str,int]; list[str]→None; bare int→None; Union[None]/Optional-of-None edge.
- `strip_annotated`: Annotated[int,"x"]→int; Annotated[list[str],meta]→list[str]; bare int→int.
- Per-helper behavioral parity (call each helper, assert exact return) for: `list[str]`, `Optional[list[str]]`, `int | None` (PEP604), `typing.List[str]`, `dict[str,Any]`, `str | int` (multi-union — `_resolve_type` returns as-is, others recurse first), `Annotated[int,"x"]` (NEW: now strips to int everywhere — document as the consolidation's proof), datetime/Decimal, plain str.
- **Structural-invariant** `@pytest.mark.regression`: assert exactly ONE `def union_non_none_args` exists (AST/grep across `packages/kailash-dataflow/src`), AND each of the 4 sites imports/calls it (no inline `is types.UnionType` survives outside type_introspection.py). Directly per cross-sdk-inspection Rule 3a signature-invariant pattern + refactor-invariants.md.
- Regression `tests/regression/test_issue_772_*.py` mirroring #768 (parameterized-generics on \_resolve_type), #1207, #1228 (PEP604) coverage so the consolidated path keeps them green.

## Cross-SDK (cross-sdk-inspection MUST)

kailash-rs is a different language — Rust's type system has no runtime Optional/Union
introspection problem (no `get_origin`/`types.UnionType` duck-typing). Structural API divergence
(Rule 3a): no equivalent parallel-helper duplication exists in Rust. No cross-SDK issue. (Also:
`terrene-foundation/kailash-rs` is not resolvable on GitHub per session traps — no filing target.)

## Sizing / gates

~1 shard: new module ~50 LOC + 4 site edits ~40 LOC load-bearing; 5 invariants; live pytest loop.

- `/implement` reviewer + security-reviewer: REQUIRED (agents.md MUST gate).
- kailash-dataflow package change → version bump (2.11.2 → 2.11.3 patch, refactor+Annotated-add)
  - `/release` — both USER-GATED (BUILD-repo trap; feedback_build_repo_release).
- Annotated handling is a strict behavior ADD (current helpers fall through to `str` for Annotated).
  If any existing test changes, surface it — do not silently alter.
