# ADR-006: Agent Base Architecture Design

## Status
**Proposed** (2025-10-01)

## Context

### The Problem: Massive Code Duplication

Our current Kaizen agent examples exhibit severe code duplication across three primary implementations:

- **SimpleQAAgent** (`examples/1-single-agent/simple-qa/workflow.py`): 496 lines
- **ChainOfThoughtAgent** (`examples/1-single-agent/chain-of-thought/chain_of_thought_agent.py`): 442 lines
- **KaizenReActAgent** (`examples/1-single-agent/react-agent/workflow.py`): 599 lines

**Total: 1,537 lines with ~1,400 lines (91%) duplicated code**

### Duplication Analysis

Each agent reimplements identical functionality:

1. **Framework Initialization** (~80-100 lines per agent)
   ```python
   # Duplicated in all three agents
   framework_config = kaizen.KaizenConfig(
       signature_programming_enabled=True,
       optimization_enabled=True,
       monitoring_enabled=True,
       audit_trail_enabled=True
   )
   self.kaizen_framework = kaizen.Kaizen(config=framework_config)
   ```

2. **Provider Auto-Detection** (~30-40 lines per agent)
   ```python
   # Duplicated auto-detection logic
   if not self.config.provider_config:
       try:
           self.config.provider_config = get_default_model_config()
           logger.info(f"Using provider: {self.config.provider_config['provider']}")
       except ConfigurationError as e:
           raise RuntimeError(f"Failed to configure LLM provider: {e}")
   ```

3. **Error Handling** (~50-70 lines per agent)
   ```python
   # Duplicated error patterns
   except TimeoutError as e:
       return self._error_response("Request timed out", "TIMEOUT_ERROR", str(e))
   except ConnectionError as e:
       return self._error_response("Connection failed", "CONNECTION_ERROR", str(e))
   except ValueError as e:
       return self._error_response("Configuration error", "CONFIG_ERROR", str(e))
   ```

4. **Logging Configuration** (~20 lines per agent)
   ```python
   # Duplicated in each file
   logging.basicConfig(
       level=logging.INFO,
       format='[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s',
       datefmt='%H:%M:%S'
   )
   logger = logging.getLogger(__name__)
   ```

5. **Performance Tracking** (~30-40 lines per agent)
   ```python
   # Duplicated metrics tracking
   self.performance_metrics = {
       'framework_init_time': 0,
       'agent_creation_time': 0,
       'total_executions': 0,
       'successful_executions': 0,
       'average_execution_time': 0
   }
   ```

### Why This Matters

**Current Impact:**
- **Maintenance Nightmare**: Bug fixes require changes in 3+ locations
- **Inconsistent Behavior**: Each agent handles errors differently
- **Testing Overhead**: Must test identical logic 3+ times
- **Development Velocity**: New agents require 400+ lines before domain logic
- **Knowledge Fragmentation**: No single source of truth for agent patterns

**Risk Assessment (from deep-analyst):**
- 8 Critical/High risks identified
- Inconsistent error handling across agents
- No standardized configuration approach
- Performance tracking varies by implementation
- Logging patterns create duplicate handlers

### Business Context

**Developer Experience Goals:**
- Create new agent in <50 lines of code
- Consistent behavior across all agent types
- Single source of truth for enterprise features
- Easy extension without touching base functionality

**Technical Requirements:**
- <100ms framework initialization
- <200ms agent creation
- 95%+ test coverage for base architecture
- 100% backward compatibility with existing examples

## Decision

We will implement a **Unified BaseAgent Architecture** using **Strategy Pattern** for execution flows and **Mixin Composition** for optional capabilities.

### Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     BaseAgent                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Core Responsibilities                                │   │
│  │ • Framework initialization (Kaizen + Core SDK)       │   │
│  │ • Provider auto-detection (OpenAI/Ollama)           │   │
│  │ • Signature compilation and execution               │   │
│  │ • Configuration management (BaseAgentConfig)        │   │
│  │ • Extension point definition (hooks)                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Optional Mixins (Composition)                        │   │
│  │ • LoggingMixin - Standardized logging              │   │
│  │ • ErrorHandlingMixin - Consistent error patterns   │   │
│  │ • PerformanceMixin - Metrics tracking              │   │
│  │ • BatchProcessingMixin - Batch operations          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Execution Strategy (Strategy Pattern)                │   │
│  │ • SingleShotStrategy - QA, CoT agents              │   │
│  │ • MultiCycleStrategy - ReAct agent                 │   │
│  │ • StreamingStrategy - Future: streaming responses  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ inherits
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Specialized Agents (15-35 lines)               │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  QAAgent     │  │  CoTAgent    │  │ ReActAgent   │    │
│  │              │  │              │  │              │    │
│  │ • Signature  │  │ • Signature  │  │ • Signature  │    │
│  │ • Config     │  │ • Config     │  │ • Config     │    │
│  │ • Overrides  │  │ • Overrides  │  │ • Overrides  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Components

