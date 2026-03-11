# ADR-006: Requirements Matrix & Specifications

**Related ADR**: ADR-006-agent-base-architecture.md
**Date**: 2025-10-01
**Status**: Proposed

This document provides comprehensive functional and non-functional requirements for the Agent Base Architecture refactoring.

---

## Functional Requirements Matrix

| Requirement ID | Description | Input | Output | Business Logic | Edge Cases | SDK Mapping | Priority | Status |
|----------------|-------------|-------|--------|----------------|------------|-------------|----------|---------|
| **FR-001** | BaseAgent handles framework initialization | BaseAgentConfig | Initialized Kaizen framework + agent | Auto-detect provider, build config, create agent | Missing API keys, Ollama not running | Kaizen.create_agent() | P0 | Pending |
| **FR-002** | BaseAgent supports signature-based execution | Signature, **kwargs | Structured result dict | Compile signature, execute agent.execute(**kwargs) | Signature compilation fails, missing fields | SignatureCompiler, LLMAgentNode | P0 | Pending |
| **FR-003** | BaseAgent supports fallback execution (no signature) | **kwargs as prompt | String or dict result | Build prompt from kwargs, execute without signature | Empty inputs, malformed kwargs | LLMAgentNode direct execution | P1 | Pending |
| **FR-004** | Single BaseAgentConfig with feature flags | Feature flags (bool) | Configured BaseAgentConfig | Feature flags enable/disable capabilities | Conflicting flags, invalid combinations | N/A (config only) | P0 | Pending |
| **FR-005** | Provider auto-detection (OpenAI/Ollama) | Environment vars (OPENAI_API_KEY) or Ollama availability | provider_config dict | Check OPENAI_API_KEY → OpenAI, check Ollama running → Ollama, else error | Both available (OpenAI priority), neither available | get_default_model_config() | P0 | Pending |
| **FR-006** | Standardized error handling across agents | Exception during execution | Error response dict with error_code, message, details | Catch specific exceptions (Timeout, Connection, Value), return structured error | Unknown exceptions, nested exceptions | ErrorHandlingMixin | P0 | Pending |
| **FR-007** | Consistent logging (no duplicate handlers) | Log messages | Formatted log output | Configure logging once in BaseAgent, check for existing handlers | Multiple BaseAgent instances, concurrent logging | LoggingMixin | P1 | Pending |
| **FR-008** | Performance metrics tracking (optional) | enable_performance_tracking=True | performance_metrics dict | Track framework init, agent creation, execution times, success rate | Very fast execution (<1ms), clock skew | PerformanceMixin | P1 | Pending |
| **FR-009** | Batch processing capability (opt-in via mixin) | enable_batch_processing=True, list of inputs | list of results | Execute agent for each input, collect results, add batch metadata | Empty list, failures mid-batch | BatchProcessingMixin | P2 | Pending |
| **FR-010** | SingleShotStrategy for QA, CoT | agent, signature_input, config | Result dict with metadata | Execute once: pre_execute → execute → parse → post_execute | Execution timeout, invalid signature | ExecutionStrategy protocol | P0 | Pending |
| **FR-011** | MultiCycleStrategy for ReAct (up to 10 cycles) | agent, signature_input, config, max_cycles | Result dict with action_history, observations | Loop: pre_cycle → execute → parse → check termination → extract observation | Max cycles reached, termination condition never met | ExecutionStrategy protocol | P0 | Pending |
| **FR-012** | Extension hooks: pre_execute, post_execute, parse_result | Override methods | Modified input/result | Call hooks at appropriate points in execution flow | Hook raises exception, hook modifies structure | BaseAgent methods | P0 | Pending |
| **FR-013** | Strategy-specific hooks: pre_cycle, should_terminate, extract_observation | Override methods in strategy | Modified cycle input, bool termination, observation string | MultiCycleStrategy calls hooks during execution | Termination logic error, observation extraction fails | MultiCycleStrategy methods | P0 | Pending |
| **FR-014** | QA Agent - question answering with confidence scoring | question, context | answer, confidence, reasoning | Execute QASignature, extract structured outputs | Low confidence (<threshold), empty question | QAAgent + SingleShotStrategy | P0 | Pending |
| **FR-015** | QA Agent - batch processing with shared context | list of questions, shared context | list of results with batch metadata | Use BatchProcessingMixin to process all questions with same context | Large batch (100+ questions), rate limiting | QAAgent + BatchProcessingMixin | P2 | Pending |
| **FR-016** | CoT Agent - 5-step reasoning extraction | problem, context | step1-5, final_answer, confidence | Execute CoTSignature, extract 5 reasoning steps + final answer | LLM skips steps, malformed steps | CoTAgent + SingleShotStrategy | P0 | Pending |
| **FR-017** | CoT Agent - performance metrics tracking | problem, context | result + detailed metrics | Use PerformanceMixin to track init, creation, execution times | Performance overhead impacts execution | CoTAgent + PerformanceMixin | P1 | Pending |
| **FR-018** | ReAct Agent - MCP tool discovery and execution | task, context | solution with tool usage trace | Discover MCP tools, make available in signature, execute via MCP client | No MCP tools available, tool execution fails | ReActAgent + MultiCycleStrategy | P0 | Pending |
| **FR-019** | ReAct Agent - multi-cycle reasoning loop | task, context, max_cycles | action_history, observations, solution | Execute MultiCycleStrategy with ReActSignature | Infinite loop, no progress | ReActAgent + MultiCycleStrategy | P0 | Pending |
| **FR-020** | ReAct Agent - action history tracking | Each cycle's thought, action, observation | action_history list | Append each cycle's results to action_history | Large history (memory), serialization | ReActAgent result building | P1 | Pending |

