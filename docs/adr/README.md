# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Kailash Python SDK project.

## What is an ADR?

An Architecture Decision Record (ADR) is a document that captures an important architectural decision made along with its context and consequences.

## ADR Format

We use the following format for ADRs:

```markdown
# Title

## Status
[Proposed | Accepted | Deprecated | Superseded]

## Context
What is the issue motivating this decision or change?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or more difficult to do because of this change?
```

## Creating a New ADR

1. Copy the template from `0000-template.md`
2. Name it using sequential numbering: `NNNN-short-title.md`
3. Update the status (typically starts as "Proposed")
4. Fill in all sections
5. Submit for review

## ADR Workflow

1. **Proposed**: Initial creation and discussion
2. **Accepted**: Decision has been agreed upon
3. **Deprecated**: Decision is no longer relevant
4. **Superseded**: Replaced by another ADR (reference the new one)

## Current ADRs

- [0000-template.md](0000-template.md) - ADR Template
- [0001-base-node-interface.md](0001-base-node-interface.md) - Base Node Interface Design
- [0002-workflow-representation.md](0002-workflow-representation.md) - Workflow Representation
- [0003-base-node-interface.md](0003-base-node-interface.md) - Base Node Interface
- [0004-workflow-representation.md](0004-workflow-representation.md) - Workflow Representation
- [0005-local-execution-strategy.md](0005-local-execution-strategy.md) - Local Execution Strategy
- [0006-task-tracking-architecture.md](0006-task-tracking-architecture.md) - Task Tracking Architecture
- [0007-export-format.md](0007-export-format.md) - Export Format
- [0008-docker-runtime-architecture.md](0008-docker-runtime-architecture.md) - Docker Runtime Architecture
- [0009-src-layout-for-package.md](0009-src-layout-for-package.md) - Source Layout for Package
- [0010-python-code-node.md](0010-python-code-node.md) - Python Code Node
- [0011-workflow-execution-improvements.md](0011-workflow-execution-improvements.md) - Workflow Execution Improvements
- [0012-workflow-conditional-routing.md](0012-workflow-conditional-routing.md) - Workflow Conditional Routing
- [0013-simplify-conditional-logic-nodes.md](0013-simplify-conditional-logic-nodes.md) - Simplify Conditional Logic Nodes
- [0014-async-node-execution.md](0014-async-node-execution.md) - Asynchronous Node Execution & Parallel Workflow Runtime
- [0015-immutable-state-management.md](0015-immutable-state-management.md) - Immutable State Management
- [0015-api-integration-architecture.md](0015-api-integration-architecture.md) - API Integration Architecture

## References

- [Michael Nygard's article on ADRs](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [GitHub ADR template](https://github.com/joelparkerhenderson/architecture_decision_record)