#### 1. BaseAgent Class

**File**: `src/kaizen/core/base_agent.py`

```python
from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass
from abc import ABC, abstractmethod

from kaizen import Kaizen, KaizenConfig
from kaizen.signatures import Signature
from kaizen.config import get_default_model_config


@dataclass
class BaseAgentConfig:
    """
    Unified configuration for all Kaizen agents.

    Feature flags enable optional capabilities without inheritance complexity.
    """
    # Provider configuration (auto-detected if None)
    llm_provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 500
    timeout: int = 30

    # Feature flags
    enable_logging: bool = True
    enable_performance_tracking: bool = True
    enable_batch_processing: bool = False
    enable_audit_trail: bool = True

    # Framework configuration
    signature_programming_enabled: bool = True
    optimization_enabled: bool = True
    monitoring_enabled: bool = True

    # Error handling
    retry_attempts: int = 3
    confidence_threshold: float = 0.7

    # Provider config (populated by auto-detection)
    provider_config: Dict[str, Any] = None


class ExecutionStrategy(Protocol):
    """
    Strategy interface for agent execution patterns.

    Decouples execution logic from base agent, enabling:
    - Single-shot execution (QA, CoT)
    - Multi-cycle execution (ReAct)
    - Streaming execution (future)
    """

    def execute(
        self,
        agent: Any,
        signature_input: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Execute the agent with given inputs."""
        ...


class BaseAgent(ABC):
    """
    Base class for all Kaizen agents.

    Provides:
    - Framework initialization (Kaizen + Core SDK)
    - Provider auto-detection (OpenAI/Ollama)
    - Signature-based execution
    - Fallback execution (no signature)
    - Extension hooks for specialization

    Reduces agent implementation from 400+ lines to 15-35 lines.
    """

    def __init__(self, config: BaseAgentConfig):
        """
        Initialize base agent with unified configuration.

        Handles all framework setup, provider detection, and
        signature compilation automatically.
        """
        self.config = config
        self.kaizen_framework: Optional[Kaizen] = None
        self.agent = None
        self.performance_metrics = {}

        # Initialize framework (calls extension hooks)
        self._initialize_framework()

    def _initialize_framework(self):
        """
        Initialize Kaizen framework with comprehensive setup.

        Extension points:
        - _get_framework_config_extensions(): Add custom framework config
        - _get_agent_config_extensions(): Add custom agent config
        - _create_execution_strategy(): Override execution strategy
        """
        start_time = time.time()

        # Auto-detect provider if not configured
        if self.config.provider_config is None:
            self.config.provider_config = self._detect_provider()

        # Build framework configuration
        framework_config = self._build_framework_config()

        # Initialize Kaizen framework
        self.kaizen_framework = Kaizen(config=framework_config)

        framework_init_time = (time.time() - start_time) * 1000

        # Create agent with signature
        agent_start = time.time()
        signature = self.create_signature()
        agent_config = self._build_agent_config()

        self.agent = self.kaizen_framework.create_agent(
            agent_id=self._get_agent_id(),
            config=agent_config,
            signature=signature
        )

        agent_creation_time = (time.time() - agent_start) * 1000

        # Initialize performance tracking if enabled
        if self.config.enable_performance_tracking:
            self._initialize_performance_tracking(
                framework_init_time,
                agent_creation_time
            )

        # Log initialization if enabled
        if self.config.enable_logging:
            self._log_initialization(framework_init_time, agent_creation_time)

    def _detect_provider(self) -> Dict[str, Any]:
        """Auto-detect LLM provider (OpenAI or Ollama)."""
        try:
            return get_default_model_config()
        except Exception as e:
            raise RuntimeError(
                f"Failed to auto-detect LLM provider: {e}\n\n"
                "Please ensure either:\n"
                "  1. OPENAI_API_KEY is set for OpenAI, or\n"
                "  2. Ollama is installed and running"
            )

    def _build_framework_config(self) -> KaizenConfig:
        """
        Build Kaizen framework configuration.

        Extension point: Override _get_framework_config_extensions()
        to add custom configuration.
        """
        base_config = {
            'signature_programming_enabled': self.config.signature_programming_enabled,
            'optimization_enabled': self.config.optimization_enabled,
            'monitoring_enabled': self.config.monitoring_enabled,
            'audit_trail_enabled': self.config.enable_audit_trail,
            'debug': False
        }

        # Allow subclasses to extend configuration
        extensions = self._get_framework_config_extensions()
        base_config.update(extensions)

        return KaizenConfig(**base_config)

    def _build_agent_config(self) -> Dict[str, Any]:
        """
        Build agent configuration.

        Extension point: Override _get_agent_config_extensions()
        to add custom agent configuration.
        """
        agent_config = self.config.provider_config.copy()
        agent_config.update({
            'temperature': self.config.temperature,
            'max_tokens': self.config.max_tokens,
            'timeout': self.config.timeout,
            'enable_monitoring': self.config.monitoring_enabled
        })

        # Allow subclasses to extend configuration
        extensions = self._get_agent_config_extensions()
        agent_config.update(extensions)

        return agent_config

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the agent with given inputs.

        Uses execution strategy pattern to support:
        - Single-shot execution (QA, CoT)
        - Multi-cycle execution (ReAct)
        - Custom execution patterns
        """
        strategy = self._create_execution_strategy()

        try:
            result = strategy.execute(
                agent=self.agent,
                signature_input=kwargs,
                config=self.config
            )

            # Post-processing hook
            result = self.post_execute(result)

            return result

        except Exception as e:
            return self._handle_execution_error(e, kwargs)

    # ============================================
    # Extension Points (Override in Subclasses)
    # ============================================

    @abstractmethod
    def create_signature(self) -> Optional[Signature]:
        """
        Create agent signature.

        Return None to use fallback execution without signature.
        """
        pass

    def _get_agent_id(self) -> str:
        """Override to set custom agent identifier."""
        return "base_agent"

    def _get_framework_config_extensions(self) -> Dict[str, Any]:
        """Override to add custom framework configuration."""
        return {}

    def _get_agent_config_extensions(self) -> Dict[str, Any]:
        """Override to add custom agent configuration."""
        return {}

    def _create_execution_strategy(self) -> ExecutionStrategy:
        """
        Override to use different execution strategy.

        Default: SingleShotStrategy
        Override for: MultiCycleStrategy (ReAct), StreamingStrategy
        """
        from kaizen.core.execution_strategies import SingleShotStrategy
        return SingleShotStrategy()

    def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-process execution result.

        Override to add custom post-processing logic.
        """
        return result

    # ============================================
    # Optional Mixin Integration Points
    # ============================================

    def _initialize_performance_tracking(
        self,
        framework_time: float,
        agent_time: float
    ):
        """Initialize performance metrics (mixin integration point)."""
        self.performance_metrics = {
            'framework_init_time': framework_time,
            'agent_creation_time': agent_time,
            'total_executions': 0,
            'successful_executions': 0,
            'average_execution_time': 0
        }

    def _log_initialization(self, framework_time: float, agent_time: float):
        """Log initialization (mixin integration point)."""
        if self.config.enable_logging:
            logger.info(f"Framework initialized in {framework_time:.1f}ms")
            logger.info(f"Agent created in {agent_time:.1f}ms")

    def _handle_execution_error(
        self,
        error: Exception,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle execution errors (mixin integration point)."""
        return {
            'error': str(error),
            'error_type': type(error).__name__,
            'inputs': inputs,
            'success': False
        }

    # ============================================
    # Performance Targets
    # ============================================

    def _get_performance_targets(self) -> Dict[str, float]:
        """
        Define performance targets for validation.

        Override to set agent-specific targets.
        """
        return {
            'framework_init_max_ms': 100,
            'agent_creation_max_ms': 200,
            'execution_max_ms': 500
        }
```

