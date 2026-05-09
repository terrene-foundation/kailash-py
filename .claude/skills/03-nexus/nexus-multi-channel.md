---
skill: nexus-multi-channel
description: Nexus multi-channel architecture - single workflow, three interfaces (API/CLI/MCP)
priority: HIGH
tags: [nexus, multi-channel, api, cli, mcp, architecture]
---

# Nexus Multi-Channel Architecture

Register once, deploy to API + CLI + MCP automatically.

## Core Concept

Traditional platforms require separate implementations for each interface. Nexus generates all three from a single registration:

```
app = Nexus()
app.register("github-user", workflow.build())

# Now available as:
# 1. REST API: POST /workflows/github-user/execute
# 2. CLI: nexus run github-user --username octocat
# 3. MCP: AI agents discover as "github-user" tool
```

## Architecture

```
                    Nexus Core
  +-----------+  +-----------+  +-----------+
  |    API    |  |    CLI    |  |    MCP    |
  |  Channel  |  |  Channel  |  |  Channel  |
  +-----+-----+  +-----+-----+  +-----+-----+
        +---------------+---------------+
           Session Manager & Event Router
  +------------------------------------------+
  |          Enterprise Gateway              |
  +------------------------------------------+
  +------------------------------------------+
  |             Kailash SDK                  |
  |       Workflows | Nodes | Runtime        |
  +------------------------------------------+
```

## API Channel

Registered workflows get REST endpoints automatically:

```bash
# Execute workflow
curl -X POST http://localhost:8000/workflows/github-user/execute \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"username": "octocat"}}'

# Get workflow schema
curl http://localhost:8000/workflows/github-user/schema

# Health check
curl http://localhost:8000/health
```

## CLI Channel

Registered workflows become CLI commands:

```bash
# Execute workflow
nexus run github-user --username octocat

# List available workflows
nexus list

# Get workflow info
nexus info github-user
```

## MCP Channel

Workflows become MCP tools discoverable by AI agents:

```
app = Nexus(mcp_port=3001)
app.register("github-lookup", workflow.build())
# AI agents connect on port 3001 and discover "github-lookup" as a tool
```

## Cross-Channel Parameter Consistency

Same inputs work across all channels:

```
# API Request
{"inputs": {"username": "octocat", "include_repos": true}}

# CLI Command
nexus run github-user --username octocat --include-repos true

# MCP Call
{"name": "github-user", "arguments": {"username": "octocat", "include_repos": true}}
```

## Unified Sessions

Sessions work across all channels. A workflow started via API can be continued via CLI or MCP using the same session ID.

```
# API: start session
POST /workflows/process/execute
Headers: X-Session-ID: session-123
Body: {"inputs": {"step": 1}}

# CLI: continue same session
nexus run process --session session-123 --step 2

# MCP: complete with full state preserved
{"name": "process", "arguments": {"step": 3, "session_id": "session-123"}}
```

## Channel Configuration

Port configuration is shared:

```
app = Nexus(api_port=8000, mcp_port=3001)
```

Channel-specific configuration (CLI prompts, API compression, MCP caching) varies by SDK. See language-specific variant for channel configuration details.

## Best Practices

### 1. Channel-Agnostic Design

Design workflows that produce structured output usable by all channels. Avoid channel-specific logic in the workflow itself.

### 2. Progressive Enhancement

Start with basic registration, then add channel-specific features as needed:

```
app = Nexus()
app.register("workflow", workflow.build())
# API, CLI, MCP all work immediately
# Add auth, rate limiting, middleware progressively
```

### 3. Test All Channels

During development, verify your workflow works via API, CLI, and MCP. Parameters should behave identically across all three.

## Key Takeaways

- Single registration creates three interfaces automatically
- Same parameters work across all channels
- Unified session management across channels
- Test all channels during development
- Channel-specific configuration available per SDK

## Related Skills

- [nexus-api-patterns](nexus-api-patterns.md) - API usage patterns
- [nexus-cli-patterns](nexus-cli-patterns.md) - CLI command patterns
- [nexus-mcp-channel](nexus-mcp-channel.md) - MCP integration details
- [nexus-sessions](nexus-sessions.md) - Session management guide
