# DECISION: Codification Scope for 23-Issue Sprint

## What was codified

3 new project skills capturing the major capability additions:

1. **pact-enforcement-modes.md** — ENFORCE/SHADOW/DISABLED modes, envelope adapter, HELD verdicts
2. **fabric-cache-consumers.md** — Cache control, consumer adapters, MCP tools, fabric-only mode
3. **dataflow-provenance-audit.md** — Provenance[T] type, audit trail persistence

## What was proposed upstream

6 changes in `.claude/.proposals/latest.yaml`:

- 3 new skills (coc-py tier — Python-specific patterns)
- 3 existing skill updates needed at loom/ (coc tier — language-agnostic concepts)

## Why these and not more

The 23 issues span 5 packages but cluster into 3 knowledge domains:

- PACT governance (9 issues → 1 skill)
- DataFlow quality (3 issues → 1 skill)
- Fabric engine (8 issues → 1 skill)

Nexus (#233) and governance (#231) are smaller — their patterns are adequately captured in the existing Nexus and PACT skills with the proposed updates.

## For Discussion

1. Should the enforcement modes skill be coc (language-agnostic) since kailash-rs needs the same pattern?
2. The consumer adapter pattern is generic enough for coc tier — is the Python-specific API shape important enough to keep at coc-py?