#### 2. Execution Strategies

**File**: `src/kaizen/core/execution_strategies.py`

```python
from typing import Dict, Any, List, Optional
import time


class SingleShotStrategy:
    """
    Single-shot execution strategy for QA and CoT agents.

    Executes agent once and returns structured result.
    """

    def execute(
        self,
        agent: Any,
        signature_input: Dict[str, Any],
        config: Any
    ) -> Dict[str, Any]:
        """
        Execute agent with single invocation.

        Supports:
        - Signature-based execution
        - Fallback execution (no signature)
        - Pre/post hooks
        """
        start_time = time.time()

        # Pre-execute hook
        signature_input = self.pre_execute(**signature_input)

        # Execute based on signature availability
        if agent.has_signature:
            result = agent.execute(**signature_input)
        else:
            # Fallback execution
            prompt = self._build_fallback_prompt(signature_input)
            result = agent.execute(prompt)

        # Parse result
        parsed_result = self.parse_result(result)

        # Post-execute hook
        parsed_result = self.post_execute(parsed_result)

        # Add execution metadata
        execution_time = (time.time() - start_time) * 1000
        parsed_result['metadata'] = parsed_result.get('metadata', {})
        parsed_result['metadata']['execution_time_ms'] = execution_time
        parsed_result['metadata']['strategy'] = 'single_shot'

        return parsed_result

    # Extension hooks
    def pre_execute(self, **kwargs) -> Dict[str, Any]:
        """Pre-process inputs before execution."""
        return kwargs

    def parse_result(self, result: Any) -> Dict[str, Any]:
        """Parse execution result."""
        if isinstance(result, dict):
            return result
        return {'result': str(result)}

    def post_execute(self, parsed_result: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process parsed result."""
        return parsed_result

    def _build_fallback_prompt(self, inputs: Dict[str, Any]) -> str:
        """Build prompt for fallback execution."""
        return "\n".join(f"{k}: {v}" for k, v in inputs.items())


class MultiCycleStrategy:
    """
    Multi-cycle execution strategy for ReAct agents.

    Executes multiple reasoning cycles with tool integration,
    terminating when task is complete or max cycles reached.
    """

    def __init__(self, max_cycles: int = 10):
        self.max_cycles = max_cycles

    def execute(
        self,
        agent: Any,
        signature_input: Dict[str, Any],
        config: Any
    ) -> Dict[str, Any]:
        """
        Execute agent with multi-cycle reasoning loop.

        Supports:
        - ReAct pattern (Thought -> Action -> Observation)
        - Tool integration
        - Termination conditions
        - Action history tracking
        """
        start_time = time.time()

        action_history = []
        observations = []
        current_context = signature_input.get('context', '')

        for cycle in range(self.max_cycles):
            # Pre-cycle hook
            cycle_input = self.pre_cycle(
                cycle=cycle,
                observations=observations,
                **signature_input
            )

            # Execute reasoning cycle
            if agent.has_signature:
                result = agent.execute(**cycle_input)
            else:
                prompt = self._build_react_prompt(cycle_input, action_history)
                result = agent.execute(prompt)

            # Parse cycle result
            parsed_result = self.parse_cycle_result(result, cycle)

            # Check termination
            if self.should_terminate(parsed_result, cycle):
                action_history.append(parsed_result)
                break

            # Extract observation for next cycle
            observation = self.extract_observation(parsed_result)
            observations.append(observation)

            # Update context
            current_context += f"\n\nObservation {cycle + 1}: {observation}"
            signature_input['context'] = current_context

            action_history.append(parsed_result)

        # Build final response
        execution_time = (time.time() - start_time) * 1000

        return {
            'action_history': action_history,
            'observations': observations,
            'total_cycles': len(action_history),
            'metadata': {
                'execution_time_ms': execution_time,
                'strategy': 'multi_cycle',
                'max_cycles': self.max_cycles
            }
        }

    # Extension hooks
    def pre_cycle(
        self,
        cycle: int,
        observations: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Prepare input for cycle execution."""
        return kwargs

    def parse_cycle_result(self, result: Any, cycle: int) -> Dict[str, Any]:
        """Parse result from cycle execution."""
        if isinstance(result, dict):
            return result
        return {'result': str(result), 'cycle': cycle}

    def should_terminate(self, parsed_result: Dict[str, Any], cycle: int) -> bool:
        """Check if execution should terminate."""
        # Default: terminate if action is 'finish'
        return parsed_result.get('action', '') == 'finish'

    def extract_observation(self, parsed_result: Dict[str, Any]) -> str:
        """Extract observation from cycle result."""
        return parsed_result.get('observation', str(parsed_result))

    def _build_react_prompt(
        self,
        inputs: Dict[str, Any],
        history: List[Dict]
    ) -> str:
        """Build ReAct prompt for fallback execution."""
        base = f"Task: {inputs.get('task', '')}\n"
        base += f"Context: {inputs.get('context', '')}\n"

        if history:
            base += "\nPrevious actions:\n"
            for h in history[-3:]:  # Last 3 actions
                base += f"- {h.get('thought', '')}\n"

        return base
```

