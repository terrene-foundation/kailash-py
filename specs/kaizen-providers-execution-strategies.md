# Kailash Kaizen -- Domain Specification — Execution Strategies

Version: 2.13.1
Package: `kailash-kaizen`

Parent domain: Kailash Kaizen AI agent framework. This file covers execution strategies — the `ExecutionStrategy` protocol, SingleShot/AsyncSingleShot/MultiCycle/Streaming/ParallelBatch/Fallback/HumanInLoop strategies, and convergence strategies. Split from `kaizen-providers.md` (specs-authority.md Rule 8 — the original file exceeded the 300-line split threshold). Sibling sub-files covering the rest of the parent domain: `kaizen-providers.md` (index), `kaizen-providers-provider-system.md`, `kaizen-providers-execution-strategies.md`, `kaizen-providers-tool-integration.md`, `kaizen-providers-memory-system.md`, `kaizen-providers-error-handling.md`, `kaizen-providers-streaming.md`. See also `kaizen-core.md`, `kaizen-signatures.md`, and `kaizen-advanced.md`.

---

## 9. Execution Strategies

All strategies implement the `ExecutionStrategy` protocol:

```python
@runtime_checkable
class ExecutionStrategy(Protocol):
    def execute(self, agent: Any, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]: ...
    def build_workflow(self, agent: Any) -> WorkflowBuilder: ...
```

### 9.1 SingleShotStrategy

One-pass execution. Suitable for Q&A, classification, extraction.

```python
strategy = SingleShotStrategy()
result = strategy.execute(agent, {"question": "What is AI?"})
```

### 9.2 AsyncSingleShotStrategy

Async variant of SingleShotStrategy. Default strategy for BaseAgent.

### 9.3 MultiCycleStrategy

Multi-cycle execution with feedback loops. Used for ReAct, iterative refinement, tool-using agents.

```python
def __init__(
    self,
    max_cycles: int = 5,
    convergence_check: callable = None,      # Legacy: (cycle_results) -> bool
    cycle_processor: callable = None,        # (inputs, cycle_num) -> Dict
    convergence_strategy: ConvergenceStrategy = None,  # New, takes precedence
)
```

**Execution flow per cycle:**

1. Pre-cycle hook
2. Execute cycle (Reason + Act)
3. Parse cycle result
4. Extract observation
5. Check termination condition
6. Continue or break

**Termination conditions:** max_cycles reached, agent signals completion (e.g., `"FINAL ANSWER:"`), error occurs, explicit `done` flag.

### 9.4 StreamingStrategy

Token-by-token streaming for chat/interactive use cases.

```python
strategy = StreamingStrategy(chunk_size=1)

# Blocking (returns final result)
result = await strategy.execute(agent, inputs)

# Streaming (yields tokens)
async for token in strategy.stream(agent, inputs):
    print(token, end="", flush=True)
```

### 9.5 ParallelBatchStrategy

Concurrent batch processing for high-throughput scenarios. Executes multiple inputs in parallel.

### 9.6 FallbackStrategy

Sequential fallback with progressive degradation. Tries strategies in order until one succeeds.

### 9.7 HumanInLoopStrategy

Human approval checkpoints for critical decisions. Pauses execution to request human input via ControlProtocol.

### 9.8 Convergence Strategies

Used with `MultiCycleStrategy` to determine when to stop iterating:

| Strategy                  | Description                          |
| ------------------------- | ------------------------------------ |
| `TestDrivenConvergence`   | Stop when all tests pass             |
| `SatisfactionConvergence` | Stop when confidence threshold met   |
| `HybridConvergence`       | Compose strategies with AND/OR logic |

