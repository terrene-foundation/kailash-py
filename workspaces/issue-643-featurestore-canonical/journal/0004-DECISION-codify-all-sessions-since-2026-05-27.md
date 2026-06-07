---
type: DECISION
date: 2026-06-07
author: co-authored
project: codify (all sessions since 2026-05-27)
topic: BUILD→loom codify proposal — FeatureStore cutover skills + 5 rule items
phase: codify
tags:
  [
    codify,
    proposal,
    featurestore,
    tenant-isolation,
    observability,
    verify-claims,
  ]
---

# DECISION — /codify all sessions since the last codification (2026-05-27)

User-directed `/codify` covering every session since `learning-codified.json::last_codified`
= 2026-05-27 (not just this session's #643 cutover). Single-operator (no roster); codify
lease granted clean (`codify/esperie-2026-06-07`).

## Method

Two parallel extraction agents surveyed the June 1–7 journal corpus (~30 entries across
~12 workspaces) + 15 deploy records, clustered DataFlow/core-SDK and Nexus/process/cross-SDK.
Each was instructed to be selective: flag only learnings that generalize to a NEW or UPDATED
rule/skill, and SKIP point-fixes already captured by journal + regression test. Of ~17
distinct learnings surveyed, most were SKIP (already captured).

## What was codified (proposal appended to `.claude/.proposals/latest.yaml`, 10 → 16 changes)

The existing 10-change pending proposal (2026-05-18 #1086 + others, still awaiting loom
Gate-1) was PRESERVED; 6 new entries appended (append-not-overwrite per `artifact-flow.md`):

| Entry                               | Type         | Target                          | Evidence                 |
| ----------------------------------- | ------------ | ------------------------------- | ------------------------ |
| FeatureStore 2.0.0 cutover examples | skill_update | 6 skill files (applied locally) | #643 (this session)      |
| verify-claims-before-durable-write  | rule_new     | new baseline rule               | #1125 / PRs #1187/#1188  |
| nexus-http-status SDK-scope         | rule_update  | nexus-http-status-convention.md | #937 / errors.py:79-90   |
| credential-redaction-every-surface  | rule_update  | observability.md §6.3           | #1260 (4 review rounds)  |
| contextvars-thread-boundary         | rule_update  | patterns.md                     | #1200 (all 4 runtimes)   |
| one-canonical-tenant-source         | rule_update  | tenant-isolation.md             | #1252 (bulk NULL-tenant) |

Local edits (immediate-use, BUILD `/codify` norm): the 6 FeatureStore skill examples'
top-level `from kailash_ml import FeatureStore` → explicit legacy import (top-level now
resolves to the canonical read surface post-2.0.0; these are legacy write workflows).

## Deferred (codify-on-recurrence, single-incident — recorded in proposal `deferred`)

#772 type-introspection consolidation (AST-invariant regression test covers it; not yet a
cross-SDK pattern), #1245 sqlite per-thread conn leak, #1248 cross-loop pool disposal. Per
the corpus discipline: codify on recurrence signal, not first instance.

## Why this shape (BUILD→loom, not local rule authoring)

This is a BUILD repo: rules are loom-canonical (synced via `/sync-to-build`). Per
`artifact-flow.md` "loom Splits, Never Originates," the rule clauses are PROPOSED (with
draft MUST-text the agents produced) for loom Gate-1 to classify global/variant and author
canonically (with Trust Posture Wiring + DO/DO NOT per `rule-authoring.md`). Authoring the
rules locally would double-author what loom re-derives. Only the lower-risk skill examples
were edited locally for immediate use.

## Consequences / follow-up

- The proposal stays `pending_review`; loom drains it at the next `/sync` Gate-1 (the queue
  has been BLOCKED on loom since 2026-05-18 — F1 in prior session ledgers).
- The FeatureStore skill examples need a FULL canonical rewrite at loom (see [[0005]] — the
  phantom-method finding); this session's local import swap is a partial fix only.

## For Discussion

1. Counterfactual: had the extraction agents NOT been told to SKIP regression-test-captured
   point-fixes, the proposal would have ~17 entries instead of 6 — would loom Gate-1's
   classify cost favor the lean proposal, or does the broader capture surface cross-SDK
   patterns the lean one drops (e.g. #1245/#1248 resource-lifecycle siblings)?
2. The verify-claims rule already exists as an auto-memory + is actively cited across the
   June cross-SDK journals — does promoting it to a structural rule with Trust-Posture wiring
   add enforcement value, or is the memory + zero-tolerance Rule 1c sufficient?
3. Five of six rule items propose GLOBAL classification — is the nexus-http-status SDK-scope
   fix actually a `variant` (Python-vs-Rust divergence is inherently per-SDK)?
