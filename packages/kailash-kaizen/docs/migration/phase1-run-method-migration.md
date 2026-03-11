# Phase 1 Migration Guide: Universal .run() Method

## Overview

Phase 1 of the Unified Agent Framework standardizes all 17 agent types to use a single `.run()` method for execution, replacing domain-specific methods. This migration guide shows you how to update your code.

## Quick Migration

### Before (Phase 0)
```python
from kaizen.agents import SimpleQAAgent, ReActAgent, VisionAgent

# Different methods for each agent type
qa_agent = SimpleQAAgent(config)
answer = qa_agent.ask("What is AI?")  # ❌ Removed

react_agent = ReActAgent(config)
result = react_agent.solve_task("Build a website")  # ❌ Removed

vision_agent = VisionAgent(config)
analysis = vision_agent.analyze(image="photo.jpg", question="What is this?")  # ❌ Removed
```

### After (Phase 1)
```python
from kaizen.agents import SimpleQAAgent, ReActAgent, VisionAgent

# Universal .run() method for all agents
qa_agent = SimpleQAAgent(config)
answer = qa_agent.run(question="What is AI?")  # ✅ Universal method

react_agent = ReActAgent(config)
result = react_agent.run(task="Build a website")  # ✅ Universal method

vision_agent = VisionAgent(config)
analysis = vision_agent.run(image="photo.jpg", question="What is this?")  # ✅ Universal method
```

## Changed Methods by Agent Type

### Specialized Agents (8 agents)

#### SimpleQAAgent
```python
# OLD
result = agent.ask("What is AI?")

# NEW
result = agent.run(question="What is AI?")
```

#### ChainOfThoughtAgent
```python
# OLD
result = agent.solve_problem("Explain quantum computing")

# NEW
result = agent.run(problem="Explain quantum computing")
```

#### ReActAgent
```python
# OLD
result = agent.solve_task("Create a Python script")

# NEW
result = agent.run(task="Create a Python script")
```

#### RAGResearchAgent
```python
# OLD
result = agent.research("What are transformers?", context="ML research")

# NEW
result = agent.run(query="What are transformers?", context="ML research")
```

#### CodeGenerationAgent
```python
# OLD
result = agent.generate_code("Create a REST API")

# NEW
result = agent.run(task="Create a REST API")
```

#### SelfReflectionAgent
```python
# OLD
result = agent.reflect("Improve this code", previous_attempts=[...])

# NEW
result = agent.run(task="Improve this code", previous_attempts=[...])
```

#### MemoryAgent
```python
# OLD
result = agent.chat("What did we discuss?", session_id="user123")

# NEW
result = agent.run(message="What did we discuss?", session_id="user123")
```

#### StreamingChatAgent
```python
# OLD - Streaming was via separate method
for chunk in agent.chat_stream("Hello"):
    print(chunk)

# NEW - Streaming via .run() with stream=True parameter
result = agent.run(message="Hello", stream=True)
for chunk in result:
    print(chunk)
```

### Enterprise Agents (3 agents)

#### BatchProcessingAgent
```python
# OLD
results = agent.process_batch([item1, item2, item3])

# NEW
results = agent.run(items=[item1, item2, item3])
```

#### HumanApprovalAgent
```python
# OLD
result = agent.execute_with_approval("Sensitive operation")

# NEW
result = agent.run(task="Sensitive operation", require_approval=True)
```

#### ResilientAgent
```python
# OLD
result = agent.execute_with_retry("May fail operation", max_retries=3)

# NEW
result = agent.run(task="May fail operation", max_retries=3)
```

### Multi-Modal Agents (3 agents)

#### VisionAgent
```python
# OLD
result = agent.analyze(image="receipt.jpg", question="What is the total?")

# NEW
result = agent.run(image="receipt.jpg", question="What is the total?")
```

#### TranscriptionAgent
```python
# OLD
result = agent.transcribe(audio="meeting.mp3")

# NEW
result = agent.run(audio="meeting.mp3")
```

#### MultiModalAgent
```python
# OLD
result = agent.process(image="chart.png", audio="narration.mp3", query="Explain this")

# NEW
result = agent.run(image="chart.png", audio="narration.mp3", query="Explain this")
```

### Autonomous Agents (3 agents)

#### BaseAutonomousAgent
```python
# OLD
result = agent.plan_and_execute("Complex multi-step task")

# NEW
result = agent.run(goal="Complex multi-step task")
```

#### CodexAgent (OpenAI Codex Integration)
```python
# OLD
result = agent.generate("Write a sorting algorithm")

# NEW
result = agent.run(prompt="Write a sorting algorithm")
```

#### ClaudeCodeAgent (Claude Code Integration)
```python
# OLD
result = agent.execute_command("/ask What is the codebase structure?")

# NEW
result = agent.run(command="/ask What is the codebase structure?")
```

