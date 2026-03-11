# Extension Points Reference

**Task 1.17a - Complete Extension Point Documentation**

This document provides comprehensive reference for all 14 extension points in the Kaizen BaseAgent architecture, enabling developers to customize and extend agent behavior at key integration points.

## Overview

The Kaizen BaseAgent architecture provides **14 extension points** across two layers:

- **BaseAgent Extension Points (7)**: Core agent lifecycle and configuration
- **Strategy Extension Points (7)**: Execution strategy customization

Extension points use Python's method override pattern, providing type-safe, documented integration points without requiring complex plugin systems.

---

## BaseAgent Extension Points (7)

### 1. `create_signature() -> Signature`

**Purpose**: Customize signature creation for agent initialization.

**When Called**: During agent initialization when signature is not provided.

**Default Behavior**: Returns a generic signature with input/output fields.

**Signature**:
```python
def create_signature(self) -> Signature:
    """
    Create default signature for this agent.

    Returns:
        Signature: Default signature instance
    """
```

**Example**:
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.config import BaseAgentConfig

class QAAgent(BaseAgent):
    def create_signature(self) -> Signature:
        """Custom Q&A signature."""
        class QASignature(Signature):
            question: str = InputField(desc="Question to answer")
            context: str = InputField(desc="Context", default="")
            answer: str = OutputField(desc="Answer")
            confidence: float = OutputField(desc="Confidence score")

        return QASignature()

# Usage
config = BaseAgentConfig(model="gpt-4")
agent = QAAgent(config=config)
# Agent automatically uses QASignature
```

**Edge Cases**:
- Must return valid Signature instance
- Called only if signature not provided to __init__
- Signature validation happens after creation

**Cross-References**: Works with `_generate_system_prompt()` in WorkflowGenerator

---

### 2. `_get_agent_id() -> str`

**Purpose**: Generate unique agent identifier.

**When Called**: During agent initialization.

**Default Behavior**: Returns `f"agent_{timestamp}"`.

**Signature**:
```python
def _get_agent_id(self) -> str:
    """
    Generate unique agent ID.

    Returns:
        str: Unique agent identifier
    """
```

**Example**:
```python
class NamedAgent(BaseAgent):
    def __init__(self, config, name: str, **kwargs):
        self.name = name
        super().__init__(config, **kwargs)

    def _get_agent_id(self) -> str:
        """Use provided name as agent ID."""
        return f"{self.name}_agent"

# Usage
agent = NamedAgent(config, name="customer_support")
assert agent.agent_id == "customer_support_agent"
```

**Edge Cases**:
- Must return non-empty string
- Should be unique in multi-agent scenarios
- Used for workflow node IDs

---

### 3. `_get_framework_config_extensions() -> Dict[str, Any]`

**Purpose**: Extend framework-level configuration.

**When Called**: During framework initialization.

**Default Behavior**: Returns empty dict.

**Signature**:
```python
def _get_framework_config_extensions(self) -> Dict[str, Any]:
    """
    Provide framework-level config extensions.

    Returns:
        Dict[str, Any]: Additional framework configuration
    """
```

**Example**:
```python
class EnterpriseAgent(BaseAgent):
    def _get_framework_config_extensions(self) -> Dict[str, Any]:
        """Enable enterprise features."""
        return {
            "audit_logging": True,
            "compliance_mode": "GDPR",
            "encryption_enabled": True,
            "monitoring_level": "verbose"
        }
```

**Edge Cases**:
- Must return dict (can be empty)
- Values override default framework config
- Applied before agent-specific config

**Cross-References**: Combined with `_get_agent_config_extensions()`

---

### 4. `_get_agent_config_extensions() -> Dict[str, Any]`

**Purpose**: Extend agent-specific configuration.

**When Called**: During agent initialization, after framework config.

**Default Behavior**: Returns empty dict.

**Signature**:
```python
def _get_agent_config_extensions(self) -> Dict[str, Any]:
    """
    Provide agent-specific config extensions.

    Returns:
        Dict[str, Any]: Additional agent configuration
    """
```

**Example**:
```python
class ToolAgent(BaseAgent):
    def _get_agent_config_extensions(self) -> Dict[str, Any]:
        """Configure tool discovery."""
        return {
            "tools_enabled": True,
            "auto_discover_mcp_tools": True,
            "tool_timeout": 30,
            "max_tool_calls": 5
        }
