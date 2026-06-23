---
skill: nexus-transport-architecture
description: Transport abstraction layer, built-in transports (HTTP, MCP, CLI), handler registry, and custom transport interface
priority: MEDIUM
tags: [nexus, transport, http, mcp, cli, registry, handler]
---

# Nexus Transport Architecture

## Overview

Nexus uses a transport abstraction layer to decouple handler registration from protocol-specific dispatch. Handlers are registered once in a central registry, and each transport maps them to protocol-appropriate endpoints. This is what enables "register once, serve everywhere" across API, CLI, and MCP.

## When to Use

- Understanding how Nexus multi-channel delivery works internally
- Adding a custom transport (WebSocket, gRPC, message queue)
- Debugging transport-specific behavior
- Building protocol adapters for new integration channels

## Architecture

### Component Relationships

```
Handler Registration
    |
    v
Handler Registry (central store of all handler definitions)
    |
    +---> HTTP Transport (maps handlers to REST endpoints)
    +---> MCP Transport (maps handlers to MCP tools)
    +---> CLI Transport (maps handlers to CLI commands)
    +---> Custom Transport (maps handlers to custom protocol)
```

### Core Components

| Component            | Purpose                                                                      |
| -------------------- | ---------------------------------------------------------------------------- |
| Handler Registry     | Central store for all handler definitions                                    |
| Handler Definition   | Metadata for a single handler: name, function, parameters, description, tags |
| Handler Parameter    | Metadata for a single parameter: name, type, default value, required flag    |
| Transport (abstract) | Base interface that all transports implement                                 |

## Transport Interface

Every transport must provide:

| Method/Property                      | Purpose                                                             |
| ------------------------------------ | ------------------------------------------------------------------- |
| `name`                               | Unique transport identifier (e.g., "http", "mcp")                   |
| `start(registry)`                    | Initialize transport, reading handler definitions from the registry |
| `stop()`                             | Graceful shutdown (must be idempotent)                              |
| `is_running`                         | Whether the transport is currently active                           |
| `on_handler_registered(handler_def)` | Callback for hot-reload when handlers are added after start         |

## Transport Lifecycle

1. Transport instantiated with protocol-specific configuration (port, options)
2. Transport registered with Nexus
3. On `Nexus.start()`, each transport's `start(registry)` is called with the handler registry
4. Transport reads all handler definitions and sets up protocol-specific dispatch
5. As new handlers are registered after start, `on_handler_registered()` fires for hot-reload
6. On `Nexus.stop()`, each transport's `stop()` is called for graceful shutdown

## Built-in Transports

### HTTP Transport

Maps registered handlers to HTTP REST endpoints. Handles:

- Route generation from handler names
- Request body parsing into handler parameters
- Response serialization
- CORS, middleware, and authentication integration
- File upload via multipart form data

### MCP Transport

Maps registered handlers to MCP (Model Context Protocol) tools. Handles:

- Tool registration with name and description
- Parameter schema generation from handler definitions
- Tool invocation dispatch to handler functions
- File transfer via base64 encoding

### CLI Transport

Maps registered handlers to command-line interface commands. Handles:

- Command generation from handler names
- Argument parsing from handler parameters
- File input from filesystem paths
- Output formatting for terminal display

## Handler Registry

The registry is the single source of truth for all handlers. It stores:

- **Handler name** -- unique identifier used across all transports
- **Handler function** -- the actual callable
- **Parameters** -- extracted from function signatures (name, type, default, required)
- **Description** -- human-readable explanation (critical for MCP/AI agent discovery)
- **Tags** -- optional grouping metadata

### Parameter Extraction

Handler parameters are introspected from function signatures:

- Type annotations map to transport-appropriate types
- Default values determine required vs optional status
- File type parameters are detected and handled specially per transport (multipart upload for HTTP, file path for CLI, base64 for MCP)

## Custom Transports

New transports can be created by implementing the transport interface. The transport receives the full handler registry at startup, allowing it to set up protocol-specific dispatch for every registered handler. The `on_handler_registered()` callback enables adding handlers while the transport is running.

Common custom transport candidates:

| Transport     | Protocol  | Use Case                              |
| ------------- | --------- | ------------------------------------- |
| WebSocket     | WS        | Real-time bidirectional communication |
| gRPC          | HTTP/2    | High-performance service-to-service   |
| Message Queue | AMQP/MQTT | Async event-driven architectures      |
| GraphQL       | HTTP      | Flexible query-based APIs             |

## Best Practices

1. **Write handler descriptions** -- MCP and CLI transports use them for discovery and help text
2. **Use standard types in handler signatures** -- ensures all transports can serialize/deserialize correctly
3. **Test across all active transports** -- behavior can differ per protocol
4. **Implement idempotent stop** -- transports may be stopped multiple times during shutdown
5. **Support hot-reload** -- implement `on_handler_registered()` for dynamic handler addition

See language-specific variant for implementation details and code examples.

## Related Skills

- [nexus-multi-channel](nexus-multi-channel.md) - Multi-channel usage patterns
- [nexus-mcp-channel](nexus-mcp-channel.md) - MCP channel details
- [nexus-api-patterns](nexus-api-patterns.md) - API transport patterns
- [nexus-cli-patterns](nexus-cli-patterns.md) - CLI transport patterns