---

## Non-Functional Requirements

### Performance Requirements

| Requirement ID | Description | Target | Measurement | Acceptance Criteria | Priority | Status |
|----------------|-------------|--------|-------------|---------------------|----------|---------|
| **NFR-001** | Framework initialization latency | <100ms | Time from BaseAgent.__init__() start to framework ready | 95th percentile <100ms across 100 runs | P0 | Pending |
| **NFR-002** | Agent creation latency | <200ms | Time from framework ready to agent.create_agent() complete | 95th percentile <200ms across 100 runs | P0 | Pending |
| **NFR-003** | QA execution average latency | <500ms | Time from agent.execute() to result returned (excluding LLM time) | Average <500ms across 50 executions | P1 | Pending |
| **NFR-004** | CoT execution average latency | <1000ms | Time from agent.execute() to result returned (excluding LLM time) | Average <1000ms across 50 executions | P1 | Pending |
| **NFR-005** | ReAct cycle overhead | <50ms per cycle | Time overhead of strategy logic (excluding LLM time) | <50ms per cycle measured across 100 cycles | P2 | Pending |
| **NFR-006** | Memory overhead | <10MB per agent instance | Memory usage of BaseAgent + strategy + mixins | <10MB measured via memory profiler | P2 | Pending |
| **NFR-007** | Abstraction overhead | <1% vs direct execution | Performance difference between BaseAgent and direct LLMAgentNode | <1% measured via benchmarks | P2 | Pending |

### Quality Requirements

| Requirement ID | Description | Target | Measurement | Acceptance Criteria | Priority | Status |
|----------------|-------------|--------|-------------|---------------------|----------|---------|
| **NFR-008** | Test coverage for base architecture | 95%+ | pytest-cov coverage report | 95%+ line and branch coverage for base_agent.py, execution_strategies.py | P0 | Pending |
| **NFR-009** | Code reduction from current | 90%+ | Lines of code comparison | Old: 1,537 lines → New: <200 lines for all agents combined | P0 | Pending |
| **NFR-010** | Duplication elimination | <5% | Code clone detection | <5% duplicated code across agents (currently 91%) | P0 | Pending |
| **NFR-011** | Backward compatibility | 100% | All existing examples pass without changes | All examples in examples/1-single-agent/ work with compatibility shims | P0 | Pending |
| **NFR-012** | Zero functional regression | 100% | Tier 2-3 tests pass | All integration and E2E tests pass with new architecture | P0 | Pending |
| **NFR-013** | Documentation completeness | 100% | All public methods documented | Docstrings for all public methods, extension guide complete | P1 | Pending |

### Security Requirements

| Requirement ID | Description | Target | Measurement | Acceptance Criteria | Priority | Status |
|----------------|-------------|--------|-------------|---------------------|----------|---------|
| **NFR-014** | API key protection | No logging of secrets | Audit log output | API keys never appear in logs or error messages | P0 | Pending |
| **NFR-015** | Error message safety | No sensitive info in user-facing errors | Error message review | Error messages don't expose internal paths, keys, or tokens | P0 | Pending |
| **NFR-016** | Audit trail completeness | All agent executions logged (when enabled) | Audit trail validation | Every execution recorded with timestamp, inputs (sanitized), outputs | P1 | Pending |

### Scalability Requirements

| Requirement ID | Description | Target | Measurement | Acceptance Criteria | Priority | Status |
|----------------|-------------|--------|-------------|---------------------|----------|---------|
| **NFR-017** | Concurrent agent instances | 100+ agents | Stress test with 100 agents | 100 agents can initialize and execute concurrently | P2 | Pending |
| **NFR-018** | Batch processing scalability | 1000+ items | Batch test with 1000 questions | QA agent can process 1000 questions in batch | P2 | Pending |
| **NFR-019** | Long-running ReAct workflows | 50+ cycles | Extended ReAct execution | ReAct agent stable for 50+ cycle workflows | P2 | Pending |

