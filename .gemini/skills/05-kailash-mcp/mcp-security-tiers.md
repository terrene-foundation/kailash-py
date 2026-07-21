---
name: mcp-security-tiers
description: "MCP platform server security tier system (T1-T4), env var controls, tier escalation. Use when asking 'mcp security', 'mcp tiers', 'mcp permissions', 'execution tier', or 'mcp access control'."
---

# MCP Security Tiers

The kailash-mcp platform server uses a 4-tier security model that controls which tools are available based on environment variable configuration. Tiers are cumulative -- higher tiers include progressively more powerful operations.

> **Skill Metadata**
> Category: `mcp`
> Priority: `HIGH`
> SDK Version: `0.9.25+`
> Related Skills: [`mcp-platform-overview`](mcp-platform-overview.md), [`mcp-tool-catalog`](mcp-tool-catalog.md), [`mcp-contributor-pattern`](mcp-contributor-pattern.md)
> Related Subagents: `mcp-platform-specialist` (security configuration, tier escalation)

## Tier Overview

| Tier | Name              | Default   | Operations                                   | Risk Level                      |
| ---- | ----------------- | --------- | -------------------------------------------- | ------------------------------- |
| T1   | **INTROSPECTION** | Always on | List, describe, query                        | None -- read-only discovery     |
| T2   | **SCAFFOLD**      | Always on | Generate code, create files                  | Low -- produces code for review |
| T3   | **VALIDATION**    | On        | Validate structures, check correctness       | Low -- reads and analyzes       |
| T4   | **EXECUTION**     | **Off**   | Run code in subprocess, test handlers/agents | Medium -- executes user code    |

**Why this default?** T1-T3 are safe for unattended operation -- they read files, generate code for review, and validate structures. T4 executes user code in subprocesses, which could trigger side effects (database writes, API calls, file mutations). Requiring explicit opt-in for T4 prevents accidental execution.

## Tier Details

### Tier 1: INTROSPECTION (Always Enabled)

Read-only discovery of project artifacts. No side effects possible.

**Operations**: List items, describe items, query metadata, get versions, read status.

**Tools in this tier**:

- `core.list_node_types`, `core.list_node_categories`, `core.describe_node`, `core.get_sdk_version`
- `platform.platform_map`, `platform.project_info`
- `dataflow.list_models`, `dataflow.describe_model`, `dataflow.query_schema`
- `nexus.list_handlers`, `nexus.list_channels`
- `kaizen.list_agents`, `kaizen.describe_agent`
- `trust.trust_status`
- `pact.org_tree`

**Cannot be disabled.** These tools are the foundation of project introspection.

### Tier 2: SCAFFOLD (Always Enabled)

Code generation and test scaffolding. Produces code strings in tool responses -- does not write files.

**Operations**: Generate model/handler/agent definitions, generate test scaffolds.

**Tools in this tier**:

- `dataflow.scaffold_model`, `dataflow.generate_tests`
- `nexus.scaffold_handler`, `nexus.generate_tests`
- `kaizen.scaffold_agent`, `kaizen.generate_tests`

**Cannot be disabled.** Scaffold tools return code as strings in the response. The MCP client decides whether to write the code to disk. The server itself makes no filesystem changes.

**Why always enabled?** Generated code is reviewed by the agent and user before being applied. There is no risk in producing code -- only in executing it.

### Tier 3: VALIDATION (Enabled by Default)

Structural validation of project artifacts against known rules.

**Operations**: Validate model definitions, validate handler definitions, validate workflow JSON.

**Tools in this tier**:

- `core.validate_workflow`
- `dataflow.validate_model`
- `nexus.validate_handler`

**Controlled by**: `KAILASH_MCP_ENABLE_VALIDATION`

```bash
# Enabled by default. To disable:
export KAILASH_MCP_ENABLE_VALIDATION=false
```

**Why enabled by default?** Validation is read-only analysis -- it checks structures against rules without modifying anything. Disabling is available for environments where even analysis overhead is unwanted.

### Tier 4: EXECUTION (Disabled by Default)

Runs user code in isolated subprocesses. The only tier that can trigger side effects.

**Operations**: Execute handlers with test input, run agent tasks.

**Tools in this tier**:

- `nexus.test_handler` (30s timeout)
- `kaizen.test_agent` (60s timeout)

**Controlled by**: `KAILASH_MCP_ENABLE_EXECUTION`

```bash
# Disabled by default. To enable:
export KAILASH_MCP_ENABLE_EXECUTION=true
```

**Isolation guarantees**:

- User code runs in a **separate subprocess** (not imported into the server process)
- Subprocess has a **hard timeout** (30s for handlers, 60s for agents)
- Subprocess inherits `PYTHONPATH` pointing to project root
- Subprocess output is captured and parsed as JSON

