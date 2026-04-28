---
name: architecture-decisions
description: "Architecture decision guides for Kailash SDK including framework selection (Core SDK vs DataFlow vs Nexus vs Kaizen), runtime selection (Async vs Sync), database selection (PostgreSQL vs SQLite), node selection, and test tier selection. Use when asking about 'which framework', 'choose framework', 'which runtime', 'which database', 'which node', 'architecture decision', 'when to use', 'Core SDK vs DataFlow', 'PostgreSQL vs SQLite', 'AsyncLocalRuntime vs LocalRuntime', or 'test tier selection'."
---

# Kailash Architecture Decisions

Decision guides for selecting the right frameworks, runtimes, databases, nodes, and testing strategies.

## Reference Documentation

| Decision  | File                                                                      | Quick Answer                                                                |
| --------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Framework | [decide-framework](decide-framework.md)                                   | Core SDK (custom), DataFlow (DB), Nexus (multi-channel), Kaizen (AI agents) |
| Runtime   | [decide-runtime](decide-runtime.md)                                       | Docker/async -> AsyncLocalRuntime; CLI/Scripts -> LocalRuntime            |
| Database  | [decide-database-postgresql-sqlite](decide-database-postgresql-sqlite.md) | Production -> PostgreSQL; Dev/Test -> SQLite                                |
| Node      | [decide-node-for-task](decide-node-for-task.md)                           | See node selection flow below                                               |
| Test Tier | [decide-test-tier](decide-test-tier.md)                                   | Unit (fast), Integration (real infra), E2E (full system)                    |

## Framework Selection Matrix

| Need                  | Framework    | Why                       |
| --------------------- | ------------ | ------------------------- |
| **Custom workflows**  | Core SDK     | Full control, 140+ nodes  |
| **Database CRUD**     | DataFlow     | Auto-generated nodes      |
| **Multi-channel API** | Nexus        | API + CLI + MCP instantly |
| **AI agents**         | Kaizen       | Signature-based agents    |
| **All of above**      | Combine them | They work together        |

## Runtime Selection Flow

```
Deploying to Docker/async/Kubernetes?
  YES -> AsyncLocalRuntime (async-first, no threads)
  NO  -> CLI/script?
    YES -> LocalRuntime (sync execution)
    NO  -> Use get_runtime() for auto-detection
```

## Database Selection Flow

```
Production deployment?     -> PostgreSQL (scalable, enterprise)
Development/testing?       -> SQLite (simple, fast setup)
High concurrency?          -> PostgreSQL (better concurrency)
```

## Node Selection Flow

```
Custom Python logic        -> PythonCodeNode
LLM/AI tasks               -> LLMNode, OpenAINode, AnthropicNode
Database operations        -> DataFlow auto-generated nodes
HTTP API calls             -> HTTPRequestNode
File reading               -> FileReaderNode
Conditional routing        -> SwitchNode
Not sure?                  -> Check nodes-quick-index
```

## Test Tier Flow

```
Individual function        -> Tier 1 (Unit)
Workflow execution         -> Tier 2 (Integration, real infrastructure)
Complete user flow         -> Tier 3 (E2E)
```

## Critical Decision Rules

### Framework

- NEVER use ORM when DataFlow can generate nodes
- NEVER build API/CLI/MCP manually when Nexus can do it

### Runtime

- Docker/async -> AsyncLocalRuntime (mandatory)
- NEVER use LocalRuntime in Docker (causes hangs)
- NEVER mix runtimes in same application

### Database

- Production -> PostgreSQL; NEVER SQLite for production high-concurrency
- NEVER skip connection pooling config
- Multi-instance -> One DataFlow per database

## Related Skills

- **[01-core-sdk](../../01-core-sdk/SKILL.md)** - Core SDK fundamentals
- **[02-dataflow](../../02-dataflow/SKILL.md)** - DataFlow framework
- **[03-nexus](../../03-nexus/SKILL.md)** - Nexus framework
- **[04-kaizen](../../04-kaizen/SKILL.md)** - Kaizen framework
- **[08-nodes-reference](../../08-nodes-reference/SKILL.md)** - Node reference
- **[12-testing-strategies](../../12-testing-strategies/SKILL.md)** - Testing strategies

## Support

- `decide-framework` skill - Framework selection and architecture
- `analyst` - Deep analysis for complex decisions
- `pattern-expert` - Pattern recommendations
