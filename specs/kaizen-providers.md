# Kailash Kaizen -- Domain Specification — Providers, Strategies, Tools & Memory (Index)

Version: 2.13.1
Package: `kailash-kaizen`

Parent domain: Kailash Kaizen AI agent framework. This file is a thin index over the provider system, execution strategies, tool integration (MCP), memory system, error handling, and streaming support — split into self-contained sub-domain files per `specs-authority.md` Rule 8 (this file exceeded the 300-line split threshold at 489 lines). See also `kaizen-core.md`, `kaizen-signatures.md`, and `kaizen-advanced.md`.

---

## Sub-domain files

| File                                                                              | Sections | Description                                                                                                   |
| ---------------------------------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------- |
| [kaizen-providers-provider-system.md](kaizen-providers-provider-system.md)         | §8       | Provider ABC + Protocol hierarchy, `ProviderCapability`, provider registry (`get_provider`, retired dispatch), provider error hierarchy, unified types (`Message`, `ChatResponse`, `TokenUsage`, `ToolCall`, `StreamEvent`), `governance_required` posture coverage |
| [kaizen-providers-execution-strategies.md](kaizen-providers-execution-strategies.md) | §9       | `ExecutionStrategy` protocol; SingleShot / AsyncSingleShot / MultiCycle / Streaming / ParallelBatch / Fallback / HumanInLoop strategies; convergence strategies |
| [kaizen-providers-tool-integration.md](kaizen-providers-tool-integration.md)       | §10      | MCP as the sole tool-integration mechanism: builtin MCP server, tool discovery, tool execution, tool types, MCP suppression under structured output |
| [kaizen-providers-memory-system.md](kaizen-providers-memory-system.md)             | §11      | `KaizenMemory` abstract base, memory implementations (Buffer / PersistentBuffer / Summary / Vector / KnowledgeGraph), `SharedMemoryPool`, enterprise 3-tier memory, persistence backends |
| [kaizen-providers-error-handling.md](kaizen-providers-error-handling.md)           | §20      | BaseAgent `_handle_error` extension point, retry via RetryMixin, fallback strategy, provider-error wrapping   |
| [kaizen-providers-streaming.md](kaizen-providers-streaming.md)                     | §21      | `StreamingProvider` protocol, `StreamingStrategy`, `StreamEvent`, resolving a streaming provider by name or model |

Section numbers follow the parent domain's global numbering scheme shared across `kaizen-core.md` (§1, §3–§7, §25–§28), `kaizen-signatures.md` (§2, §18), `kaizen-providers-*.md` (§8–§11, §20–§21), and `kaizen-advanced.md` (§12–§17, §19, §22–§24) — a section number is stable regardless of which physical file currently hosts it.
