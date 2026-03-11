"""
Autonomous Agent Patterns for Kaizen Framework.

This module provides proven autonomous agent architectures based on
Claude Code and Codex patterns, enabling truly autonomous AI agents
capable of multi-hour execution sessions.

## Key Components

### Base Pattern
- `BaseAutonomousAgent`: Foundational autonomous agent with agent loop pattern
- `AutonomousConfig`: Base configuration for autonomous agents

### Specialized Implementations
- `ClaudeCodeAgent`: Implements Claude Code's 15-tool autonomous coding workflow
- `ClaudeCodeConfig`: Configuration for Claude Code pattern
- `CodexAgent`: Implements Codex's container-based PR generation workflow
- `CodexConfig`: Configuration for Codex pattern

## Usage

### Basic Autonomous Agent

```python
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig

config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=20,
    planning_enabled=True
)

agent = BaseAutonomousAgent(config=config)
result = await agent.execute_autonomously("Build a REST API with tests")
```

### Claude Code Pattern

```python
from kaizen.agents.autonomous import ClaudeCodeAgent, ClaudeCodeConfig

config = ClaudeCodeConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=100,
    context_threshold=0.92,
    enable_diffs=True
)

agent = ClaudeCodeAgent(config=config)
result = await agent.execute_autonomously("Refactor authentication module")
```

### Codex Pattern

```python
from kaizen.agents.autonomous import CodexAgent, CodexConfig

config = CodexConfig(
    llm_provider="openai",
    model="gpt-4",
    timeout_minutes=30,
    agents_md_path="AGENTS.md"
)

agent = CodexAgent(config=config)
result = await agent.execute_autonomously("Fix bug #123 and add tests")
```

## Architecture

All autonomous agents extend `BaseAgent` and use `MultiCycleStrategy` for
iterative execution. The key pattern is:

```
while tool_calls_exist:
    gather_context()  # Read files, search code
    take_action()     # Edit files, run commands
    verify()          # Check results, run tests
    iterate()         # Update plan, continue
```

Convergence is detected objectively via the `tool_calls` field from LLM
responses, following Claude Code's proven `while(tool_call_exists)` pattern.

## References

- Claude Code Architecture: `docs/research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md`
- Codex Architecture: `docs/research/CODEX_AUTONOMOUS_ARCHITECTURE.md`
- ADR-013: Objective Convergence Detection
"""

# Base autonomous agent
from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent

# Specialized agents
from kaizen.agents.autonomous.claude_code import ClaudeCodeAgent, ClaudeCodeConfig
from kaizen.agents.autonomous.codex import CodexAgent, CodexConfig

__all__ = [
    # Base pattern
    "BaseAutonomousAgent",
    "AutonomousConfig",
    # Specialized implementations
    "ClaudeCodeAgent",
    "ClaudeCodeConfig",
    "CodexAgent",
    "CodexConfig",
]

__version__ = "0.1.0"
