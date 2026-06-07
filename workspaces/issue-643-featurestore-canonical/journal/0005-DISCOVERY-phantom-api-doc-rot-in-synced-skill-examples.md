---
type: DISCOVERY
date: 2026-06-07
author: agent
project: codify (FeatureStore skill examples)
topic: phantom-API doc-rot recurs across README + 6 synced skill examples
phase: codify
tags: [doc-rot, phantom-api, featurestore, skills, spec-accuracy]
---

# DISCOVERY — phantom-API doc-rot in FeatureStore docs + synced skill examples

## What surfaced

During the #643 cutover (PR #1274) the README FeatureStore section was found to document
three methods that exist on NEITHER FeatureStore surface — `ingest()`, `get_features_at_time()`,
`list_feature_sets()`. Fixing the skill examples in this `/codify` surfaced the SAME class
again, broader: 6 `.claude/skills/` files teach `fs.ingest()`, `fs.compose()`,
`fs.register_schema()`, `store.register_group()` — none of which exist. The real legacy
FeatureStore API is `register_features(schema)` / `store(...)` / `compute(...)` /
`get_features(...)` / `get_training_set` / `get_features_lazy` / `list_schemas`.

So across THREE artifact surfaces — README, `docs/guides/02-feature-pipelines.md` (a fictional
`put`/`get` API, rewritten in PR #1274), and 6 skill examples — the FeatureStore docs taught a
**fictional API** that matches no shipped code.

## Why it persisted invisibly

1. **No executable gate on doc/skill examples.** Unit/integration tests exercise the real
   API; prose examples are never run, so a fictional method name never fails a gate. This is
   the `user-flow-validation.md` gap one layer out: the _example_ is a deliverable nobody walks.
2. **Synced-artifact blind spot.** The skill examples are loom-canonical (synced via
   `/sync-to-build`). The rot lives in loom's canonical copy; every BUILD repo inherits it.
   A BUILD-side reader sees "it came from loom, it must be right."
3. **The cutover masked it.** Pre-2.0.0, `from kailash_ml import FeatureStore` + a phantom
   method was _doubly_ wrong; the cutover's import flip made the import correct, which made the
   remaining phantom-method rot the only error — easy to miss when "fixing the import."

## Disposition

The local import swap this session is a PARTIAL fix (correct module, phantom methods remain).
The full accurate rewrite — decide legacy-explicit vs canonical-DataFlow-model framing per
example, replace every phantom method with the real signature — is flagged in the codify
proposal for loom Gate-1 canonical authoring (see [[0004]]).

## Codify candidate (surfaced for loom)

A mechanical defense worth proposing: an **AST/import-execution sweep over doc + skill code
fences** that imports the cited symbol and asserts every called method resolves
(`hasattr(cls, m)`), run at `/redteam` or pre-sync. This is the `spec-accuracy.md` Rule 1
"every citation resolves against working code" discipline extended from spec prose to
README/skill/guide code examples. Would have caught all three surfaces mechanically.

## For Discussion

1. Counterfactual: if the skill examples were generated FROM the real API surface (codegen
   from `inspect.signature`) rather than hand-authored, would the rot exist at all — i.e. is
   the fix a one-time rewrite or a generation-discipline change?
2. The phantom methods (`ingest`/`compose`/`register_schema`) are _plausible_ names a user
   would guess — did they originate as an aspirational API that was renamed before ship and
   never reconciled in docs? (Same shape as `spec-accuracy.md` split-state rot.)
3. Should the proposed import-execution sweep gate `/sync` (block distribution of a skill
   whose example calls a non-existent method), or only advise at `/redteam`?
