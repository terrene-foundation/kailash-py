# Failure Points & Requirements — Issues #492, #493, #495, #496, #497

Workspace: `workspaces/issues-492-497/`
Date: 2026-04-18
Source brief: `briefs/01-scope.md`

---

## #492 — `bulk_upsert._build_upsert_query` inlines values via string-escape (P0 SQLi)

### Failure points

- **Location:** `packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py:423-496`. Confirmed by direct read — line 442 does `escaped_value = value.replace("'", "''")` then line 443 wraps it as `f"'{escaped_value}'"` and line 453 splices everything into `INSERT INTO {self.table_name} ({column_names}) VALUES {...}`. `datetime.isoformat()` at line 447 takes the same unsafe path; `bool`/numeric go through `str(value)` without any escaping at all (line 449).
- **Symptom:** An attacker-controlled string containing backslash-quote (`\'`), `\0`, Unicode quote homoglyphs (`ʼ`, `‘`, `’`, fullwidth `＇`), or multi-byte sequences can break out of the quoted literal. The naïve `.replace("'", "''")` is the classic SQL-escape vulnerability pattern — `\0` terminates PostgreSQL string literals on some drivers, and backslash-escapes vary by `standard_conforming_strings`. On MySQL path (`INSERT OR REPLACE INTO`, line 490) no escaping is done at all for backslash.
- **Root cause:** The method returns a finished SQL string instead of `(sql, params)`. The upstream caller at `bulk_upsert.py:326` (`query = self._build_upsert_query(...)`) then runs that string through a `SQLDatabaseNode` that has no per-row binding path. Fixing requires the method to emit placeholders (`$1, $2, ...` for Postgres, `?, ?` for SQLite, `%s` for MySQL) and a flat params list matching the row-major column order.
- **Cross-SDK:** brief notes kailash-rs has a parallel `bulk_upsert.rs`. Not reachable from this worktree — cross-SDK issue MUST be filed per `rules/cross-sdk-inspection.md` MUST 1.

### Requirements

