---
priority: 0
scope: baseline
cli_delivery: baseline
---

# Framework-First: Use the Highest Abstraction Layer

<!-- slot:neutral-body -->

## ABSOLUTE: Work-Domain → Framework Binding

| Work domain                                                           | MANDATORY framework       |
| --------------------------------------------------------------------- | ------------------------- |
| Workflow orchestration, node building, runtime, parameters            | **Core SDK** (foundation) |
| LLM, prompts, completions, embeddings, agents, RAG, multi-agent       | **Kaizen**                |
| DB schema, queries, CRUD, migrations, repositories, pools, cache      | **DataFlow**              |
| Data pipelines, ETL, fabric, feature stores                           | **DataFlow** (+ ML)       |
| HTTP API, REST, gateway, middleware, login, sessions, websockets      | **Nexus**                 |
| MCP servers, tools, resources, transports, exposing APIs as LLM tools | **MCP**                   |
| LLM fine-tuning, LoRA, DPO/SFT, model serving                         | **Align**                 |
| ML training, inference, drift, AutoML, feature stores                 | **ML**                    |
| Governance, RBAC, policy, access control, envelopes, audit            | **PACT**                  |

**Auth split**: Nexus owns authentication (login, sessions, JWT middleware). PACT owns authorization (RBAC, policy, role, permission, access control).

Default to Engines. Drop to Primitives only when Engines can't express the behavior. Never use Raw. The framework specialists for each domain auto-invoke proactively; this rule is the always-on brief-form mandate.

**Why:** Rolling your own LLM service, custom HTTP gateway, or hand-rolled repository class is the #1 source of "we'll migrate later" debt that never migrates. The framework choice MUST be made before the first line of code.

## Raw Is Always Wrong

When a Kailash framework exists for your use case, MUST NOT write raw code that duplicates framework functionality.

**Why:** Raw code bypasses framework guarantees (validation, audit logging, connection pooling, dialect portability), creating maintenance debt that grows with every framework upgrade.

**Depth → `framework-first` skill**: the four-layer hierarchy, DO/DO-NOT examples, the specialist-consultation pattern-lookup table, the version-stable external-integration discipline, and the Rust-bindings framing. The specialist-consultation MANDATE is always-on via `rules/agents.md` § Specialist Delegation — consult the named specialist before any raw/primitive pattern (`zero-tolerance.md` Rule 4 otherwise).

<!-- /slot:neutral-body -->

Origin: the work-domain → framework binding mandate is the highest-leverage defense against raw-code-bypass debt (the #1 source of "we'll migrate later" that never migrates), which is what makes it baseline-worthy. Promoted path-scoped → baseline + depth extracted to the `framework-first` skill per journal/0237 (#408 AC#5-c, Rule-10 paired extraction).
