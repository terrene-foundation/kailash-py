---
type: RISK
date: 2026-04-20
created_at: 2026-04-20T07:56:32.459Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: specs/mcp-server.md §4.9 ElicitationSystem was a 2-line placeholder violating specs-authority MUST Rule 3
phase: implement
tags:
  [auto-generated, kailash-mcp, specs, elicitation, spec-completeness, shard-d]
related_journal: [0011-DISCOVERY-mcp-spec-sibling-sweep-shard-d.md]
---

# RISK — mcp-server.md §4.9 ElicitationSystem was a 2-line placeholder

## Commit

`9c63133573ef` — docs(mcp): expand specs/mcp-server.md §4.9 ElicitationSystem contract (#556, shard-D)

## Body

The §4.9 `ElicitationSystem` section was a 2-line placeholder that violated `rules/specs-authority.md` MUST Rule 3 (spec files are detailed, not summaries). Expanded to ~105 lines covering:

- Two-half architecture (send + receive) with wiring to production call site
- Construction contract (`ElicitationSystem(send=...)` and `bind_transport()`)
- `request_input` / `provide_input` semantics including timeout + validation
- JSON-RPC wire shape for MCP 2025-06-18 `elicitation/create`
- Server dispatch wiring (`MCPServer.elicitation_system` as public attribute)
- Error taxonomy (`MCPError(INVALID_REQUEST)`, `MCPError(REQUEST_TIMEOUT)`, `MCPError(REQUEST_CANCELLED)`, `ValidationError`)
- Security requirement: schema validation MUST run before returning to caller

Sibling-spec sweep (`rules/specs-authority.md` MUST 5b) recorded in journal 0011 — 0 findings across `mcp-client.md` + `mcp-auth.md`. The expanded surface is orthogonal to client-side and auth concerns; no cross-spec drift.

**Risk**: a 2-line spec placeholder for a production-wired subsystem means any session working on MCP tools that call `request_input` had no authoritative reference for the error taxonomy, timeout semantics, or security requirements. That session would have had to infer the contract from source code — which is the failure mode `rules/specs-authority.md` exists to prevent.

## For Discussion

1. **Counterfactual**: The spec placeholder existed from when `ElicitationSystem` was first introduced as a stub. Between the stub landing and this spec expansion, if a second agent had been tasked with writing MCP tool tests that exercise `request_input`, what incorrect assumptions about error types or timeout behavior would the agent have made based on the 2-line placeholder — and how would those tests have broken when the real implementation landed?

2. **Data-referenced**: The expanded spec is ~105 lines for a single subsystem (§4.9 of `mcp-server.md`). The full `mcp-server.md` file presumably covers many subsystems. Per `rules/specs-authority.md` MUST Rule 8, spec files exceeding 300 lines must be split. Did the §4.9 expansion push `mcp-server.md` over 300 lines, and if so, was the split deferred or executed in this session?

3. **Pattern**: This is the second case in this session where a spec was found to be a placeholder for a production-wired feature (the other being `specs/ml-engines.md` §12.1 stale phase-status in 0016). Both were caught by the post-release reviewer. Is there a structural hook or CI check that could detect spec sections below a minimum line count threshold for subsystems that have corresponding production code, or does this require reviewer judgment?
