---
type: AMENDMENT
date: 2026-07-05
author: agent
display_id: esperie
person_id: esperie
project: dataflow-driver-error-sanitization-1552
topic: outcome of the authorized kailash-rs cross-SDK inspection + filing (0012)
phase: codify
relates_to: 0012-AUTHORIZATION-cross-repo-kailash-rs-1552-cross-sdk
---

# AMENDMENT — kailash-rs #1552 cross-SDK inspection: outcome

Extends the 0012 authorization receipt with the completed disposition.

## Inspection findings (READ, per grant part 1)

The #1552 driver-error leak class IS present in the Rust SDK, with **no
`sanitize_db_error`-equivalent** driver-error redactor (only `sanitize_validation_errors`

- classification redaction + `sql_log_mask` which masks _password literals_ in
  `CREATE ROLE/USER` DDL, not driver-error values):

* `crates/kailash-dataflow/src/error.rs` — `DataFlowError::Database(#[from] sqlx::Error)`
  with `#[error("database error: {0}")]` renders the raw `sqlx::Error` verbatim;
  `DDLFailed { message: err.to_string() }` captures the raw driver string. Both reach
  logs + the returned `NodeError` (via `impl From<DataFlowError> for NodeError`).
* **Dialect-scoped severity** (the honest nuance): on **MySQL** the value is in the
  driver PRIMARY message (`Duplicate entry '<value>' for key`) that sqlx `Display`
  renders → LEAKS. On **PostgreSQL** the value lives in the `DETAIL` field, which the
  code never accesses (`grep .detail()` → zero hits) and sqlx's default `Display`
  omits → the PG value does NOT currently leak via this path.

## Filing (per grant part 2)

Filed **esperie-enterprise/kailash-rs#1639** — `cross-sdk` label, cross-referenced to
kailash-py#1552, scrubbed per `upstream-issue-hygiene.md` MUST-2/3 (SDK-API-surface
scope + minimal MySQL repro + acceptance criteria; no consumer/workspace/path leakage).

## Cross-reference direction (Rule 6 compliance)

Referenced rs#1639 → kailash-py#1552 only. Did NOT add a reverse comment on the public
#1552 naming the private rs repo — that would leak the private-repo slug into a
public artifact per `cross-sdk-inspection.md` Rule 6.

## Deferred

The rs REMEDIATION (add the redactor + route `Database`/`DDLFailed` renders through it,
mirroring #1552) is a dedicated kailash-rs session — NOT covered by the 0012 grant
(inspect + file only). Tracked as rs#1639.
