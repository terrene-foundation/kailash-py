---
type: DISCOVERY
date: 2026-03-31
created_at: 2026-03-31T12:00:00+08:00
author: agent
session_id: session-10
session_turn: 1
project: kailash
topic: PACT module has 4 spec-conformance gaps — Python trailing Rust on all 4
phase: analyze
tags: [pact, spec-conformance, eatp, governance, cross-sdk]
---

# PACT Module Has 4 Spec-Conformance Gaps (All Exist in Rust)

## Discovery

A red team audit of the PACT governance module against PACT-Core-Thesis.md revealed 4 spec-conformance gaps, filed as GitHub issues #199-#202. All 4 are areas where the Rust SDK (`kailash-rs`) is already compliant but the Python SDK is not.

### Gap 1: EATP Record Emission (#199, CRITICAL)

PACT builds its own audit chain (`AuditAnchor`/`AuditChain` in `audit.py`) but never emits the EATP record types (`GenesisRecord`, `DelegationRecord`, `CapabilityAttestation`) from `kailash.trust.chain`. Zero imports from `kailash.trust.chain` exist in the PACT module. Spec Section 5.7 calls this mapping "normative."

### Gap 2: Write-Time Tightening Incomplete (#200, HIGH)

`validate_tightening()` (envelopes.py:415-544) checks 4 of 7 dimensions: Financial, Confidentiality, Operational, Delegation. Missing: Temporal (`active_hours`, `blackout_periods`), Data Access (`read_paths`, `write_paths`), Communication (`internal_only`, `allowed_channels`). The runtime intersection functions for these 3 dimensions exist (lines 240-307) but they aren't used for write-time validation.

Also missing: per-dimension gradient configuration (spec Section 5.6) — `RoleEnvelope` has no gradient field.

### Gap 3: Compilation + Bridge Protocol (#201, HIGH)

- `compile_org()` silently drops departments/teams without a head role instead of auto-creating vacant heads (spec Section 4.2)
- `create_bridge()` validates LCA approval but not bilateral consent from both endpoint roles (spec Section 4.4)
- Bridge scope not validated against role envelopes

### Gap 4: Vacancy Handling (#202, MEDIUM)

`_check_vacancy()` (engine.py:1381-1437) returns a hard block for any vacancy without designation. Spec says there should be an interim envelope (degraded-but-operational) during the 24h deadline window. Also, the 24h deadline is hardcoded instead of configurable.

## Significance

These are all spec-level gaps in a mature module (1,139 tests, 22 source files). The Rust SDK is already compliant on all 4 points. This is a Python catch-up sprint — no novel design decisions required.

## For Discussion

1. Given that the Rust SDK implements all 4 features already, should we treat this as a mechanical port (match Rust semantics exactly) or re-derive from spec? The Rust implementation may have made design choices we don't want to inherit.
2. If EATP record emission (#199) is truly "normative" per Section 5.7, why was the PACT module released without it? Was there a conscious decision to defer, or was it simply missed during the initial implementation sprint?
3. If the write-time tightening had been complete from the start, would the intersection functions (lines 240-307) have been written differently — or are they already structured to support both runtime intersection and write-time validation?
