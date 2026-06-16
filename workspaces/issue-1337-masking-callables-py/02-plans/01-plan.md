# Issue #1337 — Standalone callable masking + record-agnostic redaction

## Brief correction (verified against source 2026-06-16)

The issue probed only core `kailash` (`kailash.security`, `kailash.database`) and
concluded "no standalone callable masking". That probe **missed the actual parity
home** — the `kailash-dataflow` package (py counterpart of rs `kailash.dataflow`),
which already ships a masking surface.

Ground truth:

| Surface                                                                                                         | Location                                     | Status                             |
| --------------------------------------------------------------------------------------------------------------- | -------------------------------------------- | ---------------------------------- |
| `MaskingStrategy` enum (NONE/HASH/REDACT/LAST_FOUR/ENCRYPT)                                                     | `dataflow/classification/types.py:54`        | EXISTS                             |
| `ClassificationPolicy.apply_masking_strategy(value, strategy)` — static, directly callable over arbitrary value | `dataflow/classification/policy.py:346`      | EXISTS                             |
| `apply_masking_to_record` / `apply_masking_to_rows` (model-bound)                                               | `dataflow/classification/policy.py:376,419`  | EXISTS (needs ModelDefinition)     |
| core `DataMaskingStage` (pipeline stage → ACM)                                                                  | `kailash/database/execution_pipeline.py:243` | EXISTS (unrelated path)            |
| core `DataMasker._mask_*` (private, dict+rule bound)                                                            | `kailash/access_control_abac.py:480`         | EXISTS (unrelated path)            |
| `SecureLogger` (regex logger-wrapper, not a Filter)                                                             | `kailash/utils/secure_logging.py:90`         | EXISTS (not classification-driven) |

## Re-scoped gap vs the two ACs

- **AC1** (directly-callable hash/last_four/redact over arbitrary strings): ~80%
  already satisfied by `apply_masking_strategy`. Genuine deltas:
  - `HASH` has NO salt/HMAC. Issue explicitly asks `hash(value, salt)`. Unsalted
    hash of low-entropy PII (SSN, phone, card) is rainbow-table-reversible.
  - Not exposed as ergonomic module-level free functions.
- **AC2** (record-agnostic redaction usable from a `logging.Filter`): GENUINELY
  MISSING. `apply_masking_to_record` requires a registered model; there is no
  `logging.Filter` anywhere.

This is real work but smaller than the issue implies. NOT a "close as
already-conformant" (#1335 was) — there are two concrete missing primitives.

## Plan (single shard — pure functions + a stdlib logging.Filter)

New module `dataflow/classification/masking.py`:

1. `hash_value(value, salt=None, length=None)` — HMAC-SHA256(salt, value) when salt
   given, else SHA-256; full hexdigest unless `length` truncates. Deterministic.
2. `last_four(value)` — mask all but final 4 chars; ≤4 → fully masked.
3. `redact(value)` — constant `"[REDACTED]"`.
4. `redact_text(text, *, patterns, keys, strategy)` — record-agnostic redaction over
   arbitrary log text / dict args (regex patterns + sensitive key names).
5. `RedactionFilter(logging.Filter)` — applies `redact_text` to `record.msg` +
   `record.args`; never raises; always returns True (never drops records).

Refactor `apply_masking_strategy` to DELEGATE to the free functions (DRY; preserves
exact current behavior for every existing enum path — backward compat).

Exports via `dataflow.classification.__init__` + `__all__`.

## Invariants (≤6, within shard budget)

1. HMAC correctness; salted ≠ unsalted; deterministic for fixed (value, salt).
2. `last_four` preserves exactly the final 4; short strings fully masked.
3. `redact` → exact `"[REDACTED]"` sentinel.
4. `apply_masking_strategy` output UNCHANGED for every existing enum path.
5. `RedactionFilter.filter()` never raises; always returns True.
6. Public exports resolve from `dataflow.classification`.

Feedback loop: Tier-2 unit tests run during the session.

## Out of scope (explicit)

- core `DataMasker` / `DataMaskingStage` (separate access-control path; not the
  parity surface; touching it risks the regression tests at
  `tests/regression/test_classification_fail_closed.py`).
- The held untracked workspace-records backlog (F5 — user gate).
