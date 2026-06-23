---
skill: codegen-decision-tree
description: Structured decision logic for selecting the right Kailash pattern
priority: HIGH
tags: [nexus, codegen, decision-tree, anti-patterns, templates]
---

# Codegen Decision Tree

Every scaffolding task MUST start by traversing this tree.

## Master Decision Tree

```
START: What are you building?
|
+-- API endpoint that reads/writes data?
|   +-- Simple CRUD?
|   |   --> Handler + DataFlow model
|   +-- Multi-model with relationships?
|   |   --> Nexus + DataFlow (multiple instances if needed)
|   +-- Complex validation/transformation?
|   |   --> Workflow + custom node
|   +-- Requires authentication?
|       --> Auth plugin + any of the above
|
+-- AI-powered feature?
|   +-- Single LLM call?
|   |   --> Handler wrapping an agent invocation
|   +-- Multi-step agent?
|   |   --> Kaizen agent + handler
|   +-- RAG/semantic search?
|   |   --> Kaizen agent + MCP + vector storage
|   +-- AI agent integration?
|       --> MCP channel
|
+-- Background/batch processing?
|   +-- Event-driven?
|   |   --> Workflow + async runtime
|   +-- Scheduled jobs?
|   |   --> Scheduled task handler
|   +-- Bulk data import?
|       --> DataFlow bulk operations
|
+-- Infrastructure only?
    +-- Authentication?
    |   --> Auth plugin (basic, SaaS, or enterprise tier)
    +-- Custom middleware?
        --> Middleware registration
```

## Anti-Patterns

### 1. Sandbox-restricted code for business logic

When handler code needs to import libraries, call external APIs, or access databases, use direct handler registration instead of sandboxed code nodes. Sandbox restrictions block most imports and I/O operations.

### 2. Bypassing the Nexus API surface

Access platform internals through public APIs only. Internal gateway or app references are unstable across versions. Use handler registration, middleware registration, or router inclusion.

### 3. Building authentication from scratch

Use the built-in auth plugin. It handles JWT verification, refresh tokens, RBAC, and tenant isolation with correct middleware ordering.

### 4. Database instance per request

Create DataFlow instances at module level. Per-request instances exhaust connection pools and cause resource leaks.

### 5. Workflows for simple CRUD

Use handler registration for simple operations. Workflows are for multi-step orchestration with branching and data flow between nodes.

### 6. Mocking DataFlow in integration tests

Use a real DataFlow instance with an in-memory database (e.g., SQLite memory mode) instead of mocking.

### 7. Accessing platform internals directly

Use public middleware and routing APIs. Internal references break across versions without notice.

## Scaffolding Templates

### Template 1: SaaS API Backend

Components:

- Nexus instance with DataFlow integration (`auto_discovery=False`)
- DataFlow instance with auto-migration
- Auth plugin with JWT, RBAC, and tenant isolation
- DataFlow models with `id` primary key
- Handlers for CRUD operations with permission-based authorization
- Async runtime for workflow execution within handlers
- Health endpoint

### Template 2: AI Agent Backend

Components:

- Nexus instance with MCP enabled
- Kaizen agent with signature (input/output field definitions)
- Handler wrapping agent invocation
- Session support for conversational context

### Template 3: Multi-Tenant Enterprise

Components:

- Multiple DataFlow instances per concern (primary, analytics, audit)
- Models scoped to their respective DataFlow instance
- Full enterprise auth (JWT + RBAC + tenant isolation + audit)
- Async database initialization

## Critical Configuration

| Setting               | Value                      | Why                                               |
| --------------------- | -------------------------- | ------------------------------------------------- |
| Auto-discovery        | Disabled                   | Prevents DataFlow startup blocking                |
| DataFlow auto-migrate | Enabled                    | Handles schema creation automatically             |
| Runtime               | Async variant              | Required for async handler contexts               |
| Workflow build        | Called before registration | Workflow objects must be built before registering |

## Auth Configuration Pitfalls

| Wrong                        | Correct                        | Context                                          |
| ---------------------------- | ------------------------------ | ------------------------------------------------ |
| `secret_key`                 | `secret`                       | JWT config parameter name                        |
| `exclude_paths`              | `exempt_paths`                 | JWT config parameter name                        |
| `admin_roles` (plural list)  | `admin_role` (singular string) | Tenant config parameter name                     |
| RBAC config object           | Plain dict                     | Role definitions are plain dictionaries          |
| Boolean for tenant isolation | Config object                  | Tenant isolation requires a configuration object |

See language-specific variant for implementation details and code examples.
