# Post-Release Gap Analysis — v2.8.3

**Date**: 2026-04-12
**Input**: `04-validate/09-post-release-redteam.md` (3 CRITICAL, 8 HIGH, 4 MEDIUM)
**Revised**: 3 CRITICAL, 7 HIGH (1 false positive), 4 MEDIUM = **14 real gaps**

## Workstream Grouping

### WS-1: Security Hardening (4 items)

| ID     | Severity | Gap                                           | Fix                                                           | Complexity |
| ------ | -------- | --------------------------------------------- | ------------------------------------------------------------- | ---------- |
| SEC-01 | CRITICAL | `create_index()` no identifier validation     | Add `_validate_identifier()` at entry point + regression test | Trivial    |
| SEC-02 | HIGH     | `connection_parser.py` credential drift       | Replace inline unquote with `decode_userinfo_or_raise`        | Trivial    |
| SEC-03 | HIGH     | `eatp_human_origin.py` raw DDL                | Add local `_quote_pg_identifier()` helper                     | Low        |
| SEC-04 | MEDIUM   | `schema_manager.py` DROP without `force_drop` | Add `force_drop=True` gate                                    | Trivial    |

### WS-2: Test Infrastructure (4 items)

| ID      | Severity | Gap                                            | Fix                                              | Complexity |
| ------- | -------- | ---------------------------------------------- | ------------------------------------------------ | ---------- |
| TEST-01 | CRITICAL | 61 collection failures (pact+mcp not in venv)  | Add to `dev` extra in pyproject.toml             | Trivial    |
| TEST-02 | CRITICAL | CoreErrorEnhancer import broken                | Add export to `__init__.py`                      | Trivial    |
| TEST-03 | MEDIUM   | No LOC invariant tests                         | Create `tests/regression/test_loc_invariants.py` | Low        |
| TEST-04 | MEDIUM   | `test_reasoning_integration.py` missing import | Add `from hypothesis import given`               | Trivial    |

### WS-3: Kaizen Spec Compliance (3 items)

| ID      | Severity | Gap                                         | Fix                                 | Complexity |
| ------- | -------- | ------------------------------------------- | ----------------------------------- | ---------- |
| SPEC-01 | HIGH     | @deprecated not applied to extension points | Apply decorator to 4 methods        | Trivial    |
| SPEC-02 | HIGH     | 2/6 audit modules parallel                  | Delegate to canonical `audit_store` | Medium     |
| SPEC-03 | MEDIUM   | StreamingAgent not in Delegate wrapper      | Design decision — may be by-design  | Low        |

### WS-4: Cross-SDK Issues (3 items)

| ID     | Severity | Gap                                   | Fix                                           | Complexity |
| ------ | -------- | ------------------------------------- | --------------------------------------------- | ---------- |
| GH-418 | HIGH     | Fail-closed PACT classification       | Audit read-path defaults, enforce fail-closed | Medium     |
| GH-419 | HIGH     | CacheBackend CAS + tenant enforcement | New CAS protocol + tenant key validation      | Complex    |
| GH-420 | HIGH     | BulkResult WARN + orphan audit        | Add WARN logging to bulk ops                  | Medium     |

## False Positive

**HIGH-7 (pact.enforcement zero tests)**: DISMISSED. `test_enforcement_modes.py` contains 643 lines / 46 tests covering all enforcement mode behavior. The redteam grep missed the filename variant.

## Execution Strategy

WS-1 through WS-3 are all implementable this session (trivial to medium complexity). WS-4 items are feature-level work — #418 is feasible this session, #419 and #420 may need a follow-up.

Parallelize: WS-1 + WS-2 are independent. WS-3 SPEC-01 is independent. WS-3 SPEC-02 and WS-4 GH-418 require focused sequential work.