- **Minimum code change:** change `_build_upsert_query` signature to return `(sql, params)`. For each row, emit `($1, $2, ...)` (or the dialect's placeholder) across all columns; collect `row[col]` values into a list. Convert `isoformat()` on datetime to the driver-native bound parameter — drivers already serialize datetime correctly. Update the single caller at line 326 to pass `params` through. NULL stays literal (drivers accept `None` → NULL). For the sqlite `INSERT OR REPLACE` branch, same treatment — placeholders + params.
- **Minimum new tests:** Tier 2 regression at `tests/integration/security/test_bulk_upsert_sql_injection.py` with payloads `"'; DROP TABLE x; --"`, `"\\'; DROP TABLE"`, `"\x00admin"`, Unicode quote variants, and multi-row batches mixing safe and malicious values. Assert the target table is intact post-execute AND the malicious string landed as a literal value in a row. Use `IntegrationTestSuite` per `tests/CLAUDE.md`. Also add Tier 1 unit tests in `tests/unit/nodes/test_bulk_upsert_conflict_on.py` (already exercises `_build_upsert_query`) asserting the returned SQL contains `$1, $2, ...` placeholders — NOT quoted literals — and params tuple matches input length × column count.
- **Rule/docs:** no rule change required. Existing `rules/infrastructure-sql.md` + `rules/security.md` § Parameterized Queries already mandate this — the fix makes bulk*upsert compliant. Add a `regression/test_issue_492*\*.py`entry per`rules/testing.md` Regression section.
- **Verification before done:** (1) Tier 2 regression passes against real PostgreSQL via IntegrationTestSuite; (2) Tier 1 asserts placeholder-only SQL; (3) existing `test_bulk_upsert_conflict_on.py` tests still pass with the new return shape (they currently read `query` as a string — will need to unpack `(sql, params)` or call a thin adapter); (4) `grep -nE "replace\\(.*'',\s*''\"\\)|replace\\(\"'\",\\s*\"''\"\\)" src/` returns zero across the package; (5) cross-SDK GH issue filed on kailash-rs.

### Risk

- **API break for `_build_upsert_query` signature** — private method (underscore prefix), only one production caller + six unit tests. Low blast radius, but the unit tests WILL fail on signature change — counts as an invariant-test sweep per `rules/refactor-invariants.md` spirit.
- **Driver path divergence:** `SQLDatabaseNode` is shared across adapters. Need to confirm it accepts `(sql, params)` on all three dialects (PostgreSQL / MySQL / SQLite) before landing — a driver that silently re-interpolates params would re-open the vuln. Read `packages/kailash-dataflow/src/dataflow/core/nodes.py` to confirm the bind path.
- **Performance:** parameterized multi-row INSERT on PostgreSQL is faster than string-concat, so a net win. MySQL `executemany` path already exists at `adapters/mysql.py:188` and is the intended target.
- **Cross-SDK drift:** if kailash-rs bulk_upsert has the same bug and ships a fix on a different schedule, semantic behavior diverges (Python raises, Rust silently escapes). Mitigate by filing the cross-SDK issue before merging.

### Effort (autonomous sessions)

**1 shard / 1 session.** ~80-120 LOC load-bearing logic (one method rewrite + one caller + unit test fixups). Invariants held: placeholder-per-column, param-order-stable, dialect-branch-parity, datetime-binding, sqlite INSERT-OR-REPLACE path = 5. Call-graph depth 2 (method → caller → node executor). Tier 2 DB harness is an executable feedback loop → well within base budget.

---

## #493 — 3 pre-existing failures in DataFlow security suite (P1 drift)

### Failure points

- **`test_create_node_sql_injection_protection`** at `test_connection_sql_injection_protection.py:38-87`. The assertions are **self-contradictory**: line 83 asserts `"DROP TABLE" not in str(create_result.get("name", ""))`, but line 86 asserts `create_result.get("name") == "'; DROP TABLE test_users; --"` — the literal contains `"DROP TABLE"`, so line 83 CANNOT be true whenever line 86 is true. Test authored assuming sanitizer escapes quotes (`''; DROP TABLE...`) but the sanitizer at `src/dataflow/core/nodes.py:680-686` does **token-replace**: `(?i)(\;\s*(drop|delete|insert|update|exec))` → `"; STATEMENT_BLOCKED"`. So the actual post-sanitize value is `"'; STATEMENT_BLOCKED test_users; --"` — line 83 passes, line 86 fails.
- **`test_parameter_type_enforcement_prevents_injection`** at lines 302-349. Expects `pytest.raises(Exception)` around `runtime.execute(workflow.build())` when a dict/list is passed where a string is expected. The validator at `nodes.py:676` coerces with `value = str(value)` — so `{"injection": "..."}` becomes `"{'injection': '...'}"` which passes validation and gets stored. No exception is raised; test fails at line 344 (`pytest.raises` context exits without a match).
- **`test_ddl_error_logging_and_reporting`** at `test_unsafe_ddl_protection.py:246-261`. Test expects an ERROR log from logger `dataflow.core.engine` containing `"DDL"` OR `"error"` in `rec.message`. Code at `engine.py:5383` does `logger.error("engine.multi_ddl_transaction_rolled_back", extra={"error": str(e)})`. The `message` field is `"engine.multi_ddl_transaction_rolled_back"` — does NOT contain `"DDL"` (case-sensitive), and `"error"` is in `extra`, not `message`. Rule 8 of `rules/observability.md` explicitly requires structured event keys, so the code is correct; the test asserts against the old f-string shape.
- **Failing since `b032635f` (2026-04-02, Phase 8.1d)** per brief — 330+ commits. Silent CI drift.

### Requirements

- **Canonical sanitizer contract decision:** three options visible in code (quote-escape, token-replace, raise). Evidence favors **token-replace for safe display-path sanitization** (current behavior) + **raise for type-confusion** (not yet implemented). The reason: token-replace preserves auditability of the attacker's intent in the stored record (`STATEMENT_BLOCKED` is grep-able), and parameter-binding in the actual SQL path (#492's fix) is the real defense — the sanitizer is belt-and-suspenders display hygiene, not the primary control.
- **Minimum code change:** (a) `nodes.py:676` — change the `str(value)` coercion for declared-string parameters that receive non-string types (`dict`, `list`, `set`) to raise `ValueError("parameter type mismatch: expected str, got {type}")`. Keep `int`/`float`/`bool` coercion as-is. (b) No code change to the sanitizer token-replace path — it's correct. (c) No code change to `_execute_multi_statement_ddl` — it logs correctly.
- **Test updates:**
  - `test_create_node_sql_injection_protection`: replace line 86 with `assert "STATEMENT_BLOCKED" in create_result.get("name", "")` (asserts token-replace worked) and keep line 83's `"DROP TABLE" not in ...` check.
  - `test_parameter_type_enforcement_prevents_injection`: keep `pytest.raises`, update match to `re="parameter type mismatch"` after (a) lands.
  - `test_ddl_error_logging_and_reporting`: change the assertion to match structured-log shape — `assert any("multi_ddl" in rec.message or rec.levelname == "ERROR" and "error" in (rec.__dict__.get("error", "") or "") for rec in caplog.records)`. Match `rec.message` against the actual event key, not the free-text "DDL".
