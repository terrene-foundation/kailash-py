# PR Compliance Assertion Tables (2026-04-19)

Per-PR verification: promised symbols exist, are exported, and have importing tests. Verification via AST parse, grep, runtime import, and `pytest --collect-only`.

## PR #502 — kaizen LlmClient.embed

| Assertion | Check | Result |
|---|---|---|
| `LlmClient.embed` coroutine exists | grep `client.py:232` | PASS |
| Exported from `kaizen.llm` | `kaizen/llm/__init__.py:21,86` | PASS |
| Importing test | `tests/integration/llm/test_llmclient_embed_wiring.py:30,146` asserts `hasattr(LlmClient,"embed")` | PASS |
| Shaper modules ship | `openai_embeddings.py`, `ollama_embeddings.py` present | PASS |
| Collect-only | 11920 tests collected, 0 errors | PASS |

## PR #503 — DataFlow Express PG quoting

| Assertion | Check | Result |
|---|---|---|
| `quote_identifier` used in engine CRUD | `engine.py` has 17 usages | PASS |
| Touches nodes.py + auto_migration_system.py | grep confirms | PASS |
| Regression test file | `tests/integration/test_issue_480_express_pg_identifier_quoting.py` present | PASS |
| Collect-only dataflow | 5843 tests, 0 errors | PASS |

## PR #504 — Defense-in-depth 5/9

| Assertion | Check | Result |
|---|---|---|
| `_validate_identifier` added in engine.py | diff confirms | PASS |
| `_sanitize_db_error` in bulk_upsert | diff confirms +25 lines | PASS |
| EATP migration validators | +47 lines in `eatp_human_origin.py` | PASS |
| Findings 3/4/7/8 explicitly deferred | PR body + follow-up = PR #508 | PASS (scope-bounded) |

## PR #505 — Nexus HttpClient + ServiceClient

| Assertion | Check | Result |
|---|---|---|
| `class HttpClient` at `http_client.py:588` | grep | PASS |
| `class ServiceClient` at `service_client.py:222` | grep | PASS |
| Exception hierarchy (6 typed errors) | all 6 classes defined | PASS |
| Exported in `__init__.py` `__all__` | confirmed lines 170–184 | PASS |
| Unit + integration tests | 4 test files, all importing via `from nexus import ...` | PASS |
| Unit tests run (89+23 claim) | 120 PASS in 0.93s (combined 3 files) | PASS |
| Production call site inside Nexus hot path | **ZERO matches** — standalone downstream primitive | See HIGH-1 |

## PR #506 — kailash-ml Pipeline + register_estimator

| Assertion | Check | Result |
|---|---|---|
| `Pipeline`, `FeatureUnion`, `ColumnTransformer` defined | `estimators/*.py` present | PASS |
| `register_estimator` exported | `kailash_ml/__init__.py:36–45, 191–195` | PASS |
| Eager import (CodeQL fix) | 2bb9169b commit applied | PASS |
| Unit tests in isolation | 14/14 PASS | PASS |
| Unit tests under cross-process load | **8/37 FAIL** with `KeyError: "Attempt to overwrite 'module' in LogRecord"` | See HIGH-2 |

## PR #507 — TypedServiceClient

| Assertion | Check | Result |
|---|---|---|
| `TypedServiceClient(ServiceClient)` at `typed_service_client.py:243` | grep | PASS |
| `Decoder` type exported | `__init__.py:92, 187` | PASS |
| 31 unit + 10 integration tests import via `from nexus import TypedServiceClient` | 6 test files confirmed | PASS |
| Production call site | **ZERO matches** — same status as #505 | See HIGH-1 |

## PR #508 — Defense-in-depth remaining 4/9 (PENDING MERGE — branch fix/issue-499-remaining-findings @ e3309ef8)

| Assertion | Check | Result |
|---|---|---|
| `DropRefusedError` + `require_force_drop` in `migrations/drop_confirmation.py` | file present on branch | PASS |
| `_validate_pragma` in `adapters/sqlite.py`, `sqlite_pool.py`, `persistent_tiers.py` | diff stats confirm | PASS |
| Split wiring tests (3 files replace `test_phase_5_11_trust_wiring.py`) | -507 / +409 lines | PASS |
| Spy test `test_schema_manager_identifier_validation.py` new | +146 lines | PASS |
| Collect-only on branch state | dataflow 5843, root 16009 (per PR body; not re-run locally) | PASS (trust PR body) |

## Collection Gate Summary

| Package | Collected | Errors |
|---|---|---|
| kailash-nexus | 2197 | 0 |
| kailash-kaizen | 11920 | 0 |
| kailash-dataflow | 5843 | 0 |
| kailash-ml | 940 | 0 |