**Why disabled by default?** Executing user code can:

- Write to databases (if `DATABASE_URL` is set in the environment)
- Make API calls (if API keys are in the environment)
- Modify the filesystem
- Consume resources (CPU, memory, network)

Requiring explicit opt-in ensures that execution only happens in environments where the operator understands these risks.

## Environment Variable Reference

| Variable                        | Values         | Default         | Effect                |
| ------------------------------- | -------------- | --------------- | --------------------- |
| `KAILASH_MCP_ENABLE_VALIDATION` | `true`/`false` | `true`          | Controls Tier 3 tools |
| `KAILASH_MCP_ENABLE_EXECUTION`  | `true`/`false` | `false` (empty) | Controls Tier 4 tools |

## Implementation

The tier system is implemented in `kailash.mcp.contrib.__init__`:

```python
class SecurityTier(enum.IntEnum):
    INTROSPECTION = 1
    SCAFFOLD = 2
    VALIDATION = 3
    EXECUTION = 4


def is_tier_enabled(tier: SecurityTier) -> bool:
    """Check if the given security tier is enabled."""
    if tier <= SecurityTier.SCAFFOLD:
        return True  # Always enabled
    if tier == SecurityTier.VALIDATION:
        return os.environ.get("KAILASH_MCP_ENABLE_VALIDATION", "true").lower() != "false"
    if tier == SecurityTier.EXECUTION:
        return os.environ.get("KAILASH_MCP_ENABLE_EXECUTION", "").lower() == "true"
    return False
```

Contributors check `is_tier_enabled` at registration time to conditionally register higher-tier tools:

```python
def register_tools(server, project_root, namespace):
    # T1 and T2 tools always registered
    @server.tool(name=f"{namespace}.list_things")
    async def list_things() -> dict: ...

    # T3 tools: gated
    if is_tier_enabled(SecurityTier.VALIDATION):
        @server.tool(name=f"{namespace}.validate_thing")
        async def validate_thing(name: str) -> dict: ...

    # T4 tools: gated
    if is_tier_enabled(SecurityTier.EXECUTION):
        @server.tool(name=f"{namespace}.test_thing")
        async def test_thing(name: str) -> dict: ...
```

**Why check at registration time instead of call time?** Tools that are not registered do not appear in the MCP tool listing. This means agents cannot attempt to call disabled tools, eliminating an entire class of "permission denied" errors.

## Tier Escalation for Agents

When an agent needs a higher tier than currently enabled, it should:

1. **Report what it needs and why** -- not attempt to enable the tier itself
2. **Suggest the env var change** to the human operator
3. **Proceed with lower-tier alternatives** if possible

```
Agent: "I'd like to verify the handler works by running it, but
execution tools are disabled. To enable them, set
KAILASH_MCP_ENABLE_EXECUTION=true and restart the MCP server.

In the meantime, I can validate the handler structure (Tier 3)
and generate test code (Tier 2) for you to run manually."
```

**Why agents should not self-escalate:** Tier boundaries are operator decisions. An agent enabling execution on its own bypasses the operator's security posture.

## Configuration by Environment

| Environment                  | Recommended Tiers | Rationale                                |
| ---------------------------- | ----------------- | ---------------------------------------- |
| **Local development**        | T1-T3 (default)   | Safe introspection and validation        |
| **Local with testing**       | T1-T4             | Enable execution for interactive testing |
| **Shared CI server**         | T1-T2 only        | Disable validation overhead in CI        |
| **Production introspection** | T1 only           | Minimal surface area                     |

```bash
# Local development (default)
kailash-mcp --project-root .

# Local with execution enabled
KAILASH_MCP_ENABLE_EXECUTION=true kailash-mcp --project-root .

# CI: validation disabled for speed
KAILASH_MCP_ENABLE_VALIDATION=false kailash-mcp --project-root .
```

## Quick Tips

- T1-T2 are always on and cannot be disabled -- design your contributor accordingly
- T3 validation tools are read-only analysis -- safe for almost all environments
- T4 execution tools run in subprocesses with hard timeouts -- they cannot hang the server
- Check `is_tier_enabled` at registration time, not call time
- Missing tier tools do not appear in MCP tool listings -- agents never see them

## When to Escalate to Subagent

Use `mcp-platform-specialist` when:

- Designing custom tier boundaries for a new contributor
- Implementing subprocess isolation for Tier 4 tools
- Configuring security tiers in production environments
- Debugging tools that appear/disappear unexpectedly (check env vars)

<!-- Trigger Keywords: mcp security, mcp tiers, mcp permissions, execution tier, mcp access control, security tier, tier escalation, mcp environment variables -->
