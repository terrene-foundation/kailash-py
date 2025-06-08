# Mistake 064: MCP Client as Separate Node

## Description
Creating MCPClient as a registered node forced users to manually orchestrate complex multi-node workflows for simple MCP interactions. This violated the principle of making the SDK intuitive and resulted in 5+ node workflows where 1-2 nodes would suffice.

## What Happened
```python
# Users had to create complex workflows like this:
workflow.add_node("mcp_server", AIRegistryMCPServerNode())
workflow.add_node("mcp_client", MCPClient())  # Unnecessary complexity
workflow.add_node("strategic_analyzer", PythonCodeNode())  # Manual orchestration
workflow.add_node("prompt_retriever", PythonCodeNode())  # More manual work
workflow.add_node("llm_agent", LLMAgentNode())
workflow.add_node("report_generator", PythonCodeNode())

# With 6+ connections required
workflow.connect("mcp_server", "mcp_client")
workflow.connect("mcp_client", "strategic_analyzer")
# ... many more connections
```

## Root Cause
1. **Protocol exposure** - Exposed low-level protocol details as user-facing API
2. **Separation of concerns taken too far** - Made protocol client a separate node instead of internal utility
3. **Missing integration** - LLMAgentNode didn't have built-in MCP capabilities
4. **Manual orchestration** - Required users to manually connect protocol operations

## Why This Is Wrong
1. **Unnecessary complexity** - Simple use cases required complex workflows
2. **Poor abstraction** - Users shouldn't need to understand MCP protocol details
3. **Unnatural flow** - Separates agent intelligence from tool usage
4. **Error-prone** - Multiple connection points increase chance of mistakes

## Correct Approach
```python
# MCPClient should be internal utility
# LLMAgentNode should have built-in MCP capabilities
workflow.add_node("ai_consultant", LLMAgentNode(),
    provider="ollama",
    model="llama3.2",
    mcp_servers=["http://localhost:8080/ai-registry"],  # Simple!
    auto_discover_tools=True
)
# That's it - agent handles everything internally
```

## Key Lessons
1. **Hide protocol details** - Protocols should be implementation details, not user APIs
2. **Integrate related functionality** - If features are always used together, integrate them
3. **Simplify common patterns** - Make the common case simple, allow complexity when needed
4. **Think like users** - "AI agent with tools" is more natural than "protocol client + agent + orchestration"

## Related Patterns
- Similar to HTTP clients - you don't create a separate HTTPClient node
- Like database connections - handled internally by data nodes
- Follows "batteries included" philosophy

## Prevention
1. **User journey mapping** - Map out user workflows before creating nodes
2. **Integration over separation** - Default to integration, separate only when necessary
3. **Protocol abstraction** - Always hide protocol details behind domain concepts
4. **Simplicity metrics** - Count nodes/connections required for common tasks

## Code Smells That Led to This
```python
# 1. Node that's always used with another node
workflow.add_node("client", MCPClient())  # Always used with LLMAgent

# 2. Manual protocol orchestration
workflow.add_node("tool_executor", PythonCodeNode(), code="""
    # Manually calling MCP endpoints
    # Should be automatic
""")

# 3. Too many nodes for simple task
# If "talk to AI with tools" requires 5+ nodes, something's wrong
```

## Impact
- **High** - Affected all MCP-related workflows
- **User confusion** - Multiple support questions about MCP setup
- **Adoption barrier** - Complex examples discouraged MCP usage

## Migration Path
1. Make MCPClient internal utility class
2. Add MCP capabilities to LLMAgentNode
3. Provide migration examples
4. Add deprecation warnings
5. Update all documentation

## Timestamp
- **Identified**: 2025-01-07 (Session 54)
- **Context**: User feedback on AI strategy consultant example
- **Fixed**: ADR-0038 MCP Client Internalization Architecture
