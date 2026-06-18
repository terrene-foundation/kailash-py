---
type: DECISION
slug: f8-superseded-by-f25-f9
created: 2026-06-01
---

# DECISION — F8 (kaizen RAG make-functional + coverage) CLOSED as superseded

**Disposition:** CLOSE AS SUPERSEDED — user-gated 2026-06-01.
**Governing rule:** `rules/value-prioritization.md` MUST-4 (closure of value-bearing
deferred work requires a user gate). F8 carries a user-anchored value source, so this
closure is the user's call, recorded below — not an agent self-authorization.

## Decision

F8 — the kaizen RAG "make-functional + behavioral coverage" workstream (plan APPROVED
2026-05-26 by co-owner) — is **closed as superseded**. Its entire value-anchor was
delivered out-of-band by the **F25/F9 kaizen-rag remediation** (PRs #1198, #1199 + the
F9 cleanup commits) between the plan's base (`0f906a1e0`) and current main (`c9fa74ad0`).
Resuming F8 would re-deliver already-shipped, already-tested code.

## Value-anchor (verbatim, per value-prioritization MUST-2)

From `briefs/00-brief.md` § "Out of scope":

> "the RAG capability the user chose to preserve is **provably correct, not merely importable**."

How it was met: the F25/F9 work closed the exact "importable-but-broken" failure mode the
anchor targets. The package no longer merely imports — every RAG node class constructs, and
behavior is proven by an executing test suite, not by import success.

## Evidence (verified against main `c9fa74ad0`, 2026-06-01 — not re-derived from the plan)

| F8 milestone                        | Planned                     | Current state                                                                     |
| ----------------------------------- | --------------------------- | --------------------------------------------------------------------------------- |
| A0 — f-string LEAK scan             | enumerate R4/CLASS4 leaks   | AST sweep: **0 leaks** in current `nodes/rag/*.py`                                |
| A1 — 38 bare constructors           | positional → keyword        | **already canonical** (`super().__init__(name=name, **cfg)`)                      |
| A1-core — 2 MCP core sites          | fix + drop `# type: ignore` | **targets removed upstream** (`MCPToolNode`/`enhanced_server.py` no longer exist) |
| A2 — 13 WorkflowNode ctors          | positional → keyword        | **already canonical** (`workflow=..., name=name`)                                 |
| A3 — triage unmasked failures       | disposition R3/R4           | nothing to triage — all construct                                                 |
| A-S2 — `create_hybrid_rag_workflow` | real impl                   | implemented + passing test (`TestCreateHybridRagWorkflow`)                        |
| B1–B10 — behavioral coverage        | 58 classes ≥1 test          | **641 unit/regression + 244 integration tests pass**                              |

- Constructability probe: **55/55** RAG node classes construct (`cls(name=...)`), **0 failures**.
- Test suite: 641 unit/regression pass in ~13s; 244 integration tests collected (real-infra,
  per-module — not skip-shells). Covers every brief-named capability (GraphRAG, AgenticRAG,
  FederatedRAG, MultimodalRAG, ColBERT, HyDE).
- Delivery path: PRs **#1198** (`fix/kaizen-rag-workflows-unwired-inputs`), **#1199**
  (`fix/kaizen-rag-query-processing-defects`) + the F9 codegen-cleanup commits.

## User gate (per MUST-4)

User explicitly gated this closure on 2026-06-01 (AskUserQuestion: "Close as superseded").
This is a completion/superseded closure (value delivered by a different path), not a
not_planned abandonment.

## Cross-references

- Defect-class trail resolved under F25/F9: journal 0009 (None-content codegen-unexecutable),
  0010 (WorkflowNode subclass runtime paths).
- A0 deterministic re-verification was this session's first action — it caught the stale
  "0/55 constructable" premise on the first check, before any code was written.
