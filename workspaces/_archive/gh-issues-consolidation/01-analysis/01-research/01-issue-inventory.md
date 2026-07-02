# Issue Inventory — 22 Open GitHub Issues

## Workstream Summary

| Workstream              | Issues        | Security/Bugs    | Enhancement       | Scope                               |
| ----------------------- | ------------- | ---------------- | ----------------- | ----------------------------------- |
| PACT Engine Hardening   | #232-#241 (9) | 4 HIGH, 1 MEDIUM | 4 features        | `packages/kailash-pact/`            |
| DataFlow Data Quality   | #242-#244 (3) | 0                | 3 features        | `packages/kailash-dataflow/`        |
| Fabric Engine Hardening | #245-#252 (8) | 2 bugs           | 6 features        | `packages/kailash-dataflow/fabric/` |
| Nexus Observability     | #233 (1)      | 0                | 2 features        | `packages/kailash-nexus/`           |
| Governance Alignment    | #231 (1)      | 1 HIGH           | 6 alignment items | `src/kailash/trust/pact/`           |

## Priority Matrix

### P0 — Security + Critical Bugs (fix immediately)

| #    | Title                                                  | Impact                              |
| ---- | ------------------------------------------------------ | ----------------------------------- |
| #234 | Single-gate governance — no per-node verify_action     | Governance bypass after submit gate |
| #235 | Stale supervisor budget — reused across submit() calls | Budget enforcement bypass           |
| #236 | Mutable GovernanceEngine exposed via .governance       | Privilege escalation                |
| #231 | Vacant role can approve bridges                        | Unauthorized bridge approvals       |
| #245 | Virtual products return data:None                      | Virtual products completely broken  |

### P1 — Correctness + Compliance

| #    | Title                           | Impact                                |
| ---- | ------------------------------- | ------------------------------------- |
| #237 | NaN-guard on budget_consumed    | Budget evasion (indirect)             |
| #238 | HELD verdict treated as BLOCKED | Governance model degradation          |
| #248 | dev_mode skips pre-warming      | Products appear broken in development |
| #243 | Audit trail persistence         | Compliance — events lost on restart   |
| #242 | ProvenancedField                | Financial/regulated field tracking    |

### P2 — Architecture + Observability

| #    | Title                                       | Impact                                |
| ---- | ------------------------------------------- | ------------------------------------- |
| #239 | Enforcement modes (enforce/shadow/disabled) | Production rollout safety             |
| #240 | Envelope-to-execution adapter               | Maps all 5 PACT constraint dimensions |
| #233 | Prometheus /metrics + SSE streaming         | Enterprise observability              |
| #246 | Cache invalidation API                      | Operational control over fabric cache |
| #247 | ?refresh=true cache bypass                  | Per-request freshness control         |
| #244 | Consumer adapter registry                   | Multi-view data products              |
| #250 | MCP tool generation from products           | Auto-generate MCP tools               |
| #251 | Fabric-only mode                            | DataFlow without mandatory database   |

### P3 — Operational + Cosmetic

| #    | Title                                   | Impact                                         |
| ---- | --------------------------------------- | ---------------------------------------------- |
| #241 | Degenerate envelope detection at init   | Startup warnings for misconfigured envelopes   |
| #249 | FileSourceAdapter directory scanning    | Date-pattern file selection for financial data |
| #252 | BaseAdapter.database_type → source_type | Cosmetic naming fix                            |
| #232 | Parent tracker issue                    | Subsumes #234-#241                             |

## Cross-SDK Items

Issues requiring coordinated kailash-rs changes:

- #231 — Vacancy checks (kailash-rs already done, kailash-py needs parity)
- #234 — Per-node governance (kailash-rs PactEngine needs same pattern)
- #235 — Stale budget (kailash-rs needs same fix)
- #236 — Read-only governance (kailash-rs should expose read-only view)
- #237 — NaN guard (kailash-rs needs same guard)
- #233 — SSE streaming (match kailash-rs sse_url() interface)
