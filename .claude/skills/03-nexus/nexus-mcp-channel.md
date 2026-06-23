---
skill: nexus-mcp-channel
description: MCP (Model Context Protocol) tool exposure and AI agent integration patterns
priority: HIGH
tags: [nexus, mcp, ai-agents, tool-discovery, integration]
---

# Nexus MCP Channel

AI agent integration via Model Context Protocol (MCP).

## What is MCP?

MCP (Model Context Protocol) exposes workflows as discoverable tools for AI agents like Claude, ChatGPT, and custom agents. Nexus runs an MCP server alongside the API server -- any registered workflow becomes an MCP tool automatically.

## Basic Setup

```
app = Nexus(mcp_port=3001)

# Workflows automatically become MCP tools
app.register("github-lookup", workflow.build())

app.start()
# AI agents can now discover "github-lookup" on localhost:3001
```

## Tool Discovery

MCP clients discover tools automatically. Each registered workflow appears with its name and schema:

```json
{
  "tools": [
    {
      "name": "github-lookup",
      "description": "Look up GitHub user information",
      "input_schema": {
        "type": "object",
        "properties": {
          "username": {
            "type": "string",
            "description": "GitHub username"
          }
        },
        "required": ["username"]
      }
    }
  ]
}
```

## Tool Metadata

Add metadata to workflows for better AI discovery and understanding. Metadata includes tool name, description, parameter descriptions, and return type documentation.

The exact API for adding metadata varies by SDK (WorkflowBuilder metadata methods, handler descriptions, etc.). See language-specific variant for metadata API.

## MCP Client Usage

```json
{
  "method": "tools/call",
  "params": {
    "name": "github-lookup",
    "arguments": { "username": "octocat" }
  }
}
```

## MCP Port Configuration

```
app = Nexus(mcp_port=3001)
```

The MCP server starts alongside the API server. Default port is 3001.

## MCP Transport

Nexus MCP supports bidirectional communication via `receive_message()` for custom MCP transports.

## Best Practices

1. **Add rich descriptions** -- AI agents rely on descriptions to understand when and how to use tools
2. **Use clear parameter names** -- descriptive names help AI agents construct correct calls
3. **Structure outputs** -- return well-structured data (dicts/maps) for easy AI parsing
4. **Include metadata** -- descriptions, parameter docs, and return type docs improve tool discovery
5. **Handle errors gracefully** -- return structured error information rather than raw exceptions
6. **Provide examples** -- include usage examples in descriptions where applicable

## Key Takeaways

- Workflows automatically become MCP tools on registration
- AI agents discover and execute tools via the MCP protocol
- MCP server runs on a separate port (default 3001) alongside the API server
- Tool metadata improves AI agent integration quality
- Same workflow is accessible via API, CLI, and MCP simultaneously

See language-specific variant for metadata API, MCP configuration options, and structured output examples.

## Related Skills

- [nexus-multi-channel](nexus-multi-channel.md) - MCP, API, CLI overview
- [nexus-api-patterns](nexus-api-patterns.md) - REST API usage
- [nexus-enterprise-features](nexus-enterprise-features.md) - Auth for MCP
