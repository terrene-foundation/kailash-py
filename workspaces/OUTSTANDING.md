# Outstanding GH Issues — kailash-py

Generated: 2026-04-18 (post `/redteam` round-2, post `/analyze` for #498)

Single consolidated view of all open issues with workspace assignment,
priority, status, and blocking dependencies. Supersedes ad-hoc lists.

## Status legend

- **OPEN** — not started
- **WIP** — workspace exists, `/analyze` done
- **IMPLEMENTED** — code landed, pending release
- **BLOCKED** — waiting on external dependency

## By workspace

### ✅ issues-492-497 — CLEARED (5 of 5 closed, redteam round-2 green)

All security / audit tickets from 2026-04-18 session queue. Round-2 clean
pass 2026-04-18: 3 HIGH fixed (connection_adapter params leak,
bulk_upsert pool dead branch, `_tenant_trust_manager` orphan). 90/91
tests green. See `workspaces/issues-492-497/04-validate/aggregate-round1.md`
and `journal/0001-0003-RISK-*.md`.

| #   | State  | Note                                                       |
| --- | ------ | ---------------------------------------------------------- |
| 492 | CLOSED | bulk_upsert SQLi (commit 7a4fd364)                         |
| 493 | CLOSED | sanitizer contract (commit 2dbb9107)                       |
| 495 | CLOSED | ML register_estimator audit — NO-GAP (commit 27c77cf4)     |
| 496 | CLOSED | PG placeholder audit — fix shipped in 7a4fd364             |
| 497 | CLOSED | Nexus webhook HMAC audit — architectural (commit 27c77cf4) |

### 🔄 issue-498-llm-deployment — WIP (`/analyze` done)

Cross-SDK mirror of kailash-rs#406. Four-axis LLM deployment abstraction.
8 sessions (10 sub-shards after S4b/S6 splits per autonomous-execution
capacity budget).

- **#498** — OPEN, analyst surfaced: Python has NO `LlmClient` today, so
  back-compat target = provider registry (`kaizen.providers.registry`),
  not an `LlmClient` class. Flag at `/todos` gate.

## By priority / category

### P0 — Bugs blocking users today

| #   | Labels     | Title (short)                                        | Status          | Notes                                                                                                   |
| --- | ---------- | ---------------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------- |
| 480 | bug, x-sdk | DataFlowExpress malformed PG create/list/read        | **OPEN**        | Downstream workaround: `execute_raw(sql, [params])` with `$N`. Cross-SDK w/ kailash-rs#403.             |
| 478 | bug        | model_registry emits LocalRuntime DeprecationWarning | **IMPLEMENTED** | Fixed in commit 6fcba899 (mark_externally_managed API). Close pending `kailash-dataflow 2.0.9` release. |
| 477 | bug        | SignatureMeta broken on Python 3.14 (PEP 749)        | **IMPLEMENTED** | Fixed in commit 6fcba899 (annotations helper + regression test). Close pending release.                 |

### P1 — Features / enhancements

| #   | Labels             | Title (short)                                 | Status  | Workspace                                              |
| --- | ------------------ | --------------------------------------------- | ------- | ------------------------------------------------------ |
| 498 | enh, x-sdk         | Kaizen LLM deployment-target abstraction      | **WIP** | issue-498-llm-deployment                               |
| 488 | x-sdk              | kaizen.ml register_estimator() API            | OPEN    | — (audit done in #495 confirmed NO-GAP for kailash-py) |
| 479 | x-sdk              | kailash.ml.Pipeline rejects custom estimators | OPEN    | — (duplicate of #488 concern)                          |
| 473 | enh, x-sdk         | nexus typed service-to-service ServiceClient  | OPEN    | —                                                      |
| 465 | enh, x-sdk         | nexus typed S2S client (OpenAPI-generated)    | OPEN    | — (parent of #473)                                     |
| 464 | enh, x-sdk, **P1** | nexus outbound HttpClient SSRF-aware          | OPEN    | —                                                      |
| 463 | enh, x-sdk         | llm-client typed LlmError hierarchy           | OPEN    | — (blocked by LlmClient binding work)                  |
| 462 | **BLOCKER**, x-sdk | llm-client.embed() Python bindings            | OPEN    | — (supersedes pattern w/ #498 work?)                   |

**Note on #462 / #463**: These pre-date #498's four-axis abstraction.
When #498 lands the `LlmDeployment` preset architecture, the Python
`LlmClient.embed()` and `LlmError` surface becomes part of that
deployment-scoped client — #462/#463 may be subsumed. Re-scope after
#498 S2 (OpenAI migration) lands.

## Already shipped, waiting on release cut

These are IMPLEMENTED in main but the issue is OPEN because
`kailash-dataflow 2.0.9` / next-release hasn't cut yet. Close with
release SHA per `rules/git.md` § Issue Closure Discipline.

| #   | Fix commit | Release blocker             |
| --- | ---------- | --------------------------- |
| 477 | 6fcba899   | kailash 2.8.7 (or next cut) |
| 478 | 6fcba899   | kailash-dataflow 2.0.9      |

## Deferred / out-of-scope (loose ends from `.session-notes`)

| Item                                        | Origin    | Status                                                  |
| ------------------------------------------- | --------- | ------------------------------------------------------- |
| event-payload-classification.md loom commit | loose end | ✅ DONE (loom commit 459ba71, already synced)           |
| BulkUpsertNode pool dead branch             | loose end | ✅ FIXED (redteam round-1, HIGH-1)                      |
| LocalRuntime.execute() no-ctxmgr in 8 tests | loose end | OPEN (file-as-enhancement — filterwarnings suppression) |

## Red-team MEDIUM findings from 2026-04-18 round-1 (defense-in-depth)

Non-exploitable gaps surfaced during `/redteam`. File as single issue
tagged `defense-in-depth` for batch fix.

1. `engine.py:3756, 3774, 3800` PRAGMA paths read `sqlite_master` without `_validate_identifier`
2. `kaizen/trust/migrations/eatp_human_origin.py:203, 271, 319` identifier interpolation (kailash-core sibling validates)
3. SQLite PRAGMA interpolation in 3 files (persistent_tiers, sqlite_pool, adapters/sqlite)
4. DROP paths in 5 migration builders lack `force_drop=True` gate
5. `bulk_upsert.py:364-368` WARN echoes DB error text (may include PII)
6. `engine.py:5086` FK constraint missing `_validate_identifier` on 4 identifiers
7. `schema_manager.py` hardcoded-list validation has no spy-based regression test
8. `test_phase_5_11_trust_wiring.py` monolithic (facade-manager-detection MUST 2 wants per-manager files)
9. `496-pg-placeholder-audit.md` uses future tense after fix landed

## Next session priorities

1. Sample-merge + push redteam round-1 fixes (4 files, 3 journal entries)
2. `/todos` gate for #498 — confirm back-compat target (provider registry, not LlmClient class)
3. File the consolidated `defense-in-depth` GH issue for items 1-9 above
4. Cut `kailash-dataflow 2.0.9` to close #477 + #478 with release SHAs

## References

- `/Users/esperie/repos/loom/kailash-py/workspaces/issues-492-497/.session-notes`
- `/Users/esperie/repos/loom/kailash-py/workspaces/issues-492-497/04-validate/aggregate-round1.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/issue-498-llm-deployment/01-analysis/`
- `/Users/esperie/repos/loom/kailash-py/workspaces/issue-498-llm-deployment/02-plans/`
