---
type: RISK
date: 2026-04-18
author: agent
project: kailash-py
topic: connection_adapter.ConnectionManagerAdapter logs raw params at ERROR
phase: redteam
tags: [security, observability, classification, dataflow]
---

# Raw `params` logged at ERROR in connection_adapter exception handler

**File**: `packages/kailash-dataflow/src/dataflow/utils/connection_adapter.py:170`

**Finding**: The `except Exception` branch of `ConnectionManagerAdapter.execute_query`
emitted `logger.error("connection_adapter.params", extra={"params": params})`.
`params` is the bound-parameter list from DataFlow write paths — it contains
row values (email, password if upserting, SSN-bearing classified fields,
API keys). Every query failure wrote every bound parameter to the ERROR
log stream where every aggregator, SRE dashboard, and observability vendor
could read it.

**Blast radius**:

- `bulk_upsert.py::_handle_batch_error` catches per-row exceptions and
  may re-enter this path when adapters route through
  `ConnectionManagerAdapter`. Error trigger → full param set leaked.
- `str(batch_error)` for asyncpg / aiomysql / sqlite errors often echoes
  the offending column value (`duplicate key "alice@example.com"`), so
  the raw payload was leaking through TWO independent channels.

**Rules violated**:

- `rules/security.md` § No secrets in logs
- `rules/observability.md` Rule 4 (Never log secrets, tokens, or PII)
- `rules/dataflow-classification.md` MUST Rule 1 (classified fields
  outside redaction boundary)

**Fix**: Replaced `extra={"params": params}` with `extra={"param_count":
len(params) if params is not None else 0}`. SQL is parameterized
(`$N` / `%s` / `?`) and safe to log — the SQL string never carries raw
values. Consolidated the 3-line error emission into one structured call
with `error`, `sql`, `param_count`.

**Regression gap**: No test asserts that the error path does NOT echo
params. Consider a unit test that injects a failing SQL + mixed-classified
params and asserts `caplog.records[0].params` is absent.

## For Discussion

- Should the sanitizer contract extend to log-path scrubbing generally,
  or is it enough to pin "error-path cannot have raw values" via a rule?
  Counterfactual: if we add a scrubber, any future `logger.error(...,
extra={"payload": ...})` site inherits the defense. If we pin via
  rule, reviewers must catch it every time.
- kailash-rs almost certainly has the same adapter-error pattern. File
  a cross-SDK ticket? The two session notes from prior rounds mentioned
  the Rust SDK uses `tracing::error!` with structured fields — same
  blast radius class.
- How did this survive 4 commits of active security work? The audit
  scope was limited to "did the fix close #492"; the connection_adapter
  was one hop away from the fix site. Adjacent-code audit needs to be
  the default for security commits.
