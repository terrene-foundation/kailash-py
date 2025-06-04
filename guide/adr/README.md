# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Kailash Python SDK project.

## What is an ADR?

An Architecture Decision Record (ADR) is a document that captures an important architectural decision made along with its context and consequences.

## ADR Structure

Each ADR should be stored in the `guide/adr/` directory with a filename pattern of `NNNN-title-with-dashes.md` where `NNNN` is a sequential number.

```
guide/
└── adr/
    ├── 0001-base-node-interface.md
    ├── 0002-workflow-representation.md
    ├── 0003-local-execution-strategy.md
    └── README.md  # Overview of the ADR process
```

## ADR Template

We use the following format for ADRs:

```markdown
# ADR-NNNN: Title of the Decision

## Status

[Proposed | Accepted | Deprecated | Superseded by ADR-XXXX]

Date: YYYY-MM-DD

## Context

Describe the circumstances and forces at play, including technological, political, social, project-specific, and organizational factors that influenced the decision.

## Decision

State the decision made clearly and concisely. Explain the "what" not the "how" of implementation.

## Rationale

Explain why this decision was made, what alternatives were considered, and why they were rejected.

## Consequences

Describe the resulting context after applying the decision, including both positive and negative consequences. Include any risks introduced and mitigations.

## Implementation Notes

Optional section for specific implementation details, guidelines, or considerations.

## Related ADRs

- [ADR-XXXX: Related Decision](XXXX-related-decision.md)

## References

- [Link to relevant documentation or resources]
```

## Process for Creating ADRs

1. **Identification**: Identify the need for an architectural decision
2. **Discussion**: Discuss the decision with team members
3. **Documentation**: Document the decision using the ADR template
4. **Review**: Review the ADR with stakeholders
5. **Status Update**: Update the status
   - **Proposed**: Initial creation and discussion
   - **Accepted**: Decision has been agreed upon
   - **Deprecated**: Decision is no longer relevant
   - **Superseded**: Replaced by another ADR (reference the new one)
6. **Implementation**: Implement the decision as described
7. **Update**: Update the ADR if the decision changes or evolves

## When to Create an ADR

Create an ADR when making a significant architectural decision that:

1. Has a significant impact on the system architecture
2. Affects multiple components or subsystems
3. Has long-term implications for maintenance or extensibility
4. Represents a choice between multiple viable alternatives
5. Changes a previous architectural decision

## Maintenance of ADRs

ADRs should be treated as immutable once accepted. If a decision needs to be changed:

1. Create a new ADR that references the old one
2. Update the status of the old ADR to "Superseded by ADR-XXXX"
3. Include a clear explanation of why the decision was changed

## Creating a New ADR

1. Copy the template
2. Name it using sequential numbering: `NNNN-short-title.md`
3. Update the status (typically starts as "Proposed")
4. Fill in all sections

## Current ADRs

### Core Architecture (Accepted)
- [0000-template.md](0000-template.md) - ADR Template
- [0003-base-node-interface.md](0003-base-node-interface.md) - Base Node Interface
- [0004-workflow-representation.md](0004-workflow-representation.md) - Workflow Representation
- [0005-local-execution-strategy.md](0005-local-execution-strategy.md) - Local Execution Strategy
- [0006-task-tracking-architecture.md](0006-task-tracking-architecture.md) - Task Tracking Architecture
- [0007-export-format.md](0007-export-format.md) - Export Format
- [0009-src-layout-for-package.md](0009-src-layout-for-package.md) - Source Layout for Package

### Advanced Features (Accepted)
- [0008-docker-runtime-architecture.md](0008-docker-runtime-architecture.md) - Docker Runtime Architecture
- [0010-python-code-node.md](0010-python-code-node.md) - Python Code Node
- [0011-workflow-execution-improvements.md](0011-workflow-execution-improvements.md) - Workflow Execution Improvements
- [0012-workflow-conditional-routing.md](0012-workflow-conditional-routing.md) - Workflow Conditional Routing
- [0013-simplify-conditional-logic-nodes.md](0013-simplify-conditional-logic-nodes.md) - Simplify Conditional Logic Nodes
- [0014-async-node-execution.md](0014-async-node-execution.md) - Asynchronous Node Execution & Parallel Workflow Runtime
- [0015-api-integration-architecture.md](0015-api-integration-architecture.md) - API Integration Architecture
- [0016-immutable-state-management.md](0016-immutable-state-management.md) - Immutable State Management
- [0018-performance-metrics-architecture.md](0018-performance-metrics-architecture.md) - Performance Metrics Architecture
- [0019-real-time-dashboard-architecture.md](0019-real-time-dashboard-architecture.md) - Real-time Dashboard Architecture
- [0029-mcp-ecosystem-architecture.md](0029-mcp-ecosystem-architecture.md) - MCP Ecosystem Zero-Code Workflow Builder Architecture

