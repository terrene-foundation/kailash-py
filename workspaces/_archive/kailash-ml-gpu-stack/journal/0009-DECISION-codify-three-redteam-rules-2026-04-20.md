---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T07:00:00.000Z
author: co-authored
session_id: continue-session-2026-04-20-outstanding-items
project: kailash-ml-gpu-stack
topic: Codify three new rules from 2026-04-20 /redteam full-specs sweep — pytest plugin declaration, per-package collect-only, full-sibling spec re-derivation
phase: codify
tags: [codify, rules, testing, orphan-detection, specs-authority, cross-sdk]
related_journal:
  [
    0007-DISCOVERY-full-specs-sweep-round.md,
    0008-GAP-full-specs-redteam-2026-04-20-findings.md,
  ]
---

# DECISION — Three rule additions from 2026-04-20 /redteam cycle

## Context

The 2026-04-20 session ran `/redteam` scoped to "gaps against full specs" following resolution of three outstanding items from the kailash-ml 0.12.1 cut (PR #543 merged; issue #541 closed). Three analyst agents audited 34 spec files in parallel, surfacing 13 HIGH findings. Two were fixed inline (PR #544). Eleven were deferred to future implementation sessions.

Three distinct failure modes emerged that warrant codification as institutional rules. All three are cross-SDK applicable.

## Decisions

### 1. rules/testing.md — Pytest Plugin + Marker Declaration Pair

**Rule added**: `### MUST: Pytest Plugin + Marker Declaration Pair` (after the existing JWT-secret section, before `## 3-Tier Testing`).

**Contract**: Any test file using `@pytest.mark.<X>` or fixture `<X>` from a pytest plugin MUST declare the plugin in the owning sub-package's `[dev]` extras AND register the marker in that sub-package's pytest `markers` config in the same commit.

**Evidence**: `packages/kailash-kaizen/tests/e2e/memory/test_persistent_buffer_e2e.py` used `@pytest.mark.benchmark` + `benchmark` fixture from `pytest-benchmark`; the plugin was declared nowhere and the marker was never registered. Result: 11,917 kaizen tests blocked from collection. Fixed commit `1313ae56`.

### 2. rules/orphan-detection.md — §5a Per-Package Collect-Only Gate

**Rule added**: `### 5a. Collect-Only Gate Passes Per-Package, Not Combined Root Invocation` (clarifies §5 interpretation for monorepos).

**Contract**: §5 ("Collect-Only Is A Merge Gate") MUST NOT be interpreted as requiring a single combined `pytest --collect-only tests/ packages/*/tests/` invocation. Monorepos with sub-package test-only deps (hypothesis, respx, pytest-benchmark) CANNOT pass the combined shape from root venv because `python-environment.md` Rule 4 blocks duplicating sub-package test deps in root `[dev]`. Gate passes via per-package invocation after installing `packages/<pkg>[dev]` extras.

**Evidence**: Combined invocation failed with `ModuleNotFoundError: hypothesis` + `ModuleNotFoundError: respx` + `ImportPathMismatchError: tests.conftest`. Per-package iteration succeeded for all 9 sub-packages (~42,000 tests collected cleanly).

### 3. rules/specs-authority.md — MUST 5b Full Sibling-Spec Re-Derivation

**Rule added**: `### 5b. Spec Edits MUST Trigger Full Sibling-Spec Re-Derivation` (between existing §5 and §6).

**Contract**: Every spec edit MUST trigger re-derivation against the full sibling-spec set in the same domain (e.g. editing `specs/ml-engines.md` → re-derive against all `specs/ml-*.md`). Narrow-scope ("specs I just edited") is BLOCKED.

**Evidence**: Two-session reproducibility. Session 2026-04-19 (journal 0007) got "14/14 green" APPROVE on 2 edited ML specs. Session 2026-04-20 (journal 0008) re-ran full `specs/ml-*.md` sweep and surfaced 9 HIGH cross-spec drift findings in specs the edit never touched. The rule extension strengthened by reproducibility of the same failure mode across sessions.

## What landed

- Commit pending (this branch): 3 rule updates + fresh proposal `.claude/.proposals/latest.yaml` + archived prior proposal
- Journal entries: `0008-GAP-full-specs-redteam-2026-04-20-findings.md` (findings) + `0009-DECISION-codify-three-redteam-rules-2026-04-20.md` (this entry)
- Audit artifacts: `workspaces/kailash-ml-gpu-stack/04-validate/05-07-specs-gap-audit-*.md` (3 files, ~113 assertion rows with literal verification commands)
- Proposal: `/codify` Step 7 submission to loom/ Gate-1 for classification (3 global rule changes proposed, 1 HIGH + 2 MEDIUM)

## Alternatives considered

- **Consolidate all 3 rules into a single `rules/collection-gate.md`**: Rejected. The three rules target different audiences (testing authors, gate reviewers, spec editors) and different file patterns. Splitting keeps `paths:` scoping tight.
- **Defer rule 3 (spec-authority 5b) to a future codify cycle**: Rejected. Two-session reproducibility meets the rule-authoring meta-rule threshold for codification now. Deferring invites a third recurrence.
- **Extract rule 2 (collect-only §5a) as its own file rather than an §5 extension**: Rejected. It's a direct interpretation clarification of §5 — splitting would create cross-reference overhead for every reader of §5.

## Consequences

- Rule file sizes: testing.md now 416 lines (pre-existing overflow), orphan-detection.md 209 lines (+55), specs-authority.md 227 lines (+39). Per `cc-artifacts.md` Rule 6 and `rule-authoring.md` MUST NOT, rules over 200 lines are "skimmed; agent misses load-bearing clauses." Flag for future codify: extract reference material from testing.md into a separate skill.
- loom/ Gate-1 will classify the 3 proposed rule additions. All 3 have `classification_suggestion: global` (cross-SDK applicable).
- Follow-up workstreams seeded for the 11 deferred HIGH findings (ML Phase 6, ONNX matrix, km.doctor, kailash-trust orphan, dialect drift) — each will need its own `/analyze` → `/todos` → `/implement` cycle.

## For Discussion

1. **Counterfactual**: If the /redteam had stopped at "2 inline fixes" without codifying the underlying patterns, the next session would have hit (a) a different sub-package declaring a new pytest plugin without registering the marker, (b) another combined-invocation attempt failing with the same hypothesis/respx errors, and (c) another spec edit producing narrow-scope APPROVE with hidden cross-spec drift. Three identical re-learn cycles. The codify cost is ~100 lines of rule text across 3 files; the avoided cost is ~3 sessions of re-discovery. Is the rule-per-failure-mode ratio the right granularity, or should we batch multiple failure modes into broader rule additions?

2. **Data-referenced**: Journal 0007 proposed "rules/specs-authority.md MUST 5b" as a candidate extension pending recurrence. Journal 0008 observed the recurrence. This session codified the rule. The observation-to-codification loop took exactly one session turn between the two journals. Question: should codify cycles actively look for "candidate extensions from prior journals awaiting recurrence" as a mechanical step? Currently `learning-digest.json` captures error patterns but not "codification candidates awaiting a second data point."

3. **Rule-authoring meta-rule compliance**: All three new rules include MUST phrasing, BLOCKED rationalizations, DO/DO NOT examples, `**Why:**` lines, and `Origin:` references per `rule-authoring.md` checklist. The "Loud, Linguistic, Layered" test passes for each. Question: should `/codify` include a mechanical pass that greps new rule additions against the meta-rule checklist before commit, or does LLM-judgment review of the rule text suffice?
