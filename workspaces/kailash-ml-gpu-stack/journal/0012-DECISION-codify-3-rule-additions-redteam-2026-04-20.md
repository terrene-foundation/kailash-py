---
type: DECISION
date: 2026-04-20
created_at: 2026-04-19T23:10:39.107Z
author: agent
session_id: 5224fc34-0ee5-4928-9769-52fcda88a097
session_turn: n/a
project: kailash-ml-gpu-stack
topic: 3 rule additions from 2026-04-20 /redteam cycle codified to proposal
phase: codify
tags:
  [auto-generated, codify, rules, testing, orphan-detection, specs-authority]
related_journal: []
---

# DECISION — 3 rule additions from 2026-04-20 /redteam cycle

## Commit

`7c4ecaaf8f90` — chore(codify): 3 rule additions from 2026-04-20 /redteam cycle

## Body

Captures institutional knowledge from the 2026-04-20 full-specs red-team sweep. Three distinct failure modes emerged and are codified as rule extensions; all three are cross-SDK applicable and submitted to loom Gate-1 for classification.

Rule additions (all HIGH/MEDIUM, per rule-authoring.md Loud/Linguistic/Layered):

1. `rules/testing.md` — MUST: Pytest Plugin + Marker Declaration Pair.
   Any test file using @pytest.mark.\<X\> or fixture \<X\> from a pytest plugin MUST declare the plugin in the sub-package's [dev] extras AND register the marker in pytest markers config in the same commit. Origin: `test_persistent_buffer_e2e.py` used @pytest.mark.benchmark + benchmark fixture without declaring pytest-benchmark; blocked 11,917 kaizen tests.

2. `rules/orphan-detection.md` — §5a: Collect-Only Gate Per-Package With [dev] Extras.
   Clarifies §5 for monorepos: the gate passes via per-package `pytest --collect-only` after installing each sub-package's [dev] extras, NOT a single combined root-venv invocation. python-environment.md Rule 4 explicitly blocks duplicating sub-package test deps in root [dev], making combined invocation structurally impossible without the sub-package installs.

3. `rules/specs-authority.md` — MUST 5b: Full Sibling-Spec Re-Derivation.
   Every spec edit MUST trigger re-derivation against the full sibling-spec set in the same domain. Narrow scope ("specs I just edited") is BLOCKED. Two-session reproducibility (journals 0007 + 0008) confirms the pattern.

Artifacts in this commit:

- 3 rule file updates (+106 lines total across testing/orphan-detection/specs-authority)
- Fresh `.claude/.proposals/latest.yaml` for loom Gate-1 review
- Archived prior proposal to `.claude/.proposals/archive/2026-04-19-kailash-py-ml-gpu-phase1.yaml` (resolves stale merge conflict markers from distributed proposal; verified template kailash-coc-claude-py at v3.5.9)
- 3 /redteam audit artifacts (`workspaces/kailash-ml-gpu-stack/04-validate/05-07-specs-gap-audit-*.md`)
- 2 journal entries (0008-GAP findings, 0009-DECISION codify rationale)

Post-release followups (11 HIGH findings deferred to dedicated sessions):

- ML Phase 6: km.track() NotImplementedError + 16 auto-capture fields + run statuses
- ONNX bridge matrix: torch/lightning/catboost branches + regression tests
- km.doctor console script absent
- packages/kailash-trust orphan (zero tests, minimal re-export)
- dialect.quote_identifier() drift between core and dataflow layers

## For Discussion

1. **Counterfactual**: If the pytest-benchmark marker violation had NOT been caught by the collection-gate sweep, and the kaizen test suite had continued shipping without the `benchmark` plugin declared, how many CI matrix jobs would have silently shown 0 tests collected (rather than failing loudly), and for how many releases?

2. **Data-referenced**: Rule addition 3 (specs-authority.md MUST 5b) cites two-session reproducibility from journals 0007 + 0008. The two sessions were 2026-04-19 and 2026-04-20 — within 24 hours, same workspace, same author. Does two-session reproducibility within a single sprint constitute strong evidence, or does it only rule out session-level random variation (not cross-project or cross-domain variation)?

3. **Scope**: All three rule additions were submitted to loom Gate-1 as `global` candidates. Rule 2 (per-package collection gate) is structurally tied to the Python packaging model — `pyproject.toml [dev] extras` and `pytest markers` are Python-specific artifacts. What would the Rust cross-SDK form look like, and does it belong in the same global rule or a py-variant?