---

## Extension Point Specification

### BaseAgent Extension Points

All extension points are designed to be **optional overrides**. Default implementations provide sensible behavior.

#### 1. Signature Creation

**Method**: `create_signature() -> Optional[Signature]`

**Purpose**: Define the structured input/output specification for the agent.

**Default**: Returns `None` (fallback execution mode)

**When to Override**: Always for signature-based agents

**Example**:
```python
def create_signature(self) -> Signature:
    class CustomSignature(Signature):
        input_field: str = InputField(desc="Input description")
        output_field: str = OutputField(desc="Output description")
    return CustomSignature()
```

**Edge Cases**:
- Return `None` to use fallback execution (no signature)
- Signature compilation fails → error with clear message
- Missing required fields → validation error

#### 2. Agent Identifier

**Method**: `_get_agent_id() -> str`

**Purpose**: Set unique identifier for the agent (used in logging, audit trail, metrics)

**Default**: `"base_agent"`

**When to Override**: For specialized agents to enable identification

**Example**:
```python
def _get_agent_id(self) -> str:
    return "qa_agent_v1"
```

**Edge Cases**:
- Empty string → use default
- Non-string return → convert to string
- Duplicate IDs → allowed (agents are independent)

#### 3. Framework Configuration Extensions

**Method**: `_get_framework_config_extensions() -> Dict[str, Any]`

**Purpose**: Add custom framework-level configuration (e.g., enable MCP, multi-agent)

**Default**: `{}` (no extensions)

**When to Override**: When agent needs framework-level features

**Example**:
```python
def _get_framework_config_extensions(self) -> Dict[str, Any]:
    return {
        'mcp_enabled': True,
        'multi_agent_enabled': False,
        'compliance_mode': 'enterprise'
    }
```

**Edge Cases**:
- Conflicting with base config → extensions override
- Invalid config keys → validated by KaizenConfig
- Type mismatches → validation error

#### 4. Agent Configuration Extensions

**Method**: `_get_agent_config_extensions() -> Dict[str, Any]`

**Purpose**: Add custom agent-level configuration (e.g., generation settings, tools)

**Default**: `{}` (no extensions)

**When to Override**: When agent needs specific generation or behavior settings

**Example**:
```python
def _get_agent_config_extensions(self) -> Dict[str, Any]:
    return {
        'generation_config': {
            'reasoning_pattern': 'chain_of_thought',
            'step_verification': True
        },
        'tools': ['calculator', 'web_search']
    }
```

**Edge Cases**:
- Conflicting with base config → extensions override
- Provider-specific settings → passed through to LLMAgentNode
- Invalid settings → error from underlying provider

#### 5. Execution Strategy

**Method**: `_create_execution_strategy() -> ExecutionStrategy`

**Purpose**: Select execution pattern (single-shot, multi-cycle, streaming)

**Default**: `SingleShotStrategy()`

**When to Override**: For multi-cycle agents (ReAct) or custom execution patterns

**Example**:
```python
def _create_execution_strategy(self) -> ExecutionStrategy:
    return MultiCycleStrategy(max_cycles=10)
```

**Edge Cases**:
- Return `None` → use default (SingleShotStrategy)
- Custom strategy doesn't implement protocol → runtime error
- Strategy raises exception → propagated to caller

#### 6. Performance Targets

**Method**: `_get_performance_targets() -> Dict[str, float]`

**Purpose**: Define performance targets for validation and monitoring

**Default**: `{'framework_init_max_ms': 100, 'agent_creation_max_ms': 200, 'execution_max_ms': 500}`

**When to Override**: When agent has different performance characteristics

**Example**:
```python
def _get_performance_targets(self) -> Dict[str, float]:
    return {
        'framework_init_max_ms': 100,
        'agent_creation_max_ms': 200,
        'execution_max_ms': 1000  # CoT needs more time
    }
```

**Edge Cases**:
- Missing keys → use defaults
- Negative values → validation error
- Zero values → validation error (unrealistic)

#### 7. Post-Execution Processing

**Method**: `post_execute(result: Dict[str, Any]) -> Dict[str, Any]`

**Purpose**: Process execution result before returning to caller

**Default**: Returns result unchanged

**When to Override**: To add custom metadata, transform outputs, validate results

**Example**:
```python
def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
    # Add agent-specific metadata
    result['metadata']['agent_type'] = 'react'
    result['metadata']['tools_used'] = len([
        a for a in result.get('action_history', [])
        if a.get('action') == 'tool_use'
    ])
    return result
```

**Edge Cases**:
- Raise exception → execution fails with error
- Return incompatible structure → caller may fail
- Modify in-place → allowed but discouraged