### Agentic AI Architecture
**Priority**: 🔴 **URGENT** - Client-driven requirements for agentic workflows

#### Accepted
- [0022-mcp-integration-architecture.md](0022-mcp-integration-architecture.md) - Model Context Protocol (MCP) Integration Architecture
- [0024-llm-agent-architecture.md](0024-llm-agent-architecture.md) - LLM Agent Architecture for Real Integration
- [0025-hierarchical-document-processing.md](0025-hierarchical-document-processing.md) - Hierarchical Document Processing for RAG
- [0026-unified-ai-provider-architecture.md](0026-unified-ai-provider-architecture.md) - Unified AI Provider Architecture (LLM + Embeddings)
- [0027-node-organization-architecture.md](0027-node-organization-architecture.md) - Node Organization and Registration Architecture
- [0028-workflow-node-hierarchical-composition.md](0028-workflow-node-hierarchical-composition.md) - WorkflowNode for Hierarchical Workflow Composition

#### Proposed
- [0023-a2a-communication-architecture.md](0023-a2a-communication-architecture.md) - Agent-to-Agent (A2A) Communication Architecture

### Package & Documentation (Accepted)
- [0020-package-distribution-strategy.md](0020-package-distribution-strategy.md) - Package Distribution Strategy
- [0021-documentation-structure.md](0021-documentation-structure.md) - Documentation Structure and Organization

### DevOps & CI/CD (Proposed)
- [0017-ci-optimization-unified-workflow.md](0017-ci-optimization-unified-workflow.md) - CI Optimization - Unified Workflow Strategy

### Deprecated/Superseded
- [0001-base-node-interface.md](0001-base-node-interface.md) - Base Node Interface Design (Superseded by 0003)
- [0002-workflow-representation.md](0002-workflow-representation.md) - Workflow Representation (Superseded by 0004)

## Project Status

As of 2025-06-03, the Kailash Python SDK has achieved major milestones:
- **100% test pass rate** (678/678 tests passing)
- **All core architectural decisions** implemented and validated
- **Hierarchical RAG** fully implemented with 7 specialized nodes
- **Workflow API Wrapper** enabling REST API exposure in 3 lines of code
- **PyPI release v0.1.2** ready with comprehensive improvements
- **Documentation structure** reorganized with 0 build warnings/errors
- **GitHub Actions** passing completely with documentation pipeline
- **Code Quality** All linting issues resolved, pre-commit hooks configured

### Next Phase: Agentic AI Implementation (Q1 2025)

The project is entering a new phase focused on agentic AI capabilities:

1. **Phase 1 Implementation** (8-10 weeks):
   - **MCP Integration**: Model Context Protocol for advanced context sharing
   - **A2A Communication**: Agent-to-Agent coordination and message passing
   - **LLM Agent Node**: Real integration with OpenAI, Anthropic, Azure OpenAI
   - **EmbeddingGeneratorNode**: Vector embeddings for RAG systems

2. **Client Requirements**: Active projects using LangChain/Langgraph need production-ready:
   - Multi-agent workflow coordination
   - Real LLM integration (not mock implementations)
   - Context sharing between AI models and tools
   - Function calling and tool execution

3. **Architecture Foundation**: New ADRs provide roadmap for:
   - MCP protocol integration patterns
   - Distributed agent communication
   - Production-ready LLM agent architecture
   - Integration with existing async and API infrastructure

## References

- [Michael Nygard's article on ADRs](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [GitHub ADR template](https://github.com/joelparkerhenderson/architecture_decision_record)
