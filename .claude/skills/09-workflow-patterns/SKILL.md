---
name: workflow-patterns
description: "Workflow templates: finance, healthcare, logistics, manufacturing, retail, ETL, RAG, document processing, API."
---

# Kailash Workflows - Industry Patterns & Templates

Production-ready workflow patterns and templates for industry-specific use cases and common application patterns.

## When to Use

Use these patterns when asking about workflow examples, workflow templates, industry workflows, finance workflows, healthcare workflows, logistics workflows, manufacturing workflows, retail workflows, ETL workflows, RAG workflows, API workflows, document processing, business rules, or workflow patterns.

## Industry-Specific Patterns

| Industry      | File                                                                  | Key Use Cases                                                                      |
| ------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Finance       | [workflow-industry-finance](workflow-industry-finance.md)             | Payment processing, fraud detection, risk assessment, compliance, trade settlement |
| Healthcare    | [workflow-industry-healthcare](workflow-industry-healthcare.md)       | Patient data, clinical decision support, insurance claims, HIPAA compliance        |
| Logistics     | [workflow-industry-logistics](workflow-industry-logistics.md)         | Order fulfillment, route optimization, shipment tracking, warehouse automation     |
| Manufacturing | [workflow-industry-manufacturing](workflow-industry-manufacturing.md) | Production planning, quality control, equipment monitoring, defect tracking        |
| Retail        | [workflow-industry-retail](workflow-industry-retail.md)               | Order processing, inventory, pricing optimization, returns processing              |

## Common Use Case Patterns

| Pattern            | File                                                                  | Key Use Cases                                                          |
| ------------------ | --------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| AI Document        | [workflow-pattern-ai-document](workflow-pattern-ai-document.md)       | Classification, entity extraction, OCR, form processing                |
| API Integration    | [workflow-pattern-api](workflow-pattern-api.md)                       | API orchestration, retry logic, rate limiting, error handling          |
| Business Rules     | [workflow-pattern-business-rules](workflow-pattern-business-rules.md) | Rule evaluation, decision tables, approval workflows                   |
| Cyclic             | [workflow-pattern-cyclic](workflow-pattern-cyclic.md)                 | Iterative processing, feedback loops, state machines, convergence      |
| Data Processing    | [workflow-pattern-data](workflow-pattern-data.md)                     | Validation, enrichment, aggregation, normalization                     |
| ETL                | [workflow-pattern-etl](workflow-pattern-etl.md)                       | Extraction, transformation, loading, incremental updates               |
| File Processing    | [workflow-pattern-file](workflow-pattern-file.md)                     | Bulk processing, monitoring, transformation, archive management        |
| Project Management | [workflow-pattern-project-mgmt](workflow-pattern-project-mgmt.md)     | Task automation, status tracking, resource allocation, approvals       |
| RAG                | [workflow-pattern-rag](workflow-pattern-rag.md)                       | Document indexing, vector search, context retrieval, answer generation |
| Security           | [workflow-pattern-security](workflow-pattern-security.md)             | Access control, audit logging, threat detection, incident response     |

## Quick Patterns

### ETL Workflow

```python
workflow.add_node("Extract", "extract", {"source": "..."})
workflow.add_node("Transform", "transform", {"logic": "..."})
workflow.add_node("Load", "load", {"destination": "..."})
workflow.add_connection("extract", "data", "transform", "input")
workflow.add_connection("transform", "output", "load", "data")
```

### RAG Workflow

```python
workflow.add_node("Embed", "embed", {"model": "text-embedding-ada-002"})
workflow.add_node("Search", "search", {"index": "vectors"})
workflow.add_node("Generate", "generate", {"model": os.environ["LLM_MODEL"]})
```

### ML Training Workflow (W31a spec nodes)

```python
# Train → promote through registry tiers in one workflow (skill 34-kailash-ml is authority)
workflow.add_node("MLTrainingNode", "train", {"engine": "sklearn", "model_name": "churn", "task": "classification"})
workflow.add_node("MLRegistryPromoteNode", "promote", {"model_name": "churn", "tier": "staging"})
workflow.add_connection("train", "model_uri", "promote", "model_uri")
```

## Pattern Structure

Each sub-file includes: overview, architecture, nodes used, configuration, example code, best practices, testing strategies.

## CRITICAL Warnings

| Rule                      | Reason                    |
| ------------------------- | ------------------------- |
| NEVER hardcode secrets    | Use environment variables |
| ALWAYS validate inputs    | At workflow boundaries    |
| NEVER skip error handling | Required in production    |

## Related Skills

- **[01-core-sdk](../../01-core-sdk/SKILL.md)** - Core workflow creation
- **[06-cheatsheets](../cheatsheets/SKILL.md)** - Pattern quick reference
- **[08-nodes-reference](../nodes/SKILL.md)** - Node reference
- **[02-dataflow](../../02-dataflow/SKILL.md)** - Database workflows
- **[03-nexus](../../03-nexus/SKILL.md)** - Workflow deployment
- **[17-gold-standards](../../17-gold-standards/SKILL.md)** - Best practices

## Support

- `pattern-expert` - Workflow pattern selection and design
- `decide-framework` skill - Architecture decisions
- `testing-specialist` - Pattern testing strategies