---

### SingleShotStrategy Extension Points

#### 1. Pre-Execute Hook

**Method**: `pre_execute(**kwargs) -> Dict[str, Any]`

**Purpose**: Prepare inputs before execution

**Default**: Returns kwargs unchanged

**When to Override**: To validate, transform, or enrich inputs

**Example**:
```python
def pre_execute(self, **kwargs) -> Dict[str, Any]:
    # Ensure question is not empty
    if not kwargs.get('question', '').strip():
        raise ValueError("Question cannot be empty")

    # Add default context if missing
    if 'context' not in kwargs:
        kwargs['context'] = ""

    return kwargs
```

**Edge Cases**:
- Raise exception → execution fails immediately
- Return incompatible structure → execution may fail
- Add new keys → passed to agent.execute()

#### 2. Result Parsing Hook

**Method**: `parse_result(result: Any) -> Dict[str, Any]`

**Purpose**: Parse and structure execution result

**Default**: If dict, return as-is; else wrap in `{'result': str(result)}`

**When to Override**: To extract structured outputs, handle different result formats

**Example**:
```python
def parse_result(self, result: Any) -> Dict[str, Any]:
    # Handle signature-based results
    if isinstance(result, dict) and 'answer' in result:
        return {
            'answer': result['answer'],
            'confidence': float(result.get('confidence', 0.8)),
            'reasoning': result.get('reasoning', '')
        }

    # Handle text results
    if isinstance(result, str):
        return {
            'answer': result,
            'confidence': 0.7,
            'reasoning': 'Direct string response'
        }

    # Fallback
    return {'answer': str(result), 'confidence': 0.5, 'reasoning': 'Unknown format'}
```

**Edge Cases**:
- Raise exception → execution fails
- Return non-dict → caller may fail
- Missing required fields → caller may fail

#### 3. Post-Execute Hook

**Method**: `post_execute(parsed_result: Dict[str, Any]) -> Dict[str, Any]`

**Purpose**: Post-process parsed result before returning

**Default**: Returns parsed_result unchanged

**When to Override**: To validate outputs, add metadata, transform structure

**Example**:
```python
def post_execute(self, parsed_result: Dict[str, Any]) -> Dict[str, Any]:
    # Validate confidence is in valid range
    confidence = parsed_result.get('confidence', 0.5)
    if not 0.0 <= confidence <= 1.0:
        parsed_result['confidence'] = max(0.0, min(1.0, confidence))

    # Add execution metadata
    parsed_result['metadata'] = parsed_result.get('metadata', {})
    parsed_result['metadata']['strategy'] = 'single_shot'

    return parsed_result
```

**Edge Cases**:
- Raise exception → execution fails
- Return incompatible structure → caller may fail
- Modify in-place → allowed but discouraged

---

### MultiCycleStrategy Extension Points

#### 1. Pre-Cycle Hook

**Method**: `pre_cycle(cycle: int, observations: List[str], **kwargs) -> Dict[str, Any]`

**Purpose**: Prepare inputs for cycle execution

**Default**: Returns kwargs unchanged

**When to Override**: To update context with observations, adjust inputs per cycle

**Example**:
```python
def pre_cycle(self, cycle: int, observations: List[str], **kwargs) -> Dict[str, Any]:
    # Add cycle-specific context
    kwargs['cycle_number'] = cycle

    # Update context with all observations
    if observations:
        obs_text = "\n\n".join([
            f"Observation {i+1}: {obs}"
            for i, obs in enumerate(observations)
        ])
        kwargs['context'] = kwargs.get('context', '') + "\n\n" + obs_text

    return kwargs
```

**Edge Cases**:
- Raise exception → cycle fails, execution terminates
- Return incompatible structure → agent.execute() may fail
- Very long context → may exceed token limits

#### 2. Cycle Result Parsing Hook

**Method**: `parse_cycle_result(result: Any, cycle: int) -> Dict[str, Any]`

**Purpose**: Parse result from cycle execution

**Default**: If dict, return with cycle number; else wrap in dict

**When to Override**: To extract thought, action, observation from result

**Example**:
```python
def parse_cycle_result(self, result: Any, cycle: int) -> Dict[str, Any]:
    if isinstance(result, dict) and 'action' in result:
        return {
            'cycle': cycle,
            'thought': result.get('thought', ''),
            'action': result.get('action', 'finish'),
            'action_input': result.get('action_input', {}),
            'confidence': result.get('confidence', 0.8),
            'timestamp': time.time()
        }

    # Parse from text response
    thought, action, action_input = self._parse_text_result(str(result))
    return {
        'cycle': cycle,
        'thought': thought,
        'action': action,
        'action_input': action_input,
        'confidence': 0.7,
        'timestamp': time.time()
    }
```