#### 3. Specialized Agent Examples

**QA Agent** (15-20 lines):

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField


class QASignature(Signature):
    """Answer questions with confidence scoring."""
    question: str = InputField(desc="The question to answer")
    context: str = InputField(desc="Additional context", default="")

    answer: str = OutputField(desc="Clear, accurate answer")
    confidence: float = OutputField(desc="Confidence 0.0-1.0")
    reasoning: str = OutputField(desc="Brief reasoning")


class QAAgent(BaseAgent):
    """Q&A Agent - 15 lines vs 496 lines previously."""

    def create_signature(self) -> Signature:
        return QASignature()

    def _get_agent_id(self) -> str:
        return "qa_agent"


# Usage (exactly the same as before)
config = BaseAgentConfig(temperature=0.1)
agent = QAAgent(config)
result = agent.execute(
    question="What is machine learning?",
    context="Explain for general audience"
)
```

**Chain-of-Thought Agent** (25-30 lines):

```python
class CoTSignature(Signature):
    """Chain-of-Thought structured reasoning."""
    problem: str = InputField(desc="Complex problem")
    context: str = InputField(desc="Additional context", default="")

    step1: str = OutputField(desc="Problem understanding")
    step2: str = OutputField(desc="Data identification")
    step3: str = OutputField(desc="Systematic analysis")
    step4: str = OutputField(desc="Solution verification")
    step5: str = OutputField(desc="Final answer formulation")
    final_answer: str = OutputField(desc="Complete solution")
    confidence: float = OutputField(desc="Confidence 0.0-1.0")


