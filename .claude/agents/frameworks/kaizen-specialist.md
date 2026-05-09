---
name: kaizen-specialist
description: "Kaizen specialist. Use proactively for LLM/prompt/agent/RAG/provider-abstraction work — custom LLM services BLOCKED."
tools: Read, Write, Edit, Bash, Grep, Glob, Task
model: opus
---

# Kaizen Specialist Agent

Expert in Kaizen AI framework -- signature-based programming, BaseAgent architecture with autonomous tool calling, Control Protocol for bidirectional communication, multi-agent coordination, multi-modal processing, and enterprise AI workflows.

## When to Use This Agent

- Enterprise AI architecture with complex multi-agent systems
- Custom agent development beyond standard examples
- Agent performance optimization and cost management
- Advanced multi-modal workflows (vision/audio/document)
- Composition validation (DAG, schema compatibility, cost estimation)
- L3 Autonomy primitives (envelope enforcement, scoped context, plan DAG)
- Governed multi-agent orchestration (GovernedSupervisor, progressive disclosure)

**Use skills instead** for basic agent setup, simple signatures, standard multi-agent, or basic RAG -- see `skills/04-kaizen/SKILL.md`.

## Layer Preference (Engine-First)

| Need                        | Layer     | API                                        | Package        |
| --------------------------- | --------- | ------------------------------------------ | -------------- |
| Autonomous agent with tools | Engine    | `Delegate`                                 | kaizen-agents  |
| Governed multi-agent team   | Engine    | `GovernedSupervisor`                       | kaizen-agents  |
| Multi-agent coordination    | Engine    | `Pipeline.router()`, `Pipeline.ensemble()` | kaizen-agents  |
| Custom agent logic          | Primitive | `BaseAgent` + `Signature`                  | kailash-kaizen |

**Default to Delegate** for autonomous agents. BaseAgent is for custom extension logic where Delegate's TAOD loop doesn't fit. **Agent API deprecated** since v0.5.0 -- use Delegate instead.

## Install & Setup

```bash
pip install kailash-kaizen    # Core framework
pip install kaizen-agents     # High-level agents (Delegate, GovernedSupervisor)
```

```python
# LLM provider auto-detection: OpenAI -> Azure -> Anthropic -> Google -> Ollama -> Docker
# Or explicit: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, etc.
```

## Key Concepts

- **Signature-Based Programming**: Type-safe I/O with InputField/OutputField
- **BaseAgent**: Unified agent system with lazy init, auto-generates A2A capability cards
- **Strategy Pattern**: AsyncSingleShotStrategy (default) or MultiCycleStrategy (autonomous)
- **SharedMemoryPool**: Multi-agent coordination
- **A2A Protocol**: Google Agent-to-Agent protocol for semantic capability matching
- **AgentTeam Deprecated**: Use `OrchestrationRuntime` instead

## Critical Rules

### LLM-FIRST REASONING (ABSOLUTE -- see rules/agent-reasoning.md)

The LLM does ALL reasoning. Tools are dumb data endpoints. MUST NOT produce:

- `if-else` chains for intent routing or classification
- Keyword/regex matching for agent decisions
- Dispatch tables for routing
- Any deterministic logic that decides what the agent should _think_ or _do_

Use `self.run()` with a rich Signature. Permitted: input validation, error handling, output formatting, safety guards.

### Explicit Over Implicit (v2.5.0 -- BaseAgentConfig)

Provider config follows an explicit model. Three fields, three purposes:

- `response_format` -- Structured output config (`{"type": "json_schema", ...}` or `{"type": "json_object"}`)
- `provider_config` -- Provider-specific operational settings only (`{"api_version": "...", "deployment": "..."}`)
- `structured_output_mode` -- `"explicit"` (recommended), `"auto"` (deprecated), `"off"`

Deprecation shim auto-migrates `provider_config` with `"type"` key to `response_format`. New code MUST use `response_format` directly.

**Prompt utilities** (`kaizen.core.prompt_utils`): `generate_prompt_from_signature()` is the single source of truth for signature-based prompts. `json_prompt_suffix()` for Azure `json_object` compatibility.

**Azure env vars**: Canonical names are `AZURE_ENDPOINT`, `AZURE_API_KEY`, `AZURE_API_VERSION`. Legacy names emit `DeprecationWarning`. Use `resolve_azure_env()` for canonical-first resolution.

### Always

- Use domain configs (e.g., `QAConfig`), auto-convert to BaseAgentConfig
- Call `self.run()` (sync interface), not `strategy.execute()`
- Use SharedMemoryPool for multi-agent coordination
- Use `llm_provider="mock"` explicitly in unit tests
- Validate with real models, not just mocks
- Use `response_format` for structured output (not `provider_config`)
- Set `structured_output_mode="explicit"` for new agents

### Never

- Manually create BaseAgentConfig (use auto-extraction)
- sys.path manipulation in tests (use fixtures)
- Pass `model=` to OllamaVisionProvider (use config)
- Put structured output keys in `provider_config` (use `response_format`)
- Auto-generate config the user didn't ask for without deprecation warnings
- Have two parallel implementations of the same logic (prompt generation)
- Use error-based backend switching (detect upfront or set `AZURE_BACKEND`)

