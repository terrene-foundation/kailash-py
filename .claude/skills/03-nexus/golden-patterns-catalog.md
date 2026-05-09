---
skill: golden-patterns-catalog
description: Top 10 Kailash patterns ranked by production usage for codegen agents
priority: HIGH
tags: [nexus, patterns, codegen, handler, dataflow, auth, workflow, kaizen, mcp]
---

# Top 10 Kailash Patterns -- Codegen Catalog

## Pattern 1: Handler Registration

Register async functions as multi-channel endpoints. A single registration makes the function available on API, CLI, and MCP simultaneously.

**What it does**: Takes a function with typed parameters and a description, and exposes it across all active transports. Type annotations drive parameter validation and schema generation (OpenAPI, MCP tool schema, CLI argument parsing).

**Common mistakes**:

- Using sandboxed code nodes for business logic (blocks imports and I/O)
- Missing type annotations (transports cannot generate schemas)
- Returning non-dictionary types (serialization issues)
- Complex collection types that serialize ambiguously

## Pattern 2: DataFlow Model

Declare a data model and automatically get CRUD operations: Create, Read, Update, Delete, List, Upsert, Count, and Bulk variants.

**What it does**: A model declaration with typed fields auto-generates workflow nodes for all standard database operations. The primary key must be named `id`.

**Common mistakes**:

- Primary key not named `id`
- Manually setting auto-managed timestamps (`created_at`, `updated_at`)
- Using ORM save patterns instead of generated nodes

## Pattern 3: Nexus + DataFlow Integration

Combine handler registration with DataFlow models for API-backed database operations.

**What it does**: Handlers invoke DataFlow-generated nodes through workflows, providing multi-channel CRUD endpoints with a single model declaration.

**Critical**: Disable auto-discovery when integrating DataFlow with Nexus. Without this, the application blocks on startup.

**Common mistakes**:

- Missing auto-discovery disable (infinite blocking)
- Using removed/renamed configuration parameters

## Pattern 4: Auth Middleware Stack

Add authentication, authorization, and security middleware through the unified auth plugin.

**What it does**: Assembles JWT verification, RBAC, tenant isolation, rate limiting, and audit logging into a correctly-ordered middleware chain. Factory methods provide pre-configured bundles (basic, SaaS, enterprise).

**Middleware order** (automatic): Audit -> Rate Limit -> JWT -> Tenant -> RBAC -> Handler.

**Common mistakes**:

| Wrong                        | Correct                 | Context                        |
| ---------------------------- | ----------------------- | ------------------------------ |
| `secret_key`                 | `secret`                | JWT config parameter           |
| `exclude_paths`              | `exempt_paths`          | JWT config parameter           |
| `admin_roles` (plural)       | `admin_role` (singular) | Tenant config parameter        |
| RBAC config object           | Plain dictionary        | Role definitions               |
| Boolean for tenant isolation | Config object           | Tenant isolation configuration |
| Wrong import path            | Varies by SDK           | Auth plugin import             |

## Pattern 5: Multi-DataFlow Instance

Separate DataFlow instances per database or domain concern for isolation.

**What it does**: Creates independent DataFlow instances with separate connection pools, each managing its own set of models. Models are scoped to their DataFlow instance.

**Use cases**: Primary data + analytics database, read replicas, audit database separation.

## Pattern 6: Custom Node

Create reusable workflow nodes with typed parameters for domain-specific operations.

**What it does**: Defines a node with explicit parameter declarations (name, type, required, default) and an async execute method. Nodes are registered by name and can be used in any workflow.

**Common mistakes**:

- Missing node registration decorator
- Using blocking I/O libraries instead of async variants

## Pattern 7: Kaizen Agent

Build AI agents with structured input/output signatures.

**What it does**: Defines a signature with typed input and output fields, then creates an agent that uses LLM reasoning to produce structured outputs. The agent is invoked through a run method with keyword arguments matching the signature.

**Common mistakes**:

- Manually constructing agent configuration instead of using defaults
- Calling strategy methods directly instead of the agent's run method
- Missing environment variable loading for LLM provider keys

## Pattern 8: Workflow Builder

Multi-step orchestration with branching, connections, and data flow between nodes.

**What it does**: Declaratively builds a workflow by adding nodes, connecting outputs to inputs, and optionally adding conditional branching. The workflow must be built (finalized) before execution.

**Critical**: Always call build before registration or execution. Use explicit connections between nodes, not template syntax.

**Common mistakes**:

- Forgetting to build before registration
- Using template variable syntax (`${...}`) instead of explicit connections
- Missing runtime for execution

## Pattern 9: Async Runtime

Execute workflows asynchronously within handler contexts.

**What it does**: Provides an async-compatible runtime for executing built workflows. Returns results and a run ID. The runtime should be initialized once at module level, not per request.

**Common mistakes**:

- Creating a new runtime per request (resource waste)
- Using the sync runtime in async contexts (blocks the event loop)

## Pattern 10: MCP Integration

Every registered handler automatically becomes an MCP tool accessible to AI agents.

**What it does**: When an MCP port is configured, all handlers are exposed as MCP tools with their descriptions and parameter schemas. AI agents discover and invoke these tools via the MCP protocol.

**Critical**: Handler descriptions are essential for AI agent discovery. Without descriptions, agents cannot determine what tools do.

**Common mistakes**:

- Missing descriptions (AI agents need them for tool selection)
- Complex return types that are hard for agents to parse
- Missing parameter defaults (forces agents to guess required values)

## Quick Reference

| Pattern             | Primary Use        | When to Choose                                         |
| ------------------- | ------------------ | ------------------------------------------------------ |
| 1. Handler          | API endpoints      | Any function that should be accessible via API/CLI/MCP |
| 2. DataFlow Model   | Database entities  | Persistent data with CRUD operations                   |
| 3. Nexus + DataFlow | API + database     | Most CRUD API applications                             |
| 4. Auth Stack       | Security           | Any production deployment with users                   |
| 5. Multi-DataFlow   | Multiple databases | Separate concerns across databases                     |
| 6. Custom Node      | Reusable logic     | Domain operations used in multiple workflows           |
| 7. Kaizen Agent     | AI features        | LLM-powered analysis, generation, or conversation      |
| 8. Workflow Builder | Orchestration      | Multi-step processes with branching                    |
| 9. Async Runtime    | Workflow execution | Running workflows in async handler contexts            |
| 10. MCP Integration | AI tools           | Exposing functionality to AI agents                    |

## Critical Configuration

| Setting               | Requirement                                                          |
| --------------------- | -------------------------------------------------------------------- |
| Auto-discovery        | Disable when using DataFlow                                          |
| DataFlow auto-migrate | Enable for automatic schema management                               |
| Runtime               | Initialize once at module level, use async variant in async contexts |
| Workflow build        | Always call before registration or execution                         |

See language-specific variant for implementation details and code examples.