class CoTAgent(BaseAgent):
    """Chain-of-Thought Agent - 25 lines vs 442 lines previously."""

    def create_signature(self) -> Signature:
        return CoTSignature()

    def _get_agent_id(self) -> str:
        return "cot_agent"

    def _get_agent_config_extensions(self) -> Dict[str, Any]:
        return {
            'generation_config': {
                'reasoning_pattern': 'chain_of_thought',
                'step_verification': True,
                'confidence_tracking': True
            }
        }

    def _get_performance_targets(self) -> Dict[str, float]:
        return {
            'framework_init_max_ms': 100,
            'agent_creation_max_ms': 200,
            'execution_max_ms': 1000  # CoT needs more time
        }
```

**ReAct Agent** (30-35 lines):

```python
from kaizen.core.execution_strategies import MultiCycleStrategy


class ReActSignature(Signature):
    """ReAct reasoning and acting pattern."""
    task: str = InputField(desc="Task to solve")
    context: str = InputField(desc="Previous context", default="")
    available_tools: list = InputField(desc="Available tools", default=[])

    thought: str = OutputField(desc="Current reasoning")
    action: str = OutputField(desc="Action to take")
    action_input: dict = OutputField(desc="Action parameters")
    confidence: float = OutputField(desc="Confidence 0.0-1.0")


class ReActAgent(BaseAgent):
    """ReAct Agent - 30 lines vs 599 lines previously."""

    def create_signature(self) -> Signature:
        return ReActSignature()

    def _get_agent_id(self) -> str:
        return "react_agent"

    def _get_framework_config_extensions(self) -> Dict[str, Any]:
        return {
            'mcp_enabled': True  # Enable MCP integration
        }

    def _create_execution_strategy(self):
        return MultiCycleStrategy(max_cycles=10)

    def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
        # Add ReAct-specific metadata
        result['metadata']['tools_used'] = len([
            a for a in result.get('action_history', [])
            if a.get('action') == 'tool_use'
        ])
        return result