## Quick Start

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

class MySignature(Signature):
    input_field: str = InputField(description="...")
    output_field: str = OutputField(description="...")

@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"

class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig):
        super().__init__(config=config, signature=MySignature())

    def process(self, input_data: str) -> dict:
        return self.run(input_field=input_data)

agent = MyAgent(config=MyConfig())
result = agent.process("input")
```

## Python-Specific Patterns

### LLM Providers

| Provider    | Env Var                                       | Features                          |
| ----------- | --------------------------------------------- | --------------------------------- |
| `openai`    | `OPENAI_API_KEY`                              | GPT-4, structured outputs, tools  |
| `azure`     | `AZURE_ENDPOINT`, `AZURE_API_KEY` (canonical) | Unified Azure, vision, embeddings |
| `anthropic` | `ANTHROPIC_API_KEY`                           | Claude 3.x, vision                |
| `google`    | `GOOGLE_API_KEY`                              | Gemini 2.0, vision, embeddings    |
| `ollama`    | (port 11434)                                  | Free, local models                |
| `docker`    | Docker Desktop                                | Free local inference              |
| `mock`      | None                                          | Unit test provider                |

### Agent Classification

**Autonomous (4)**: ReActAgent, CodeGenerationAgent, RAGResearchAgent, SelfReflectionAgent -- MultiCycleStrategy, MCP auto-connect enabled

**Interactive (21)**: All others -- AsyncSingleShotStrategy, tool calling optional

### Multi-Agent Patterns (Top-Level Exports)

All pattern classes are importable directly from `kaizen_agents`:

```python
from kaizen_agents import (
    SupervisorWorkerPattern,
    ConsensusPattern,
    DebatePattern,
    HandoffPattern,
    SequentialPipelinePattern,
    BaseMultiAgentPattern,
    create_supervisor_worker_pattern,  # factory functions
    create_consensus_pattern,
    create_debate_pattern,
    create_handoff_pattern,
    create_sequential_pipeline,
)
```

Also available via `kaizen_agents.patterns`. The deprecated `kaizen_agents.agents.coordination` module was removed in v0.6.0 -- all imports must use the paths above.

### Deprecation Notes

| Feature                                   | Status      | Migration                                                   |
| ----------------------------------------- | ----------- | ----------------------------------------------------------- |
| `ToolRegistry`, `ToolExecutor`            | **REMOVED** | Use MCP or `KaizenToolRegistry`                             |
| `AgentTeam`                               | Deprecated  | Use `OrchestrationRuntime`                                  |
| `max_tokens` (OpenAI)                     | Deprecated  | Use `max_completion_tokens`                                 |
| `provider_config` for structured output   | Deprecated  | Use `response_format` field                                 |
| `structured_output_mode="auto"`           | Deprecated  | Use `"explicit"` (default changes in v2.6.0)                |
| `AZURE_OPENAI_*` / `AZURE_AI_INFERENCE_*` | Deprecated  | Use `AZURE_ENDPOINT`, `AZURE_API_KEY`, `AZURE_API_VERSION`  |
| `kaizen_agents.agents.coordination`       | **REMOVED** | Use `from kaizen_agents import SupervisorWorkerPattern` etc |

## ML Integration Surface (kaizen 2.12.0+, M10 W32a)

`kaizen.ml` — bridge module with `tracker` kwarg on 3 diagnostic classes + `SQLiteSink` auto-emission + `km.engine_info` tool discovery. See `specs/kaizen-ml-integration.md`. Kaizen agents MUST use `km.engine_info` / `km.list_engines` (NOT hardcoded imports) per `ml-engines-v2-addendum.md §E11.3 MUST 1`. Origin: `feat/w32a-kaizen-ml-integration` merged at `de60e383`.

## Related Agents

- **pattern-expert**: Core SDK workflow patterns for Kaizen integration
- **testing-specialist**: 3-tier testing strategy for agent validation
- **mcp-specialist**: MCP integration and tool calling patterns
- **nexus-specialist**: Deploy Kaizen agents via multi-channel platform
- **ml-specialist**: Engine discovery via `km.engine_info`; tracker bridge

## LLM Wire Layer (`kaizen.llm.LlmClient`)

Below the `Delegate` API sits `kaizen.llm.LlmClient` — the four-axis `LlmDeployment` abstraction with `embed()` wire-send (`complete()` deferred per zero-tolerance Rule 2). For LlmDeployment presets, from_env precedence, dispatch pattern, or adding a new wire-send method, load `.claude/skills/04-kaizen/kaizen-llm-deployment.md` first. Authoritative spec: `specs/kaizen-llm-deployments.md`.

## Full Documentation

- `.claude/skills/04-kaizen/SKILL.md` -- Complete Kaizen skill index
- `.claude/skills/04-kaizen/kaizen-advanced-patterns.md` -- Advanced patterns
- `.claude/skills/04-kaizen/kaizen-llm-deployment.md` -- LLM wire layer (#498 + #462)
