# Nexus Agent Reference

Quick-reference for agents working with Nexus deployments. Covers capabilities, common issues, and navigation to detailed skills.

## Platform Capabilities

| Capability              | Description                                                   |
| ----------------------- | ------------------------------------------------------------- |
| Multi-channel serving   | Single registration serves API + CLI + MCP simultaneously     |
| Handler registration    | Register functions as multi-channel endpoints                 |
| Workflow registration   | Register Core SDK workflows as multi-channel endpoints        |
| Authentication          | JWT, RBAC, tenant isolation via unified auth plugin           |
| Rate limiting           | Per-route and global rate limiting with memory/Redis backends |
| Session management      | Cross-channel session state with configurable backends        |
| Event system            | Lifecycle events, custom events, scheduled tasks              |
| DataFlow integration    | Database operations with event bridging                       |
| Plugin system           | Extensible architecture for custom functionality              |
| Health monitoring       | Health endpoints, metrics, custom probes                      |
| Kubernetes probes       | Readiness, liveness, and startup probe endpoints              |
| OpenAPI generation      | Automatic specification from handler type annotations         |
| Security middleware     | CORS, CSRF, security headers, deployment presets              |
| File handling           | Unified file abstraction across all transports                |
| Transport extensibility | Custom transport implementations for new protocols            |

## Authentication Summary

The auth system uses a unified plugin with factory methods for common configurations:

| Tier       | Includes                                              |
| ---------- | ----------------------------------------------------- |
| Basic auth | JWT + audit logging                                   |
| SaaS app   | JWT + RBAC + tenant isolation + audit                 |
| Enterprise | JWT + RBAC + rate limiting + tenant isolation + audit |

**Security defaults**: 32-char minimum for HS256 secrets, generic RBAC error responses (no role leakage), sanitized SSO errors, CORS credentials disabled by default.

**Middleware order** (automatic): Audit -> Rate Limit -> JWT -> Tenant -> RBAC -> Handler.

## Common Issues and Solutions

| Issue                           | Solution                                                                                      |
| ------------------------------- | --------------------------------------------------------------------------------------------- |
| Nexus blocks on startup         | Use `auto_discovery=False` with DataFlow                                                      |
| Workflow not found              | Ensure `.build()` called before registration                                                  |
| Port conflicts                  | Use custom ports via constructor configuration                                                |
| Auth dependency injection fails | Remove `from __future__ import annotations` (PEP 563)                                         |
| RBAC not resolving permissions  | Ensure JWT is configured (RBAC requires JWT)                                                  |
| Wrong auth parameter names      | `secret` not `secret_key`, `exempt_paths` not `exclude_paths`, `admin_role` not `admin_roles` |

## Configuration Essentials

| Setting                | Purpose                                   | Critical Notes                     |
| ---------------------- | ----------------------------------------- | ---------------------------------- |
| `auto_discovery=False` | Prevents DataFlow startup blocking        | Required when integrating DataFlow |
| API port               | HTTP transport listen port                | Default varies by implementation   |
| MCP port               | MCP transport listen port                 | Enables AI agent integration       |
| CORS origins           | Allowed origins for cross-origin requests | Restrict in production             |
| Rate limit             | Global requests per minute                | Default is typically 100           |
| Monitoring             | Enable health and metrics endpoints       | Enable in production               |
| Log level              | Logging verbosity                         | Use INFO or above in production    |

## Skill References

### Quick Start

- **[nexus-quickstart](nexus-quickstart.md)** -- Basic setup
- **[nexus-workflow-registration](nexus-workflow-registration.md)** -- Registration patterns
- **[nexus-essential-patterns](nexus-essential-patterns.md)** -- Setup, handlers, DataFlow, connections

### Channel Patterns

- **[nexus-api-patterns](nexus-api-patterns.md)** -- API deployment
- **[nexus-cli-patterns](nexus-cli-patterns.md)** -- CLI integration
- **[nexus-mcp-channel](nexus-mcp-channel.md)** -- MCP server
- **[nexus-multi-channel](nexus-multi-channel.md)** -- Multi-channel architecture

### Integration

- **[nexus-dataflow-integration](nexus-dataflow-integration.md)** -- DataFlow integration
- **[nexus-sessions](nexus-sessions.md)** -- Session management

### Authentication and Authorization

- **[nexus-auth-plugin](nexus-auth-plugin.md)** -- Auth architecture and configuration
- **[nexus-enterprise-features](nexus-enterprise-features.md)** -- Enterprise deployment patterns

### Platform Internals

- **[nexus-transport-architecture](nexus-transport-architecture.md)** -- Transport layer
- **[nexus-event-system](nexus-event-system.md)** -- Event system
- **[nexus-plugins](nexus-plugins.md)** -- Plugin system
- **[nexus-health-monitoring](nexus-health-monitoring.md)** -- Health and metrics
- **[nexus-k8s-probes](nexus-k8s-probes.md)** -- Kubernetes probes and security middleware

### Codegen

- **[codegen-decision-tree](codegen-decision-tree.md)** -- Pattern selection logic
- **[golden-patterns-catalog](golden-patterns-catalog.md)** -- Top patterns by usage

## Related Agents

- **dataflow-specialist** -- Database integration with Nexus
- **mcp-specialist** -- MCP channel implementation
- **pattern-expert** -- Core SDK workflows for Nexus registration
- **release-specialist** -- Production deployment and scaling

## Troubleshooting

- **[nexus-troubleshooting](nexus-troubleshooting.md)** -- Detailed troubleshooting guide