**Edge Cases**:
- Raise exception → cycle fails, execution terminates
- Missing required fields → use defaults
- Malformed result → fallback parsing

#### 3. Termination Condition Hook

**Method**: `should_terminate(parsed_result: Dict[str, Any], cycle: int) -> bool`

**Purpose**: Determine if execution should terminate

**Default**: Returns `True` if `parsed_result['action'] == 'finish'`

**When to Override**: For custom termination logic

**Example**:
```python
def should_terminate(self, parsed_result: Dict[str, Any], cycle: int) -> bool:
    # Terminate on finish action
    if parsed_result.get('action') == 'finish':
        return True

    # Terminate on low confidence after 3 cycles
    if cycle >= 3 and parsed_result.get('confidence', 1.0) < 0.3:
        logger.warning(f"Terminating due to low confidence at cycle {cycle}")
        return True

    # Terminate if no progress
    if parsed_result.get('action') == 'clarify':
        return True

    return False
```

**Edge Cases**:
- Always return `False` → max cycles reached, forced termination
- Raise exception → cycle fails, execution terminates
- Non-bool return → converted to bool

#### 4. Observation Extraction Hook

**Method**: `extract_observation(parsed_result: Dict[str, Any]) -> str`

**Purpose**: Extract observation for next cycle's context

**Default**: Returns `parsed_result.get('observation', str(parsed_result))`

**When to Override**: For custom observation extraction logic

**Example**:
```python
def extract_observation(self, parsed_result: Dict[str, Any]) -> str:
    # Extract observation based on action type
    action = parsed_result.get('action', '')

    if action == 'tool_use':
        tool_name = parsed_result.get('action_input', {}).get('tool', 'unknown')
        tool_result = parsed_result.get('tool_result', 'No result')
        return f"Tool '{tool_name}' executed: {tool_result}"

    if action == 'finish':
        return "Task completed"

    # Fallback
    return parsed_result.get('observation', str(parsed_result))
```

**Edge Cases**:
- Raise exception → cycle fails, execution terminates
- Return empty string → valid observation (no new info)
- Return very long string → may exceed token limits in next cycle

---

## Migration Requirements

### Migration Path from Old to New

**Timeline**: Phased migration with backward compatibility

**Phase 1**: New architecture available alongside old implementations
**Phase 2**: All examples updated to use new architecture (with compatibility shims)
**Phase 3**: Old implementations deprecated (with warnings)
**Phase 4**: Old implementations removed (next major version)

### Migration Checklist

**For SDK Developers**:
- [ ] Create BaseAgent with full framework initialization logic
- [ ] Create BaseAgentConfig with all feature flags
- [ ] Implement SingleShotStrategy with all hooks
- [ ] Implement MultiCycleStrategy with all hooks
- [ ] Create all mixins (Logging, Error, Performance, Batch)
- [ ] Write comprehensive Tier 1 unit tests (95%+ coverage)
- [ ] Implement QAAgent (15-20 lines)
- [ ] Implement CoTAgent (25-30 lines)
- [ ] Implement ReActAgent (30-35 lines)
- [ ] Write Tier 2 integration tests (real LLMs)
- [ ] Write Tier 3 E2E tests (complete workflows)
- [ ] Update all example files to use new agents
- [ ] Add compatibility shims in old files
- [ ] Create migration guide documentation
- [ ] Create extension point guide documentation
- [ ] Run performance benchmarks (old vs new)
- [ ] Validate performance targets met (<100ms, <200ms)
- [ ] Add deprecation warnings to old implementations
- [ ] Update architecture documentation
- [ ] Create PR with all changes

**For End Users** (using Kaizen):
- [ ] Review migration guide
- [ ] Identify usage of old agent classes (SimpleQAAgent, ChainOfThoughtAgent, KaizenReActAgent)
- [ ] Update imports from `examples.*` to `kaizen.agents.*`
- [ ] Update config from `QAConfig` to `BaseAgentConfig`
- [ ] Update method calls from `agent.ask()` to `agent.execute()`
- [ ] Test with updated code (should work identically)
- [ ] Remove compatibility shims when ready (optional)

### Breaking Changes

**None** - 100% backward compatible with compatibility shims

**Compatibility Shims** (temporary, deprecated):
```python
# examples/1-single-agent/simple-qa/workflow.py
from kaizen.agents import QAAgent as NewQAAgent
from kaizen.core import BaseAgentConfig

import warnings

# Deprecated - use kaizen.agents.QAAgent directly
class SimpleQAAgent(NewQAAgent):
    def __init__(self, config):
        warnings.warn(
            "SimpleQAAgent is deprecated. Use kaizen.agents.QAAgent instead.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(config)

    def ask(self, question: str, context: str = ""):
        # Compatibility wrapper
        return self.execute(question=question, context=context)

# Deprecated - use kaizen.core.BaseAgentConfig
QAConfig = BaseAgentConfig
```

