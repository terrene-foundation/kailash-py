---
type: DECISION
date: 2026-05-22
created_at: 2026-05-22T00:00:00+00:00
author: co-authored
project: issue-1035-delegate-py
topic: S7 conformance schema design — alignment with rs canonical schema + Fence B
phase: implement
tags: [s7, conformance, cross-sdk, fence-b, behavioural-only]
---

# S7 ConformanceVector schema — design alignment with kailash-rs canonical

## Context

S7 of issue #1035 (Delegate composition primitive) ships the conformance schema

- first cross-SDK byte-shape vectors. The brief proposed:

* `ConformanceVector(vector_id, category, inputs, expected_byte_hash, expected_payload, pinned_at, pinned_by_sdk)`
* `receipts_agree(rs_result: RuntimeExecutionResult, py_result: RuntimeExecutionResult) -> ReceiptsAgreeReport`
* 5 JSON-fixture vectors with SHA-256 hashes of canonical-JSON serializations

Discovery of the kailash-rs canonical (`crates/kailash-delegate-conformance/`, READ-only
per `repo-scope-discipline.md` User-Authorized Exception receipt at journal/0002)
surfaced two structural constraints that force a re-design:

## Discovery — rs canonical schema (READ-only inspection)

The rs crate `kailash-delegate-conformance` (Cargo.toml `publish = false` +
`LicenseRef-Proprietary`, with OSS-mirror plan documented in lib.rs) ships:

1. **`ConformanceVector { id, spec_anchor: SpecAnchor, given, behaviour, expected: BehaviouralOutcome }`** —
   behavioural-only assertions anchored to Delegate-spec § numbers.
   `BehaviouralOutcome` is a CLOSED enum: `Accept | Reject | EscalateToHuman`.
2. **`ConformanceReceipt { implementation, vector_crate_version, commit_sha, vectors_total, vectors_passed }`** —
   counts-based cross-impl agreement record.
3. **`receipts_agree(a, b) -> bool`** — verifies BOTH receipts name SAME
   `(vector_crate_version, commit_sha)` AND both fully conformed AND impls
   are DISTINCT. NEVER a field-by-field engine diff.
4. **F1 fence** — the conformance crate depends on NO `kailash-delegate-*`
   engine crate; an engine symbol structurally cannot resolve.
5. **F4 protocol** — the spec deliberately AVOIDS field-by-field engine diff:
   "Naively, 'agree' would mean diffing the two engines' outputs field-by-field —
   but that re-introduces the F1 leak (an engine internal becomes the comparison key)."

## Constraints This Imposes On S7

### Constraint 1 — Fence B (`tools/lint-delegate-fences.py:42-51`)

