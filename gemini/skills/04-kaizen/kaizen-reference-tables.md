---
skill: kaizen-reference-tables
description: Kaizen reference tables for LLM providers, deprecations, agent classification, and model selection
priority: MEDIUM
tags: [kaizen, reference, providers, deprecation, models, agents]
---

# Kaizen Reference Tables

Quick-reference tables for Kaizen framework versions, providers, and classifications.

## LLM Providers (v0.8.2)

| Provider    | Type    | Requirements                      | Features                                            |
| ----------- | ------- | --------------------------------- | --------------------------------------------------- |
| `openai`    | Cloud   | `OPENAI_API_KEY`                  | GPT-4, GPT-4o, structured outputs, tool calling     |
| `azure`     | Cloud   | `AZURE_ENDPOINT`, `AZURE_API_KEY` | Unified Azure, vision, embeddings, reasoning models |
| `anthropic` | Cloud   | `ANTHROPIC_API_KEY`               | Claude 3.x, vision support                          |
| `google`    | Cloud   | `GOOGLE_API_KEY`                  | Gemini 2.0, vision, embeddings, tool calling        |
| `ollama`    | Local   | Ollama on port 11434              | Free, local models                                  |
| `docker`    | Local   | Docker Desktop Model Runner       | Free local inference                                 |
| `mock`      | Testing | None                              | Unit test provider                                  |

**Auto-Detection Priority**: OpenAI -> Azure -> Anthropic -> Google -> Ollama -> Docker

## Agent Classification

**Autonomous Agents (4)**: ReActAgent, CodeGenerationAgent, RAGResearchAgent, SelfReflectionAgent

- Multi-cycle execution with tool calling REQUIRED
- Use MultiCycleStrategy by default
- MCP tool discovery ENABLED by default (`mcp_enabled=True` / `mcp_discovery_enabled=True`)
- ALL reasoning happens in the LLM -- tools are dumb data endpoints (see rules/agent-reasoning.md)

**Interactive Agents (21)**: All other agents

- Single-shot execution (AsyncSingleShotStrategy)
- Tool calling OPTIONAL

**Universal MCP Support**: ALL 25 agents support MCP auto-connect with 12 builtin tools

## Model Selection Guide

| Model     | Size  | Speed | Accuracy | Cost       | Best For             |
| --------- | ----- | ----- | -------- | ---------- | -------------------- |
| bakllava  | 4.7GB | 2-4s  | 40-60%   | $0         | Development, testing |
| llava:13b | 7GB   | 4-8s  | 80-90%   | $0         | Production (local)   |
| GPT-4V    | API   | 1-2s  | 95%+     | ~$0.01/img | Production (cloud)   |

## Deprecation Notes (v1.0)

| Feature                         | Status                             | Migration                                                                           |
| ------------------------------- | ---------------------------------- | ----------------------------------------------------------------------------------- |
| `ToolRegistry`, `ToolExecutor`  | **REMOVED**                        | Use MCP via `BaseAgent.execute_mcp_tool()` or `KaizenToolRegistry` for native tools |
| `kaizen.agents.coordination`    | **DEPRECATED** (removal in v0.5.0) | Use `kaizen.orchestration.patterns`                                                 |
| `max_tokens` (OpenAI providers) | **DEPRECATED**                     | Use `max_completion_tokens` instead                                                 |
| `AgentTeam`                     | **DEPRECATED**                     | Use `OrchestrationRuntime` for multi-agent coordination                             |

## Key Concepts Quick Reference

- **Signature-Based Programming**: Type-safe I/O with InputField/OutputField
- **BaseAgent**: Unified agent system with lazy initialization, auto-generates A2A capability cards
- **Autonomous Tool Calling** (v0.2.0): 12 builtin tools with danger-level approval workflows
- **Control Protocol** (v0.2.0): Bidirectional agent-client communication (CLI, HTTP/SSE, stdio, memory)
- **Observability** (v0.5.0): Complete monitoring stack (tracing, metrics, logging, audit)
- **Lifecycle Infrastructure** (v0.5.0): Hooks, State, Interrupts for event-driven control
- **Permission System** (v0.5.0+): Policy-based access control with budget enforcement
- **Persistent Buffer Memory** (v0.6.0): DataFlow backend for conversation persistence
- **Strategy Pattern**: Pluggable execution (AsyncSingleShotStrategy is default)
- **SharedMemoryPool**: Multi-agent coordination
- **A2A Protocol**: Google Agent-to-Agent protocol for semantic capability matching
- **CARE/EATP Trust Framework** (v1.2.1): Cryptographic trust chains, 5-posture enum with state machine
- **FallbackRouter Safety Hardening**: `on_fallback` callback, WARNING-level logging, model capability validation
- **AgentTeam Deprecated**: Use `OrchestrationRuntime` instead for multi-agent coordination
- **MCP Session Wiring**: `discover_mcp_resources()`, `read_mcp_resource()`, `discover_mcp_prompts()`, `get_mcp_prompt()`
- **Performance Caches** (v1.0): 7 caches with 10-100x speedup (Schema, Embedding, Prompt, etc.)
- **GPT-5 Support** (v1.0): Automatic temperature=1.0 enforcement, 8000 max_tokens for reasoning
- **Agent Manifest & Deploy** (v1.3): TOML-based agent declaration with governance metadata
- **Composition Validation** (v1.3): DAG cycle detection, JSON Schema structural subtyping, cost estimation
- **MCP Catalog Server** (v1.3): `CatalogMCPServer` with 11 tools, 14 pre-seeded agents
- **Posture-Budget Integration** (v1.3): `PostureBudgetIntegration` with configurable thresholds

## Examples Directory

**Location**: the Kaizen examples directory

- **1-single-agent/** (10): simple-qa, chain-of-thought, rag-research, code-generation, memory-agent, react-agent, self-reflection, human-approval, resilient-fallback, streaming-chat
- **2-multi-agent/** (6): consensus-building, debate-decision, domain-specialists, producer-consumer, shared-insights, supervisor-worker
- **3-enterprise-workflows/** (5): compliance-monitoring, content-generation, customer-service, data-reporting, document-analysis
- **4-advanced-rag/** (5): agentic-rag, federated-rag, graph-rag, multi-hop-rag, self-correcting-rag
- **5-mcp-integration/** (3): agent-as-client, agent-as-server, auto-discovery-routing
- **8-multi-modal/** (6): image-analysis, audio-transcription, document-understanding, document-rag
