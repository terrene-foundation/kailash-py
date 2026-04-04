---
name: nodes-reference
description: "Comprehensive node reference documentation for all 110+ Kailash SDK nodes organized by category: AI, API, Code, Data, Database, File, Logic, Monitoring, Admin, Transaction, and Transform nodes. Use when asking about 'node reference', 'available nodes', 'node list', 'AI nodes', 'API nodes', 'code nodes', 'data nodes', 'database nodes', 'file nodes', 'logic nodes', 'monitoring nodes', 'transaction nodes', 'transform nodes', 'which nodes', 'node documentation', or 'node capabilities'."
---

# Kailash Nodes - Complete Reference

Comprehensive reference for all 110+ workflow nodes in Kailash SDK, organized by category.

## Quick Access

- **[nodes-quick-index](nodes-quick-index.md)** - Quick node lookup index

## By Category

| Category          | File                                                          | Key Nodes                                                                            |
| ----------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| AI & ML           | [nodes-ai-reference](nodes-ai-reference.md)                   | LLMNode, AnthropicNode, OpenAINode, VisionNode, AudioNode, EmbeddingNode, OllamaNode |
| API & Integration | [nodes-api-reference](nodes-api-reference.md)                 | HTTPRequestNode, WebhookNode, GraphQLNode                                            |
| Code Execution    | [nodes-code-reference](nodes-code-reference.md)               | PythonCodeNode, JavaScriptNode, BashNode                                             |
| Data Processing   | [nodes-data-reference](nodes-data-reference.md)               | CSVReaderNode, JSONParserNode, DataValidatorNode, FilterNode, MapNode                |
| Database          | [nodes-database-reference](nodes-database-reference.md)       | SQLQueryNode, AsyncSQLNode, DatabaseReadNode (+ DataFlow auto-generated)             |
| File Operations   | [nodes-file-reference](nodes-file-reference.md)               | FileReaderNode, FileWriterNode, FileWatcherNode, ZipNode                             |
| Logic & Control   | [nodes-logic-reference](nodes-logic-reference.md)             | SwitchNode, IfElseNode, LoopNode, MergeNode, SplitNode, CycleNode                    |
| Monitoring        | [nodes-monitoring-reference](nodes-monitoring-reference.md)   | LoggerNode, MetricsNode, AlertNode, HealthCheckNode                                  |
| Admin             | [nodes-admin-reference](nodes-admin-reference.md)             | ConfigNode, SecretManagerNode, SchedulerNode, CacheNode                              |
| Transactions      | [nodes-transaction-reference](nodes-transaction-reference.md) | TransactionBeginNode, SagaNode, TwoPhaseCommitNode                                   |
| Transform         | [nodes-transform-reference](nodes-transform-reference.md)     | MapperNode, AggregatorNode, EnrichNode, NormalizeNode                                |

## Node Selection by Use Case

| Task                | Recommended Node                                 |
| ------------------- | ------------------------------------------------ |
| Text generation     | LLMNode, OpenAINode, AnthropicNode               |
| Vision / Audio      | VisionNode, AudioNode                            |
| Local LLMs          | OllamaNode                                       |
| REST APIs           | HTTPRequestNode                                  |
| Webhooks / GraphQL  | WebhookNode, GraphQLNode                         |
| Custom Python logic | PythonCodeNode (most flexible)                   |
| Database CRUD       | DataFlow auto-generated nodes (not raw DB nodes) |
| CSV / JSON / XML    | CSVReaderNode, JSONParserNode, XMLParserNode     |
| File read / write   | FileReaderNode, FileWriterNode                   |
| Conditional routing | SwitchNode, IfElseNode                           |
| Loops / cycles      | LoopNode, CycleNode                              |
| Logging / metrics   | LoggerNode, MetricsNode                          |

## Critical Node Patterns

All nodes follow the **canonical 4-parameter pattern** from `/01-core-sdk`:

```python
workflow.add_node("PythonCodeNode", "node1", {"code": "result = input_data * 2"})
workflow.add_connection("node1", "result", "node2", "input_data")
```

## CRITICAL Gotchas

| Rule                             | Why                       |
| -------------------------------- | ------------------------- |
| NEVER use raw database nodes     | Use DataFlow instead      |
| ALWAYS use string-based node IDs | Variables cause issues    |
| NEVER forget `.build()`          | Required before execution |

## Related Skills

- **[01-core-sdk](../../01-core-sdk/SKILL.md)** - Core workflow patterns
- **[06-cheatsheets](../cheatsheets/SKILL.md)** - Node usage patterns
- **[07-development-guides](../development-guides/SKILL.md)** - Custom node development
- **[02-dataflow](../../02-dataflow/SKILL.md)** - Auto-generated database nodes

## Support

- `pattern-expert` - Node pattern recommendations
- `dataflow-specialist` - DataFlow-generated nodes