**Removal Timeline**:
- **v0.10.0**: New architecture available, old implementations work with warnings
- **v0.11.0**: Old implementations removed (breaking change for those not migrated)

---

## Testing Requirements

### Tier 1: Unit Tests (No External Dependencies)

**Goal**: Test base architecture in isolation with 95%+ coverage

**Files**:
- `tests/unit/core/test_base_agent.py` (300-400 lines)
- `tests/unit/core/test_execution_strategies.py` (200-300 lines)
- `tests/unit/agents/test_qa_agent.py` (100-150 lines)
- `tests/unit/agents/test_cot_agent.py` (100-150 lines)
- `tests/unit/agents/test_react_agent.py` (100-150 lines)

**Test Cases**:

```python
# test_base_agent.py
class TestBaseAgentInitialization:
    def test_init_with_auto_detection_openai(self, mock_openai):
        """Test BaseAgent init with OpenAI auto-detected."""

    def test_init_with_auto_detection_ollama(self, mock_ollama):
        """Test BaseAgent init with Ollama auto-detected."""

    def test_init_with_explicit_provider(self):
        """Test BaseAgent init with explicit provider config."""

    def test_init_failure_no_provider(self):
        """Test BaseAgent init fails when no provider available."""

    def test_framework_config_building(self):
        """Test framework config is built correctly."""

    def test_agent_config_building(self):
        """Test agent config is built correctly."""

    def test_signature_compilation(self, mock_agent):
        """Test signature is compiled and assigned."""

    def test_performance_tracking_enabled(self):
        """Test performance metrics tracked when enabled."""

    def test_performance_tracking_disabled(self):
        """Test performance metrics not tracked when disabled."""


class TestBaseAgentExtensionPoints:
    def test_get_agent_id_override(self):
        """Test _get_agent_id can be overridden."""

    def test_framework_config_extensions_override(self):
        """Test _get_framework_config_extensions merges correctly."""

    def test_agent_config_extensions_override(self):
        """Test _get_agent_config_extensions merges correctly."""

    def test_create_execution_strategy_override(self):
        """Test _create_execution_strategy can be overridden."""

    def test_performance_targets_override(self):
        """Test _get_performance_targets can be overridden."""

    def test_post_execute_hook_called(self, mock_agent):
        """Test post_execute hook is called after execution."""


class TestBaseAgentExecution:
    def test_execute_with_signature(self, mock_agent_with_signature):
        """Test execute with signature-based agent."""

    def test_execute_without_signature(self, mock_agent_no_signature):
        """Test execute with fallback (no signature)."""

    def test_execute_calls_strategy(self, mock_strategy):
        """Test execute delegates to strategy."""

    def test_execute_calls_post_execute(self, mock_agent):
        """Test execute calls post_execute hook."""

    def test_execute_error_handling(self, mock_agent):
        """Test execute handles errors correctly."""


# test_execution_strategies.py
class TestSingleShotStrategy:
    def test_execute_with_signature(self, mock_agent):
        """Test SingleShotStrategy with signature-based agent."""

    def test_execute_without_signature(self, mock_agent):
        """Test SingleShotStrategy with fallback execution."""

    def test_pre_execute_hook_called(self, mock_strategy):
        """Test pre_execute hook is called."""

    def test_parse_result_hook_called(self, mock_strategy):
        """Test parse_result hook is called."""

    def test_post_execute_hook_called(self, mock_strategy):
        """Test post_execute hook is called."""

    def test_execution_metadata_added(self, mock_agent):
        """Test execution metadata is added to result."""

    def test_execution_time_tracked(self, mock_agent):
        """Test execution time is tracked."""


class TestMultiCycleStrategy:
    def test_execute_single_cycle(self, mock_agent):
        """Test MultiCycleStrategy with immediate termination."""

    def test_execute_multiple_cycles(self, mock_agent):
        """Test MultiCycleStrategy with multiple cycles."""

    def test_execute_max_cycles_reached(self, mock_agent):
        """Test MultiCycleStrategy terminates at max cycles."""

    def test_pre_cycle_hook_called(self, mock_strategy):
        """Test pre_cycle hook is called each cycle."""

    def test_parse_cycle_result_hook_called(self, mock_strategy):
        """Test parse_cycle_result hook is called each cycle."""

    def test_should_terminate_hook_called(self, mock_strategy):
        """Test should_terminate hook is called each cycle."""

    def test_extract_observation_hook_called(self, mock_strategy):
        """Test extract_observation hook is called each cycle."""

    def test_action_history_tracked(self, mock_agent):
        """Test action history is tracked across cycles."""

    def test_observations_accumulated(self, mock_agent):
        """Test observations are accumulated across cycles."""

    def test_context_updated_with_observations(self, mock_agent):
        """Test context is updated with observations each cycle."""
```

