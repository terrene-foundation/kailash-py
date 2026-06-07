---
type: AMENDMENT
date: 2026-06-07
author: agent
project: F32 (kailash-ml doc phantom-API remediation)
topic: /redteam convergence + sweep-enhancement closure
phase: redteam
relates_to: 0006-DISCOVERY-sweep-reveals-platform-wide-ml-doc-rot
tags: [redteam, convergence, doc-rot, phantom-api, sweep]
---

# AMENDMENT — F32 /redteam reached convergence

Closure receipt for the F32 platform-wide kailash-ml doc phantom-API remediation
(branch `fix/kailash-ml-doc-phantom-api-f32`, 9 commits on top of `9ac09f117`).

## Outcome

- **87 → 0** phantom-API findings across 17 doc files under the original sweep.
- The sweep (`tools/check_doc_api_examples.py`) was **strengthened** during /redteam to
  also enumerate the method-call-kwarg + cross-fence-binding classes the R1 reviewer
  exploited by hand → it now gates **5 check classes** (import / method-existence /
  ctor-kwarg / method-kwarg / cross-fence) and is **green across 417 doc files**. This
  closes the journal-0006 §"For Discussion #3" sweep-enhancement follow-on.

## Round-history (receipts)

| Round | Agents / mechanism                                          | Verdict                                             |
| ----- | ----------------------------------------------------------- | --------------------------------------------------- |
| R1    | reviewer `a2968f6dcbcfa3f94` + security `a49f58fd59b7ab447` | security clean; reviewer 2 HIGH + 2 MED → all fixed |
| R2    | strengthened sweep (method-kwargs + cross-fence)            | 18 findings → all fixed                             |
| R3    | manual return-attribute audit (sweep blind spot)            | README ONNX + ml-agent-guardrails fiction → fixed   |
| R4    | reviewer `ae072e96ced6f5636` (ground-truth verify)          | every fence clean; 2 PROSE defects → fixed          |

R4 ground-truth-verified — against `inspect.signature` / `__dataclass_fields__` of the
installed kailash-ml 2.0.0 — every return-attribute, every method/ctor arity, and every
`km.*` module-level call across all 17 changed files. The only R4 findings were two prose
lines (outside python fences, the sweep's documented blind spot): `km.serve` return-type
(`ServeResult` not `ServeHandle`) and a `TrialRecord` field name. Both corrected.

## Disposition of the two-surface (canonical vs legacy) hazard

R4 confirmed every fence consistently uses ONE FeatureStore surface and ONE
ExperimentTracker surface — the highest-residual-risk pattern (same class name, different
module, different API) is handled correctly throughout.

## Durability follow-on (NOT yet done — surfaced for the operator)

`README.md` / `MIGRATION.md` / `docs/guides/**` / `tools/check_doc_api_examples.py` are
BUILD-repo-owned and durable on merge. BUT `.claude/skills/**` are loom-canonical (synced
via `/sync-to-build`): the skill rewrites in this PR are the **immediate BUILD-local fix**
and will be **overwritten on the next loom `/sync-to-build`** unless loom adopts them. To
make the skill fixes + the sweep gate durable, they MUST flow to loom via a BUILD `/codify`
proposal append (per `artifact-flow.md` "Append, Never Overwrite") → loom Gate-1 → loom
canonical authoring → `/sync-to-build`. The pre-existing proposal already flags the
FeatureStore skill rewrite (journal 0004); this AMENDMENT broadens that to the full
platform-wide rewrite + the import-execution-sweep gate as a codify candidate (rule:
"doc/skill code fences MUST pass an import-execution sweep at /redteam").

## For Discussion

1. Should the strengthened sweep be wired into the BUILD CI (not just `/redteam`) so the
   doc rot cannot regress between releases — given it now gates 5 classes in O(seconds)?
2. The two-`FeatureStore` / two-`ExperimentTracker` name collisions are the root cause of
   the most resilient fiction (a fence that imports one and calls the other's method). Is
   the durable fix the sweep (permanent guard) or collapsing the duplicate names in the
   package (#643 follow-up)?
