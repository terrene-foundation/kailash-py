# Workspace: issues-492-497 — Security hardening + cross-SDK audits

Created: 2026-04-18
Source: open GH issues filed 2026-04-17 → 2026-04-18 (excluding #490, #491, #494 — resolved)

## Goal

Work through 5 open issues consolidated from this session's audit wave and yesterday's bulk_upsert audit. Mix of one confirmed P0 SQLi + one pre-existing test-suite drift + three cross-SDK verification tickets.

## Issues in scope

### P0 — confirmed vulnerability

**#492 — `bulk_upsert._build_upsert_query` inlines values via string-escape (SQLi risk)**

- `packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py:432-450` — `_build_upsert_query` builds INSERT VALUES via `value.replace("'", "''")` instead of parameterized placeholders.
- Injection vector on backslash, `\0`, Unicode quote variants, multi-byte sequences.
- Every other DataFlow codegen path uses `$N` / `%s` / `?`.
- Violates `rules/infrastructure-sql.md` and `rules/security.md` § Parameterized Queries.
- Fix: route VALUES through driver parameter binding. Add Tier 2 regression test with injection payloads at `tests/integration/security/test_bulk_upsert_sql_injection.py`.
- Cross-SDK: check kailash-rs `crates/kailash-dataflow/src/nodes/bulk_upsert.rs` for same pattern.

### P1 — pre-existing test drift

**#493 — 3 pre-existing failures in DataFlow security suite (sanitizer + DDL logging drift)**

- `test_create_node_sql_injection_protection` — self-contradictory assertions (lines 83 vs 86). Test authored assuming quote-escape; sanitizer now does token-replace.
- `test_parameter_type_enforcement_prevents_injection` — expected `pytest.raises(Exception)` doesn't fire; sanitizer silently strips.
- `test_ddl_error_logging_and_reporting` — expected ERROR log not emitted; DDL error path likely moved to WARN.
- Failing since `b032635f` (2026-04-02, DataFlow 2.0 Phase 8.1d), 330+ commits.
- Fix requires deciding canonical sanitizer contract (quote-escape vs token-replace vs raise), aligning all 3 tests, pinning contract in `rules/security.md`.

### P2 — cross-SDK audit (may find nothing)

**#495 — ML register_estimator() parity**

- kailash-rs#402 (commit `5429928c`) added `register_estimator()` / `register_transformer()` to open hardcoded allowlist in Pipeline/FeatureUnion/ColumnTransformer.
- Verify kailash-py ML Pipeline has the same hardcoded allowlist; if so, add parallel API.
- Registry keyed by type (not duck-typed). Error messages surface the unregistered type name + exact `register_estimator(...)` command.
- Tier 2 tests for built-in + registered user types through facade.

**#496 — PG placeholder bug class verification**

- kailash-rs#403 fixed Postgres codegen emitting `?` instead of `$N`.
- kailash-py uses SQLAlchemy which abstracts placeholders via bound params — exact bug likely does NOT apply.
- But verify: any raw-SQL path that bypasses SQLAlchemy (schema migration runners, DDL codegen, identifier quoting, custom SQL builders).
- Audit-only ticket — may conclude with "no parity bug" after verification.

**#497 — Nexus webhook HMAC raw-body exposure**

- kailash-rs confirmed `axum::extract::Json` discards raw bytes before handler — HMAC-over-re-serialized-JSON fails for Stripe/GitHub/Twilio (they sign exact bytes).
- Verify Python Nexus HTTP channel handler signature exposes raw `bytes`, full header map, or underlying `Request` object.
- If no: same architectural gap; document workaround. Loom global rule `rules/nexus-webhook-hmac.md` already codified.

## Out of scope

- **Closed today**: #490 (mutation-return redaction — fixed in 0a9da432), #491 (event-payload PK hash — fixed in 36060c98), #494 (cross-SDK parity tracker for #490 — closed).
- **Loom-side sync commit** for `event-payload-classification.md` — separate loom-session task.

## Success criteria

- #492: injection vector closed, Tier 2 regression green, kailash-rs cross-SDK issue filed if present there.
- #493: sanitizer contract decided + documented in `rules/security.md`, all 3 tests green.
- #495: audit concluded — either feature implemented with Tier 2 tests, or documented "no gap found".
- #496: audit concluded with enumeration of raw-SQL paths checked and verdict per path.
- #497: audit concluded with handler signature mapped — either feature gap documented + workaround rule active, or no-gap-found.

## References

- loom rules (already synced): `rules/infrastructure-sql.md`, `rules/security.md`, `rules/cross-sdk-inspection.md`, `rules/dataflow-classification.md` (no-op here — already done), `rules/nexus-webhook-hmac.md`.
- Prior session: `workspaces/gh-issues-apr14/` (structurally similar consolidation pattern).
