# Kailash SDK Feature Guides

This directory contains in-depth guides for key features and architectural patterns in the Kailash Python SDK. These guides help you understand when and how to use specific features for building sophisticated AI workflows.

## 📚 Feature Index

### [Access Control](./access_control.md)
**Unified security framework with RBAC/ABAC/Hybrid support**
- Single interface for all access control strategies
- Role-based access control (RBAC) for traditional permissions
- Attribute-based access control (ABAC) with 16 operators
- Hybrid mode combining RBAC and ABAC
- Database integration with automatic permission checks
- Data masking based on user attributes
- Best practices for multi-tenant systems

### [Agent Coordination Patterns](./agent_coordination_patterns.md)
**Patterns for orchestrating multi-agent systems**
- A2ACoordinatorNode: Direct task orchestration (project manager pattern)
- AgentPoolManagerNode: Dynamic agent registry (talent pool pattern)
- Comparison and integration strategies
- When to use each approach

### [API Integration](./api_integration.md)
**Connecting to external services and APIs**
- HTTPRequestNode for REST APIs
- GraphQLNode for GraphQL endpoints
- Authentication patterns (OAuth, API keys, JWT)
- Error handling and retry strategies
- Rate limiting and caching

### [Conditional Routing](./conditional_routing.md)
**Dynamic workflow routing with SwitchNode**
- Boolean and multi-case conditional routing
- Quality improvement cycles with conditional exits
- Error handling and fallback patterns
- Integration with cyclic workflows
- Best practices for complex decision trees

### [MCP Ecosystem](./mcp_ecosystem.md)
**Model Context Protocol integration**
- Understanding MCP servers and clients
- Integrating tools like Exa and Perplexity
- Building custom MCP servers
- Best practices for tool orchestration

### [WebSocket Transport](./websocket-transport.md)
**Enterprise WebSocket transport for MCP**
- Connection pooling and performance optimization
- Security configuration and best practices
- Error handling and resilience patterns
- Production monitoring and troubleshooting

### [Performance Tracking](./performance_tracking.md)
**Monitoring and optimizing workflow performance**
- Built-in metrics collection
- Performance visualization
- Identifying bottlenecks
- Optimization strategies
- Real-time monitoring dashboards

### [Python Code Node](./python_code_node.md)
**Dynamic code execution within workflows**
- Safe code execution patterns
- Input/output schema validation
- Security considerations
- Common use cases and examples
- Integration with other nodes

### [Workflow Patterns](./workflow_pattern.md)
**Common workflow design patterns**
- Sequential processing
- Parallel execution
- Conditional branching
- Error handling patterns
- State management
- Nested workflows

### [XAI-UI Middleware](./xai_ui_middleware.md)
**Real-time agent-UI communication with explainability**
- Event-driven architecture (16 standard events)
- Bidirectional state synchronization
- Human-in-the-loop workflows
- Generative UI capabilities
- Transport agnostic (SSE, WebSocket, Webhook)
- Sub-200ms latency performance

## 🎯 Quick Decision Guide

**What are you trying to build?**

| If you need to... | Read this guide |
|-------------------|-----------------|
| Coordinate multiple AI agents | [Agent Coordination Patterns](./agent_coordination_patterns.md) |
| Add user authentication/permissions | [Access Control](./access_control.md) |
| Call external APIs or services | [API Integration](./api_integration.md) |
| Create conditional workflows with routing | [Conditional Routing](./conditional_routing.md) |
| Use AI tools (Exa, Perplexity, etc.) | [MCP Ecosystem](./mcp_ecosystem.md) |
| Monitor workflow performance | [Performance Tracking](./performance_tracking.md) |
| Execute custom Python logic | [Python Code Node](./python_code_node.md) |
| Design complex workflows | [Workflow Patterns](./workflow_pattern.md) |
| Build real-time agent UIs | [XAI-UI Middleware](./xai_ui_middleware.md) |

## 💡 How to Use These Guides

### For Learning
1. **Start with your use case** - Use the decision guide above
2. **Read the overview** - Each guide starts with a high-level explanation
3. **Study the examples** - Code examples demonstrate real usage
4. **Understand trade-offs** - Each guide discusses pros/cons

### For Implementation
1. **Copy example code** - Each guide provides working examples
2. **Follow best practices** - Security and performance tips included
3. **Test incrementally** - Start simple, add complexity
4. **Check integration** - Guides show how features work together

### For Reference
1. **API details** - Each guide documents relevant APIs
2. **Configuration options** - All parameters explained
3. **Error handling** - Common issues and solutions
4. **Performance tips** - Optimization strategies

## 🔗 Related Resources

- **API Reference**: `../reference/api-registry.yaml` - Complete API documentation
- **Node Catalog**: `../reference/node-catalog.md` - All available nodes
- **Pattern Library**: `../patterns/` - Workflow patterns organized by category
- **Examples**: `../../examples/` - Working code examples
- **Architecture Decisions**: `../adr/` - Design rationale

## 🚀 Getting Started

If you're new to Kailash SDK features:

1. **Basic Workflow** → Start with [Workflow Patterns](./workflow_pattern.md)
2. **Add Intelligence** → Explore [Agent Coordination](./agent_coordination_patterns.md)
3. **External Data** → Learn [API Integration](./api_integration.md)
4. **AI Tools** → Understand [MCP Ecosystem](./mcp_ecosystem.md)
5. **Production Ready** → Implement [Access Control](./access_control.md) and [Performance Tracking](./performance_tracking.md)

## 📝 Contributing

When adding new feature guides:

1. **Follow the template** - Consistent structure helps readers
2. **Include examples** - Show real, working code
3. **Explain why** - Not just how, but when to use
4. **Add to index** - Update this README
5. **Cross-reference** - Link to related guides

## 🎓 Advanced Topics

For complex scenarios combining multiple features:

- **Multi-tenant AI Platform**: Combine Access Control + Agent Coordination + Performance Tracking
- **External Tool Orchestra**: Integrate MCP Ecosystem + API Integration + Workflow Patterns
- **Dynamic Workflows**: Use Python Code Node + Conditional Patterns + Agent Coordination
- **Production Systems**: All features with emphasis on security, monitoring, and scalability

---

*These guides are living documents. As the Kailash SDK evolves, these guides are updated to reflect new capabilities and best practices.*