- **Rule update:** add §"Sanitizer Contract" to `rules/security.md` pinning token-replace for display-path sanitization + raise for type-confusion, so a future refactor doesn't swing back to quote-escape. Update `rules/observability.md` Rule 5 DNS for the structured-log-aware caplog assertion pattern.
- **Verification:** all 3 tests pass; `.venv/bin/python -m pytest packages/kailash-dataflow/tests/integration/security/ -v` fully green; grep for other suite members that assert against the old contract.

### Risk

- **Hidden callers of type-coercion:** the `str(value)` at `nodes.py:676` may be relied on by downstream tests or production paths that pass dicts intentionally. Raising instead may break tests that weren't red-teamed. Grep for `create_user(name={` patterns across tests before landing.
- **Contract-pinning risk:** if we pin token-replace in `rules/security.md` and a future session argues for raise-always, the rule is the tie-breaker. Worth it — institutional memory.
- **Log-level downgrade BLOCKED by `rules/observability.md` § "No silent log-level downgrades"** — good, no temptation to silence the failure.

### Effort (autonomous sessions)

**1 shard / 1 session.** ~30 LOC logic (one validator change), 3 test edits, 1 rule addition. Invariants: 3 (sanitizer contract, type-enforcement raise, DDL log structure). Call-graph depth 1. Trivially described in 3 sentences.

---

## #495 — ML `register_estimator()` parity (P2 audit)

### Failure points

