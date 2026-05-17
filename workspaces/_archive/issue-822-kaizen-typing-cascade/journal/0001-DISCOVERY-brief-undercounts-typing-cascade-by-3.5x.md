---
type: DISCOVERY
date: 2026-05-05
created_at: 2026-05-05T00:00:00Z
author: agent
session_id: issue-822-kaizen-typing-cascade
session_turn: /analyze
project: kailash-py / issue-822-kaizen-typing-cascade
topic: brief under-counts typing cascade by 3.5×
phase: analyze
tags:
  [issue-822, brief-verification, parallel-brief-claim-verification, pyright]
---

# DISCOVERY — Brief under-counts #822 typing cascade by 3.5×

**Date:** 2026-05-05
**Phase:** /analyze
**Trigger:** `rules/agents.md` MUST Parallel-Brief-Claim Verification (≥3-issue brief)

## Finding

Issue #822 brief enumerates 4 lying-type sites + "4 errors + 6 warnings" cascade in
`kaizen/core/framework.py` + cascade "extends into" `kaizen/core/agents.py`. Mechanical
pyright run + 3 parallel deep-dive agents:

| File                       | Brief          | Pyright ground truth          | Delta                       |
| -------------------------- | -------------- | ----------------------------- | --------------------------- |
| `kaizen/__init__.py`       | 2 sites        | 0e / 3w (2 sites + 1 param)   | match                       |
| `kaizen/core/framework.py` | 4e / 6w        | **4e / 21w**                  | warnings under-counted 3.5× |
| `kaizen/core/agents.py`    | "extends into" | **3e / 12w**                  | scope omitted entirely      |
| Lying-type sites           | 4              | **6** (4 brief + 2 in agents) | +2 omitted                  |

Bug class is also broader than typing — surfaced 1 real Rule-3 silent-fallback
(`signature_programming_enabled` gate) + 1 Rule-2 fake-integration cluster (5
NEVER_EXISTED imports gating 6 dead public-API methods).

## Why this matters

This is the second consecutive #814-class brief that under-counts mechanical pyright
output by ≥3× (issue #814 brief said 7 BaseTool sites; pyright found 17). The pattern:
human-authored briefs from a recently-touched mental model decay against a moving
codebase. Single-agent analysis on such briefs would have inherited the framing into
`/todos` and shipped fixes targeted at the wrong scope.

The mitigation is the `rules/agents.md` parallel-brief-verification gate. Three parallel
deep-dive agents independently verified each cluster; orchestrator reconciled findings
into the architecture plan's "Brief Corrections" table BEFORE `/todos`.

## Action

- Architecture plan documents all corrections in TL;DR + Brief Corrections table.
- Two shards proposed instead of the brief's implied "one 4-line fix."
- Recommend codifying this pattern at `/codify` time: `kaizen/core/*.py` pyright
  briefs MUST always include explicit "Cluster A/B/C" scoping (matching the #814
  template) since single-bullet briefs reliably under-scope.

## For Discussion

1. **Counterfactual:** if the brief had been written with explicit Cluster A/B/C
   scoping (matching the #814 template that consistently surfaces accurate
   counts), would the parallel-brief-verification gate have produced different
   findings, or would it have rubber-stamped the brief? Is the gate value the
   counts or the framing?
2. **Specific data:** the framework.py warnings count (brief: 6, actual: 21)
   under-counted by 15. Two consecutive #814-class briefs (this one + #814)
   under-count mechanical pyright by ≥3×. Is this a brief-authoring discipline
   problem or a tooling gap (no `pyright` invocation at brief-writing time)?
3. **Cost:** parallel verification cost 3 background agents × ~3 min each.
   Worth it for a typing cleanup? At what brief-claim count does the cost
   exceed the value?

## References

- `02-plans/01-architecture.md` § Brief Corrections
- `01-analysis/01-cluster-a-lying-types.md`
- `01-analysis/02-cluster-b-agent-model.md`
- `01-analysis/03-cluster-c-imports-orphans.md`
- Prior precedent: `workspaces/issue-814-kaizen-pyright/02-plans/01-architecture.md` § Brief Corrections
