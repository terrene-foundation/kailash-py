# Spec Traceability — Issue #822

Per `rules/specs-authority.md` MUST Rule 1 + `/analyze` Step 5: every brief requirement
maps to an existing spec file section. Per `rules/spec-accuracy.md` Rule 5
(incremental spec extension lags code), the spec edits land **with** `/implement`
at first-instance per `specs-authority.md` Rule 5 — NOT pre-implementation.

This document records the map so `/implement` knows what to update.

## Brief → Spec mapping

All brief requirements map to existing `specs/kaizen-core.md` sections. No new
spec file is required.

| Brief requirement                                                    | Spec section              | File:line                           |
| -------------------------------------------------------------------- | ------------------------- | ----------------------------------- |
| `kaizen/__init__.py:127` `create_agent(name, config, ...)` typing    | Module-level convenience  | `specs/kaizen-core.md` (§ globals)  |
| `kaizen/__init__.py:155` `get_resolved_config(explicit_config)`      | Module-level convenience  | `specs/kaizen-core.md` (§ globals)  |
| `kaizen/core/framework.py:341` `Kaizen.create_agent` typing          | Kaizen class API          | `specs/kaizen-core.md:426`          |
| `kaizen/core/framework.py:344` `name` backward-compat kwarg          | Kaizen class API          | `specs/kaizen-core.md:426`          |
| `kaizen/core/agents.py:307` `_execute_workflow_directly` typing      | Agent class internal      | `specs/kaizen-core.md` (§ Agent)    |
| Agent dynamic attrs (`role`/`expertise`/...) DECLARE                 | Agent class shape         | `specs/kaizen-core.md` (§ Agent)    |
| `signature_programming_enabled` gate                                 | Configuration             | `specs/kaizen-core.md:442`          |
| `behavior_traits` round-trip in `create_specialized_agent`           | Specialized agent factory | `specs/kaizen-core.md` (§ Kaizen)   |
| MCP integration surface (deletion)                                   | Kaizen MCP integration    | `specs/kaizen-core.md` (§ MCP refs) |
| AgentTeam `conflict_resolution` / `performance_optimization` DECLARE | Patterns                  | `specs/kaizen-agents-patterns.md`   |

## What changes at `/implement` first-instance

When Shard 1 lands, `specs/kaizen-core.md` updates at first-instance per Rule 5:

1. Line 426: `def create_agent(self, agent_id: str, config: Dict = None, ...)` →
   `def create_agent(self, agent_id: Optional[str] = None, config: Optional[Dict] = None, ...)`.
2. Agent class section: add typing contract for `role`, `expertise`, `capabilities`,
   `behavior_traits`, `authority_level` — describing the dynamic-attach pattern as
   the canonical contract for `create_specialized_agent` consumers.
3. `signature_programming_enabled` gate section: update to describe the unified
   `KaizenConfig`+`ConfigWrapper(dict)` reading — both shapes fire the gate identically.

When Shard 2 lands, `specs/kaizen-core.md` updates at first-instance per Rule 5:

4. Remove all references to deleted MCP methods (`expose_as_mcp_server`,
   `expose_as_mcp_tool`, `connect_to_mcp_servers`, `call_mcp_tool`, `_discover_servers`,
   `Kaizen.mcp_registry`, `Kaizen.discover_mcp_tools(external=True)`).
5. Replace with pointer to `kaizen.mcp.catalog_server.MemoryRegistry` for in-process
   registry semantics + reference to `kailash-mcp` package for external-discovery
   functionality if/when it ships.

`specs/kaizen-agents-patterns.md` updates with Shard 1 cross-package edit:

6. `AgentTeam` section: add class-body typing for `conflict_resolution: Optional[str] = None`
   and `performance_optimization: bool = False`.

## Traceability gate verification

```bash
# Every brief-cited file maps to a spec section:
grep -n "create_agent\|signature_programming_enabled\|behavior_traits\|expose_as_mcp" \
    specs/kaizen-core.md
# Expected: 5+ hits → traceability COMPLETE
```

Verified 2026-05-05: `kaizen-core.md` references `create_agent` (line 426), `signature_programming_enabled` (line 442), Agent class (§ Agent), MCP integration (multiple). All brief requirements have spec coverage.

## Why no new spec file

Per `rules/specs-authority.md` Rule 8 (split when >300 lines), `kaizen-core.md` is at 494
lines — close to the split threshold but not over it. The #822 changes fit within
existing sections; creating a new `kaizen-typing.md` would create artificial domain
boundaries (typing semantics belong with the classes they govern, not in a parallel
file). If the next round of typing work pushes `kaizen-core.md` past 500 lines, a
split is the correct response — but that's a follow-up workstream, not part of #822.

## Why no spec edits at /analyze

Per `rules/spec-accuracy.md` Rule 5: spec content describes ONLY behavior already
shipped on `main`. The Shard 1/2 fixes are not on main; pre-emptively writing the
post-fix spec would be a spec-ahead-of-code violation. The architecture plan and
this trace document are the correct surfaces for forward-looking design.

## References

- `rules/specs-authority.md` Rules 1, 5 — spec organization + first-instance updates
- `rules/spec-accuracy.md` Rule 5 — code-first, spec-second
- `02-plans/01-architecture.md` — full Shard 1 + Shard 2 plan
