# Agent Orchestration Rules

## Specialist Delegation (MUST)

When working with Kailash frameworks, MUST consult the relevant specialist:

- **dataflow-specialist**: Database or DataFlow work
- **nexus-specialist**: API or deployment work
- **kaizen-specialist**: AI agent work
- **mcp-specialist**: MCP integration work
- **pact-specialist**: Organizational governance work

**Applies when**: Creating workflows, modifying DB models, setting up endpoints, building agents, implementing governance.

## Analysis Chain (Complex Features)

1. **analyst** → Identify failure points
2. **analyst** → Break down requirements
3. **`decide-framework` skill** → Choose approach
4. Then appropriate specialist

**Applies when**: Feature spans multiple files, unclear requirements, multiple valid approaches.

## Parallel Execution

When multiple independent operations are needed, launch agents in parallel using Task tool, wait for all, aggregate results. MUST NOT run sequentially when parallel is possible.

## Quality Gates (MUST — Gate-Level Review)

Reviews happen at COC phase boundaries, not per-edit. Skip only when explicitly told to.

| Gate                | After Phase  | Review                                                                                     |
| ------------------- | ------------ | ------------------------------------------------------------------------------------------ |
| Analysis complete   | `/analyze`   | **reviewer**: Are findings complete? Gaps?                                    |
| Plan approved       | `/todos`     | **reviewer**: Does plan cover requirements?                                   |
| Implementation done | `/implement` | **reviewer**: Code review all changes. **security-reviewer**: Security audit. |
| Validation passed   | `/redteam`   | **reviewer**: Are red team findings addressed?                                |
| Knowledge captured  | `/codify`    | **gold-standards-validator**: Naming, licensing compliance.                                |

## Zero-Tolerance

Pre-existing failures MUST be fixed (see `rules/zero-tolerance.md` Rule 1). No workarounds for SDK bugs — deep dive and fix directly (Rule 4).

## MUST NOT

- Framework work without specialist
- Sequential when parallel is possible
- Raw SQL when DataFlow exists
- Custom API when Nexus exists
- Custom agents when Kaizen exists
- Custom governance when PACT exists
