# Analysis: PACT Spec-Conformance Issues #199-#202

**Date**: 2026-03-31
**Status**: Analysis complete — ready for /todos
**Workspace**: kailash
**Scope**: 4 GitHub issues, PACT governance module, spec-conformance

## Summary

4 PACT spec-conformance gaps identified by red team audit. All 4 exist in Python but not in Rust (kailash-rs is already compliant). This is a catch-up sprint with clear spec references and existing implementation patterns to follow.

| Issue                                                               | Severity | Spec Section | What's Missing                                                   |
| ------------------------------------------------------------------- | -------- | ------------ | ---------------------------------------------------------------- |
| [#199](https://github.com/terrene-foundation/kailash-py/issues/199) | CRITICAL | 5.7          | EATP record types never emitted by GovernanceEngine              |
| [#200](https://github.com/terrene-foundation/kailash-py/issues/200) | HIGH     | 5.3, 5.6     | Write-time tightening missing 3/7 dimensions; no gradient config |
| [#201](https://github.com/terrene-foundation/kailash-py/issues/201) | HIGH     | 4.2, 4.4     | No vacant head auto-creation; no bridge bilateral consent        |
| [#202](https://github.com/terrene-foundation/kailash-py/issues/202) | MEDIUM   | 5.5          | Vacancy blocks instead of degrading; hardcoded 24h deadline      |

## Current State

- **Source files**: 22 in `src/kailash/trust/pact/`
- **Key file sizes**: engine.py (1618 LOC), envelopes.py (937), compilation.py (974), audit.py (371)
- **Tests**: 1,139 passing, 10 skipped, 47 test files
- **CI**: All green on main

## Key Findings

### 1. PACT and EATP are structurally adjacent but functionally isolated

PACT (`src/kailash/trust/pact/`) and EATP (`src/kailash/trust/chain.py`) live in the same `trust/` tree but share zero code. PACT has its own `AuditAnchor` class. The EATP types (`GenesisRecord`, `DelegationRecord`, `CapabilityAttestation`) exist and are fully implemented — they've just never been wired to PACT.

### 2. Intersection functions exist but write-time validation doesn't use them

`_intersect_temporal()`, `_intersect_data_access()`, `_intersect_communication()` (envelopes.py:240-307) exist for runtime use in `intersect_envelopes()`. But `validate_tightening()` (line 415-544) only validates Financial, Confidentiality, Operational, and Delegation. The tightening check semantics are different from intersection — tightening checks subset/ordering, intersection computes min/overlap.

### 3. Compilation silently drops headless units

`compile_org()` builds `unit_head_map` (line 427-430) from roles with `is_primary_for_unit`. Units not in this map get no address in the compiled org. The spec says these should get a vacant head role auto-synthesized.

### 4. Vacancy is binary instead of graduated

`_check_vacancy()` returns either "OK" or "blocked". The spec defines a middle state: within the deadline window, direct reports should operate under an interim envelope (more restrictive of own + parent's for the vacant role). Only after the deadline should actions be fully blocked.

## Dependency Graph

```
#200 (tightening) ──── no dependencies, implement first
#201 (compilation + bridges) ──── #202 depends on vacant heads existing
#202 (vacancy interim) ──── depends on #201 sub-issue 1
#199 (EATP records) ──── independent, can run in parallel
```

## Estimated Scope

~950 LOC production + ~600 LOC tests = ~1,550 LOC total. 1 autonomous session.

## Detailed Research

See `01-analysis/01-research/01-pact-spec-conformance-audit.md` for:

- Line-by-line code analysis of all affected methods
- Sub-issue breakdown per GitHub issue
- Cross-SDK status comparison
- Security considerations
- Test impact assessment

## Journal Entries

- `0014-DISCOVERY-pact-spec-conformance-four-gaps.md` — Gap summary, cross-SDK status
- `0015-CONNECTION-pact-eatp-bridge-never-wired.md` — Architecture: why PACT/EATP are isolated
