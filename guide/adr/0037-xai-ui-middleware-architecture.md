# ADR-0037: XAI-UI Middleware Architecture

## Status

Proposed

Date: 2025-06-07

## Context

The Kailash SDK currently has rudimentary frontend communication capabilities:
- Basic REST API endpoints in `studio.py`
- WebSocket support exists but is underutilized
- No standardized event system for agent-UI communication
- Limited real-time interaction capabilities
- No human-in-the-loop workflow support
- Mock implementations in frontend components

Meanwhile, the AG-UI Protocol has emerged as a standard for AI agent-frontend communication, offering:
- 16 standardized event types
- Bidirectional state synchronization
- Tool execution with approval workflows
- Generative UI capabilities
- Transport-agnostic design
- Sub-200ms latency performance

We need a middleware layer that provides these modern capabilities while maintaining Kailash SDK's architectural principles and coding standards.

## Decision

We will implement XAI-UI (eXplainable AI - User Interface) middleware as a comprehensive replacement for our current frontend communication system. XAI-UI will:

1. **Provide AG-UI feature parity** while following Kailash patterns
2. **Use event-driven architecture** with 16 standard event types
3. **Support multiple transports** (SSE, WebSocket, Webhook)
4. **Enable real-time state synchronization** using JSON Patch
5. **Implement human-in-the-loop workflows** with approval mechanisms
6. **Support generative UI** for dynamic interface generation
7. **Maintain explainability** as a core principle

The middleware will be implemented as a new package `src/kailash/xai_ui/` with:
- Event system and router
- Transport layer abstractions
- State management with delta updates
- Bridge nodes for workflow integration
- React hooks for frontend integration

## Rationale

### Why XAI-UI over direct AG-UI adoption?

1. **Kailash-native implementation**: Follows our coding standards (snake_case, Node suffix, etc.)
2. **Explainability focus**: XAI emphasizes transparency in AI decision-making
3. **Integrated with our architecture**: Works seamlessly with our node system
4. **Custom features**: Can add Kailash-specific capabilities beyond AG-UI

### Why event-driven architecture?

1. **Real-time requirements**: Workflow execution needs immediate feedback
2. **Scalability**: Event systems handle concurrent sessions well
3. **Flexibility**: Easy to add new event types and handlers
4. **Industry standard**: Proven pattern for agent-UI communication

### Why JSON Patch for state sync?

1. **Efficiency**: Only transmit changes, not full state
2. **Standard**: RFC 6902 is well-supported
3. **Performance**: Reduces bandwidth and latency
4. **Compatibility**: Works with React's state management

## Consequences

### Positive
- **Enhanced user experience**: Real-time feedback and rich interactions
- **Developer productivity**: Standardized patterns and reusable hooks
- **Future-proof**: Compatible with emerging AI frameworks
- **Performance**: Sub-200ms latency for responsive interactions
- **Extensibility**: Easy to add new event types and transports

### Negative
- **Migration effort**: Existing frontend code needs updates
- **Learning curve**: Developers need to understand event-driven patterns
- **Complexity**: More moving parts than simple REST APIs
- **Testing**: Requires new testing strategies for real-time features

### Neutral
- **Dependency on event streaming**: Requires stable connections
- **State management complexity**: Need to handle eventual consistency
- **Security considerations**: Real-time channels need proper auth

## Implementation Notes

### Phase 1: Core Infrastructure (Week 1)
- Event type definitions matching AG-UI's 16 types
- Event router with handler registration
- SSE transport implementation
- State manager with JSON Patch support
- XAIUIBridgeNode for workflow integration

### Phase 2: Frontend Integration (Week 2)
- React hooks (useXAIUI, useXAIAgent, etc.)
- WebSocket transport addition
- Update Studio components
- Tool execution UI components

### Phase 3: Agent Integration (Week 3)
- Update agent nodes to emit events
- Implement approval workflows
- Add generative UI support
- Enable media streaming

### Phase 4: Advanced Features (Week 4)
- Binary optimization for performance
- Monitoring and metrics
- Framework adapters
- Documentation and examples

### Key Design Patterns

```python
# Event emission pattern
async def emit_agent_message(self, message: str):
    event = XAIEvent(
        type=XAIEventType.TEXT_MESSAGE_CONTENT,
        session_id=self.session_id,
        text=message
    )
    await self.router.emit(event)

# State synchronization pattern
def update_state(self, updates: Dict[str, Any]):
    patch = self.state_manager.create_patch(self.session_id, updates)
    self.emit_state_delta(patch)

# Tool execution with approval
async def execute_with_approval(self, tool_name: str, args: Dict):
    if self.require_approval:
        approved = await self.request_approval(tool_name, args)
        if not approved:
            return None
    return await self.execute_tool(tool_name, args)
```

## Alternatives Considered

### Direct AG-UI Protocol Adoption
- **Rejected**: Would require significant changes to match Kailash patterns
- **Reason**: Need custom features and explainability focus

### GraphQL Subscriptions
- **Rejected**: More complex than needed
- **Reason**: SSE/WebSocket sufficient for our use cases

### Custom Protocol from Scratch
- **Rejected**: Would miss industry compatibility
- **Reason**: AG-UI patterns are proven and well-designed

### Minimal REST Enhancement
- **Rejected**: Doesn't meet real-time requirements
- **Reason**: Users need immediate feedback for agent interactions

## Related ADRs

- [ADR-0015: API Integration Architecture](0015-api-integration-architecture.md)
- [ADR-0019: Real-time Dashboard Architecture](0019-real-time-dashboard-architecture.md)
- [ADR-0033: Workflow Studio Multi-Tenant Architecture](0033-workflow-studio-multi-tenant-architecture.md)
- [ADR-0034: AI Assistant Architecture](0034-ai-assistant-architecture.md)

## References

- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)
- [JSON Patch RFC 6902](https://tools.ietf.org/html/rfc6902)
- [Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [CopilotKit](https://www.copilotkit.ai/)