### Tier 2: Integration Tests (Real Infrastructure)

**Goal**: Test with real LLM providers (OpenAI, Ollama) - NO MOCKING

**Files**:
- `tests/integration/agents/test_qa_agent_integration.py`
- `tests/integration/agents/test_cot_agent_integration.py`
- `tests/integration/agents/test_react_agent_integration.py`

**Test Cases**:

```python
# test_qa_agent_integration.py
@pytest.mark.integration
@pytest.mark.openai
class TestQAAgentOpenAI:
    def test_qa_simple_question_openai(self):
        """Test QA agent with simple question using OpenAI."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4o-mini")
        agent = QAAgent(config)
        result = agent.execute(question="What is 2+2?")
        assert "4" in result['answer']
        assert result['confidence'] > 0.7

    def test_qa_with_context_openai(self):
        """Test QA agent with context using OpenAI."""
        config = BaseAgentConfig(llm_provider="openai")
        agent = QAAgent(config)
        result = agent.execute(
            question="What is the capital?",
            context="France is a country in Europe."
        )
        assert "paris" in result['answer'].lower()


@pytest.mark.integration
@pytest.mark.ollama
class TestQAAgentOllama:
    def test_qa_simple_question_ollama(self):
        """Test QA agent with simple question using Ollama."""
        config = BaseAgentConfig(llm_provider="ollama", model="llama3.2")
        agent = QAAgent(config)
        result = agent.execute(question="What is 2+2?")
        assert "4" in result['answer']


# test_cot_agent_integration.py
@pytest.mark.integration
@pytest.mark.openai
class TestCoTAgentOpenAI:
    def test_cot_math_problem_openai(self):
        """Test CoT agent with math problem using OpenAI."""
        config = BaseAgentConfig(llm_provider="openai")
        agent = CoTAgent(config)
        result = agent.execute(
            problem="If a train travels 60 mph for 3 hours, then 80 mph for 2 hours, what total distance?"
        )
        assert 'step1' in result
        assert 'step2' in result
        assert 'final_answer' in result
        assert "340" in result['final_answer'] or "340" in str(result)


# test_react_agent_integration.py
@pytest.mark.integration
@pytest.mark.openai
class TestReActAgentOpenAI:
    def test_react_simple_task_openai(self):
        """Test ReAct agent with simple task using OpenAI."""
        config = BaseAgentConfig(llm_provider="openai")
        agent = ReActAgent(config)
        result = agent.execute(task="What is 10 + 15?")
        assert 'action_history' in result
        assert len(result['action_history']) > 0
```

### Tier 3: E2E Tests (Complete Workflows)

**Goal**: Test complete example workflows end-to-end

**Files**:
- `tests/e2e/agents/test_all_agents_e2e.py`

**Test Cases**:

```python
@pytest.mark.e2e
class TestQAAgentE2E:
    def test_qa_example_workflow(self):
        """Test QA example from documentation works end-to-end."""
        # Run the exact code from docs/examples/qa_agent.md
        from kaizen.agents import QAAgent
        from kaizen.core import BaseAgentConfig

        config = BaseAgentConfig(temperature=0.1)
        agent = QAAgent(config)

        result = agent.execute(
            question="What is machine learning?",
            context="Explain for general audience"
        )

        assert result['answer']
        assert result['confidence'] > 0.0
        assert result['reasoning']
        assert result['metadata']['execution_time_ms'] > 0

    def test_qa_batch_processing_e2e(self):
        """Test QA batch processing workflow."""
        config = BaseAgentConfig(enable_batch_processing=True)
        agent = QAAgent(config)

        questions = [
            "What is AI?",
            "What is ML?",
            "What is DL?"
        ]

        results = agent.batch_execute(questions=questions)
        assert len(results) == 3
        for result in results:
            assert result['answer']


@pytest.mark.e2e
class TestCoTAgentE2E:
    def test_cot_example_workflow(self):
        """Test CoT example from documentation works end-to-end."""
        from kaizen.agents import CoTAgent
        from kaizen.core import BaseAgentConfig

        config = BaseAgentConfig(temperature=0.1)
        agent = CoTAgent(config)

        result = agent.execute(
            problem="Train travels 60 mph for 3 hours, then 80 mph for 2 hours. Total distance?"
        )

        assert result['step1']
        assert result['final_answer']
        assert result['confidence'] > 0.0


@pytest.mark.e2e
class TestReActAgentE2E:
    def test_react_example_workflow(self):
        """Test ReAct example from documentation works end-to-end."""
        from kaizen.agents import ReActAgent
        from kaizen.core import BaseAgentConfig

        config = BaseAgentConfig(temperature=0.1)
        agent = ReActAgent(config)

        result = agent.execute(
            task="Calculate the area of a circle with radius 5"
        )

        assert result['action_history']
        assert len(result['action_history']) > 0
        assert result['metadata']['total_cycles'] > 0
```