- **Grep result:** `register_estimator` / `register_transformer` returns **zero matches** in `packages/kailash-ml/` and `src/kailash/`. kailash-rs added this API in `5429928c` to open hardcoded `sklearn.Pipeline` / `FeatureUnion` / `ColumnTransformer` allowlists; kailash-py has no equivalent registry.
- **But:** preliminary source read of `packages/kailash-ml/src/kailash_ml/engines/preprocessing.py` (line 104 `class PreprocessingPipeline`) does **not** show an `isinstance(step, (Pipeline, FeatureUnion, ColumnTransformer))` allowlist pattern. `automl_engine.py`, `training_pipeline.py`, `hyperparameter_search.py` referenced but not read line-by-line. Per `rules/framework-first.md` the ML package defines its own `PreprocessingPipeline` class (not sklearn's), so the exact bug shape may not map.
- **Verdict candidate:** the audit may conclude "no 1:1 hardcoded-allowlist gap in kailash-py" AND "architectural equivalent: confirm kailash-ml's pipeline/feature-union classes accept user-defined transformers via duck-typing (fit/transform) or a registry." The literal `register_estimator` name only matters if parity with the rs API surface matters; EATP D6 allows implementation divergence as long as semantics match.

### Requirements

- **Audit-only — no code until gap confirmed.** Steps:
  1. Read `kailash_ml/engines/automl_engine.py`, `training_pipeline.py`, `hyperparameter_search.py`, `preprocessing.py` line-by-line; identify every `isinstance(x, (A, B, C))` pattern that gates acceptance of a user-supplied estimator/transformer.
  2. For each pattern, determine if (a) extending the allowlist requires editing the source, or (b) the user can pass any `fit`/`transform`-capable object. Latter = no gap.
  3. If gap found: add `register_estimator(cls)` / `register_transformer(cls)` class-method on the relevant engine that appends to an internal set; the `isinstance` check becomes `isinstance(x, tuple(self._allowed))`. Error message MUST name the unregistered type AND the exact `ModelRegistry.register_estimator(YourClass)` command per cross-SDK parity.
  4. Tier 2 integration test: built-in + user-registered class, run through the facade, assert no `TypeError`.
- **Rule/docs:** update `packages/kailash-ml/docs/guides/02-feature-pipelines.md` if the registry API lands.
- **Verification:** if "no gap" is the verdict, the issue's disposition is a documented note on the GH issue citing the file:line evidence (which duck-typed pattern satisfies the same requirement). If gap confirmed, Tier 2 + Tier 1 tests green.

### Risk

- **Over-building:** if kailash-ml already accepts duck-typed estimators, adding a registry is API bloat with no user benefit. The audit MUST land BEFORE implementation.
- **Registry ≠ validation:** per kailash-rs behavior, the registry is keyed by type not structural check. Python duck-typing makes type-keyed registries slightly awkward; may want `register_estimator(cls, *, tags=...)` or similar. Defer to ml-specialist if gap confirmed.
- **Cross-SDK drift:** if kailash-py ships duck-typed acceptance and kailash-rs keeps a registry, EATP D6 "matching semantics" needs a carve-out or both SDKs land registries.

### Effort (autonomous sessions)

**Audit: ~½ session.** Code read only, 4 files, well under the invariant budget.
**If gap found + implement: 1 shard / 1 session.** ~100-150 LOC + 2 Tier 2 tests, all within one module. Invariants: register/unregister idempotence, error message format, Tier 2 wiring per `rules/facade-manager-detection.md` § 1 = 3.

---

## #496 — PG placeholder bug class verification (P2 audit)

### Failure points

- **Nature of bug (rs context):** kailash-rs#403 fixed a codegen path that emitted `?` placeholders in PostgreSQL SQL where `$N` is required. Python side uses SQLAlchemy + asyncpg where placeholders are abstracted; **exact bug shape is unlikely**, but any raw-SQL path that bypasses SQLAlchemy is exposed.
- **Grep evidence of raw-SQL paths in kailash-dataflow/src/** (already listed under tool output above):
  - **DDL-only paths (identifier-quoted, no VALUES):** `transactions.py:110,169,180,185`, `transaction_nodes.py:361,439`, `fk_safe_migration_executor.py:225,503,514,525,560,860,884`, `application_safe_rename_strategy.py:324,483,568,583`, `rename_transaction_manager.py:179,217`, `postgresql_test_manager.py:935,982`, `tdd_support.py:287,321,350`, `sqlite.py:439,561,1056`. These do `BEGIN`, `SAVEPOINT`, `RELEASE`, `ROLLBACK TO SAVEPOINT`, `DROP VIEW` with interpolated identifiers. Identifier safety is `rules/dataflow-identifier-safety.md`'s domain, NOT placeholder bugs — audit each for identifier-quoting compliance while we're here.
  - **Diagnostic SELECTs:** `database_source_adapter.py:183,219,244` (`PRAGMA table_info({table})`, `SELECT COUNT(*) FROM {table}`, `SELECT * FROM {table}`) — interpolated table names. These are **identifier-injection** candidates, not placeholder-mismatch candidates. Flag per `rules/dataflow-identifier-safety.md` MUST 1 and MUST 5.
  - **PRAGMA paths:** `sqlite.py:339,376,761,798,848,1047` — SQLite PRAGMA with interpolated `{pragma} = {value}`. Same identifier-injection concern, SQLite-only, lower severity.
  - **Potential placeholder-bypass paths:** `batched_migration_executor.py:560,589,619,707,721,738` — `cursor.execute(sql)` with pre-built SQL. Need to read those call sites to see whether `sql` came from a codegen function that hardcoded `?` vs `$N`.
  - **Admin path:** `staging_environment_manager.py:709` — `CREATE DATABASE {quoted_name}` interpolation.

### Requirements

- **Audit-only.** Enumerate every raw-SQL path; for each:
  1. Is it DDL-only (identifier interpolation, no VALUES)? → identifier-safety audit per `rules/dataflow-identifier-safety.md` (separate concern from #496).
  2. Does it execute SQL with VALUES/WHERE params? → verify placeholder style matches the driver (asyncpg → `$N`, psycopg2 → `%s`, aiosqlite → `?`).
  3. Does the SQL come from a codegen function? → read the codegen function, verify dialect-aware placeholder selection.
- **Specific paths to read in this audit:**
  - `migrations/batched_migration_executor.py` lines ±560, ±589, ±619, ±707, ±721, ±738 — the cluster of `cursor.execute(sql)` sites.
  - `migrations/sync_ddl_executor.py:284` — `cursor.execute(sql, params)` — the ONLY site in the grep with a `params` argument; verify dialect-match.
  - `core/engine.py:6150, 6155, 6155` — migration SQL execution without params; verify SQL codegen uses no VALUES placeholders.
  - `nodes/transaction_nodes.py:361, 439` — `SAVEPOINT "{name}"` — identifier branch, but verify `name` is validated (`rules/dataflow-identifier-safety.md` MUST 5).
- **Expected verdict:** most paths are identifier-interpolation DDL (correct per the rules, assuming validation) + migration codegen SQL that accepts no runtime VALUES. Placeholder-mismatch bug is unlikely but confirm each migration-executor call site.
- **Output:** an audit table in a follow-up note: `path | category (DDL/diag/migration/values) | placeholder style | verdict`. File GH issue only if a placeholder bug OR an unvalidated identifier is found.

### Risk

- **Drift with #492:** if the audit finds the same string-concat pattern in another place, that's a second P0 SQLi, not just a placeholder mismatch. Flag separately.
- **Audit scope creep:** every identifier-interpolated path also needs `rules/dataflow-identifier-safety.md` compliance. Temptation is to fix them all here — resist; file separate issues per bug class so the PRs stay sharded per `rules/autonomous-execution.md`.

### Effort (autonomous sessions)

**Audit: ~½–1 session.** ~30 call sites × 3-5 lines each = ~150 LOC of code to read. No load-bearing logic. Fits one shard.
**If bugs found:** each fix is its own shard (#492-class if SQLi, identifier-safety-class otherwise).

---

## #497 — Nexus webhook HMAC raw-body exposure (P2 audit)

### Failure points

- **Grep evidence:** `packages/kailash-nexus/src/nexus/transports/webhook.py` **already has a dedicated WebhookTransport class that accepts `payload_bytes` as a separate parameter** (lines 252, 329-372). `WebhookTransport.verify_signature(payload_bytes, signature)` uses HMAC-SHA256 over the raw bytes, and `receive()` raises `ValueError` if `payload_bytes is None` when a secret is configured. This is NOT the architectural gap the brief hypothesizes for the generic HTTP handler surface.
- **The real audit question is narrower:** does the _generic Nexus HTTP channel handler_ (not the dedicated webhook transport) expose raw bytes to arbitrary handlers? Users wanting to verify a Stripe webhook without using `WebhookTransport` — i.e., routing it through `@app.register(workflow)` or a plain Nexus handler — would hit the gap.
- **Need to read:** `packages/kailash-nexus/src/nexus/transports/http.py` handler dispatch (file exists, only shown `HTTPTransport` class header at line 34 + `mount` method). The dispatch path to user-registered workflows needs confirmation: does it pass `raw_body` / `headers` / `Request` through, or only pre-parsed JSON?
- **Also:** `packages/kailash-nexus/src/nexus/trust/middleware.py`, `nexus/middleware/*.py`, and `auth/*.py` — check whether any middleware already reads `await request.body()` and stashes on `request.state`, which would make the rule's "Workaround A" already available.

### Requirements

- **Audit-only.** Map the handler signature for each inbound surface:
  1. `WebhookTransport.receive()` — already raw-body-aware. **No gap.**
  2. `HTTPTransport` generic handler dispatch — read `transports/http.py` in full; identify what is passed into user-registered workflows. If pre-parsed JSON only → gap exists for the generic path.
  3. Starlette/FastAPI-layer ASGI extensibility — confirm whether users can attach a `BaseHTTPMiddleware` that reads body + stashes on `state`.
  4. SSE/WebSocket paths — out of scope for HMAC, but check for unexpected body-consumption side effects.
- **Document findings:** if `WebhookTransport` is the only intended path for signed webhooks, the issue's disposition is "architectural: WebhookTransport is the supported surface; generic HTTP handlers do not expose raw body because dedicated transport exists. Rule `nexus-webhook-hmac.md` stays active as policy." If the generic handler also has a gap, file a fix ticket with the same D1 / `NexusExtract` pattern referenced in `nexus-webhook-hmac.md` origin note.
- **Rule:** no change; `rules/nexus-webhook-hmac.md` is already codified globally.
- **Verification:** an audit note enumerating the four surfaces, evidence per surface, and the verdict.

### Risk

- **False-negative if WebhookTransport is not exhaustively used:** if users route webhooks through the generic handler (common when using `@app.register(workflow)` for uniformity), the gap is real. The audit must map actual user-facing paths, not just the existence of a working transport.
- **Rule already mandates external middleware** — even if a gap exists, the rule blocks the vulnerable handler pattern, so the risk of exploit is limited to users who ignore the rule. File the ticket nonetheless.
- **Cross-SDK symmetry:** kailash-rs has the same gap tracked at `kailash-rs#404` (extractor-trait rework). The Python fix should align if/when it lands.

### Effort (autonomous sessions)

**Audit: ~½ session.** Read 4-6 files, map handler signatures. Fits one shard easily. **No implementation in this workspace** — if a fix is needed, it's an extractor-architecture rework that's a multi-session effort on its own (per rs mirror #404's S1-S8 shards).

---

## Execution order

Sequence reasoning below. Issues are assigned to three parallel tracks, joined at implementation.

### Recommended sequence

1. **Track A — #492 (P0 SQLi fix), strictly sequential first.** Land the parameter-binding rewrite first because it closes a confirmed injection vector. Blocks nothing downstream but every day it sits is exposure risk. One shard.

2. **Track B — #493 (sanitizer contract) in parallel with #492.** Different files (`core/nodes.py`, `test_connection_sql_injection_protection.py`, `test_unsafe_ddl_protection.py`), different invariants. Can shard to a parallel worktree per `rules/agents.md` § "Worktree Isolation." BUT: #493's contract decision (token-replace vs quote-escape) constrains what #492's Tier 2 tests assert when an injection payload survives the binding fix — if token-replace stays, #492's Tier 2 should assert `STATEMENT_BLOCKED` appears in the returned row, not the raw payload. So **#493 decision must be ratified by the end of #492's Tier 2 test design**, but implementation can proceed in parallel. Serialize the contract-decision step, parallelize code.

3. **Track C — #495, #496, #497 audits in parallel.** All three are read-only audits — no code touched unless a gap is confirmed. Spawn as three parallel agents per `rules/agents.md` § Parallel Execution. Aggregate results before deciding which audits produce follow-up implementation tickets.

4. **Second wave (conditional):**
   - If #496 finds a placeholder bug or unvalidated identifier: shard per bug, each gets a `rules/dataflow-identifier-safety.md`-compliant fix. DO NOT bundle with #492.
   - If #495 confirms a gap: ml-specialist implementation shard; cross-reference to kailash-rs#402.
   - If #497 confirms a gap in the generic HTTP handler: file a follow-up ticket matching the kailash-rs#404 D1 pattern; no code in this workspace.

### Parallelization summary

| Track | Issue | Parallel-shardable? | Rationale                                                                               |
| ----- | ----- | ------------------- | --------------------------------------------------------------------------------------- |
| A     | #492  | N — sequential gate | P0; sets the test-pattern baseline for Tier 2 SQLi tests across DataFlow                |
| B     | #493  | Y (with A)          | Different files; contract decision coordinates with A but implementation is independent |
| C1    | #495  | Y                   | Read-only, different package (kailash-ml)                                               |
| C2    | #496  | Y                   | Read-only; overlaps with #492's grep scope but different file clusters                  |
| C3    | #497  | Y                   | Read-only, different package (kailash-nexus)                                            |

### Dependencies flagged

- **#493 ↔ #492:** sanitizer contract decision is shared (ratify once, apply in both).
- **#496 → possibly more #492-class fixes:** if the audit finds string-escape in another node, it shares #492's fix pattern. Land #492's pattern first so subsequent fixes have a template.
- **#495 and #497 are fully independent** of the DataFlow work.

### Session total estimate

- **Sequential critical path:** #492 + #493 + 3 parallel audits → **1-2 sessions** for the confirmed work; audit follow-ups are each their own shard.
- **Worst case (all audits find gaps):** +2-3 sessions across audit follow-ups (ml registry, identifier-safety sweep if #496 finds bugs, nexus extractor if #497 finds gap in generic handler). None of these overflow the single-shard budget in `rules/autonomous-execution.md`.