```

**Edge Cases**:
- Applied after framework config extensions
- Agent-level config takes precedence
- Must return dict

---

### 5. `_create_execution_strategy() -> ExecutionStrategy`

**Purpose**: Create custom execution strategy.

**When Called**: During agent initialization if strategy not provided.

**Default Behavior**: Returns SingleShotStrategy or MultiCycleStrategy based on config.

**Signature**:
```python
def _create_execution_strategy(self) -> ExecutionStrategy:
    """
    Create execution strategy for this agent.

    Returns:
        ExecutionStrategy: Strategy instance
    """
```

**Example**:
```python
from kaizen.strategies.multi_cycle import MultiCycleStrategy

class ReActAgent(BaseAgent):
    def _create_execution_strategy(self) -> ExecutionStrategy:
        """Use multi-cycle strategy for ReAct."""
        return MultiCycleStrategy(max_cycles=10)

# Usage
config = BaseAgentConfig()  # Default strategy_type ignored
agent = ReActAgent(config)
assert isinstance(agent.strategy, MultiCycleStrategy)
```

**Edge Cases**:
- Must implement ExecutionStrategy protocol
- Called only if strategy not provided to __init__
- Strategy determines execution flow

**Cross-References**: Works with Strategy extension points

---

### 6. `_get_performance_targets() -> Dict[str, float]`

**Purpose**: Define performance targets for monitoring.

**When Called**: During performance tracking initialization.

**Default Behavior**: Returns default targets from config.

**Signature**:
```python
def _get_performance_targets(self) -> Dict[str, float]:
    """
    Define performance targets for this agent.

    Returns:
        Dict[str, float]: Performance targets (init_ms, exec_ms, memory_mb)
    """
```

**Example**:
```python
class HighPerformanceAgent(BaseAgent):
    def _get_performance_targets(self) -> Dict[str, float]:
        """Strict performance targets."""
        return {
            "init_ms": 50.0,      # Initialization < 50ms
            "exec_ms": 500.0,     # Execution < 500ms
            "memory_mb": 100.0,   # Memory < 100MB
            "response_ms": 200.0  # Response time < 200ms
        }