---

## Success Criteria

### Code Quality Metrics
- **Code Reduction**: 90%+ reduction achieved (1,537 → <200 lines)
- **Duplication**: <5% duplicated code (currently 91%)
- **Test Coverage**: 95%+ for base architecture (base_agent.py, execution_strategies.py)
- **Complexity**: Cyclomatic complexity <10 for all methods

### Performance Metrics
- **Framework Init**: <100ms (95th percentile across 100 runs)
- **Agent Creation**: <200ms (95th percentile across 100 runs)
- **QA Execution**: <500ms average (excluding LLM time)
- **CoT Execution**: <1000ms average (excluding LLM time)
- **Abstraction Overhead**: <1% vs direct LLMAgentNode execution

### Functional Metrics
- **Tier 1 Tests**: 100% pass rate (all unit tests)
- **Tier 2 Tests**: 100% pass rate (all integration tests with real LLMs)
- **Tier 3 Tests**: 100% pass rate (all E2E workflow tests)
- **Backward Compatibility**: 100% (all existing examples work with shims)
- **Zero Regression**: 100% (no functional changes vs current implementation)

### Developer Experience Metrics
- **New Agent Creation**: <50 lines (down from 400-600 lines)
- **Time to First Agent**: <30 minutes (down from 2-3 hours)
- **Bug Fix Locations**: 1 place (down from 3+ places)
- **Documentation Completeness**: 100% (all public methods documented, guides complete)

### Migration Metrics
- **Migration Guide Completeness**: All scenarios covered
- **Example Updates**: 100% of examples updated
- **Deprecation Warnings**: Added to all old implementations
- **User Migration Time**: <2 hours for typical usage

---

## Risk Assessment

### High-Risk Items

| Risk | Impact | Probability | Mitigation | Status |
|------|--------|-------------|------------|---------|
| **Performance regression** | High (blocks release) | Medium | Comprehensive benchmarks, profiling, optimization | Pending |
| **Breaking changes not caught** | High (user impact) | Medium | Extensive Tier 2-3 tests, manual validation | Pending |
| **Abstraction too complex** | Medium (poor DX) | Medium | User testing, documentation, examples | Pending |
| **Migration issues** | Medium (user frustration) | Low | Compatibility shims, clear migration guide | Pending |

### Medium-Risk Items

| Risk | Impact | Probability | Mitigation | Status |
|------|--------|-------------|------------|---------|
| **Strategy pattern misuse** | Medium (wrong behavior) | Low | Clear documentation, validation | Pending |
| **Extension point confusion** | Medium (wrong overrides) | Low | Extension guide with examples | Pending |
| **Test coverage gaps** | Medium (bugs in prod) | Low | 95%+ coverage requirement, code review | Pending |

### Low-Risk Items

| Risk | Impact | Probability | Mitigation | Status |
|------|--------|-------------|------------|---------|
| **Documentation drift** | Low (minor confusion) | Medium | Automated doc tests, CI validation | Pending |
| **Mixin interaction issues** | Low (edge cases) | Low | Comprehensive mixin tests | Pending |

---

## Related Documents

- **ADR-006-agent-base-architecture.md**: Main architecture decision record
- **ADR-002-signature-programming-model.md**: Signature programming foundation
- **ADR-005-testing-strategy-alignment.md**: Testing strategy for all tiers

---

## Appendix: Performance Benchmarking Plan

### Benchmark Suite

**File**: `tests/performance/test_agent_architecture_benchmarks.py`

**Benchmarks**:

1. **Framework Initialization**:
   - Measure: Time from BaseAgent.__init__() to framework ready
   - Runs: 100
   - Target: <100ms (95th percentile)

2. **Agent Creation**:
   - Measure: Time from framework ready to agent created
   - Runs: 100
   - Target: <200ms (95th percentile)

3. **Single Execution (QA)**:
   - Measure: Total execution time (including LLM)
   - Runs: 50
   - Target: <2000ms average (including LLM latency)

4. **Abstraction Overhead**:
   - Measure: BaseAgent execution vs direct LLMAgentNode execution
   - Runs: 100
   - Target: <1% difference

5. **Memory Overhead**:
   - Measure: Memory usage of BaseAgent instance
   - Runs: 10
   - Target: <10MB per instance

**Reporting**:
- Generate markdown report with tables and charts
- Compare old vs new architecture
- Highlight regressions (if any)
- Include profiling data (CPU, memory)

---

**End of Requirements Matrix**
