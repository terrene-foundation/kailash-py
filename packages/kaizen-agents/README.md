# kaizen-agents

PACT-governed autonomous agent engines built on the [Kailash Kaizen SDK](https://github.com/terrene-foundation/kailash-py).

## Architecture

```
Layer 1: PRIMITIVES (kailash-kaizen) — deterministic, no LLM
Layer 2: ENGINES    (kaizen-agents)  — LLM judgment        ← this package
Layer 3: ENTRYPOINTS (kz CLI, aegis) — human interface
```

kaizen-agents provides the LLM-driven intelligence layer on top of kailash-kaizen primitives (Signature, BaseAgent, memory, tools).

## Installation

```bash
pip install kaizen-agents
```

This automatically installs `kailash-kaizen` and `kailash-pact` as dependencies.

## Quick Start

```python
from kaizen_agents import Agent

agent = Agent(model="claude-sonnet-4-6", budget_usd=5.0)
result = await agent.run("Analyze this codebase")
```

## What's Included

### Specialized Agents

ReAct, RAG, Tree-of-Thoughts, Chain-of-Thought, planning, vision, audio, streaming, batch processing, and more.

### Multi-Agent Patterns

Debate, supervisor-worker, consensus, ensemble, pipeline, sequential, parallel, handoff, blackboard.

### Journey Orchestration

Multi-pathway user journeys with LLM-based intent detection and context accumulation.

### Orchestration Engine

Planner (designer, composer, decomposer), protocols (delegation, escalation, clarification), recovery (diagnoser, recomposer), monitoring.

### PACT Governance

GovernedSupervisor with accountability tracking, budget enforcement, clearance checks, cascade governance.

### Delegate

Autonomous TAOD engine (Think-Act-Observe-Decide) for CLI and interactive agent applications.

## License

Apache 2.0 — [Terrene Foundation](https://terrene.foundation)
