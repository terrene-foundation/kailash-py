# Autonomous Agent Decision Matrix

**Author**: Kaizen Framework Team
**Date**: 2025-10-22
**Purpose**: Define clear criteria for when agents should use autonomous (MultiCycleStrategy) vs single-shot execution

---

## Executive Summary

**Core Principle**: Not all agents should be autonomous. Autonomous execution is for agents with **iterative refinement loops** without clear termination conditions. Single-shot execution is for agents with **deterministic, one-time outputs**.

**Critical Insight**: Using autonomous execution unnecessarily wastes tokens and time. Using single-shot execution on iterative agents prevents them from completing their tasks properly.

---

## Decision Criteria

### Use **Autonomous Execution** (MultiCycleStrategy) When:

1. ✅ **Feedback Loops Required**
   - Agent needs to observe results and adjust strategy
   - Example: ReAct (Reason → Act → Observe → Repeat)

2. ✅ **Iterative Refinement**
   - Agent improves output through multiple attempts
   - Example: CodeGeneration (Generate → Test → Fix → Repeat)

3. ✅ **Tool Interaction**
   - Agent calls external tools and processes results
   - Example: RAGResearch (Query → Fetch → Analyze → Query Again)

4. ✅ **No Clear Termination Point**
   - Agent decides when task is complete (convergence detection)
   - Example: Research (explore until comprehensive)

5. ✅ **Multi-Step Reasoning with Branching**
   - Agent explores different paths dynamically
   - Example: SelfReflection (Think → Critique → Revise → Repeat)

6. ✅ **External State Changes**
   - Agent modifies external state (files, databases) and verifies changes
   - Example: Code modification + testing cycles

### Use **Single-Shot Execution** (Default) When:

1. ✅ **Deterministic Output**
   - Agent produces single, final answer
   - Example: SimpleQA (Question → Answer)

2. ✅ **Clear Termination**
   - Task completes in one pass
   - Example: VisionAgent (Image → Description)

3. ✅ **No Tool Interaction**
   - Agent only processes inputs to outputs
   - Example: ChainOfThought (structured reasoning, one pass)

4. ✅ **Streaming/Batch Processing**
   - Agent processes stream of inputs independently
   - Example: StreamingChat (each message independent)

