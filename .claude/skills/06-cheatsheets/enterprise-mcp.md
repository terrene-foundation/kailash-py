---
name: enterprise-mcp
description: "Enterprise MCP patterns for large-scale deployments. Use when asking 'enterprise MCP', 'MCP patterns', 'MCP scale', 'enterprise integration', or 'MCP production'."
---

# Enterprise Mcp

Enterprise Mcp for MCP server integration and deployment.

> **Skill Metadata**
> Category: `mcp`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Enterprise Mcp
- **Category**: mcp
- **Priority**: HIGH
- **Trigger Keywords**: enterprise MCP, MCP patterns, MCP scale, enterprise integration

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Enterprise Mcp implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **Production MCP Servers**: Enterprise-grade MCP server deployment with authentication, authorization, rate limiting, and monitoring
- **Multi-Transport Support**: Serve same MCP server over WebSocket, SSE, and stdio simultaneously for different client types
- **Resource Access Control**: Role-based permissions for resources, tools, and prompts with per-user/per-group policies
- **Event Store Integration**: Full audit trail of all MCP operations (tool calls, resource access, subscriptions) for compliance
- **High Availability Deployment**: Multi-instance coordination with Redis, automatic failover, session affinity, health checks

## Related Patterns

- **For fundamentals**: See [`workflow-quickstart`](#)
- **For patterns**: See [`workflow-patterns-library`](#)
- **For parameters**: See [`param-passing-quick`](#)

## When to Escalate to Subagent

Use specialized subagents when:
- **pattern-expert**: Complex patterns, multi-node workflows
- **testing-specialist**: Comprehensive testing strategies

## Documentation References

### Primary Sources

## Quick Tips

- 💡 **Use JWT Authentication**: Implement JWTAuth with appropriate expiration and refresh tokens for stateless auth
- 💡 **Configure Rate Limiting**: Set default_limit per minute with burst_limit to prevent abuse and ensure fair usage
- 💡 **Enable Audit Logging**: Configure event_store to log all operations for compliance, debugging, and security monitoring
- 💡 **Deploy with Redis**: Use Redis for session management, subscription coordination, and distributed state across instances
- 💡 **Monitor Performance**: Track connection count, request latency, error rates, and resource usage with built-in metrics

## Keywords for Auto-Trigger

<!-- Trigger Keywords: enterprise MCP, MCP patterns, MCP scale, enterprise integration -->
