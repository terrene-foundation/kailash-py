# Implementation Plan — 22 Open GitHub Issues

## Execution Strategy

5 workstreams, 4 parallel tracks. Security/critical bugs land first, then architecture, then enhancements. Each track is an independent branch merging to main via PR.

**Session estimate**: 4 sessions with parallel agent execution, or 7-8 sequential sessions.

## Red Team Resolutions Incorporated (Round 1)

- **C1**: PR 1A includes test migration for #236 ReadOnlyView (6 test call sites)
- **C2**: PR 1A fixes hardcoded `"claude-sonnet-4-6"` fallback → `os.environ.get("DEFAULT_LLM_MODEL")`
- **H1**: PR 3A rescoped to "make existing RED phase SSE tests pass" — `test_sse_streaming.py` (~600 lines) already exists
- **H2**: #238 → #236 dependency made explicit
- **H3**: PR 4A migrates `datetime.utcnow()` → `datetime.now(UTC)` in audit code
- **H4**: `prometheus_client` is optional extra (`pip install kailash-nexus[metrics]`) with lazy import
- **H5**: PR 1B explicitly lists kaizen-agents as co-change with cross-package integration tests
- **M1**: Resolved — Fabric Engine confirmed operational for materialized products; virtual products broken (#245)
- **M3**: PR 4A includes auto-table-creation in `DataFlow.start()` when `audit=True`

## Round 2 Update: 8 New Fabric Issues (#245-#252)

Treasury Fabric integration testing (42 loans / 22 active / 7 currencies, real data) confirmed Fabric Engine works for materialized products but found 2 bugs and 6 feature gaps. These form a new Track 5.

---

## Track 1: PACT Engine Hardening (9 issues → 3 PRs)

### PR 1A: Security Quick Fixes (#235, #236, #237, #241) + env-models fix

**Scope**: 4 security fixes + 1 rule violation fix + test migration.

| Issue | Change                                                                                                | File                               | Est. Lines |
| ----- | ----------------------------------------------------------------------------------------------------- | ---------------------------------- | ---------- |
| #237  | Add `math.isfinite()` guard on budget_consumed                                                        | pact/engine.py:220-222             | ~5         |
| #235  | Recreate supervisor per submit() instead of caching                                                   | pact/engine.py:391-431             | ~10        |
| #236  | `_ReadOnlyGovernanceView` wrapper with read-only property proxying (`org_name`, `compiled_org`, etc.) | pact/engine.py:324-333 + new class | ~60        |
| #241  | Call check_degenerate_envelope() in **init** after compile, cap 50 warnings                           | pact/engine.py:178 + envelopes.py  | ~20        |
| C2    | Replace `"claude-sonnet-4-6"` fallback with `os.environ.get("DEFAULT_LLM_MODEL")`                     | pact/engine.py:411                 | ~3         |
| C1    | Migrate 6 test call sites for `.governance` type change                                               | test_pact_engine.py                | ~30        |

**Tests**: Unit tests for each fix. ~130 lines.
**Estimated scope**: ~260 lines.

### PR 1B: HELD Verdict + Per-Node Governance (#238, #234)

**Scope**: Two features enabling per-node governance. **Spans two packages** (kailash-pact + kailash-kaizen).

| Issue | Change                                                                                              | File                                        | Est. Lines |
| ----- | --------------------------------------------------------------------------------------------------- | ------------------------------------------- | ---------- |
| #238  | Distinguish HELD from BLOCKED: `is_held` property, HeldActionCallback protocol, GovernanceHeldError | verdict.py, pact/engine.py                  | ~120       |
| #234  | GovernanceCallback protocol, \_DefaultGovernanceCallback calling verify_action() per node           | pact/engine.py, kaizen-agents/supervisor.py | ~200       |

**Depends on**: PR 1A (#235 stale budget fix, **#236 frozen governance** — explicit dependency for #238).
**Cross-package**: Changes in both `packages/kailash-pact/` and `packages/kailash-kaizen/`.
**Tests**: Integration + cross-package contract tests. ~250 lines.
**Estimated scope**: ~570 lines.

### PR 1C: Enforcement Modes + Envelope Adapter (#239, #240)

| Issue | Change                                                                          | File                               | Est. Lines |
| ----- | ------------------------------------------------------------------------------- | ---------------------------------- | ---------- |
| #239  | EnforcementMode enum (ENFORCE/SHADOW/DISABLED), env guard, shadow logging       | pact/engine.py, new enforcement.py | ~250       |
| #240  | `_adapt_envelope(role_address)` mapping all 5 constraint dimensions, NaN guards | pact/engine.py                     | ~150       |

**Depends on**: PR 1B.
**Tests**: ~250 lines.
**Estimated scope**: ~650 lines.

### Track 1 Dependency Chain

```
PR 1A: #237, #235, #236, #241, C2 (independent small fixes)
  ↓ (#238 explicitly depends on #236)
PR 1B: #238, #234 (cross-package: kailash-pact + kailash-kaizen)
  ↓
PR 1C: #239, #240 (architecture layer)
```

---

## Track 2: Governance Cross-SDK Alignment (#231)

### PR 2A: Vacancy Checks + Semantic Alignment

| Change                                        | File                                   | Est. Lines   |
| --------------------------------------------- | -------------------------------------- | ------------ |
| Add vacancy check to approve_bridge()         | src/kailash/trust/pact/engine.py:1227  | ~8           |
| Add reject_bridge() method with vacancy check | src/kailash/trust/pact/engine.py:~1250 | ~35          |
| Verify 6 semantic alignment items             | addressing.py, engine.py, schemas.py   | Review + ~20 |
| Tests                                         | test_bridge_lca.py                     | ~80          |

**Independent of all other tracks.**
**Estimated scope**: ~145 lines.

---

## Track 3: Nexus Observability (#233)

### PR 3A: Prometheus /metrics + SSE Event Streaming

| Change                                                                   | File                                        | Est. Lines |
| ------------------------------------------------------------------------ | ------------------------------------------- | ---------- |
| Add `prometheus_client` as **optional extra** (`kailash-nexus[metrics]`) | pyproject.toml                              | ~5         |
| Create /metrics endpoint with lazy import                                | nexus/transports/http.py or new metrics.py  | ~100       |
| Create /events/stream SSE endpoint                                       | nexus/transports/http.py or new sse.py      | ~120       |
| Wire EventBus.subscribe_filtered() to SSE + sse_url() method             | nexus/events.py                             | ~20        |
| Make existing RED phase tests pass                                       | test_sse_streaming.py (existing ~600 lines) | ~30 fixes  |
| New /metrics tests                                                       | test_metrics.py                             | ~80        |

**Independent of all other tracks.**
**Estimated scope**: ~355 lines + fixing existing RED tests.

---

## Track 4: DataFlow Data Quality (#242, #243, #244)

### PR 4A: Audit Trail Persistence (#243)

| Change                                                  | File                                           | Est. Lines |
| ------------------------------------------------------- | ---------------------------------------------- | ---------- |
| EventStoreBackend ABC                                   | dataflow/core/event_store.py (new)             | ~60        |
| PostgreSQL adapter                                      | dataflow/core/event_stores/postgresql.py (new) | ~150       |
| SQLite adapter                                          | dataflow/core/event_stores/sqlite.py (new)     | ~120       |
| Query API on AuditIntegration                           | dataflow/core/audit_integration.py             | ~80        |
| Wire into DataFlow(audit=True) with auto-table-creation | dataflow/engine.py                             | ~40        |
| Migrate `datetime.utcnow()` → `datetime.now(UTC)`       | 5 files                                        | ~20        |
| Tests                                                   | test_audit_persistence.py                      | ~200       |

**Estimated scope**: ~670 lines.

### PR 4B: ProvenancedField (#242)

| Change                                        | File                              | Est. Lines |
| --------------------------------------------- | --------------------------------- | ---------- |
| Provenance[T] generic type                    | dataflow/core/provenance.py (new) | ~120       |
| FieldMeta extension + @db.model integration   | schema.py, models.py              | ~70        |
| JSON column serialization (Strategy A)        | schema.py, adapters               | ~100       |
| Validation (confidence 0-1, source_type enum) | provenance.py                     | ~40        |
| Auto-tracking previous_value on updates       | events.py                         | ~50        |
| Query support + DDL generation                | query.py, adapters/               | ~140       |
| Tests                                         | test_provenance.py                | ~300       |

**Estimated scope**: ~820 lines.

### PR 4C: Consumer Adapter Registry (#244)

| Change                                | File                               | Est. Lines |
| ------------------------------------- | ---------------------------------- | ---------- |
| Consumer protocol + registry          | dataflow/fabric/consumers.py (new) | ~80        |
| ProductRegistration.consumers field   | dataflow/fabric/products.py        | ~10        |
| Serving layer ?consumer= param        | dataflow/fabric/serving.py         | ~40        |
| Pipeline hook for consumer transforms | dataflow/fabric/pipeline.py        | ~60        |
| Tests                                 | test_consumers.py                  | ~150       |

**Depends on**: PR 5A (#245 virtual products fix — serving layer must be correct first).
**Estimated scope**: ~340 lines.

---

## Track 5: Fabric Engine Hardening (#245-#252 → 4 PRs)

**NEW TRACK** — from Treasury Fabric integration testing.

### Red Team Resolutions (Round 2)

- **H1**: #252 moved to own PR 5D — scope is 80-120 lines across 15+ files (121 refs in 21 files), not 25
- **H2**: PR 5B adds `drain()` to PipelineExecutor alongside cache control (runtime.py:219 calls it but it doesn't exist)
- **H3**: #251 — `DataFlow(database_url=None)` already accepted at construction; fix is conditional DB init skip when no models registered
- **M1**: #245 fix must cover both single handler (serving.py:227-235) AND batch handler (:262-276)
- **M3**: #252 is DX/cosmetic (health check output already says "source_type"), deprioritized

### PR 5A: Critical Bug Fixes (#245, #248, #253)

**Scope**: Fix broken virtual products + dev_mode pre-warming + change detection. Kept small and fast.

| Issue | Change                                                                               | File                                               | Est. Lines |
| ----- | ------------------------------------------------------------------------------------ | -------------------------------------------------- | ---------- |
| #245  | Virtual products execute inline — **both single and batch handlers**                 | fabric/serving.py:227-235 + :262-276               | ~30        |
| #248  | dev_mode still pre-warms (serially, reduced resource usage)                          | fabric/runtime.py:162-163                          | ~15        |
| #253  | ChangeDetector receives source dicts, not adapters — extract adapters before passing | fabric/runtime.py:168-173 or change_detector.py:98 | ~10        |

**Tests**: ~100 lines.
**Estimated scope**: ~155 lines.

### PR 5B: Cache Control + Shutdown (#246, #247, #251)

**Scope**: Cache invalidation + per-request refresh + fabric-only mode + graceful drain.

| Issue | Change                                                                                                      | File                                  | Est. Lines |
| ----- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------- | ---------- |
| #246  | `invalidate(product_name)` and `invalidate_all()` on PipelineExecutor, exposed via `db.fabric.invalidate()` | fabric/pipeline.py, fabric/runtime.py | ~40        |
| H2    | Add `drain()` method to PipelineExecutor for graceful shutdown (runtime.py:219 calls it, doesn't exist)     | fabric/pipeline.py                    | ~20        |
| #247  | `?refresh=true` query param in serving layer handler — skip cache, execute fresh                            | fabric/serving.py                     | ~30        |
| #251  | Conditional DB init skip when no models registered (`DataFlow(database_url=None)` already accepted)         | dataflow/engine.py                    | ~45        |

**Depends on**: PR 5A (#245 — virtual product fix needed for refresh to work correctly).
**Tests**: ~140 lines.
**Estimated scope**: ~275 lines.

### PR 5C: Source + MCP Enhancements (#249, #250)

**Scope**: FileSourceAdapter directory scanning + MCP tool auto-generation.

| Issue | Change                                                                                                                               | File                            | Est. Lines |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------- | ---------- |
| #249  | Extend FileSourceConfig with `directory`, `pattern`, `selection` fields; build on existing mtime change detection                    | fabric/adapters/file_adapter.py | ~90        |
| #250  | `db.fabric.get_mcp_tools()` generates MCP tool defs from products; optional `register_with_mcp(server)` with lazy kailash-mcp import | fabric/mcp_integration.py (new) | ~130       |

**Depends on**: PR 5A (serving layer must be correct).
**Cross-package**: #250 requires kailash-mcp integration point (optional import).
**Tests**: ~150 lines.
**Estimated scope**: ~370 lines.

### PR 5D: Adapter Rename (#252)

**Scope**: Rename `BaseAdapter.database_type` → `source_type` with deprecation shim. DX/cosmetic — not blocking anything.

| Issue | Change                                                                                                                    | File                                                                | Est. Lines |
| ----- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ---------- |
| #252  | Rename abstract property, update 15 concrete implementations, add deprecation shim, update 121 references across 21 files | adapters/base_adapter.py + 15 subclass files + 21 referencing files | ~100       |

**Independent** — can land any time. Low priority (health check output already uses "source_type" key).
**Tests**: ~30 lines (verify deprecation shim works).
**Estimated scope**: ~130 lines.

### Track 5 Dependency Chain

```
PR 5A: #245, #248 (critical bugs only — kept small)
  ↓
PR 5B: #246, #247, #251, drain() (cache control + fabric-only + shutdown)
PR 5C: #249, #250 (source + MCP enhancements)
  (5B and 5C independent, both depend on 5A)

PR 5D: #252 (adapter rename — independent, low priority, any session)
```

---

## Execution Order (Parallel Tracks)

```
Session 1 (5 parallel PRs):
  Track 1: PR 1A (#237, #235, #236, #241, C2) — PACT security quick fixes
  Track 2: PR 2A (#231) — governance vacancy + alignment
  Track 3: PR 3A (#233) — Nexus metrics + SSE
  Track 4: PR 4A (#243) — audit trail persistence
  Track 5: PR 5A (#245, #248) — Fabric critical bugs

Session 2 (4 parallel PRs):
  Track 1: PR 1B (#238, #234) — HELD verdict + per-node governance
  Track 4: PR 4B (#242) — ProvenancedField
  Track 5: PR 5B (#246, #247, #251, drain) — Fabric cache control + shutdown
  Track 5: PR 5D (#252) — adapter rename (low priority, opportunistic)

Session 3 (3 parallel PRs):
  Track 1: PR 1C (#239, #240) — enforcement modes + envelope adapter
  Track 4: PR 4C (#244) — consumer adapter registry [depends on PR 5A]
  Track 5: PR 5C (#249, #250) — Fabric source + MCP enhancements

Session 4 (if needed):
  Overflow, cross-package integration verification, cross-SDK issue filing
```

**Note**: If PR 5A slips from Session 1, PR 4C (#244) is blocked in Session 3. PR 5A is small (~125 lines) so this is low risk.

## Cross-SDK Issue Filing

File kailash-rs issues for:

- #234 per-node governance callback
- #235 stale supervisor budget
- #236 read-only governance view
- #237 NaN guard on budget_consumed
- #233 SSE streaming interface alignment

#231 already tracks cross-SDK alignment (kailash-rs fixes already applied).

## Total Scope (Final — 23 Issues, 3 Red Team Rounds)

| Track         | PRs        | Issues        | Implementation | Tests      |
| ------------- | ---------- | ------------- | -------------- | ---------- |
| 1: PACT       | 3          | 9             | ~1,480         | ~630       |
| 2: Governance | 1          | 1             | ~145           | ~80        |
| 3: Nexus      | 1          | 1             | ~355           | ~110       |
| 4: DataFlow   | 3          | 3             | ~1,830         | ~650       |
| 5: Fabric     | 4          | 9             | ~930           | ~420       |
| **Total**     | **12 PRs** | **23 issues** | **~4,740**     | **~1,890** |
