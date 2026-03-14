# EATP SDK Gap Analysis — Synthesis

**Date**: 2026-03-14
**Workspace**: `eatp-gaps`
**Package**: `packages/eatp/src/eatp/` (v0.1.0, ~15,300 LOC, 45 modules)
**Analysis Team**: deep-analyst, requirements-analyst, eatp-expert, coc-expert

---

## Executive Summary

Four specialist agents analyzed 11 EATP SDK gaps identified during CARE Platform upstream analysis. Key findings:

1. **9 of 11 gaps confirmed as genuine EATP SDK responsibilities.** G10 (adapters) mostly belongs downstream; G11 is metadata enrichment only.
2. **4 hidden risks discovered** beyond the original brief: StrictEnforcer unbounded records (G5+), 8 deprecated `get_event_loop()` sites (G8+), systemic asyncio.Lock pattern across 10+ modules (G9+), bidirectional BUILTIN_DIMENSIONS mismatch (G11+).
3. **3 missing gaps identified** by eatp-expert: MG1 (no cascade revocation — HIGH), MG2 (no monotonic tightening at VERIFY time — MEDIUM), MG3 (StrictEnforcer unbounded records — bundle with G5).
4. **G2 (proximity thresholds) is the highest-impact gap** — it completes the verification gradient, the defining feature of EATP. The infrastructure (`ConstraintCheckResult.used`/`limit`) already exists; it's just not wired into verdict classification.

---

## Consensus Priority Order

All four agents converged on similar priorities. The synthesized order reflects:

- Deep-analyst: risk-adjusted (production safety first)
- Requirements-analyst: dependency-driven (foundations before capabilities)
- EATP-expert: spec-alignment (complete core features first)
- COC-expert: knowledge-dependency (each session builds context for next)

### Final Priority

| Phase | Gaps                    | Theme                                | Effort   | Risk        |
| ----- | ----------------------- | ------------------------------------ | -------- | ----------- |
| **1** | G5/G5+, G8/G8+, G9, G11 | Production safety & pattern learning | 2 days   | Low         |
| **2** | G2, G4                  | Core trust model completion          | 3 days   | Medium      |
| **3** | G3                      | Architectural extensibility          | 3-4 days | High        |
| **4** | G1                      | Trust scoring enrichment             | 3 days   | Medium      |
| **5** | G6, G7                  | Production hardening                 | 4-5 days | Medium-High |
| **6** | G10                     | Ecosystem alignment                  | 1-2 days | Low         |

**Total estimated effort: 18-24 days across 6 phases.**

---

## Key Architecture Decisions (from ADRs)

| ADR     | Decision                                                                                               | Rationale                                                                         |
| ------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| ADR-001 | **Complementary scoring model** — separate `BehavioralScorer` with configurable 60/40 blend            | Preserves backward compatibility; zero-data agents get structural-only score      |
| ADR-002 | **Protocol-based hooks with priority registry** — `EATPHook` protocol, `HookType` enum, `HookRegistry` | ABC pattern matches SDK conventions; supports fail-closed abort semantics         |
| ADR-003 | **Standalone ProximityScanner** consumed by enforcement layer                                          | Separates scanning from enforcement; reusable by both Strict and Shadow enforcers |
| ADR-004 | **Optional HMAC overlay** — `DualSignature` dataclass, Ed25519-only default                            | ~50 LOC, opt-in complexity, no breaking schema change                             |

---

## Revised Gap Count

| Category        | Original Brief | After Analysis                           |
| --------------- | -------------- | ---------------------------------------- |
| CRITICAL        | 3 (G1, G2, G3) | 3 (unchanged)                            |
| HIGH            | 3 (G4, G5, G6) | 4 (+MG1: cascade revocation)             |
| MEDIUM          | 4 (G7-G10)     | 5 (+MG2: monotonic tightening at VERIFY) |
| LOW             | 1 (G11)        | 1 (unchanged)                            |
| Hidden (bundle) | 0              | 4 (G5+, G8+, G9+, G11+)                  |
| **Total**       | **11**         | **14**                                   |

---

## Trust Model Impact Matrix

| EATP Element          | Current Coverage | Gaps That Improve It                           |
| --------------------- | ---------------- | ---------------------------------------------- |
| Constraint Envelope   | ~30%             | G2 directly, G11 indirectly                    |
| Verification Gradient | ~40%             | G2 directly (completes it)                     |
| Trust Postures        | ~70%             | G1 indirectly (behavioral → posture evolution) |
| Audit Anchor          | ~60%             | G6 (dual-signature)                            |
| Cascade Revocation    | 0%               | MG1 (not in original brief)                    |
| Monotonic Tightening  | ~50%             | MG2 (not in original brief)                    |

---

## Stakeholder Decisions Required

Before implementation begins, the following decisions need human input:

1. **G1 Weight Balance**: What structural/behavioral ratio? (60/40 recommended, range 50/50 to 70/30)
2. **G2 Threshold Defaults**: 70/90 (brief) vs 80/95 (kailash-rs alignment)?
3. **G3 Hook Error Policy**: Fail-closed (block on hook crash) vs fail-open (warn)?
4. **G7 Algorithm**: Accept ECDSA P-256 for AWS KMS (algorithm mismatch) or require Ed25519-capable providers?
5. **G9 Threading Model**: Document async-only vs add threading.Lock SDK-wide?
6. **G10 Ownership**: EATP SDK vocabulary docs only, or CARE-EATP bridge package?
7. **MG1/MG2 Scope**: Include cascade revocation and VERIFY-time tightening in this effort or defer to separate workspace?

---

## Analysis Documents Index

| #   | Document                          | Author               | Content                                                                          |
| --- | --------------------------------- | -------------------- | -------------------------------------------------------------------------------- |
| 01  | `01-gap-details.md`               | (pre-existing)       | Detailed gap descriptions for G1-G6                                              |
| 02  | `02-risk-analysis.md`             | deep-analyst         | Risk register, hidden risks, failure scenarios, dependency graph                 |
| 03  | `03-spec-alignment-evaluation.md` | eatp-expert          | Spec alignment verdicts, boundary analysis, missing gaps, priority re-evaluation |
| 04  | `04-requirements-breakdown.md`    | requirements-analyst | Functional/non-functional requirements, ADRs, API surfaces, test requirements    |
| 05  | `05-coc-assessment.md`            | coc-expert           | Three fault lines, anti-amnesia patterns, convention drift risks, quality gates  |
| 06  | `06-synthesis.md`                 | (this document)      | Synthesized analysis across all four agents                                      |
