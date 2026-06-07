---
type: DECISION
date: 2026-06-07
author: agent
project: F32 (kailash-ml doc phantom-API remediation)
topic: /codify the F32 gap — sweep-gate rule candidate + skill durability to loom Gate-1
phase: codify
relates_to: 0007-AMENDMENT-f32-redteam-convergence
tags: [codify, proposal, loom, doc-rot, sweep, durability]
---

# DECISION — codify the F32 gap (BUILD→loom proposal append)

PR #1277 merged to `main` (`1decd6c49`); F32 is delivered locally. This `/codify` captures
the institutional gap so it survives + propagates, appending 2 entries to the BUILD→loom
proposal (`.claude/.proposals/latest.yaml`, `pending_review`, 16 → 18 changes; per
`artifact-flow.md` "Append, Never Overwrite"; existing `deferred`/`append_session` preserved).

## What was codified

1. **`doc-api-import-execution-sweep` (rule_new, global).** Candidate rule: every doc/skill
   python code fence MUST pass an import-execution sweep at `/redteam` — extends
   `spec-accuracy.md` Rule 1 + `user-flow-validation.md` from prose/spec to README/skill/guide
   fences. Reference tool `tools/check_doc_api_examples.py` (5 check classes). loom Gate-1
   decides: author the rule (global) + whether the tool syncs (py + rs variants) or stays
   per-BUILD-repo. Cross-SDK: the failure mode is language-agnostic.
2. **`kailash-ml-doc-real-api-rewrite` (skill_update, variant/py) — closes F33 durability.**
   The 10 loom-canonical kailash-ml skill files PR #1277 rewrote MUST be adopted as loom
   canonical, ELSE the next `/sync-to-build` overwrites the BUILD-local fix with the stale
   phantom versions. README/MIGRATION/guides are BUILD-owned package docs (durable on merge);
   `.claude/skills/project/ml-quick-reference.md` is project-local (durable).

## Why these two, and why now

The sweep gate is the durable structural defense (catches recurrence + the rs surface). The
skill-adoption entry is the ONLY thing standing between "fixed today" and "overwritten on the
next sync" — F32's skill fixes are not durable until loom adopts them. Both are loom-Gate-1
work (BUILD originates the proposal; loom authors/classifies).

## Decisions / disposition

- Repo class = BUILD (kailash-py) → Step 7a (BUILD→loom, cross-SDK-first). The rule candidate
  is flagged cross-SDK; loom authors the global rule.
- Single-operator repo (no `operators.roster.json`) → codify lease uncontended (L5);
  `acquireCodifyLease` returned `ok:true` on `codify/esperie-2026-06-07`.
- NOT self-referential per `self-referential-codify.md` Rule 2: the BUILD-side codify writes
  `.claude/.proposals/latest.yaml` (not in the allowlist) — it PROPOSES; loom Gate-1 authors
  the rule (where the multi-agent redteam-with-tests gate fires). No mandatory multi-agent
  round on the proposal-append itself.
- `learning-codified.json` updated (local/gitignored): +2 `proposal_append` actions.

## For Discussion

1. Should the rule live as a new `rules/doc-api-sweep.md` or as a clause extension of
   `spec-accuracy.md` Rule 1? (The sweep is the mechanical enforcement of "citations resolve
   against working code" — extension keeps the corpus smaller; a new rule gives it its own
   Trust-Posture-Wiring + grace clock.)
2. Is the sweep tool worth a Rust variant now (rs docs unverified), or defer until an rs
   doc-rot incident provides the evidence (codify-on-recurrence)?
3. Counterfactual: had the import-execution sweep existed at the #643 cutover, would PR #1274
   have been declared "docs fixed" with 87 sibling-surface findings still open? The gate makes
   "the docs are correct" a falsifiable exit-code rather than a reviewer's judgment.