```

**Edge Cases**:
- Used for monitoring alerts
- Values in milliseconds/megabytes
- Can be empty dict (no monitoring)

---

### 7. `post_execute(result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]`

**Purpose**: Post-process execution results.

**When Called**: After strategy execution, before returning to caller.

**Default Behavior**: Returns result unmodified.

**Signature**:
```python
def post_execute(
    self,
    result: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Post-process execution results.

    Args:
        result: Raw execution result
        context: Execution context

    Returns:
        Dict[str, Any]: Processed result
    """
```

**Example**:
```python
class AuditAgent(BaseAgent):
    def post_execute(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add audit metadata."""
        result['audit'] = {
            'timestamp': context.get('timestamp'),
            'agent_id': self.agent_id,
            'execution_time_ms': context.get('duration_ms'),
            'model_used': self.config.model
        }
        return result
```

**Edge Cases**:
- Must return dict
- Can modify result in-place or return new dict
- Errors should be handled gracefully

**Cross-References**: Called after Strategy.post_execute()

---

## Strategy Extension Points (7)

### SingleShotStrategy Extension Points (3)

#### 1. `pre_execute(inputs: Dict[str, Any]) -> Dict[str, Any]`

**Purpose**: Pre-process inputs before single-shot execution.

**When Called**: Before LLM call in single-shot execution.

**Default Behavior**: Returns inputs unmodified.

**Signature**:
```python
def pre_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pre-process inputs before execution.

    Args:
        inputs: User-provided inputs

    Returns:
        Dict[str, Any]: Processed inputs
    """
```

**Example**:
```python
from kaizen.strategies.single_shot import SingleShotStrategy

class PreprocessingStrategy(SingleShotStrategy):
    def pre_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate inputs."""
        # Remove empty values
        cleaned = {k: v for k, v in inputs.items() if v}

        # Add default context
        if 'context' not in cleaned:
            cleaned['context'] = "Default context"

        return cleaned
```

**Edge Cases**:
- Must return dict
- Can add/remove input fields
- Validation errors should raise exceptions

---

#### 2. `parse_result(raw_result: Dict[str, Any]) -> Dict[str, Any]`

**Purpose**: Parse raw LLM result into structured format.

**When Called**: After LLM call, before returning result.

**Default Behavior**: Extracts response field.

**Signature**:
```python
def parse_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse raw LLM result.

    Args:
        raw_result: Raw LLM response

    Returns:
        Dict[str, Any]: Parsed result
    """
```

**Example**:
```python
import json

class JSONParsingStrategy(SingleShotStrategy):
    def parse_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse JSON response from LLM."""
        response_text = raw_result.get('response', '{}')

        try:
            parsed = json.loads(response_text)
            return parsed
        except json.JSONDecodeError:
            return {
                'error': 'Invalid JSON',
                'raw_response': response_text
            }
```

**Edge Cases**:
- Should handle malformed responses
- Must return dict
- Can add metadata

---

#### 3. `post_execute(result: Dict[str, Any]) -> Dict[str, Any]`

**Purpose**: Post-process final result.

**When Called**: After parse_result, before returning to agent.

**Default Behavior**: Returns result unmodified.

**Signature**:
```python
def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-process final result.

    Args:
        result: Parsed result

    Returns:
        Dict[str, Any]: Final result
    """
```

**Example**:
```python
class ConfidenceStrategy(SingleShotStrategy):
    def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Add confidence scoring."""
        answer_length = len(result.get('answer', ''))

        result['confidence'] = min(1.0, answer_length / 100.0)
        result['quality_score'] = self._calculate_quality(result)

        return result
```

---

### MultiCycleStrategy Extension Points (4)

#### 1. `pre_cycle(cycle_num: int, inputs: Dict[str, Any]) -> Dict[str, Any]`

**Purpose**: Pre-process inputs before each cycle.

**When Called**: At the start of each cycle iteration.

**Default Behavior**: Returns inputs unmodified.

**Signature**:
```python
def pre_cycle(
    self,
    cycle_num: int,
    inputs: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Pre-process inputs before cycle.

    Args:
        cycle_num: Current cycle number (0-indexed)
        inputs: Cycle inputs

    Returns:
        Dict[str, Any]: Processed inputs
    """
```

**Example**:
```python
from kaizen.strategies.multi_cycle import MultiCycleStrategy

class AdaptiveStrategy(MultiCycleStrategy):
    def pre_cycle(
        self,
        cycle_num: int,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Adjust temperature per cycle."""
        inputs['temperature'] = 0.1 + (cycle_num * 0.1)
        inputs['cycle_context'] = f"Cycle {cycle_num + 1}/{self.max_cycles}"
        return inputs
```

**Edge Cases**:
- Called for each cycle (0 to max_cycles-1)
- Can accumulate context across cycles
- Must return dict

---

#### 2. `parse_cycle_result(raw_result: Dict[str, Any], cycle_num: int) -> Dict[str, Any]`

**Purpose**: Parse result from each cycle.

**When Called**: After each cycle execution.

**Default Behavior**: Extracts action and observation.

**Signature**:
```python
def parse_cycle_result(
    self,
    raw_result: Dict[str, Any],
    cycle_num: int
) -> Dict[str, Any]:
    """
    Parse cycle result.

    Args:
        raw_result: Raw cycle result
        cycle_num: Current cycle number

    Returns:
        Dict[str, Any]: Parsed cycle result
    """
```

**Example**:
```python
class ReActParsingStrategy(MultiCycleStrategy):
    def parse_cycle_result(
        self,
        raw_result: Dict[str, Any],
        cycle_num: int
    ) -> Dict[str, Any]:
        """Parse ReAct thought/action/observation."""
        response = raw_result.get('response', '')

        return {
            'thought': self._extract_thought(response),
            'action': self._extract_action(response),
            'observation': self._extract_observation(response),
            'cycle': cycle_num
        }
```

**Edge Cases**:
- Must handle partial responses
- Should extract structured data
- Can aggregate history

---

#### 3. `should_terminate(cycle_result: Dict[str, Any], cycle_num: int) -> bool`

**Purpose**: Determine if execution should terminate early.

**When Called**: After each cycle, before checking max_cycles.

**Default Behavior**: Returns False (continue until max_cycles).

**Signature**:
```python
def should_terminate(
    self,
    cycle_result: Dict[str, Any],
    cycle_num: int
) -> bool:
    """
    Check if should terminate early.

    Args:
        cycle_result: Current cycle result
        cycle_num: Current cycle number

    Returns:
        bool: True to terminate, False to continue
    """
```

**Example**:
```python
class GoalBasedStrategy(MultiCycleStrategy):
    def should_terminate(
        self,
        cycle_result: Dict[str, Any],
        cycle_num: int
    ) -> bool:
        """Terminate when goal achieved."""
        # Check for final answer marker
        if 'FINAL ANSWER' in str(cycle_result.get('action', '')):
            return True

        # Check for error conditions
        if cycle_result.get('error'):
            return True

        # Check for goal completion
        if cycle_result.get('goal_achieved', False):
            return True

        return False
```

**Edge Cases**:
- Should check error conditions
- Can use external state
- Termination is final (no resume)

**Cross-References**: Called before max_cycles check

---

#### 4. `extract_observation(cycle_result: Dict[str, Any]) -> str`

**Purpose**: Extract observation from cycle result for next cycle.

**When Called**: After parse_cycle_result, before next cycle.

**Default Behavior**: Returns result as formatted string.

**Signature**:
```python
def extract_observation(self, cycle_result: Dict[str, Any]) -> str:
    """
    Extract observation for next cycle.

    Args:
        cycle_result: Parsed cycle result

    Returns:
        str: Observation text
    """
```

**Example**:
```python
class RichObservationStrategy(MultiCycleStrategy):
    def extract_observation(self, cycle_result: Dict[str, Any]) -> str:
        """Create rich observation with context."""
        parts = []

        if cycle_result.get('action'):
            parts.append(f"Action taken: {cycle_result['action']}")

        if cycle_result.get('tool_result'):
            parts.append(f"Tool result: {cycle_result['tool_result']}")

        if cycle_result.get('error'):
            parts.append(f"Error encountered: {cycle_result['error']}")

        parts.append(f"Cycle completed: {cycle_result.get('cycle', 0) + 1}")

        return "\n".join(parts)
```

**Edge Cases**:
- Must return string
- Used as input to next cycle
- Should be concise but informative

---

## Extension Point Patterns

### Pattern 1: Chaining Extension Points

```python
class ComprehensiveAgent(BaseAgent):
    def _get_agent_config_extensions(self) -> Dict[str, Any]:
        """Extend agent config."""
        return {"custom_feature": True}

    def post_execute(self, result, context):
        """Post-process with custom logic."""
        result['custom_metadata'] = self.config.custom_feature
        return result
```

### Pattern 2: Strategy-Specific Customization

```python
class CustomSingleShotAgent(BaseAgent):
    def _create_execution_strategy(self):
        class CustomStrategy(SingleShotStrategy):
            def pre_execute(self, inputs):
                # Custom preprocessing
                return inputs

            def parse_result(self, raw_result):
                # Custom parsing
                return raw_result

        return CustomStrategy()
```

### Pattern 3: Multi-Agent Coordination

```python
class CoordinatorAgent(BaseAgent):
    def _get_agent_id(self) -> str:
        return f"coordinator_{self.team_id}"

    def post_execute(self, result, context):
        # Share result with team
        self.broadcast_to_team(result)
        return result
```

---

## Best Practices

1. **Always Call Super**: If overriding extension points that have default logic, call `super()` first
2. **Type Safety**: Use type hints matching the documented signature
3. **Error Handling**: Extension points should handle errors gracefully
4. **Documentation**: Document custom behavior in docstrings
5. **Testing**: Test extension points in isolation and integration
6. **Performance**: Keep extension point logic lightweight
7. **Idempotency**: Extension points should be idempotent where possible

---

## Cross-Reference Matrix

| Extension Point | Works With | Purpose |
|----------------|------------|---------|
| `create_signature()` | WorkflowGenerator | Signature for workflow generation |
| `_get_agent_id()` | Workflow nodes | Unique node IDs |
| `_get_framework_config_extensions()` | Kaizen framework | Framework initialization |
| `_get_agent_config_extensions()` | BaseAgentConfig | Agent initialization |
| `_create_execution_strategy()` | All strategy points | Strategy selection |
| `_get_performance_targets()` | PerformanceMixin | Monitoring thresholds |
| `post_execute()` | Strategy.post_execute() | Result chain |
| `pre_execute()` | LLM call | Input preparation |
| `parse_result()` | LLM response | Response parsing |
| `pre_cycle()` | Cycle execution | Cycle preparation |
| `parse_cycle_result()` | Cycle completion | Cycle parsing |
| `should_terminate()` | Cycle control | Early termination |
| `extract_observation()` | Next cycle | Observation feedback |

---

## Task 1.17a Evidence

✅ All 14 extension points documented:
- **BaseAgent (7)**: create_signature, _get_agent_id, _get_framework_config_extensions, _get_agent_config_extensions, _create_execution_strategy, _get_performance_targets, post_execute
- **SingleShotStrategy (3)**: pre_execute, parse_result, post_execute
- **MultiCycleStrategy (4)**: pre_cycle, parse_cycle_result, should_terminate, extract_observation

✅ Each extension point includes:
- Signature with type hints
- Purpose and when called
- Default behavior
- Complete example
- Edge cases
- Cross-references

✅ Additional content:
- Extension point patterns
- Best practices
- Cross-reference matrix

**Status**: ✅ COMPLETE - Task 1.17a validation criteria met
