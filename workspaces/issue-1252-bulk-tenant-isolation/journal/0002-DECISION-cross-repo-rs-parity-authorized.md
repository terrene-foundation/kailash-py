# 0002 — DECISION: cross-repo kailash-rs parity check authorized

cross-repo-authorized: terrene-foundation/kailash-rs

**Date:** 2026-06-03
**Requester:** user (co-owner), in-session genuine turn.
**Target repo:** terrene-foundation/kailash-rs (the Rust SDK BUILD repo).
**Verbatim instruction:** "approved" — granted in direct response to the agent's
message that ended: "The Rust SDK parity check (F30) for this tenant-injection
bug class — it's a different repo, so it needs your explicit go."

## Authorized bounded action (per repo-scope-discipline.md User-Authorized Exception)

READ-ONLY inspection of kailash-rs's DataFlow tenant-isolation code to check for
parity of the three bug classes fixed in kailash-py (#1249 / #1252, dataflow
2.11.0+2.11.1):

1. Tenant-injection placeholder/identifier handling — the `?`-vs-`$N` /
   quoted-identifier class (kailash-py: `QueryInterceptor` SELECT injection
   mis-bound LIMIT on Postgres; quoted-table validator/injection).
2. Bulk-path tenant source — stale-dict vs live-context (kailash-py: `db.bulk`
   read `_tenant_context` instead of the `switch()` contextvar → NULL writes,
   unscoped update/delete).
3. Fail-open on no-bound-tenant under multi-tenant (kailash-py: write persisted
   NULL-tenant row / read returned all rows before the fail-closed guard).

## Scope bounds (MUST hold)

- READ ONLY — no edits, no branches, no pushes, no comments against kailash-rs.
- **No auto-filing.** If a parity gap is found, DRAFT a scrubbed minimal-repro
  issue (per `upstream-issue-hygiene.md` Rules 2+3) and return it to the user for
  the per-issue human filing gate (Rule 1). Do NOT run `gh issue create`.
- Only the named inspection against only kailash-rs; no incidental sibling reads.

Context note: issue #1249 noted the rs equivalent path is "structurally different
and likely unaffected, but worth a parity glance" — this inspection confirms or
refutes that.

## CONCLUSION (read-only inspection complete) — NO PARITY BUG; nothing to file

kailash-rs DataFlow (`crates/kailash-dataflow/src/express.rs`, `query.rs`,
`connection.rs`) is **structurally immune** to all three bug classes. The #1249
"structurally different and likely unaffected" note is CONFIRMED.

1. **Stale tenant source (#1252) — IMMUNE.** rs threads `tenant_id: Option<&str>`
   as an EXPLICIT parameter through every variant (`create_with_tenant`,
   `read_with_tenant`, `upsert_with_tenant`, `bulk_create_with_tenant`, …). There
   is no implicit context/dict read — no dual-source ambiguity like Python's
   `_tenant_context` dict vs `switch()` contextvar.

2. **Fail-open on no-bound-tenant (#1249) — IMMUNE.** Every non-tenant variant
   delegates with `tenant_id=None`; `_opt_with_tenant` calls
   `model.require_tenant(tenant_id)?` which returns `DataFlowError::TenantRequired`
   for multi-tenant models (express.rs:601 `if model.is_multi_tenant()`,
   :817/:1093 splice guards, bulk/upsert at :1208/:1547). Fail-closed by design,
   not by a guard bolted on after a leak.

3. **`?`-vs-`$N` placeholder regression (#1249 Postgres) — IMMUNE.** rs builds
   queries with uniform `?` placeholders (`AND tenant_id = ?`, express.rs:822/
   1093/2167) and binds via **sqlx** with the `Any` driver (connection.rs:30),
   which converts `?`→`$N` and binds positionally at the DRIVER layer over the
   WHOLE query. The Python bug arose specifically from regex-injecting a `?` into
   an already-`$N` query + not renumbering — a string-manipulation failure mode
   that cannot occur in the rs typed/sqlx path.

rs also ships dedicated tenant-isolation tests
(`tests/tenant_isolation_express_wiring.rs`, `tests/tenancy_test.rs`).

**Disposition:** No `gh issue create`. No draft needed. The Python bugs were
artifacts of the implicit-interceptor + regex-SQL-injection + dual-tenant-source
design; rs's explicit-parameter + sqlx + require_tenant design has none of those
surfaces. F30 CLOSED — parity verified clean.