```

## Consequences

### Positive

1. **Massive Code Reduction**: 90%+ reduction (496→20, 442→25, 599→30 lines)

2. **Single Source of Truth**:
   - Framework initialization: 1 place vs 3+
   - Error handling: 1 place vs 3+
   - Performance tracking: 1 place vs 3+
   - Provider detection: 1 place vs 3+

3. **Consistent Behavior**:
   - All agents handle errors identically
   - All agents use same logging format
   - All agents track performance consistently
   - All agents support same configuration options

4. **Easy Extension**:
   - New agent type: 15-35 lines
   - Override specific behavior: Override single method
   - Add capabilities: Compose mixins
   - Change execution: Switch strategy

5. **Improved Testing**:
   - Test base functionality once
   - Test specializations independently
   - Mock strategies for unit tests
   - Integration tests for real behavior

6. **100% Backward Compatibility**:
   - Existing examples continue to work
   - Same import paths available
   - Same API signatures
   - Migration path clear and documented

### Negative

1. **Increased Abstraction**:
   - More layers to understand
   - Strategy pattern adds indirection
   - Mixin composition not immediately obvious

2. **Learning Curve**:
   - Developers must understand:
     - Extension points and when to use them
     - Strategy pattern for execution
     - Mixin composition for capabilities
     - When to override vs compose

3. **Debugging Complexity**:
   - Stack traces deeper with abstractions
   - Must understand base class behavior
   - Extension hooks may hide bugs

4. **Performance Overhead**:
   - Additional method calls (minimal)
   - Strategy pattern dispatch (negligible)
   - Mixin method resolution (Python MRO)

**Mitigation**:
- Comprehensive documentation with examples
- Clear extension point guide
- Debugging utilities for tracing execution
- Performance benchmarks to validate overhead is <1%

## Alternatives Considered

### Option 1: Deep Inheritance Hierarchy

```
BaseAgent
  ├─ SingleShotAgent
  │    ├─ QAAgent
  │    └─ CoTAgent
  └─ MultiCycleAgent
       └─ ReActAgent
```

**Pros**:
- Simple to understand (traditional OOP)
- Clear inheritance path
- IDE autocomplete works well

**Cons**:
- Tight coupling between layers
- Difficult to mix capabilities (diamond problem)
- Changes propagate through hierarchy
- Hard to test in isolation
- Violates composition over inheritance

**Why Rejected**: Too rigid, doesn't support mixing capabilities (e.g., CoT + ReAct)

### Option 2: Hook-Only Approach (No Strategies)

```python
class BaseAgent:
    def execute(self, **kwargs):
        result = self.pre_execute(kwargs)
        result = self.do_execute(result)
        result = self.post_execute(result)
        return result

    def pre_execute(self, inputs): ...
    def do_execute(self, inputs): ...
    def post_execute(self, result): ...
```

**Pros**:
- Simple hook model
- Easy to override specific parts
- No additional patterns to learn

**Cons**:
- Insufficient for multi-cycle execution (ReAct)
- Encourages overriding core logic
- No clear separation of concerns
- State management becomes messy

**Why Rejected**: Doesn't handle ReAct's multi-cycle pattern well, leads to spaghetti code

### Option 3: Keep Current Duplication

**Pros**:
- No refactoring needed
- Each agent fully self-contained
- Zero abstraction overhead

**Cons**:
- 1,400 lines of duplicated code
- Maintenance nightmare (3x work for bug fixes)
- Inconsistent behavior across agents
- High testing overhead
- Poor developer experience

**Why Rejected**: Unacceptable technical debt, blocks scaling to more agents

### Option 4: Configuration-Driven Approach

```python
# Define agents via config
qa_config = {
    'signature': QASignature,
    'execution': 'single_shot',
    'features': ['logging', 'performance']
}

