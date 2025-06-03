# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Kailash Python SDK project.

## What is an ADR?

An Architecture Decision Record captures a significant architectural decision made along with its context and consequences. ADRs help us understand why certain decisions were made and provide a historical record of our architectural evolution.

## ADR Index

### Core Architecture
- [ADR-0003: Base Node Interface](0003-base-node-interface.md) - **Accepted**
- [ADR-0004: Workflow Representation](0004-workflow-representation.md) - **Accepted**
- [ADR-0009: Src Layout for Package](0009-src-layout-for-package.md) - **Accepted**
- [ADR-0016: Immutable State Management](0016-immutable-state-management.md) - **Accepted**

### Execution and Runtime
- [ADR-0005: Local Execution Strategy](0005-local-execution-strategy.md) - **Accepted**
- [ADR-0008: Docker Runtime Architecture](0008-docker-runtime-architecture.md) - **Accepted**
- [ADR-0014: Async Node Execution](0014-async-node-execution.md) - **Accepted**

### Node Types and Features
- [ADR-0010: Python Code Node](0010-python-code-node.md) - **Accepted**
- [ADR-0012: Workflow Conditional Routing](0012-workflow-conditional-routing.md) - **Accepted**
- [ADR-0013: Simplify Conditional Logic Nodes](0013-simplify-conditional-logic-nodes.md) - **Accepted**

### Integration and APIs
- [ADR-0015: API Integration Architecture](0015-api-integration-architecture.md) - **Accepted**
- [ADR-0017: Multi-Workflow API Architecture](0017-multi-workflow-api-architecture.md) - **Accepted** ⭐ NEW
- [ADR-0018: HTTP REST Client Architecture](0018-http-rest-client-architecture.md) - **Accepted**

### Workflow Management
- [ADR-0006: Task Tracking Architecture](0006-task-tracking-architecture.md) - **Accepted**
- [ADR-0007: Export Format](0007-export-format.md) - **Accepted**
- [ADR-0011: Workflow Execution Improvements](0011-workflow-execution-improvements.md) - **Accepted**

## Recent Decisions

### ADR-0017: Multi-Workflow API Architecture (December 2024)
Introduces the `WorkflowAPIGateway` for managing multiple workflows through a unified API with:
- Dynamic workflow registration and routing
- MCP (Model Context Protocol) integration for AI tools
- Support for embedded and proxied workflows
- WebSocket support for real-time updates
- Multiple deployment patterns (single, hybrid, HA, Kubernetes)

This addresses the need for running multiple workflows with different endpoints alongside MCP servers in production environments.

## Creating a New ADR

1. Copy the template: `cp 0000-template.md 00XX-your-decision-name.md`
2. Fill in the sections:
   - **Status**: Proposed, Accepted, Deprecated, or Superseded
   - **Context**: Why is this decision needed?
   - **Decision**: What are we doing?
   - **Consequences**: What are the trade-offs?
3. Update this README with the new ADR
4. Link to relevant PRD sections if applicable

## ADR Status Types

- **Proposed**: Under discussion
- **Accepted**: Approved and implemented/being implemented
- **Deprecated**: No longer recommended but still in use
- **Superseded**: Replaced by another ADR (reference the new one)