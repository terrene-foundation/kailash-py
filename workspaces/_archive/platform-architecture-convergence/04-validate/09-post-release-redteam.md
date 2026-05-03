# Post-Release Red Team Report -- v2.8.3

**Date**: 2026-04-12
**Scope**: Full platform audit after v2.8.3 release
**Prior report**: `08-aggregated-redteam.md` (2026-04-08, 26 CRITICAL)

## Release Verification

| Package          | Version | PyPI        | Notes                                                              |
| ---------------- | ------- | ----------- | ------------------------------------------------------------------ |
| kailash          | 2.8.3   | Published   |                                                                    |
| kailash-dataflow | 2.0.5   | Published   |                                                                    |
| kailash-ml       | 0.9.0   | Published   | BREAKING: `set_reference()` -> `set_reference_data()`              |
| kaizen-agents    | 0.9.2   | Published   |                                                                    |
| kailash-pact     | 0.8.1   | Published   | Was missing -- tag pushed but CI never triggered (batch tag dedup) |
| Docker Hub       | 2.8.3   | In progress | Previously failed due to missing pact 0.8.1; re-triggered          |

## Prior Critical Gaps: Resolution Status

| #   | Gap                                                  | Status      | Evidence                                                   |
| --- | ---------------------------------------------------- | ----------- | ---------------------------------------------------------- |
| 1   | BaseAgent imports from `kailash.mcp_server`          | **FIXED**   | 0 matches in kaizen/src/                                   |
| 2   | Gemini tools + response_format mutual exclusion      | **FIXED**   | Guard at google.py:414,480,557                             |
| 3   | client.py duplicated in mcp_server/ and kailash_mcp/ | **FIXED**   | `src/kailash/mcp_server/` removed                          |
| 4   | StreamingAgent is a fake stream                      | **FIXED**   | Real per-token streaming via StreamingProvider             |
| 5   | BaseAgentConfig.posture field missing                | **FIXED**   | config.py:109 with immutability guard                      |
| 6   | @deprecated never applied to extension points        | **OPEN**    | Decorator exists in deprecation.py but 0 call sites        |
| 7   | PACTMiddleware missing from nexus                    | **FIXED**   | governance.py:155                                          |
| 8   | Audit modules not using canonical store              | **PARTIAL** | 4/6 converged; kaizen security + autonomy still parallel   |
| 9   | Wrapper stack order + StreamingAgent in Delegate     | **PARTIAL** | Stack order fixed; StreamingAgent not composed by Delegate |
| 10  | Keyword routing (\_simple_text_similarity)           | **FIXED**   | Function deleted, 0 matches                                |

**Result: 7/10 FIXED, 2/10 PARTIAL, 1/10 OPEN**

## Open GitHub Issues

| Issue | Title                                            | Code Status     | Priority    |
| ----- | ------------------------------------------------ | --------------- | ----------- |
| #418  | fail-closed PACT classification                  | No code changes | **HIGHEST** |
| #419  | CacheBackend CAS + tenant key enforcement        | No code changes | HIGH        |
| #420  | FabricIntegrity + BulkResult WARN + orphan audit | No code changes | HIGH        |

All 3 cross-SDK issues are entirely unaddressed in the codebase.

## Security Audit

| Area                              | Verdict  | Detail                                                                                                |
| --------------------------------- | -------- | ----------------------------------------------------------------------------------------------------- |
| Credential decode (shared helper) | **FAIL** | `connection_parser.py:58` re-implements null-byte check instead of calling `decode_userinfo_or_raise` |
| Null-byte rejection               | PASS     | Helper at `url_credentials.py:154` rejects `\x00`                                                     |
| SQL identifier safety             | **FAIL** | `connection.py:create_index()` has no `quote_identifier` at entry point (10+ callers)                 |
| Safe logging                      | PASS     | No raw credentials in logger calls                                                                    |
| Trust plane (atomic writes)       | PASS     | `validate_id()` 63 sites, `atomic_write()` all write paths                                            |
| CodeQL sanitizer barriers         | PASS     | sanitizers.model.yml configured                                                                       |
| DDL in migrations                 | **WARN** | `eatp_human_origin.py` uses raw f-string DDL (hardcoded values, low risk)                             |
| DROP without force_drop           | **WARN** | `schema_manager.py:228` drops without explicit gate                                                   |

