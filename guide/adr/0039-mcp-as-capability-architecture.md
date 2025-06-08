# ADR-0039: MCP as Capability Architecture

## Status
Proposed

## Context

The current MCP (Model Context Protocol) implementation in Kailash has several architectural issues:

1. **Confusing Node Architecture**: MCP is implemented as both nodes (MCPClient, MCPServer) and utilities, creating confusion
2. **Improper Server Implementation**: MCPServer is implemented as a node, but MCP servers need to run as long-lived services
3. **Tight Coupling**: IterativeLLMAgentNode inherits from LLMAgentNode and directly uses internal MCP utilities
4. **Poor User Experience**: Workflows become complex with separate MCP nodes when most use cases just need agents with MCP capabilities

Our workflows primarily revolve around LLM agents that use MCP to discover and iterate on server responses. The current node-based approach adds unnecessary complexity.

## Decision

We will redesign MCP integration as a **capability** rather than standalone nodes:

1. **MCP as Built-in Capability**: LLM agents will have MCP functionality built-in via optional parameters
2. **No Separate MCP Nodes**: Remove MCPClient and MCPServer nodes from the node hierarchy
3. **MCP Service Layer**: Implement MCP client/server functionality as services using the official Anthropic SDK
4. **Rare Node Usage**: For rare cases needing standalone MCP operations, provide a mixin or use PythonCodeNode

### Architecture Overview

```
src/kailash/
├── mcp/                        # MCP service layer
│   ├── __init__.py
│   ├── client.py              # MCP client using official SDK
│   ├── server.py              # MCP server runner framework
│   └── servers/               # Pre-built MCP servers
│       ├── __init__.py
│       ├── filesystem.py
│       ├── database.py
│       └── ai_registry.py
├── nodes/
│   ├── ai/
│   │   ├── llm_agent.py       # Enhanced with MCP capabilities
│   │   └── iterative_llm_agent.py
│   └── mixins/
│       └── mcp.py             # MCP mixin for rare node usage
```

### Design Principles

1. **Progressive Disclosure**: Simple use cases are simple, complex ones are possible
2. **Human-Readable Workflows**: MCP complexity is hidden inside agents
3. **Capability over Component**: MCP is a capability of agents, not a separate component
4. **SDK Compliance**: Use official Anthropic MCP Python SDK throughout

## Consequences

### Positive

1. **Improved User Experience**: Workflows become simpler and more intuitive
2. **Better Alignment**: Matches how users think about agent capabilities
3. **Cleaner Architecture**: Clear separation between MCP services and node functionality
4. **Easier Maintenance**: MCP implementation isolated in service layer
5. **SDK Compliance**: Proper use of official Anthropic MCP SDK

### Negative

1. **Breaking Change**: Existing workflows using MCPClient/MCPServer nodes will need updates
2. **Less Explicit**: MCP usage is less visible in workflow definitions
3. **Learning Curve**: Users need to understand new MCP parameters on agents

### Neutral

1. **Migration Path**: Need to provide clear migration guide for existing users
2. **Documentation**: Requires comprehensive documentation of MCP capabilities
3. **Testing**: Need new test patterns for embedded MCP functionality

## Implementation Plan

### Phase 1: MCP Service Layer (Week 1)
- Implement MCP client using official SDK
- Create MCP server runner framework
- Build example servers (filesystem, AI registry)

### Phase 2: LLM Agent Enhancement (Week 1-2)
- Add MCP parameters to LLMAgentNode
- Implement MCP discovery and tool execution
- Update IterativeLLMAgentNode for MCP iteration

### Phase 3: Migration Support (Week 2)
- Create migration guide
- Update all examples
- Add deprecation warnings to old nodes

### Phase 4: Testing and Documentation (Week 2-3)
- Comprehensive testing of MCP capabilities
- Update all documentation
- Create new workflow examples

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [Anthropic MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [ADR-0024: LLM Agent Architecture](./0024-llm-agent-architecture.md)
- [ADR-0038: Iterative MCP Agent Architecture](./0038-iterative-mcp-agent-architecture.md)
