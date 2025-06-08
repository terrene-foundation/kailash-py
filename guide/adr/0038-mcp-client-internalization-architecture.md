# ADR-0038: MCP Client Internalization Architecture

## Status
Proposed

## Context

The current MCP (Model Context Protocol) implementation exposes MCPClient as a separate node, requiring users to manually orchestrate connections between MCP servers, clients, and LLM agents. This creates unnecessarily complex workflows and goes against the principle of making the SDK intuitive and easy to use.

Real-world usage patterns show that:
1. MCPClient is almost always used in conjunction with LLMAgentNode
2. Users struggle with the multi-node orchestration required for simple MCP interactions
3. The protocol-level details of MCP should be abstracted away from users
4. Intelligent MCP servers with built-in AI capabilities are becoming more common

## Decision

We will refactor the MCP architecture to:

1. **Remove MCPClient as a registered node** and make it an internal utility class
2. **Enhance LLMAgentNode** with built-in MCP client capabilities
3. **Create IntelligentMCPServerNode** pattern for servers with integrated AI
4. **Simplify workflow patterns** from 5+ nodes to 1-2 nodes for common use cases

### Architecture Changes

#### Before (Current Architecture)
```python
# Complex multi-node workflow
workflow.add_node("server", AIRegistryMCPServerNode())
workflow.add_node("client", MCPClient())  # Separate protocol node
workflow.add_node("analyzer", PythonCodeNode())
workflow.add_node("llm", LLMAgentNode())
workflow.add_node("report", PythonCodeNode())

# Multiple connections required
workflow.connect("server", "client")
workflow.connect("client", "analyzer")
# ... many more connections
```

#### After (New Architecture)
```python
# Simple single-node workflow
workflow.add_node("ai_consultant", LLMAgentNode(),
    provider="ollama",
    model="llama3.2",
    mcp_servers=["http://localhost:8080/ai-registry"],
    auto_discover_tools=True
)
# That's it - agent handles everything internally
```

### Technical Design

#### 1. Internal MCP Client Structure
```
src/kailash/
├── utils/                     # Internal utilities (not nodes)
│   └── mcp/
│       ├── client.py          # MCPClient class (no @register_node)
│       ├── protocol.py        # MCP protocol helpers
│       └── mixins.py          # Intelligent server mixins
└── nodes/
    ├── mcp/
    │   └── server.py          # MCP server nodes only
    └── ai/
        └── llm_agent.py       # Enhanced with internal MCP client
```

#### 2. Enhanced LLMAgentNode API
```python
@register_node()
class LLMAgentNode(AsyncNode):
    """AI Agent with built-in MCP capabilities."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            # Existing parameters...
            "mcp_servers": NodeParameter(
                type=list,
                required=False,
                default=[],
                description="List of MCP server URLs or configurations"
            ),
            "auto_discover_tools": NodeParameter(
                type=bool,
                required=False,
                default=True,
                description="Automatically discover and use MCP tools"
            ),
            "delegation_mode": NodeParameter(
                type=bool,
                required=False,
                default=False,
                description="Prefer delegating complex queries to intelligent servers"
            ),
        }
```

#### 3. MCP Tool Integration Flow
```
User Query → LLMAgent
    → Discovers MCP tools at initialization
    → Converts MCP tools to LLM function definitions
    → LLM decides which tools to call
    → Agent executes MCP tool calls internally
    → Returns synthesized response
```

#### 4. Intelligent Server Pattern
```python
@register_node()
class IntelligentAIRegistryMCPServerNode(AIRegistryMCPServerNode):
    """MCP Server with built-in AI for intelligent query processing."""

    def __init__(self, llm_provider: str = "ollama", llm_model: str = "llama3.2"):
        super().__init__()
        self.llm_agent = self._create_internal_agent(llm_provider, llm_model)

    def setup_service(self):
        super().setup_service()
        # Add intelligent analysis tools
        self.register_tool("intelligent_analysis", self._intelligent_analysis)
```

## Consequences

### Positive
- **Simplified API** - Users work with familiar LLMAgent pattern
- **Reduced complexity** - 5+ node workflows become 1-2 nodes
- **Better abstraction** - Protocol details hidden from users
- **Intuitive patterns** - "AI agent with tools" is a natural concept
- **Backward compatible** - Existing MCPClient code continues to work with deprecation warning

### Negative
- **Breaking change** - MCPClient no longer available as a node
- **Migration required** - Existing workflows need updating
- **Less flexibility** - Advanced users lose fine-grained control
- **Hidden complexity** - Debugging MCP issues may be harder

### Mitigation
- Provide comprehensive migration guide
- Keep MCPClient available internally for advanced use cases
- Add detailed logging for MCP operations
- Create examples showing both simple and advanced patterns

## Implementation Plan

### Phase 1: Foundation (2 hours)
- Restructure files to utils package
- Remove node registration from MCPClient
- Create protocol helpers and mixins

### Phase 2: LLMAgent Enhancement (3 hours)
- Add MCP parameters to LLMAgentNode
- Implement tool discovery and conversion
- Add function calling integration

### Phase 3: Intelligent Servers (2 hours)
- Create IntelligentMCPServerMixin
- Implement IntelligentAIRegistryMCPServerNode
- Add composite analysis tools

### Phase 4: Examples & Testing (2 hours)
- Create simplified example workflows
- Add comprehensive tests
- Update existing examples

### Phase 5: Documentation (1 hour)
- Update API documentation
- Create migration guide
- Update tutorials

## References
- ADR-0022: MCP Integration Architecture (original design)
- ADR-0026: Unified AI Provider Architecture (AI agent patterns)
- Model Context Protocol Specification
- User feedback on workflow complexity

## Decision Records
- **Date**: 2025-01-07
- **Deciders**: Development team based on user feedback
- **Outcome**: Proceed with internalization of MCPClient