5. ✅ **Delegation Only**
   - Agent just delegates to other agents
   - Example: Supervisor (routes tasks, doesn't iterate)

---

## Agent Classification Matrix

### Specialized Agents (11 total)

| Agent | Mode | Rationale | Max Cycles |
|-------|------|-----------|------------|
| **ReActAgent** | 🔄 Autonomous | Reason→Act→Observe feedback loops, tool interaction | 10 |
| **RAGResearchAgent** | 🔄 Autonomous | Iterative research: query→fetch→analyze→refine | 10-15 |
| **CodeGenerationAgent** | 🔄 Autonomous | Generate→test→fix cycles, no clear termination | 5-10 |
| **SelfReflectionAgent** | 🔄 Autonomous | Think→critique→revise cycles | 5-10 |
| **ResilientAgent** | 🔄 Autonomous | Retry with exponential backoff, error recovery loops | 5 |
| **SimpleQAAgent** | ⚡ Single-Shot | Direct question→answer, deterministic | 1 |
| **ChainOfThoughtAgent** | ⚡ Single-Shot | Structured reasoning in one pass | 1 |
| **MemoryAgent** | ⚡ Single-Shot | Context retrieval + generation, one pass | 1 |
| **BatchProcessingAgent** | ⚡ Single-Shot | Independent processing per batch item | 1 |
| **HumanApprovalAgent** | ⚡ Single-Shot | Generate→wait for approval (external loop) | 1 |
| **StreamingChatAgent** | ⚡ Single-Shot | Each message independent | 1 |

### Multi-Modal Agents (3 total)

| Agent | Mode | Rationale | Max Cycles |
|-------|------|-----------|------------|
| **VisionAgent** | ⚡ Single-Shot | Image→description, deterministic | 1 |
| **TranscriptionAgent** | ⚡ Single-Shot | Audio→text, deterministic | 1 |
| **MultiModalAgent** | ⚡ Single-Shot | Orchestration only, no iteration | 1 |

### Coordination Agents (11 total)

| Agent | Mode | Rationale | Max Cycles |
|-------|------|-----------|------------|
| **SupervisorAgent** | ⚡ Single-Shot | Routes tasks to workers (delegation) | 1 |
| **WorkerAgent** | Inherited | Depends on worker's nature | Varies |
| **CoordinatorAgent** | ⚡ Single-Shot | Merges results (one pass) | 1 |
| **DebateLeaderAgent** | 🔄 Autonomous | Facilitates back-and-forth debate | 10-20 |
| **DebateParticipantAgent** | ⚡ Single-Shot | Responds once per round | 1 |
| **DebateJudgeAgent** | ⚡ Single-Shot | Evaluates final arguments | 1 |
| **ConsensusLeaderAgent** | 🔄 Autonomous | Iterative voting until consensus | 10-15 |
| **ConsensusVoterAgent** | ⚡ Single-Shot | Votes once per round | 1 |
| **ConsensusTallyAgent** | ⚡ Single-Shot | Counts votes (deterministic) | 1 |
| **HandoffAgent** | ⚡ Single-Shot | Passes task to next agent | 1 |
| **PipelineAgent** | ⚡ Single-Shot | Sequential execution coordinator | 1 |

**Summary**:
- **Autonomous (8 agents)**: ReAct, RAGResearch, CodeGeneration, SelfReflection, Resilient, DebateLeader, ConsensusLeader
- **Single-Shot (17 agents)**: SimpleQA, ChainOfThought, Memory, BatchProcessing, HumanApproval, StreamingChat, Vision, Transcription, MultiModal, Supervisor, Worker (varies), Coordinator, DebateParticipant, DebateJudge, ConsensusVoter, ConsensusTally, Handoff, Pipeline

---

## Implementation Pattern

### Autonomous Agent Pattern

```python
from kaizen.strategies.multi_cycle import MultiCycleStrategy

class AutonomousAgent(BaseAgent):
    """Agent with iterative refinement loops."""

    def __init__(self, config):
        # Create autonomous execution strategy
        multi_cycle_strategy = MultiCycleStrategy(
            max_cycles=config.max_cycles,  # e.g., 10
            convergence_check=self._check_convergence  # Optional custom check
        )

        super().__init__(
            config=config,
            signature=YourSignature(),
            strategy=multi_cycle_strategy,  # CRITICAL
            tools="all"  # Enable tools via MCP
            mcp_servers=mcp_servers,
        )

    def _check_convergence(self, result: Dict[str, Any]) -> bool:
        """
        Determine if agent should stop iterating.

        Priority order:
        1. OBJECTIVE: Check tool_calls field (preferred)
        2. SUBJECTIVE: Check confidence/action fields (fallback)
        3. DEFAULT: Converged (safe fallback)
        """
        # Objective convergence (Claude Code pattern)
        if "tool_calls" in result:
            tool_calls = result.get("tool_calls", [])
            if isinstance(tool_calls, list):
                if tool_calls:
                    return False  # Has tools → continue
                return True  # Empty tools → converged

        # Subjective convergence (legacy)
        if result.get("action") == "finish":
            return True

        if result.get("confidence", 0) >= 0.85:
            return True

        # Default: converged
        return True
```

### Single-Shot Agent Pattern

```python
class SingleShotAgent(BaseAgent):
    """Agent with deterministic, one-pass execution."""

    def __init__(self, config):
        # No strategy parameter = default single-shot execution
        super().__init__(
            config=config,
            signature=YourSignature(),
            # No strategy parameter - uses default AsyncSingleShotStrategy
        )

    def process(self, **inputs):
        """Direct execution, no iterations."""
        return self.run(**inputs)
```

---

## Convergence Detection Patterns

### 1. Objective Convergence (Preferred)

**Pattern**: Check `tool_calls` field (from signature)

```python
def _check_convergence(self, result: Dict[str, Any]) -> bool:
    """Objective convergence via tool_calls field."""
    tool_calls = result.get("tool_calls", [])

    if not isinstance(tool_calls, list):
        return True  # Malformed → stop

    if tool_calls:
        return False  # Has tool calls → continue

    return True  # Empty tool calls → converged
```

**Advantages**:
- ✅ Deterministic (no hallucination)
- ✅ Clear JSON structure
- ✅ Claude Code standard pattern

**Use For**: ReAct, RAGResearch, CodeGeneration, any tool-using agent

### 2. Subjective Convergence (Fallback)

**Pattern**: Check `action` or `confidence` fields

```python
def _check_convergence(self, result: Dict[str, Any]) -> bool:
    """Subjective convergence via LLM output."""
    if result.get("action") == "finish":
        return True

    if result.get("confidence", 0) >= self.confidence_threshold:
        return True

    return False  # Continue
```

**Disadvantages**:
- ⚠️ LLM can hallucinate "finish" action
- ⚠️ Confidence scores unreliable
- ⚠️ No objective verification

**Use For**: Agents without tool calling (SelfReflection, etc.)

### 3. Hybrid Convergence (Recommended)

**Pattern**: Objective first, subjective fallback

```python
def _check_convergence(self, result: Dict[str, Any]) -> bool:
    """Hybrid: objective preferred, subjective fallback."""

    # 1. OBJECTIVE (preferred)
    if "tool_calls" in result:
        tool_calls = result.get("tool_calls", [])
        if isinstance(tool_calls, list):
            return len(tool_calls) == 0  # Empty = converged

    # 2. SUBJECTIVE (fallback)
    if result.get("action") == "finish":
        return True

    if result.get("confidence", 0) >= 0.85:
        return True

    # 3. DEFAULT (safe)
    return True
```

**Use For**: All autonomous agents

---

## Anti-Patterns to Avoid

### ❌ Anti-Pattern 1: Autonomous Simple QA

```python
# WRONG: SimpleQA doesn't need iteration
class SimpleQAAgent(BaseAgent):
    def __init__(self, config):
        strategy = MultiCycleStrategy(max_cycles=10)  # ❌ Wastes tokens
        super().__init__(config=config, strategy=strategy)
```

**Why Wrong**: Question→Answer is deterministic, no refinement needed

**Correct**:
```python
class SimpleQAAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config)  # ✅ Single-shot
```

### ❌ Anti-Pattern 2: Single-Shot Code Generation

```python
# WRONG: CodeGen needs iteration to fix errors
class CodeGenerationAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config)  # ❌ Can't refine code
```

**Why Wrong**: Code generation needs generate→test→fix cycles

**Correct**:
```python
class CodeGenerationAgent(BaseAgent):
    def __init__(self, config):
        strategy = MultiCycleStrategy(max_cycles=10)
        super().__init__(config=config, strategy=strategy)  # ✅ Autonomous
```

### ❌ Anti-Pattern 3: No Convergence Check

```python
# WRONG: Autonomous agent without convergence detection
strategy = MultiCycleStrategy(
    max_cycles=10
    # ❌ No convergence_check - will always run all 10 cycles
)
```

**Why Wrong**: Wastes tokens when task completes early

**Correct**:
```python
strategy = MultiCycleStrategy(
    max_cycles=10,
    convergence_check=self._check_convergence  # ✅ Early stopping
)
```

---

## Token Efficiency Considerations

### Autonomous Execution Cost

**Example**: ReActAgent with max_cycles=10
- Average convergence: 3-5 cycles
- Tokens per cycle: ~500 tokens (input) + ~200 tokens (output) = 700 tokens
- Total: 3 × 700 = 2,100 tokens
- Cost (GPT-3.5): ~$0.003

**With Proper Convergence**:
- Task completes in 3 cycles → $0.003
- Saves 7 cycles → $0.007 saved

**Without Convergence Check**:
- Always runs 10 cycles → $0.010
- Wastes 7 cycles even when done

### Single-Shot Execution Cost

**Example**: SimpleQAAgent
- Tokens: ~300 tokens (input) + ~100 tokens (output) = 400 tokens
- Cost (GPT-3.5): ~$0.0006

**If Made Autonomous Incorrectly**:
- Still needs 1 cycle, but overhead from MultiCycleStrategy
- Adds complexity without benefit

---

## Testing Considerations

### Autonomous Agents

**Must Test**:
1. Convergence detection accuracy (>95%)
2. Max cycles enforcement
3. Tool calling behavior
4. Early stopping when task complete

**Test Pattern**:
```python
def test_autonomous_convergence():
    agent = ReActAgent(config)
    result = agent.solve_task("Simple task")

    assert result["cycles_used"] < config.max_cycles, "Should converge early"
    assert len(result.get("tool_calls", [])) == 0, "Should have no pending tools"
```

### Single-Shot Agents

**Must Test**:
1. Single execution (cycles_used = 1)
2. No iteration overhead
3. Correct output format

**Test Pattern**:
```python
def test_single_shot_execution():
    agent = SimpleQAAgent(config)
    result = agent.ask("What is 2+2?")

    assert "cycles_used" not in result or result["cycles_used"] == 1
    assert "answer" in result
```

---

## Migration Guide

### Converting Single-Shot → Autonomous

**When**: Agent needs iterative refinement (e.g., adding tool calling)

**Steps**:
1. Add signature field: `tool_calls: list = OutputField(...)`
2. Create MultiCycleStrategy with convergence check
3. Pass strategy to BaseAgent.__init__()
4. Add _check_convergence() method
5. Update tests for multi-cycle behavior

**Example**:
```python
# Before: Single-shot
class MyAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=MySignature())

# After: Autonomous
class MyAgent(BaseAgent):
    def __init__(self, config):
        strategy = MultiCycleStrategy(
            max_cycles=config.max_cycles,
            convergence_check=self._check_convergence
        )
        super().__init__(
            config=config,
            signature=MySignature(),  # Must have tool_calls field
            strategy=strategy,
            tools="all"  # Enable tools via MCP
        )

    def _check_convergence(self, result: Dict[str, Any]) -> bool:
        tool_calls = result.get("tool_calls", [])
        return len(tool_calls) == 0 if isinstance(tool_calls, list) else True
```

### Converting Autonomous → Single-Shot

**When**: Agent doesn't actually need iteration (over-engineered)

**Steps**:
1. Remove MultiCycleStrategy initialization
2. Remove strategy parameter from BaseAgent.__init__()
3. Remove _check_convergence() method
4. Simplify tests

**Example**:
```python
# Before: Autonomous (over-engineered)
class MyAgent(BaseAgent):
    def __init__(self, config):
        strategy = MultiCycleStrategy(max_cycles=10)
        super().__init__(config=config, strategy=strategy)

# After: Single-shot (correct)
class MyAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config)
```

---

## Summary

**Golden Rules**:

1. ✅ **Default to single-shot** - only use autonomous when iterative behavior is essential
2. ✅ **Objective convergence** - use tool_calls field when possible
3. ✅ **Always provide convergence check** - enable early stopping
4. ✅ **Test convergence accuracy** - must exceed 95%
5. ✅ **Consider token costs** - autonomous execution costs 3-10× more

**Decision Checklist**:
- [ ] Does agent need feedback loops? → Autonomous
- [ ] Does agent refine outputs iteratively? → Autonomous
- [ ] Does agent interact with tools? → Autonomous
- [ ] Is output deterministic in one pass? → Single-shot
- [ ] Is agent just delegating? → Single-shot

---

**References**:
- ADR-013: Objective Convergence Detection
- ADR-016: Universal Tool Integration
- Claude Code Architecture: `while(tool_call_exists)` pattern
- MultiCycleStrategy: `src/kaizen/strategies/multi_cycle.py`

**Last Updated**: 2025-10-22
**Version**: 1.0.0
