# Kaizen Strategy Selection Guide

**Version**: 1.0
**Last Updated**: 2025-10-02
**Status**: Production-Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Strategy Types](#strategy-types)
3. [Selection Guide](#selection-guide)
4. [Configuration](#configuration)
5. [Performance Characteristics](#performance-characteristics)
6. [Integration Patterns](#integration-patterns)
7. [Best Practices](#best-practices)
8. [Migration Guide](#migration-guide)
9. [Examples](#examples)
10. [Troubleshooting](#troubleshooting)

---

## Overview

Kaizen provides **9 execution strategies** for different use cases:

| Strategy | Purpose | Use Case | Async |
|----------|---------|----------|-------|
| **SingleShotStrategy** | One-pass execution | Simple Q&A, classification | No |
| **AsyncSingleShotStrategy** | Async one-pass | Default for all agents | Yes |
| **MultiCycleStrategy** | Iterative execution | Self-improvement, refinement | Yes |
| **TestDrivenConvergence** | Test-based stopping | Test-driven development | Yes |
| **SatisfactionConvergence** | Confidence-based stopping | Quality assurance | Yes |
| **HybridConvergence** | Composite stopping | Complex conditions | Yes |
| **StreamingStrategy** | Token streaming | Real-time chat, interactive | Yes |
| **ParallelBatchStrategy** | Concurrent batch | Bulk processing, data pipelines | Yes |
| **FallbackStrategy** | Sequential fallback | Resilience, degraded service | Yes |
| **HumanInLoopStrategy** | Human approval | Critical decisions, compliance | Yes |

### Key Concepts

- **Base Strategies** (SingleShot, Async): Foundation for simple execution
- **Iterative Strategies** (MultiCycle, Convergence): Repeated execution with stopping conditions
- **Advanced Strategies** (Streaming, Batch, Fallback, HITL): Specialized execution patterns
- **Default**: AsyncSingleShotStrategy (automatic if no strategy specified)
- **Pluggable**: All strategies implement same interface

---

## Strategy Types

### 1. SingleShotStrategy

**Purpose**: Synchronous one-pass execution (legacy, not recommended).

**Architecture**:
```
┌─────────────────────────────────────┐
│    SingleShotStrategy               │
│                                     │
│  execute(agent, inputs) →          │
│    1. Call agent's signature       │
│    2. Return result                │
│                                     │
│  Synchronous, blocking             │
└─────────────────────────────────────┘
```

**Use Cases**:
- ❌ **Not recommended** (use AsyncSingleShotStrategy instead)
- Legacy compatibility only

**Configuration**:
```python
from kaizen.strategies.single_shot import SingleShotStrategy

strategy = SingleShotStrategy()
agent = MyAgent(config, strategy=strategy)
```

**Performance**:
- **Latency**: Same as AsyncSingleShotStrategy
- **Throughput**: Lower (synchronous blocking)
- **Concurrency**: None (blocks thread)

---

### 2. AsyncSingleShotStrategy (Default)

**Purpose**: Asynchronous one-pass execution.

**Architecture**:
```
┌─────────────────────────────────────┐
│   AsyncSingleShotStrategy           │
│                                     │
│  async execute(agent, inputs) →    │
│    1. Call agent's signature       │
│    2. Return result                │
│                                     │
│  Non-blocking, concurrent          │
└─────────────────────────────────────┘
```

**Use Cases**:
- ✅ Default strategy for all agents
- ✅ Simple Q&A
- ✅ Classification
- ✅ Translation
- ✅ Summarization
- ❌ Iterative refinement (use MultiCycleStrategy)
- ❌ Real-time streaming (use StreamingStrategy)

**Configuration**:
```python
# No configuration needed - used by default
agent = MyAgent(config)  # Uses AsyncSingleShotStrategy automatically
```

**Performance**:
- **Latency**: 100-500ms (depends on LLM)
- **Throughput**: 10-100 requests/sec (depends on concurrency)
- **Concurrency**: Full async support

**Example**:
```python
from kaizen.core.base_agent import BaseAgent

class QAAgent(BaseAgent):
    def __init__(self, config):
        # AsyncSingleShotStrategy used automatically
        super().__init__(config=config, signature=QASignature())

    def ask(self, question: str) -> str:
        result = self.run({"question": question})
        return result["answer"]
```

---

### 3. MultiCycleStrategy

**Purpose**: Iterative execution with convergence strategies.

**Architecture**:
```
┌─────────────────────────────────────┐
│      MultiCycleStrategy             │
│                                     │
│  async execute(agent, inputs) →    │
│    Loop (max_cycles):              │
│      1. Execute agent              │
│      2. Check convergence          │
│      3. If converged → return      │
│      4. Else → continue            │
│                                     │
│  Convergence strategies:           │
│    - TestDrivenConvergence         │
│    - SatisfactionConvergence       │
│    - HybridConvergence             │
└─────────────────────────────────────┘
```

**Use Cases**:
- ✅ Self-improvement agents
- ✅ Code generation with testing
- ✅ Quality refinement
- ✅ Iterative problem-solving
- ❌ Simple one-pass tasks (use AsyncSingleShotStrategy)
- ❌ Real-time streaming (use StreamingStrategy)

**Configuration**:
```python
from kaizen.strategies.multi_cycle import MultiCycleStrategy
from kaizen.strategies.convergence import TestDrivenConvergence

# With convergence strategy
convergence = TestDrivenConvergence(test_suite=my_tests)
strategy = MultiCycleStrategy(
    convergence_strategy=convergence,
    max_cycles=10
)

agent = MyAgent(config, strategy=strategy)
```

**Performance**:
- **Latency**: 1-10 seconds (depends on cycles)
- **Throughput**: 1-10 requests/sec
- **Concurrency**: Full async support

**Example**:
```python
from kaizen.strategies.multi_cycle import MultiCycleStrategy
from kaizen.strategies.convergence import SatisfactionConvergence

class CodeGeneratorAgent(BaseAgent):
    def __init__(self, config):
        convergence = SatisfactionConvergence(
            confidence_threshold=0.9,
            min_cycles=2
        )
        strategy = MultiCycleStrategy(
            convergence_strategy=convergence,
            max_cycles=5
        )
        super().__init__(config=config, signature=CodeGenSignature(), strategy=strategy)

    def generate(self, spec: str) -> str:
        result = self.run({"spec": spec})
        return result["code"]
```

---

### 4. TestDrivenConvergence

**Purpose**: Stop when tests pass (for MultiCycleStrategy).

**Architecture**:
```
┌─────────────────────────────────────┐
│   TestDrivenConvergence             │
│                                     │
│  should_stop(cycle, result) →      │
│    1. Extract code from result     │
│    2. Run test suite               │
│    3. Return True if pass          │
│                                     │
│  test_suite → Callable             │
└─────────────────────────────────────┘
```

**Use Cases**:
- ✅ Test-driven development
- ✅ Code generation with validation
- ✅ Contract-based refinement
- ❌ Subjective quality (use SatisfactionConvergence)

**Configuration**:
```python
from kaizen.strategies.convergence import TestDrivenConvergence

def my_test_suite(code: str) -> bool:
    """Return True if code passes tests."""
    try:
        exec(code)
        # Run tests...
        return True
    except:
        return False

convergence = TestDrivenConvergence(
    test_suite=my_test_suite,
    code_field="code"  # Field in result containing code
)
```

**Example**:
```python
from kaizen.strategies.multi_cycle import MultiCycleStrategy
from kaizen.strategies.convergence import TestDrivenConvergence

def test_suite(code: str) -> bool:
    # Your test logic
    return all_tests_pass(code)

convergence = TestDrivenConvergence(test_suite=test_suite)
strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=10)

agent = CodeGenAgent(config, strategy=strategy)
result = agent.generate("Write a function to sort a list")
# Iterates until tests pass or max_cycles reached
```

---

### 5. SatisfactionConvergence

**Purpose**: Stop when confidence threshold met (for MultiCycleStrategy).

**Architecture**:
```
┌─────────────────────────────────────┐
│   SatisfactionConvergence           │
│                                     │
│  should_stop(cycle, result) →      │
│    1. Extract confidence score     │
│    2. Check threshold              │
│    3. Return True if satisfied     │
│                                     │
│  confidence_threshold → float      │
│  min_cycles → int                  │
└─────────────────────────────────────┘
```

**Use Cases**:
- ✅ Quality assurance
- ✅ Confidence-based stopping
- ✅ Self-assessment agents
- ❌ Objective validation (use TestDrivenConvergence)

**Configuration**:
```python
from kaizen.strategies.convergence import SatisfactionConvergence

convergence = SatisfactionConvergence(
    confidence_threshold=0.9,      # Stop when confidence >= 0.9
    confidence_field="confidence",  # Field in result
    min_cycles=2                    # Minimum cycles before stopping
)
```

**Example**:
```python
convergence = SatisfactionConvergence(confidence_threshold=0.9, min_cycles=2)
strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=10)

agent = WriterAgent(config, strategy=strategy)
result = agent.write("Write an essay about AI")
# Iterates until confidence >= 0.9 or max_cycles
```

---

### 6. HybridConvergence

**Purpose**: Compose multiple convergence strategies (for MultiCycleStrategy).

**Architecture**:
```
┌─────────────────────────────────────┐
│     HybridConvergence               │
│                                     │
│  should_stop(cycle, result) →      │
│    1. Evaluate all strategies      │
│    2. Apply combination logic      │
│    3. Return True if satisfied     │
│                                     │
│  strategies → List[Convergence]    │
│  combination → "all" | "any"       │
└─────────────────────────────────────┘
```

**Use Cases**:
- ✅ Complex stopping conditions (tests AND confidence)
- ✅ Multi-criteria validation
- ✅ Composite quality checks
- ❌ Simple stopping (use TestDrivenConvergence or SatisfactionConvergence)

**Configuration**:
```python
from kaizen.strategies.convergence import (
    HybridConvergence,
    TestDrivenConvergence,
    SatisfactionConvergence
)

convergence = HybridConvergence(
    strategies=[
        TestDrivenConvergence(test_suite=my_tests),
        SatisfactionConvergence(confidence_threshold=0.9)
    ],
    combination="all"  # Both must be satisfied
)
```

**Example**:
```python
# Stop when BOTH tests pass AND confidence >= 0.9
convergence = HybridConvergence(
    strategies=[
        TestDrivenConvergence(test_suite=my_tests),
        SatisfactionConvergence(confidence_threshold=0.9)
    ],
    combination="all"
)

strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=10)
agent = CodeGenAgent(config, strategy=strategy)
```

---

### 7. StreamingStrategy

**Purpose**: Real-time token streaming for interactive use cases.

**Architecture**:
```
┌─────────────────────────────────────┐
│      StreamingStrategy              │
│                                     │
│  async execute(agent, inputs) →    │
│    1. Call agent's signature       │
│    2. Buffer complete result       │
│    3. Return final result          │
│                                     │
│  async stream(agent, inputs) →     │
│    1. Call agent's signature       │
│    2. Yield chunks incrementally   │
│    3. No return value              │
│                                     │
│  chunk_size → int                  │
└─────────────────────────────────────┘
```

**Use Cases**:
- ✅ Real-time chat
- ✅ Interactive assistants
- ✅ Live translation
- ✅ Progressive content generation
- ❌ Batch processing (use ParallelBatchStrategy)
- ❌ Offline processing (use AsyncSingleShotStrategy)

**Configuration**:
```python
from kaizen.strategies.streaming import StreamingStrategy

strategy = StreamingStrategy(chunk_size=1)  # Character-by-character
# OR
strategy = StreamingStrategy(chunk_size=5)  # Word-by-word (faster)

agent = ChatAgent(config, strategy=strategy)
```

**Performance**:
- **Latency to First Token**: 50-200ms
- **Token Throughput**: 10-50 tokens/sec
- **Total Latency**: Same as AsyncSingleShotStrategy
- **Concurrency**: Full async support

**Example**:
```python
from kaizen.strategies.streaming import StreamingStrategy

class StreamChatAgent(BaseAgent):
    def __init__(self, config):
        strategy = StreamingStrategy(chunk_size=1)
        super().__init__(config=config, signature=ChatSignature(), strategy=strategy)

    async def stream_chat(self, message: str):
        """Stream response token by token."""
        async for chunk in self.strategy.stream(self, {"message": message}):
            print(chunk, end="", flush=True)
            yield chunk

# Usage
agent = StreamChatAgent(config)
async for chunk in agent.stream_chat("What is Python?"):
    # Display chunk in UI
    pass
```

---

### 8. ParallelBatchStrategy

**Purpose**: Concurrent batch processing with semaphore limiting.

**Architecture**:
```
┌─────────────────────────────────────┐
│    ParallelBatchStrategy            │
│                                     │
│  async execute_batch(agent, batch) →│
│    1. Create semaphore             │
│    2. Launch tasks concurrently    │
│    3. Await all tasks              │
│    4. Return results               │
│                                     │
│  max_concurrent → int              │
│  Semaphore → Resource limiting     │
└─────────────────────────────────────┘
```

**Use Cases**:
- ✅ Bulk document processing
- ✅ Data pipelines
- ✅ Batch classification
- ✅ Parallel translation
- ❌ Real-time streaming (use StreamingStrategy)
- ❌ Sequential processing (use AsyncSingleShotStrategy)

**Configuration**:
```python
from kaizen.strategies.parallel_batch import ParallelBatchStrategy

strategy = ParallelBatchStrategy(max_concurrent=10)
agent = BatchProcessorAgent(config, strategy=strategy)
```

**Performance**:
- **Latency**: Same as AsyncSingleShotStrategy (per item)
- **Throughput**: max_concurrent * (1 / latency_per_item)
- **Example**: max_concurrent=10, latency=500ms → 20 items/sec
- **Concurrency**: Controlled by semaphore

**Example**:
```python
from kaizen.strategies.parallel_batch import ParallelBatchStrategy

class BatchProcessorAgent(BaseAgent):
    def __init__(self, config):
        strategy = ParallelBatchStrategy(max_concurrent=10)
        super().__init__(config=config, signature=ProcessSignature(), strategy=strategy)

    async def process_batch(self, items: List[str]) -> List[Dict]:
        """Process multiple items concurrently."""
        batch_inputs = [{"item": item} for item in items]
        results = await self.strategy.execute_batch(self, batch_inputs)
        return results

# Usage
agent = BatchProcessorAgent(config)
results = await agent.process_batch(["doc1", "doc2", ..., "doc100"])
# Processes up to 10 concurrently
```

---

### 9. FallbackStrategy

**Purpose**: Sequential fallback for resilience and degraded service.

**Architecture**:
```
┌─────────────────────────────────────┐
│      FallbackStrategy               │
│                                     │
│  async execute(agent, inputs) →    │
│    For each strategy:              │
│      1. Try strategy.execute()     │
│      2. If success → return        │
│      3. If error → try next        │
│    If all fail → raise error       │
│                                     │
│  strategies → List[Strategy]       │
│  get_error_summary() → errors      │
└─────────────────────────────────────┘
```

**Use Cases**:
- ✅ Multi-model fallback (GPT-4 → GPT-3.5 → local)
- ✅ Degraded service
- ✅ Cost optimization (try expensive, fallback to cheap)
- ✅ Resilience patterns
- ❌ Parallel redundancy (use ParallelBatchStrategy with voting)

**Configuration**:
```python
from kaizen.strategies.fallback import FallbackStrategy
from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy

# Create agents with different models
gpt4_strategy = AsyncSingleShotStrategy()
gpt35_strategy = AsyncSingleShotStrategy()
local_strategy = AsyncSingleShotStrategy()

strategy = FallbackStrategy(
    strategies=[gpt4_strategy, gpt35_strategy, local_strategy]
)

agent = ResilientAgent(config, strategy=strategy)
```

**Performance**:
- **Latency**: Sum of failed attempts + successful attempt
- **Best Case**: Same as AsyncSingleShotStrategy (first succeeds)
- **Worst Case**: N * AsyncSingleShotStrategy (all fail)
- **Success Rate**: Higher than single strategy

**Example**:
```python
from kaizen.strategies.fallback import FallbackStrategy

class ResilientAgent(BaseAgent):
    def __init__(self, models: List[str]):
        # Create strategies for each model
        strategies = [
            AsyncSingleShotStrategy() for _ in models
        ]
        strategy = FallbackStrategy(strategies=strategies)

        super().__init__(
            config=config,
            signature=QuerySignature(),
            strategy=strategy
        )
        self.models = models

    def query(self, question: str) -> Dict[str, Any]:
        result = self.run({"question": question})

        # Check which strategy succeeded
        if hasattr(self.strategy, '_fallback_strategy_used'):
            used_idx = self.strategy._fallback_strategy_used
            result['model_used'] = self.models[used_idx]

        return result

# Usage
agent = ResilientAgent(models=["gpt-4", "gpt-3.5-turbo", "local-llama"])
result = agent.query("What is Python?")
print(f"Model used: {result['model_used']}")
```

---

### 10. HumanInLoopStrategy

**Purpose**: Human approval checkpoints for critical decisions.

**Architecture**:
```
┌─────────────────────────────────────┐
│    HumanInLoopStrategy              │
│                                     │
│  async execute(agent, inputs) →    │
│    1. Execute agent                │
│    2. Request human approval       │
│    3. If approved → return         │
│    4. If rejected → raise error    │
│                                     │
│  approval_callback → Callable      │
│  approval_history → List[Decision] │
└─────────────────────────────────────┘
```

**Use Cases**:
- ✅ Financial transactions
- ✅ Content moderation
- ✅ Critical decisions
- ✅ Compliance workflows
- ✅ Legal document generation
- ❌ High-volume automation (approval bottleneck)
- ❌ Fully automated systems

**Configuration**:
```python
from kaizen.strategies.human_in_loop import HumanInLoopStrategy

def approval_callback(result: Dict) -> Dict[str, Any]:
    """Request human approval."""
    print(f"Approve this result? {result}")
    decision = input("(y/n): ")

    return {
        "approved": decision.lower() == "y",
        "feedback": "Looks good" if decision == "y" else "Needs revision"
    }

strategy = HumanInLoopStrategy(approval_callback=approval_callback)
agent = ApprovalAgent(config, strategy=strategy)
```

**Performance**:
- **Latency**: AsyncSingleShotStrategy + human response time
- **Throughput**: Depends on human response time (1-60 seconds)
- **Concurrency**: Limited by human approval

**Example**:
```python
from kaizen.strategies.human_in_loop import HumanInLoopStrategy

class ApprovalAgent(BaseAgent):
    def __init__(self, config, approval_callback):
        strategy = HumanInLoopStrategy(approval_callback=approval_callback)
        super().__init__(config=config, signature=DecisionSignature(), strategy=strategy)

    def decide(self, request: str) -> Dict[str, Any]:
        try:
            result = self.run({"request": request})
            return result
        except RuntimeError as e:
            # Human rejected
            print(f"Decision rejected: {e}")
            return {"status": "rejected", "reason": str(e)}

# Usage
def cli_approval(result: Dict) -> Dict[str, Any]:
    print(f"\nProposed decision: {result['decision']}")
    decision = input("Approve? (y/n): ")
    return {"approved": decision.lower() == "y", "feedback": ""}

agent = ApprovalAgent(config, approval_callback=cli_approval)
result = agent.decide("Transfer $10,000")
```

---

## Selection Guide

### Decision Tree

```
Start: What is your use case?

├─ Simple one-pass execution?
│  └─ AsyncSingleShotStrategy (default)
│
├─ Iterative refinement?
│  ├─ Test-driven? → TestDrivenConvergence + MultiCycleStrategy
│  ├─ Confidence-based? → SatisfactionConvergence + MultiCycleStrategy
│  └─ Complex conditions? → HybridConvergence + MultiCycleStrategy
│
├─ Real-time streaming?
│  └─ StreamingStrategy
│
├─ Batch processing?
│  └─ ParallelBatchStrategy
│
├─ Resilience needed?
│  └─ FallbackStrategy
│
└─ Human approval required?
   └─ HumanInLoopStrategy
```

### Selection Matrix

| Use Case | Best Strategy | Alternative |
|----------|---------------|-------------|
| **Simple Q&A** | AsyncSingleShotStrategy | - |
| **Classification** | AsyncSingleShotStrategy | ParallelBatchStrategy |
| **Translation** | AsyncSingleShotStrategy | StreamingStrategy |
| **Real-time chat** | StreamingStrategy | AsyncSingleShotStrategy |
| **Code generation** | TestDrivenConvergence + MultiCycle | SatisfactionConvergence |
| **Bulk processing** | ParallelBatchStrategy | AsyncSingleShotStrategy |
| **Multi-model fallback** | FallbackStrategy | - |
| **Critical decisions** | HumanInLoopStrategy | - |
| **Quality refinement** | SatisfactionConvergence + MultiCycle | - |
| **Test-driven dev** | TestDrivenConvergence + MultiCycle | - |
| **Composite validation** | HybridConvergence + MultiCycle | - |

### Performance vs. Complexity

```
Complexity
    ↑
    │  HybridConvergence
    │  │
    │  │  HumanInLoopStrategy
    │  │  │
    │  │  │  MultiCycleStrategy
    │  │  │  │
    │  │  │  │  FallbackStrategy
    │  │  │  │  │
    │  │  │  │  │  ParallelBatchStrategy
    │  │  │  │  │  │
    │  │  │  │  │  │  StreamingStrategy
    │  │  │  │  │  │  │
    │  │  │  │  │  │  │  AsyncSingleShotStrategy
    │  │  │  │  │  │  │  │
    └──┴──┴──┴──┴──┴──┴──┴─────────────→ Performance
                                      (Latency)
```

### Throughput Comparison (Requests/Second)

| Strategy | Throughput | Notes |
|----------|------------|-------|
| AsyncSingleShotStrategy | 10-100 | Depends on concurrency |
| StreamingStrategy | 10-100 | Same as Async (final result) |
| ParallelBatchStrategy | 100-1000 | max_concurrent * base_rate |
| FallbackStrategy | 5-50 | Slower (multiple attempts) |
| MultiCycleStrategy | 1-10 | Multiple cycles |
| HumanInLoopStrategy | 0.01-1 | Limited by human |

---

## Configuration

### AsyncSingleShotStrategy

```python
# No configuration - used by default
agent = MyAgent(config)
```

### MultiCycleStrategy

```python
from kaizen.strategies.multi_cycle import MultiCycleStrategy
from kaizen.strategies.convergence import SatisfactionConvergence

convergence = SatisfactionConvergence(confidence_threshold=0.9)
strategy = MultiCycleStrategy(
    convergence_strategy=convergence,
    max_cycles=10
)
```

### TestDrivenConvergence

```python
from kaizen.strategies.convergence import TestDrivenConvergence

convergence = TestDrivenConvergence(
    test_suite=lambda code: run_tests(code),
    code_field="code"
)
```

### SatisfactionConvergence

```python
from kaizen.strategies.convergence import SatisfactionConvergence

convergence = SatisfactionConvergence(
    confidence_threshold=0.9,
    confidence_field="confidence",
    min_cycles=2
)
```

### HybridConvergence

```python
from kaizen.strategies.convergence import HybridConvergence

convergence = HybridConvergence(
    strategies=[convergence1, convergence2],
    combination="all"  # or "any"
)
```

### StreamingStrategy

```python
from kaizen.strategies.streaming import StreamingStrategy

strategy = StreamingStrategy(chunk_size=1)
```

### ParallelBatchStrategy

```python
from kaizen.strategies.parallel_batch import ParallelBatchStrategy

strategy = ParallelBatchStrategy(max_concurrent=10)
```

### FallbackStrategy

```python
from kaizen.strategies.fallback import FallbackStrategy

strategy = FallbackStrategy(
    strategies=[strategy1, strategy2, strategy3]
)
```

### HumanInLoopStrategy

```python
from kaizen.strategies.human_in_loop import HumanInLoopStrategy

strategy = HumanInLoopStrategy(
    approval_callback=lambda result: {"approved": True}
)
```

---

## Performance Characteristics

### Latency Comparison (Milliseconds)

| Strategy | Min | Avg | Max | Notes |
|----------|-----|-----|-----|-------|
| AsyncSingleShotStrategy | 100 | 300 | 500 | Depends on LLM |
| StreamingStrategy | 50 | 300 | 500 | First token faster |
| ParallelBatchStrategy | 100 | 300 | 500 | Per item (parallel) |
| FallbackStrategy | 100 | 600 | 1500 | Multiple attempts |
| MultiCycleStrategy | 500 | 2000 | 5000 | Multiple cycles |
| HumanInLoopStrategy | 1000 | 30000 | 60000 | Human response time |

### Memory Usage

| Strategy | Memory | Notes |
|----------|--------|-------|
| AsyncSingleShotStrategy | O(1) | Single request |
| StreamingStrategy | O(N) | N = response length |
| ParallelBatchStrategy | O(M) | M = max_concurrent |
| FallbackStrategy | O(1) | Single active request |
| MultiCycleStrategy | O(C) | C = max_cycles |
| HumanInLoopStrategy | O(1) | Single request |

### CPU Usage

| Strategy | CPU | Notes |
|----------|-----|-------|
| AsyncSingleShotStrategy | Low | I/O bound |
| StreamingStrategy | Low | I/O bound |
| ParallelBatchStrategy | Medium | Multiple concurrent |
| FallbackStrategy | Low | Sequential |
| MultiCycleStrategy | Medium | Multiple cycles |
| HumanInLoopStrategy | Low | Waiting |

---

## Integration Patterns

### Pattern 1: Strategy Factory

```python
class StrategyFactory:
    @staticmethod
    def create(strategy_type: str, **kwargs):
        if strategy_type == "async":
            return AsyncSingleShotStrategy()
        elif strategy_type == "streaming":
            return StreamingStrategy(chunk_size=kwargs.get("chunk_size", 1))
        elif strategy_type == "batch":
            return ParallelBatchStrategy(max_concurrent=kwargs.get("max_concurrent", 10))
        elif strategy_type == "fallback":
            return FallbackStrategy(strategies=kwargs.get("strategies", []))
        elif strategy_type == "hitl":
            return HumanInLoopStrategy(approval_callback=kwargs["approval_callback"])
        elif strategy_type == "multi_cycle":
            return MultiCycleStrategy(
                convergence_strategy=kwargs["convergence"],
                max_cycles=kwargs.get("max_cycles", 10)
            )
        else:
            return AsyncSingleShotStrategy()

# Usage
strategy = StrategyFactory.create("batch", max_concurrent=10)
agent = MyAgent(config, strategy=strategy)
```

### Pattern 2: Dynamic Strategy Switching

```python
class AdaptiveAgent(BaseAgent):
    def __init__(self, config):
        self.default_strategy = AsyncSingleShotStrategy()
        self.streaming_strategy = StreamingStrategy(chunk_size=1)
        self.batch_strategy = ParallelBatchStrategy(max_concurrent=10)

        super().__init__(config=config, signature=..., strategy=self.default_strategy)

    def process_single(self, query: str) -> Dict:
        self.strategy = self.default_strategy
        return self.run({"query": query})

    async def process_streaming(self, query: str):
        self.strategy = self.streaming_strategy
        async for chunk in self.strategy.stream(self, {"query": query}):
            yield chunk

    async def process_batch(self, queries: List[str]) -> List[Dict]:
        self.strategy = self.batch_strategy
        batch_inputs = [{"query": q} for q in queries]
        return await self.strategy.execute_batch(self, batch_inputs)
```

### Pattern 3: Composable Strategies

```python
# Combine FallbackStrategy with MultiCycleStrategy
from kaizen.strategies.fallback import FallbackStrategy
from kaizen.strategies.multi_cycle import MultiCycleStrategy

# Create MultiCycle strategies with different convergence
mc_strategy1 = MultiCycleStrategy(convergence1, max_cycles=5)
mc_strategy2 = MultiCycleStrategy(convergence2, max_cycles=10)

# Fallback: Try mc_strategy1, then mc_strategy2
fallback = FallbackStrategy(strategies=[mc_strategy1, mc_strategy2])

agent = MyAgent(config, strategy=fallback)
```

---

## Best Practices

### 1. Use AsyncSingleShotStrategy by Default

✅ **DO**: Let BaseAgent use default strategy
```python
agent = MyAgent(config)  # Uses AsyncSingleShotStrategy
```

❌ **DON'T**: Explicitly set AsyncSingleShotStrategy unless needed
```python
# Unnecessary
agent = MyAgent(config, strategy=AsyncSingleShotStrategy())
```

### 2. Choose Specialized Strategies for Specific Use Cases

✅ **DO**: Use StreamingStrategy for chat
```python
strategy = StreamingStrategy(chunk_size=1)
agent = ChatAgent(config, strategy=strategy)
```

✅ **DO**: Use ParallelBatchStrategy for bulk processing
```python
strategy = ParallelBatchStrategy(max_concurrent=10)
agent = BatchAgent(config, strategy=strategy)
```

### 3. Limit max_concurrent for Resource Management

✅ **DO**: Set reasonable max_concurrent
```python
# Good: Won't exhaust resources
strategy = ParallelBatchStrategy(max_concurrent=10)
```

❌ **DON'T**: Use unlimited concurrency
```python
# Bad: May exhaust memory/connections
strategy = ParallelBatchStrategy(max_concurrent=1000)
```

### 4. Use Convergence Strategies with MultiCycle

✅ **DO**: Always provide convergence strategy
```python
convergence = SatisfactionConvergence(confidence_threshold=0.9)
strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=10)
```

❌ **DON'T**: Use MultiCycleStrategy without convergence
```python
# Bad: No stopping condition except max_cycles
strategy = MultiCycleStrategy(max_cycles=10)
```

### 5. Handle Fallback Errors Gracefully

✅ **DO**: Check error summary when fallback fails
```python
try:
    result = agent.run(inputs)
except Exception as e:
    errors = agent.strategy.get_error_summary()
    logger.error(f"All strategies failed: {errors}")
```

### 6. Test Strategies in Isolation

✅ **DO**: Test each strategy separately
```python
def test_streaming_strategy():
    strategy = StreamingStrategy(chunk_size=1)
    agent = ChatAgent(config, strategy=strategy)

    chunks = []
    async for chunk in agent.stream_chat("Hello"):
        chunks.append(chunk)

    assert len(chunks) > 0
```

### 7. Monitor Performance

✅ **DO**: Track latency and throughput
```python
import time

start = time.time()
result = agent.run(inputs)
latency = time.time() - start

logger.info(f"Latency: {latency:.2f}s, Strategy: {agent.strategy.__class__.__name__}")
```

---

## Migration Guide

### From AsyncSingleShotStrategy to StreamingStrategy

**Before**:
```python
class ChatAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=ChatSignature())

    def chat(self, message: str) -> str:
        result = self.run({"message": message})
        return result["response"]
```

**After**:
```python
from kaizen.strategies.streaming import StreamingStrategy

class ChatAgent(BaseAgent):
    def __init__(self, config):
        strategy = StreamingStrategy(chunk_size=1)
        super().__init__(config=config, signature=ChatSignature(), strategy=strategy)

    async def stream_chat(self, message: str):
        async for chunk in self.strategy.stream(self, {"message": message}):
            yield chunk
```

**Changes**:
1. Import `StreamingStrategy`
2. Add `strategy=StreamingStrategy(chunk_size=1)` to `super().__init__()`
3. Add `async` method using `self.strategy.stream()`
4. Use `async for` to yield chunks

### From AsyncSingleShotStrategy to ParallelBatchStrategy

**Before**:
```python
class ProcessorAgent(BaseAgent):
    def process(self, item: str) -> Dict:
        return self.run({"item": item})

# Process items sequentially
results = [agent.process(item) for item in items]
```

**After**:
```python
from kaizen.strategies.parallel_batch import ParallelBatchStrategy

class ProcessorAgent(BaseAgent):
    def __init__(self, config):
        strategy = ParallelBatchStrategy(max_concurrent=10)
        super().__init__(config=config, signature=..., strategy=strategy)

    async def process_batch(self, items: List[str]) -> List[Dict]:
        batch_inputs = [{"item": item} for item in items]
        return await self.strategy.execute_batch(self, batch_inputs)

# Process items concurrently
results = await agent.process_batch(items)
```

**Changes**:
1. Import `ParallelBatchStrategy`
2. Add `strategy=ParallelBatchStrategy(max_concurrent=10)`
3. Add `async` batch method using `self.strategy.execute_batch()`
4. Change sequential loop to `await agent.process_batch()`

### Adding MultiCycleStrategy to Existing Agent

**Before**:
```python
class CodeGenAgent(BaseAgent):
    def generate(self, spec: str) -> str:
        result = self.run({"spec": spec})
        return result["code"]
```

**After**:
```python
from kaizen.strategies.multi_cycle import MultiCycleStrategy
from kaizen.strategies.convergence import TestDrivenConvergence

class CodeGenAgent(BaseAgent):
    def __init__(self, config, test_suite):
        convergence = TestDrivenConvergence(test_suite=test_suite)
        strategy = MultiCycleStrategy(convergence_strategy=convergence, max_cycles=10)
        super().__init__(config=config, signature=..., strategy=strategy)

    def generate(self, spec: str) -> str:
        result = self.run({"spec": spec})
        return result["code"]
```

**Changes**:
1. Import `MultiCycleStrategy` and convergence strategy
2. Create convergence strategy in `__init__()`
3. Add `strategy=MultiCycleStrategy(...)` to `super().__init__()`
4. No changes to public API (same `generate()` method)

---

## Examples

See detailed examples in:
- [Example: streaming-chat](../examples/1-single-agent/streaming-chat/)
- [Example: batch-processing](../examples/1-single-agent/batch-processing/)
- [Example: resilient-fallback](../examples/1-single-agent/resilient-fallback/)
- [Example: human-approval](../examples/1-single-agent/human-approval/)

---

## Troubleshooting

### Problem: Strategy not executing

**Symptom**: Agent returns immediately without execution

**Solution**:
1. Check strategy is set:
   ```python
   assert agent.strategy is not None
   ```

2. Verify strategy has `execute()` method:
   ```python
   assert hasattr(agent.strategy, 'execute')
   ```

### Problem: StreamingStrategy not streaming

**Symptom**: `stream()` returns empty

**Solution**:
1. Use `stream()` not `execute()`:
   ```python
   # Correct
   async for chunk in strategy.stream(agent, inputs):
       yield chunk

   # Wrong
   result = await strategy.execute(agent, inputs)  # Not streaming!
   ```

2. Check chunk_size:
   ```python
   strategy = StreamingStrategy(chunk_size=1)  # Smaller = more chunks
   ```

### Problem: ParallelBatchStrategy not concurrent

**Symptom**: Items processed sequentially

**Solution**:
1. Use `execute_batch()` not `execute()`:
   ```python
   # Correct
   results = await strategy.execute_batch(agent, batch_inputs)

   # Wrong
   results = [await strategy.execute(agent, inp) for inp in batch_inputs]
   ```

2. Check max_concurrent:
   ```python
   strategy = ParallelBatchStrategy(max_concurrent=10)  # > 1
   ```

### Problem: FallbackStrategy not falling back

**Symptom**: Fails on first error

**Solution**:
1. Check strategies list has multiple strategies:
   ```python
   assert len(strategy.strategies) > 1
   ```

2. Verify strategies are different:
   ```python
   # Each strategy should use different model/config
   strategies = [
       create_strategy(model="gpt-4"),
       create_strategy(model="gpt-3.5-turbo")
   ]
   ```

### Problem: MultiCycleStrategy runs max_cycles

**Symptom**: Never converges early

**Solution**:
1. Check convergence strategy:
   ```python
   # Test convergence logic
   should_stop = convergence.should_stop(cycle=1, result=test_result)
   assert should_stop is True or should_stop is False
   ```

2. Verify convergence field exists in result:
   ```python
   # For SatisfactionConvergence
   assert "confidence" in result  # confidence_field must exist
   ```

---

## Related Documentation

- [Memory Patterns Guide](./memory-patterns-guide.md)
- [BaseAgent API Reference](./api/base-agent.md)
- [Signature Programming Guide](./signature-programming-guide.md)
- [Example Catalog](../examples/)

---

**End of Strategy Selection Guide**
