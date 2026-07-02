# Consolidated GitHub Issues Brief — 14 Open Issues

## Overview

14 open GitHub issues spanning 4 workstreams. This analysis consolidates them into a unified implementation plan.

## Workstream 1: PACT Engine Hardening (9 issues)

The L1 PactEngine has critical security gaps and missing architectural features identified by gap analysis against the L3 pact-platform implementation.

### Security Bugs (fix immediately)

| Issue | Title                                                     | Severity                                   |
| ----- | --------------------------------------------------------- | ------------------------------------------ |
| #234  | Single-gate governance — no per-node verify_action        | HIGH — governance bypass after submit gate |
| #235  | Stale supervisor budget — reused across submit() calls    | HIGH — budget enforcement bypass           |
| #236  | Mutable GovernanceEngine exposed via .governance property | HIGH — privilege escalation                |
| #237  | NaN-guard on supervisor result budget_consumed            | MEDIUM — budget evasion (indirect)         |

### Spec Conformance

| Issue | Title                                              | Severity                              |
| ----- | -------------------------------------------------- | ------------------------------------- |
| #238  | HELD verdict treated as BLOCKED — no approval path | MEDIUM — governance model degradation |

### Architecture Enhancements

| Issue | Title                                         | Priority                                |
| ----- | --------------------------------------------- | --------------------------------------- |
| #239  | Enforcement modes (enforce/shadow/disabled)   | HIGH — production rollout essential     |
| #240  | Envelope-to-execution adapter with NaN guards | HIGH — maps all 5 constraint dimensions |
| #241  | Degenerate envelope detection at init         | MEDIUM — operational safety             |
| #232  | Parent tracker: upstream L3 patterns          | Tracker — subsumes items from #234-#241 |

### Dependencies

- #240 (envelope adapter) should land before #234 (per-node governance) — adapter provides the constraint mapping per-node enforcement needs
- #236 (read-only governance) should land before #238 (HELD verdict) — HELD path needs safe governance access
- #237 (NaN guard) is independent, can go first
- #235 (stale budget) is independent, can go first
- #239 (enforcement modes) depends on #234 (per-node governance) for shadow mode to be meaningful

## Workstream 2: DataFlow Data Quality (3 issues)

Enhancements for regulated/financial applications needing provenance and audit capabilities.

| Issue | Title                                                           | Priority                     |
| ----- | --------------------------------------------------------------- | ---------------------------- |
| #242  | ProvenancedField — field-level source tracking and confidence   | HIGH — financial/compliance  |
| #243  | Audit trail persistence — store write events for compliance     | HIGH — compliance/regulatory |
| #244  | Consumer adapter registry — multiple views of same product data | MEDIUM — Fabric DX           |

### Dependencies

- #242 (ProvenancedField) and #243 (audit trail) are independent of each other
- #244 (consumer adapters) is independent but conceptually builds on Fabric Engine (data-fabric-engine workspace)
- #243 (audit trail) connects to #242 (provenance) — audit events should include provenance metadata

## Workstream 3: Nexus Observability (1 issue)

| Issue | Title                                                          | Priority                        |
| ----- | -------------------------------------------------------------- | ------------------------------- |
| #233  | Prometheus /metrics endpoint + SSE HTTP streaming for EventBus | HIGH — enterprise observability |

Two discrete features:

1. `/metrics` endpoint using prometheus_client — scrapeable OpenMetrics format
2. SSE streaming endpoint for EventBus — matches kailash-rs `sse_url()` method

### Dependencies

- Independent of all other workstreams
- Cross-SDK: should match kailash-rs EventBus SSE interface

## Workstream 4: Cross-SDK Governance Alignment (1 issue)

| Issue | Title                                                 | Priority                               |
| ----- | ----------------------------------------------------- | -------------------------------------- |
| #231  | Vacancy check on bridge approval + semantic alignment | HIGH — security bug + cross-SDK parity |

Fixes already applied in kailash-rs. kailash-py needs:

1. Vacancy check on approve_bridge/reject_bridge
2. set_vacancy_designation rejects filled roles
3. 6 semantic alignment items (serialization, defaults, boundary behavior, algorithm equivalence)

### Dependencies

- Independent of PACT Engine workstream (different layer — governance core vs engine)
- Cross-SDK alignment items need coordinated verification