### Security Findings

| Severity | Finding                                                           | Location                                                                     |
| -------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| CRITICAL | `create_index()` interpolates identifiers without validation      | `src/kailash/db/connection.py:91-107`                                        |
| HIGH     | `connection_parser.py` drift site (re-implements null-byte check) | `packages/kailash-dataflow/src/dataflow/adapters/connection_parser.py:57-76` |
| HIGH     | Migration DDL uses raw f-strings                                  | `src/kailash/trust/migrations/eatp_human_origin.py:204,270,316`              |
| MEDIUM   | DROP without `force_drop=True` gate                               | `src/kailash/nodes/admin/schema_manager.py:228`                              |

## Test Coverage Audit

| Metric            | Value                           |
| ----------------- | ------------------------------- |
| Tests collected   | 14,105                          |
| Collection errors | 70                              |
| Dependency check  | Clean (195 packages compatible) |

### Collection Error Root Causes

| Cause                                | Count | Severity |
| ------------------------------------ | ----- | -------- |
| `kailash-mcp` not installed in venv  | 41    | HIGH     |
| `kailash-pact` not installed in venv | 20    | HIGH     |
| `CoreErrorEnhancer` import broken    | 1     | HIGH     |
| `hypothesis.given` not imported      | 1     | MEDIUM   |
| Other (nexus, docker, cross_sdk)     | 7     | MEDIUM   |

### Module Test Coverage

| Module                                 | Tests Exist            | Severity   |
| -------------------------------------- | ---------------------- | ---------- |
| `kailash.runtime.progress`             | Yes                    | OK         |
| `kailash.runtime.watchdog`             | Yes                    | OK         |
| `kailash.trust._json` (canonical JSON) | Yes (7 files)          | OK         |
| `DriftMonitor` / `set_reference_data`  | Yes (3 files)          | OK         |
| `pact.enforcement`                     | **No dedicated tests** | **HIGH**   |
| LOC invariant tests                    | **None exist**         | **MEDIUM** |

## Consolidated Gaps

### CRITICAL (must fix)

1. **SEC-01**: `connection.py:create_index()` — no identifier validation at entry point
2. **GH-418**: fail-closed PACT classification — no code work landed
3. **TEST-01**: 61 test collection failures — kailash-pact and kailash-mcp not installed in dev venv

### HIGH (should fix next session)

4. **SEC-02**: `connection_parser.py` drift site — must delegate to shared helper
5. **SEC-03**: `eatp_human_origin.py` migration DDL uses raw f-strings
6. **GH-419**: CacheBackend CAS + tenant key enforcement — unaddressed
7. **GH-420**: FabricIntegrity + BulkResult WARN + orphan audit — unaddressed
8. **SPEC-06**: `@deprecated` decorator built but never applied to extension points
9. **SPEC-08**: 2/6 audit modules still have parallel implementations
10. **TEST-02**: `pact.enforcement` module has zero dedicated tests
11. **TEST-03**: `CoreErrorEnhancer` import broken in integration test

### MEDIUM (track for next iteration)

12. **SEC-04**: `schema_manager.py` DROP without `force_drop` gate
13. **SPEC-09**: StreamingAgent not composed by Delegate wrapper stack
14. **TEST-04**: No LOC invariant tests exist (per new `refactor-invariants` rule)
15. **TEST-05**: `test_reasoning_integration.py` missing `hypothesis.given` import

## Artifacts Cleaned This Session

- `skills/project/` directory deleted (USE-repo pattern, wrong for BUILD repo)
- 4 project skills relocated to canonical locations (29-pact, 02-dataflow, 34-kailash-ml)
- `pool-safety.md` deleted (duplicate of `rules/connection-pool.md`)
- `rules/refactor-invariants.md` authored (previously deferred)
- `skills/01-core-sdk/cross-sdk-canonical-json.md` authored (previously deferred)
- Proposal updated with 11 new entries for loom `/sync py`
