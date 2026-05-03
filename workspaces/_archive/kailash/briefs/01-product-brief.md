# Kailash SDK - Product Brief

## Product

Kailash is an open-source Python SDK for building, executing, and deploying computational workflows. It provides a node-based execution engine with 140+ built-in nodes, support for cyclic workflows, async execution, and a framework ecosystem for database operations (DataFlow), multi-channel deployment (Nexus), and AI agent orchestration (Kaizen).

## Objectives

- Provide a simple, intuitive API for workflow creation (`WorkflowBuilder`)
- Support both synchronous and asynchronous execution runtimes
- Enable enterprise-grade trust and governance through EATP integration
- Offer zero-config frameworks that eliminate boilerplate for common patterns
- Maintain production-ready security with adversarial-tested trust chains

## Tech Stack

- Backend: Python 3.11+, Kailash Core SDK
- Frameworks: DataFlow (database), Nexus (multi-channel), Kaizen (AI agents)
- Trust: EATP (Enterprise Agent Trust Protocol) with Ed25519 signatures
- Testing: pytest, 3-tier strategy (unit → integration → E2E)

## Constraints

- All frameworks build ON Core SDK — they don't replace it
- String-based node registration (`workflow.add_node("NodeType", "id", {params})`)
- Runtime executes workflow, not vice versa (`runtime.execute(workflow.build())`)
- No mocking in Tier 2/3 tests — real infrastructure required

## Users

- **SDK developers**: Build workflows, create custom nodes
- **Framework users**: Use DataFlow/Nexus/Kaizen for domain-specific work
- **Enterprise teams**: Trust verification, audit trails, multi-tenancy
- **Contributors**: Extend nodes, improve frameworks, add integrations