`conformance/` MUST NOT import `kailash.delegate.runtime`, `dispatch`, `trust`,
`audit`, `posture`. The brief's `receipts_agree(rs: RuntimeExecutionResult,
py: RuntimeExecutionResult)` signature would directly import
`kailash.delegate.runtime.RuntimeExecutionResult` into `conformance/schema.py` —
**this would fail the lint at first push.**

### Constraint 2 — F1 Licensing Fence (rs spec)

A vector that round-trips `RuntimeExecutionResult.to_dict()` bytes from kailash-py
WITHOUT corresponding rs-side bytes would assert a Python-side engine internal as
a cross-SDK contract. When rs gets its delegate runtime, its byte-shape MUST match
the pinned vector — but right now rs has NO delegate runtime (only the
conformance schema crate). Pinning RuntimeExecutionResult bytes today
unilaterally locks rs into matching py's encoding before rs has authored its own.

### Constraint 3 — cross-sdk-inspection.md Rule 4a (sibling-canonical vendoring)

The rs `ConformanceVector` schema (behavioural-only) IS THE CANONICAL. Vendoring
means kailash-py adopts the rs schema shape — not the brief's `byte_hash` shape.
A parallel `byte_hash`-shaped py-side schema would be the exact "parallel
hand-authored copy" Rule 4a blocks (sibling-canonical fixtures MUST be vendored,
not re-authored).

## Design Decision

**Adopt the rs canonical schema shape AND add a public-surface dict-shape
receipts-agree comparator that satisfies the brief's parity-verification intent
without violating Fence B.**

Specifically:

### Layer 1 — Behavioural conformance (vendored from rs canonical)

`src/kailash/delegate/conformance/schema.py` exports:

- `SpecAnchor` — dotted-decimal Delegate-spec § anchor, validated by
  `TryFrom<String>` equivalent in Python (`SpecAnchor.from_str`); raises
  `SchemaError` on malformed input. Byte-identical wire shape with rs:
  serializes as bare section string (e.g. `"7.3"`).
- `BehaviouralOutcome(Enum)` — `ACCEPT | REJECT | ESCALATE_TO_HUMAN`. CLOSED
  taxonomy. JSON-serializes as PascalCase (`Accept | Reject | EscalateToHuman`)
  matching rs `serde` default.
- `ConformanceVector` — frozen dataclass with `id`, `spec_anchor`, `given`,
  `behaviour`, `expected`. Validates all required fields non-empty via `validate()`.
- `validate_vector_set(vectors)` — checks unique IDs, all individually valid.
- `ConformanceVectorLoader` — `load_canonical()` from
  `tests/fixtures/delegate-conformance/canonical.json` (vendored byte-identical
  from rs once rs ships the JSON form).

### Layer 2 — Conformance receipt + receipts_agree (vendored from rs canonical)

`ConformanceReceipt(implementation, vector_crate_version, commit_sha,
vectors_total, vectors_passed)` + `receipts_agree(a, b) -> bool`. Counts-based,
not engine-diff. Byte-identical wire shape with rs.

### Layer 3 — Dict-shape comparator (Python-OSS-only extension; honors Fence B)

`receipts_agree_dict(a: dict, b: dict, *, exclude_fields: frozenset[str] = ...)
-> ReceiptsAgreeReport` operates on ALREADY-SERIALIZED `RuntimeExecutionResult.to_dict()`
output. The dict input is JSON, not an engine class — `conformance/` can compare
JSON shapes without importing engine modules.

This satisfies the brief's `receipts_agree(rs, py)` intent: callers serialize
their RuntimeExecutionResult via `.to_dict()` (a method on the engine), pass
the dicts in, get a structured `ReceiptsAgreeReport` back. Engine internals
NEVER cross the conformance boundary.

`exclude_fields` defaults to `frozenset({"terminated_at", "executed_at"})` —
observation-local fields not part of cross-impl contract.

### Layer 4 — Canonical fixtures (Python-OSS-only first; rs catches up)

`tests/fixtures/delegate-conformance/canonical.json` ships 5 behavioural vectors:

- DV-3-001 (§3 R2 composition validation)
- DV-5-001 (§5 monotonic tightening — mirrors rs catalog.rs vector)
- DV-7-001 (§7 TAOD lifecycle phase monotonicity)
- DV-9-001 (§9 audit chain emission)
- DV-10-001 (§10 G1 service-account separation — mirrors rs catalog.rs vector)

Each vector is byte-shape-compatible with rs `ConformanceVector` serde encoding.
When rs ships its JSON vector loader, we vendor rs's canonical.json byte-for-byte
per Rule 4a.

## What Changes vs The Brief

| Brief proposed                                  | Actually shipping                                           | Why                                          |
| ----------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------- |
| `expected_byte_hash`-shape vectors              | Behavioural-outcome-shape vectors (rs canonical)            | Rule 4a sibling-canonical vendoring          |
| `receipts_agree(RuntimeExecutionResult, ...)`   | `receipts_agree(ConformanceReceipt, ConformanceReceipt)`    | Fence B + rs F4 protocol                     |
| `byte_hash` field on each vector                | `expected: BehaviouralOutcome` (closed enum)                | rs F1 fence (no engine internals in vectors) |
| (not in brief)                                  | `receipts_agree_dict(dict, dict)` for runtime-result parity | Bridges brief's intent without Fence B viol  |
| (not in brief)                                  | `validate_vector_set()` mirror of rs validator              | rs canonical mirror                          |
| `pinned_by_sdk: Literal["py", "rs"]` provenance | NOT shipped (rs canonical doesn't carry this)               | Vendoring = byte-identical, no addenda       |

## Invariants (5 — within shard budget)

1. **Schema vendoring** — `ConformanceVector` / `SpecAnchor` / `BehaviouralOutcome`
   / `ConformanceReceipt` / `receipts_agree` byte-shape-match rs.
2. **Fence B preserved** — `conformance/schema.py` imports ZERO
   `kailash.delegate.{runtime,dispatch,trust,audit,posture}` symbols.
3. **Behavioural-only** — `BehaviouralOutcome` is a CLOSED enum; vectors cannot
   smuggle engine internals.
4. **Dict-shape parity contract** — `receipts_agree_dict` excludes timestamps
   AND uses ordered comparison for `audit_chain_entries` + `transitions`.
5. **Validating deserialization** — every vector deserialized from JSON routes
   through the same validator as in-code construction (no smuggling malformed
   anchors past the schema).

## Consequences

- S7 ships a behaviourally-correct, byte-shape-compatible-with-rs conformance
  schema FIRST. rs catches up to ship its JSON vector loader; py vendors then.
- The brief's `RuntimeExecutionResult` byte-comparison intent is preserved
  via Layer-3 dict-comparator that engine-callers feed via `.to_dict()` on
  the public API surface — Fence B intact.
- The "first 5 vectors" deliverable lands as behavioural vectors (not byte
  hashes); when rs ships byte-shape vectors of `RuntimeExecutionResult`,
  those vendor in as a SECOND fixture file
  (`tests/fixtures/delegate-conformance/runtime-byte-shapes.json`).

## For Discussion

1. (Counterfactual) Would shipping `byte_hash`-shape vectors today, then
   "fixing" them when rs catches up, be cheaper? — No: doing so creates a
   parallel hand-authored copy that drifts from rs canonical (Rule 4a
   violation), and the "fix" later requires every downstream test
   referencing the byte-hash shape to break + migrate.
2. (Specific data) The rs `BehaviouralOutcome` enum is non_exhaustive in
   Rust; should py's `BehaviouralOutcome` also be open-ended? — Python
   enums are inherently extensible (subclassing); the closed-taxonomy
   semantics live in `from_str` validation that raises on unknown variant.
   Matches rs runtime behavior (deserializer rejects unknown variants).
3. (Counterfactual) If rs never ships JSON vector loader, does py's
   `canonical.json` become the de-facto canonical? — Yes; per Rule 4a's
   "byte-identical" intent, py becomes canonical the moment it ships AND
   rs vendors py's `canonical.json` when rs ships its loader. The direction
   of canonicalness flips based on who lands first; the OSS mirror is the
   long-term canonical reference per rs lib.rs commentary.

## Receipt

This entry lands at `workspaces/issue-1035-delegate-py/journal/0003-DECISION-s7-conformance-schema-alignment-with-rs.md`
BEFORE any schema file is written. The companion journal/0002 records the
cross-repo READ authorization; this entry records the design pivot from the
brief's byte-shape intent to the rs canonical behavioural-only schema.