## Return Value Format

All agents now return consistent dictionary structures via `.run()`:

```python
result = agent.run(...)  # Returns Dict[str, Any]

# Access fields based on agent's signature
answer = result.get("answer")          # SimpleQAAgent
code = result.get("code")              # CodeGenerationAgent
transcription = result.get("text")     # TranscriptionAgent
analysis = result.get("description")   # VisionAgent
```

## Breaking Changes

**IMPORTANT**: Phase 1 has zero backward compatibility because Kaizen was not yet operational.

### Removed Methods
All domain-specific execution methods have been **removed**:
- `.ask()` (SimpleQAAgent)
- `.solve_task()` (ReActAgent)
- `.solve_problem()` (ChainOfThoughtAgent)
- `.analyze()` (VisionAgent)
- `.transcribe()` (TranscriptionAgent)
- `.research()` (RAGResearchAgent)
- `.generate_code()` (CodeGenerationAgent)
- `.chat()` (MemoryAgent)
- `.reflect()` (SelfReflectionAgent)
- `.process_batch()` (BatchProcessingAgent)
- `.execute_with_approval()` (HumanApprovalAgent)
- `.execute_with_retry()` (ResilientAgent)
- `.process()` (MultiModalAgent)
- `.plan_and_execute()` (BaseAutonomousAgent)
- `.generate()` (CodexAgent)
- `.execute_command()` (ClaudeCodeAgent)

### Migration Timeline
Since Kaizen was not operational before Phase 1:
- **No transition period** - all methods removed immediately
- **No deprecation warnings** - clean break from Phase 0
- **Examples updated** - all 35+ examples use `.run()`

## Testing Your Migration

### Unit Tests
```python
import pytest
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

def test_qa_agent_run_method():
    """Verify .run() method works."""
    config = QAConfig(llm_provider="mock")
    agent = SimpleQAAgent(config)

    # Use .run() method
    result = agent.run(question="What is 2+2?")

    # Verify result structure
    assert "answer" in result
    assert isinstance(result, dict)

def test_old_methods_removed():
    """Verify old methods are removed."""
    config = QAConfig(llm_provider="mock")
    agent = SimpleQAAgent(config)

    # Old method should not exist
    assert not hasattr(agent, "ask")
```

### Integration Tests
```python
import pytest
from kaizen.agents import VisionAgent, VisionAgentConfig

@pytest.mark.integration
def test_vision_agent_run_method():
    """Verify VisionAgent .run() with real inference."""
    config = VisionAgentConfig(
        llm_provider="ollama",
        model="llava"
    )
    agent = VisionAgent(config)

    # Use .run() method with real image
    result = agent.run(
        image="test_images/receipt.jpg",
        question="What is the total amount?"
    )

    # Verify result
    assert "answer" in result
    assert result["cost"] >= 0.0  # Ollama is free
```

## Common Pitfalls

### 1. Parameter Name Changes
Some parameters changed names during standardization:

```python
# ❌ WRONG - Old parameter name
result = agent.run(prompt="Hello")  # VisionAgent used 'prompt' before

# ✅ CORRECT - New parameter name
result = agent.run(question="Hello")  # Now uses 'question'
```

### 2. Return Key Names
Return dictionary keys are consistent with agent signatures:

```python
# ❌ WRONG - Accessing wrong key
result = agent.run(image="photo.jpg", question="What is this?")
description = result["response"]  # 'response' doesn't exist

# ✅ CORRECT - Use correct key from signature
description = result["answer"]  # VisionAgent returns 'answer'
```

### 3. Streaming Results
Streaming is now a parameter, not a separate method:

```python
# ❌ WRONG - Trying to use old streaming method
for chunk in agent.chat_stream("Hello"):
    print(chunk)

# ✅ CORRECT - Use stream parameter
result = agent.run(message="Hello", stream=True)
for chunk in result:
    print(chunk)
```

## Additional Resources

- **API Reference**: See `docs/reference/api-reference.md` for complete `.run()` signatures
- **Examples**: All 35+ examples updated in `examples/`
- **Test Suite**: 500+ tests updated to use `.run()` in `tests/`
- **Agent Registration**: See `docs/guides/agent-registration.md` for dual registration system

## Need Help?

- **Examples Directory**: `examples/1-single-agent/` contains updated basic patterns
- **Test Files**: `tests/unit/agents/specialized/` shows correct usage
- **Documentation**: Complete API reference in `docs/reference/api-reference.md`

---

**Migration Completed**: 2025-10-27
**Phase**: 1 (Days 1-5)
**Breaking Changes**: All domain-specific methods removed
**Agents Updated**: 17 (11 specialized, 3 enterprise, 3 multi-modal, 3 autonomous)