agent = AgentFactory.create(qa_config)
```

**Pros**:
- Very DRY (don't repeat yourself)
- Easy to define new agents
- Configuration-based testing

**Cons**:
- Too much "magic" behavior
- Hard to debug (config-driven bugs)
- IDE support poor (no types)
- Less Pythonic (not obvious what it does)

**Why Rejected**: Sacrifices explicitness for brevity, poor developer experience

## Implementation Plan

### Phase 1: Foundation (Week 1, Days 1-3)

**Goal**: Core base architecture without breaking existing code

**Tasks**:
- [ ] Create `BaseAgent` class with all core functionality
- [ ] Create `BaseAgentConfig` with feature flags
- [ ] Implement provider auto-detection in base
- [ ] Create `SingleShotStrategy` for QA/CoT
- [ ] Create `MultiCycleStrategy` for ReAct
- [ ] Write comprehensive unit tests (Tier 1)

**Deliverables**:
- `src/kaizen/core/base_agent.py` (200-250 lines)
- `src/kaizen/core/execution_strategies.py` (150-200 lines)
- `tests/unit/core/test_base_agent.py` (300-400 lines)
- `tests/unit/core/test_execution_strategies.py` (200-300 lines)

**Success Criteria**:
- All Tier 1 tests pass (95%+ coverage)
- BaseAgent initializes in <100ms
- Agent creation in <200ms
- Zero impact on existing agents

### Phase 2: Specialized Agents (Week 1, Days 4-5 + Week 2, Days 1-2)

**Goal**: Migrate existing agents to new architecture

**Tasks**:
- [ ] Implement new `QAAgent` (15-20 lines)
- [ ] Implement new `CoTAgent` (25-30 lines)
- [ ] Implement new `ReActAgent` (30-35 lines)
- [ ] Update all examples to use new agents
- [ ] Write integration tests (Tier 2) with real LLMs
- [ ] Write E2E tests (Tier 3) for complete workflows

**Deliverables**:
- `src/kaizen/agents/qa_agent.py` (30-40 lines total)
- `src/kaizen/agents/cot_agent.py` (40-50 lines total)
- `src/kaizen/agents/react_agent.py` (50-60 lines total)
- `tests/integration/agents/test_qa_agent_integration.py`
- `tests/integration/agents/test_cot_agent_integration.py`
- `tests/integration/agents/test_react_agent_integration.py`
- `tests/e2e/agents/test_all_agents_e2e.py`

**Success Criteria**:
- All new agents pass Tier 1-3 tests
- Functional parity with old implementations
- Performance targets met (<100ms, <200ms, <500ms)
- All examples work end-to-end

### Phase 3: Migration & Documentation (Week 2, Days 3-5)

**Goal**: Complete migration with full documentation

**Tasks**:
- [ ] Create migration guide for existing code
- [ ] Update all example documentation
- [ ] Create extension point guide with examples
- [ ] Add deprecation warnings to old implementations
- [ ] Create performance comparison report
- [ ] Update architecture documentation

**Deliverables**:
- `docs/guides/AGENT_MIGRATION_GUIDE.md`
- `docs/guides/AGENT_EXTENSION_POINTS.md`
- `docs/guides/CREATING_CUSTOM_AGENTS.md`
- `docs/architecture/AGENT_ARCHITECTURE_OVERVIEW.md`
- Performance comparison report (old vs new)

**Success Criteria**:
- Migration guide validated with real examples
- All documentation examples tested and working
- Zero regressions in functionality
- Performance improvements documented

### Phase 4: Polish & Optimization (Parallel with Phase 2-3)

**Goal**: Optimize performance and developer experience

**Tasks**:
- [ ] Add mixin implementations (Logging, Error, Performance, Batch)
- [ ] Optimize framework initialization (<100ms)
- [ ] Add debugging utilities and tracing
- [ ] Create agent creation helper utilities
- [ ] Add validation and error messages
- [ ] Performance profiling and optimization

**Deliverables**:
- `src/kaizen/core/mixins.py` (200-300 lines)
- `src/kaizen/utils/agent_debugging.py`
- `src/kaizen/utils/agent_helpers.py`
- Performance profiling report

**Success Criteria**:
- All performance targets met
- Developer experience validated
- Clear error messages for common issues
- Debugging utilities working

## Testing Strategy

### Tier 1: Unit Tests (No External Dependencies)

**Coverage**: 95%+ for base architecture

```python
# test_base_agent.py
def test_base_agent_initialization():
    """Test BaseAgent initializes correctly."""

def test_provider_auto_detection():
    """Test provider auto-detection with mocks."""

def test_framework_configuration_building():
    """Test framework config construction."""

def test_agent_configuration_building():
    """Test agent config construction."""

def test_signature_compilation():
    """Test signature is compiled correctly."""

