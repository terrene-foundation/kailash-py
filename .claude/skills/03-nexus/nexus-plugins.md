---
skill: nexus-plugins
description: Plugin system for extending Nexus with custom functionality
priority: LOW
tags: [nexus, plugins, extensibility, custom, development]
---

# Nexus Plugin System

## Overview

Nexus provides a plugin architecture for extending platform functionality without modifying core code. Plugins hook into the Nexus lifecycle to add authentication, monitoring, rate limiting, caching, and custom integrations.

## When to Use

- Adding cross-cutting concerns (logging, metrics, auth) to a Nexus deployment
- Integrating with external services (webhooks, databases, notification systems)
- Sharing reusable functionality across multiple Nexus applications
- Extending Nexus without modifying its core

## Architecture

Plugins follow a registration-based lifecycle:

```
Plugin Instantiated
    |
    v
Plugin Registered (add_plugin)
    |
    v
Plugin Setup (receives Nexus instance reference)
    |
    v
Nexus Running (plugin hooks active)
    |
    v
Plugin Teardown (Nexus stopping)
```

Plugins receive a reference to the Nexus instance during setup, allowing them to register event hooks, add middleware, and extend platform behavior.

## Plugin Interface

Every plugin must satisfy these requirements:

| Requirement | Description                                                        |
| ----------- | ------------------------------------------------------------------ |
| Name        | Non-empty string identifier, unique across registered plugins      |
| Description | Human-readable explanation of what the plugin does                 |
| Apply/Setup | Callable that receives the Nexus instance and activates the plugin |
| Validate    | Optional validation logic run before registration                  |
| Teardown    | Optional cleanup logic run when Nexus stops                        |

Validation checks that the plugin has a name and an apply method before registration. Specific error handling covers missing constructor arguments and invalid configurations.

## Built-in Plugins

| Plugin        | Purpose                          | Key Configuration                               |
| ------------- | -------------------------------- | ----------------------------------------------- |
| Auth          | JWT, RBAC, tenant isolation, SSO | Strategy, provider, token settings              |
| Monitoring    | Metrics collection and reporting | Backend (e.g., Prometheus), collection interval |
| Rate Limiting | Request throttling               | Requests per minute, burst size                 |

## Custom Plugin Capabilities

Custom plugins can:

- **Hook into lifecycle events** -- respond to workflow start, completion, failure, and session events
- **Wrap execution** -- intercept workflow execution for caching, logging, or transformation
- **Access configuration** -- accept constructor parameters for flexible setup
- **Manage resources** -- open connections on setup, close them on teardown
- **Register additional endpoints** -- add health checks or metrics endpoints

## Plugin Manager

Nexus includes a plugin manager that:

- Prevents duplicate plugin names
- Calls setup on registration
- Calls teardown on unregistration
- Provides plugin lookup by name
- Lists all active plugins

## Common Plugin Patterns

| Pattern             | Purpose                                                    |
| ------------------- | ---------------------------------------------------------- |
| Request Logger      | Log workflow invocations and responses across all channels |
| Metrics Collector   | Track request counts, success rates, average duration      |
| Webhook Integration | Send notifications to external services on workflow events |
| Caching             | Cache workflow results with configurable TTL               |
| Database Audit      | Log execution history to a persistent store                |

## Best Practices

1. **Single responsibility** -- one concern per plugin
2. **Graceful error handling** -- plugin failures should not crash the platform
3. **Clean resource management** -- release connections and handles in teardown
4. **Configuration-driven** -- accept settings via constructor, not hardcoded values
5. **Independent testability** -- plugins should be testable without a running Nexus instance
6. **Versioning** -- track plugin versions for compatibility

See language-specific variant for implementation details and code examples.

## Related Skills

- [nexus-event-system](nexus-event-system.md) - Event hooks used by plugins
- [nexus-enterprise-features](nexus-enterprise-features.md) - Built-in enterprise plugins
- [nexus-health-monitoring](nexus-health-monitoring.md) - Monitoring plugin details
