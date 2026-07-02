# DISCOVERY — Marker convention is the architectural keystone (17 of 28 mitigations)

**Date:** 2026-04-26
**Phase:** /analyze
**Workspace:** spec-drift-gate

## Finding

When designing a mechanical spec-vs-code drift gate, the SINGLE highest-leverage design axis is how the gate distinguishes assertion from informal mention. **17 of 28 enumerated failure modes** (`01-analysis/01-failure-points.md` § Closing Notes) have mitigations that collapse onto this one decision: A1 (informal mention), A2 (cross-spec sibling), A3 (deferred-section), A4 (code-block context), B1 (FQ-path requirement), B2 (extras-gated), B3 (dynamic class), B4 (method existence), B5 (field existence), B6 (test function existence), C3 (bidirectional triggering hook scope), D1 (ignore-marker governance), D4 (baseline citation), D5 (gate vs /redteam authority), E3 (executable annex evolution), F1 (Unicode evasion), F2 (commented-out code).

Two analysts working in parallel (failure-point analysis vs. requirements/ADRs) independently converged on this conclusion. Agent A explicitly flagged "marker convention is the highest-leverage decision the requirements analyst MUST anchor on — not an implementation detail." Agent B chose marker convention (ADR-2) as its single highest-confidence ADR — the only ADR where the design space was mapped exhaustively, alternatives quantified against the live corpus, and the chosen option backed by an existing reviewer's working procedure (W6.5 mechanical sweep tables).

## Why this matters

A naive design would treat marker convention as an implementation detail of the AST sweep. The discovery shows it's a primary architecture concern that determines: false positive rate, false negative rate, baseline maintenance, override governance, future evolution path, and adoption posture. Get the marker convention wrong and 17 of 28 failure modes degrade simultaneously.

## Resolution

**ADR-2 chose section-context inference + `<!-- spec-assert: ... -->` overrides.** Section-context (parse spec heading hierarchy; only sweep symbols inside allowlisted section names) is the default. Override directives are escape hatches. The chosen design has empirical grounding: ~250+ backtick references in `ml-automl.md` alone would produce ~80% FPR if all backticks were assertions; section-context narrows to <5% (the W6.5 reviewer's 17/17 + 16/18 manual sweep table is the proof).

## Replay-ability

The pattern (parallel analysts converging on a single keystone decision) is reusable for future tooling/governance design. When two independent analyses surface the same lever, prioritize that lever in the implementation plan and treat downstream design decisions as dependents.

## References

- `01-analysis/01-failure-points.md` § Closing Notes (line 460) — 17/28 dependency claim
- `01-analysis/02-requirements-and-adrs.md` § 3.2 ADR-2 (lines 487-571) — full design space
- `04-validate/00-analyze-redteam.md` § 5 Quality Signals — green flag substantiation
- `workspaces/portfolio-spec-audit/04-validate/W6.5-v2-draft-review.md` — reviewer's working procedure that ADR-2 codifies