def test_extension_hooks_called():
    """Test extension hooks are invoked."""

def test_performance_tracking():
    """Test performance metrics tracked."""

# test_execution_strategies.py
def test_single_shot_strategy():
    """Test SingleShotStrategy execution."""

def test_multi_cycle_strategy():
    """Test MultiCycleStrategy execution."""

def test_strategy_hooks_called():
    """Test pre/post hooks invoked."""

def test_termination_conditions():
    """Test MultiCycleStrategy termination."""
```

### Tier 2: Integration Tests (Real Infrastructure)

**Coverage**: Real LLM execution, no mocking

```python
# test_qa_agent_integration.py
@pytest.mark.integration
def test_qa_agent_real_openai():
    """Test QA agent with real OpenAI API."""
    config = BaseAgentConfig(llm_provider="openai")
    agent = QAAgent(config)
    result = agent.execute(question="What is 2+2?")
    assert result['answer'] == "4"

@pytest.mark.integration
def test_qa_agent_real_ollama():
    """Test QA agent with real Ollama."""
    config = BaseAgentConfig(llm_provider="ollama")
    agent = QAAgent(config)
    result = agent.execute(question="What is 2+2?")
    assert "4" in result['answer']
```

### Tier 3: E2E Tests (Complete Workflows)

**Coverage**: Full example workflows end-to-end

```python
# test_all_agents_e2e.py
@pytest.mark.e2e
def test_qa_example_workflow():
    """Test QA example from docs works end-to-end."""
    # Run the exact example from documentation

@pytest.mark.e2e
def test_cot_example_workflow():
    """Test CoT example from docs works end-to-end."""

@pytest.mark.e2e
def test_react_example_workflow():
    """Test ReAct example from docs works end-to-end."""

@pytest.mark.e2e
def test_batch_processing_e2e():
    """Test batch processing workflow."""
```

## Migration Path

### For Existing Code

**Old Code** (SimpleQAAgent):
```python
from examples.simple_qa.workflow import SimpleQAAgent, QAConfig

config = QAConfig(temperature=0.1)
agent = SimpleQAAgent(config)
result = agent.ask("What is ML?")
```

**New Code** (QAAgent):
```python
from kaizen.agents import QAAgent
from kaizen.core import BaseAgentConfig

config = BaseAgentConfig(temperature=0.1)
agent = QAAgent(config)
result = agent.execute(question="What is ML?")
```

**Backward Compatibility Shim**:
```python
# examples/simple_qa/workflow.py
from kaizen.agents import QAAgent as NewQAAgent
from kaizen.core import BaseAgentConfig

# Deprecated - use kaizen.agents.QAAgent
class SimpleQAAgent(NewQAAgent):
    def ask(self, question: str, context: str = ""):
        # Compatibility wrapper
        return self.execute(question=question, context=context)

# Deprecated - use kaizen.core.BaseAgentConfig
QAConfig = BaseAgentConfig
```

### Breaking Changes

**None** - 100% backward compatible via compatibility shims in example files.

## Success Metrics

### Code Metrics
- **Code Reduction**: Target 90%+ (1,537 → <200 lines for all agents)
- **Duplication**: Target <5% (currently 91%)
- **Test Coverage**: Target 95%+ for base architecture

### Performance Metrics
- **Framework Init**: <100ms (current: varies)
- **Agent Creation**: <200ms (current: varies)
- **Execution Time**: No regression vs current

### Developer Experience
- **New Agent Creation**: <50 lines (current: 400-600 lines)
- **Time to First Agent**: <30 minutes (current: 2-3 hours)
- **Bug Fix Propagation**: 1 place (current: 3+ places)

### Quality Metrics
- **Tier 1 Tests**: 95%+ pass rate
- **Tier 2 Tests**: 100% pass rate with real LLMs
- **Tier 3 Tests**: 100% pass rate for all examples

## Related ADRs

- **ADR-002**: Signature Programming Model Implementation
- **ADR-003**: Memory System Architecture
- **ADR-005**: Testing Strategy Alignment

## References

- Ultrathink Analysis: Deep failure analysis identifying 8 critical/high risks
- Current Implementation: `examples/1-single-agent/` with 1,537 lines
- Strategy Pattern: Gang of Four design patterns
- Mixin Composition: Python multiple inheritance patterns
