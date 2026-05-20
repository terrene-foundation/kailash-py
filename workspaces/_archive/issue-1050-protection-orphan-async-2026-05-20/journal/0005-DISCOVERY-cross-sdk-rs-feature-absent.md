# DISCOVERY — cross-SDK: kailash-rs has no write-protection feature (#1050 AC#6)

**Date:** 2026-05-17
**Phase:** post-merge follow-up (Shard 4)
**Agent receipt:** general-purpose agentId ad290ceceb8e8edbf (read-only)

## Verdict: FALSE — #1050 bug class structurally absent in kailash-rs

Exhaustive cross-crate grep (`WriteProtection`, `protect_dataflow`,
`add_model_protection`, `ProtectedDataFlow`, `protected_engine`,
`protection_middleware`, `ProtectionConfig/Policy`) across kailash-rs
`crates/` + `bindings/` = zero matches outside unrelated trust-plane/EATP
envelope code. `crates/kailash-dataflow/src/lib.rs:55-94` has no
`protection`/`protected_engine`/`write_protection` module. kailash-rs
DataFlow is async-uniform (`express.rs` create/update all `pub async fn`)
— no sync/async dispatch duality to bypass. The #1050 feature does not
exist in kailash-rs; there is nothing to fix.

## Disposition

No upstream kailash-rs issue filed or drafted — feature absent, not a
defect (cross-sdk-inspection.md Rule 5 checklist: checked, FALSE).
Issue #1050 AC#6 (cross-SDK kailash-rs inspected) **satisfied**.
repo-scope-discipline honored: read-only inspection, no kailash-rs
edits/branches/issues.

## Distinct lower-confidence lead (NOT a #1050 equivalent)

`crates/kailash-dataflow/src/strict.rs` `StrictMode::validate_insert` /
`validate_update` has zero call sites outside `strict.rs` within the
dataflow crate — a _potential_ same-GENERAL-class orphan (enforcement
engine, no hot-path call site), but a DIFFERENT feature (read-only-field
protection, opt-in `StrictMode::enable()`), and may be invoked from the
capi / python binding layer not checked in this read-only pass. Out of
#1050 scope. Recorded here as a lead only — pursuing it requires a
separate kailash-rs-side investigation (that repo's session, not this
one — repo-scope-discipline). NOT auto-filed.
