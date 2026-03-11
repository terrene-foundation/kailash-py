# Planning Agents API Reference

Complete API reference for PlanningAgent and PEVAgent - production-ready planning agents with explicit planning phases.

## Table of Contents

1. [Overview](#overview)
2. [PlanningAgent API](#planningagent-api)
3. [PEVAgent API](#pevagent-api)
4. [Signatures](#signatures)
5. [Configuration](#configuration)
6. [TypedDict Structures](#typeddict-structures)

---

## Overview

Kaizen provides two production-ready planning agents:

- **PlanningAgent**: Plan → Validate → Execute (single execution)
- **PEVAgent**: Plan → Execute → Verify → Refine (iterative loops)

Both agents feature:
- Zero-config with sensible defaults
- Progressive configuration (override as needed)
- Environment variable support (`KAIZEN_*`)
- Structured output integration (OpenAI API)
- Built-in error handling and logging

**Location**: `kaizen.agents.specialized.planning`, `kaizen.agents.specialized.pev`

---

## PlanningAgent API

### Overview

Planning agent with explicit planning phase before execution.

**Pattern**: Plan → Validate → Execute

**Location**: `src/kaizen/agents/specialized/planning.py`

```python
from kaizen.agents import PlanningAgent

# Zero-config (easiest)
agent = PlanningAgent()
result = agent.run(task="Create a research report on AI ethics")
print(result["plan"])              # Detailed execution plan
print(result["validation_result"]) # Validation status
print(result["execution_results"]) # Step-by-step results
print(result["final_result"])      # Aggregated result

# With configuration
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.3,
    max_plan_steps=10,
    validation_mode="strict",
    enable_replanning=True
)
```

### Class Definition

```python
class PlanningAgent(BaseAgent):
    """
    Production-ready Planning Agent with explicit planning phase.

    Pattern: Plan → Validate → Execute

    Differs from other agents:
    - ReAct: Interleaves reasoning and action (no upfront planning)
    - CoT: Step-by-step reasoning (no explicit planning phase)
    - Planning: Creates complete plan BEFORE execution

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Explicit planning phase before execution
    - Plan validation with configurable strictness
    - Plan replanning on validation failures
    - Max plan steps to prevent infinite planning
    - Built-in error handling and logging
    """
```

### Constructor

```python
def __init__(
    self,
    llm_provider: str = "openai",
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    max_plan_steps: int = 10,
    validation_mode: str = "strict",
    enable_replanning: bool = True,
    timeout: int = 30,
    max_retries: int = 3,
    provider_config: Dict[str, Any] = None,
    **kwargs
):
    """
    Initialize Planning Agent.

    Args:
        llm_provider: LLM provider (openai, ollama, anthropic)
        model: Model name (gpt-4, llama3.2:1b, claude-3-opus)
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum tokens for response
        max_plan_steps: Maximum steps in plan (prevents infinite planning)
        validation_mode: Plan validation mode (strict, warn, off)
        enable_replanning: Allow replanning on validation failures
        timeout: Execution timeout in seconds
        max_retries: Maximum retry attempts
        provider_config: Provider-specific configuration (e.g., structured outputs)
    """
```

### Methods

#### run()

Execute task with planning workflow.

```python
def run(
    self,
    task: str,
    context: dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Run planning workflow: Plan → Validate → Execute.

    Args:
        task: Task to plan and execute
        context: Additional context for planning

    Returns:
        Dict with:
        - plan: List[PlanStep] - Detailed execution plan
        - validation_result: ValidationResult - Plan validation results
        - execution_results: List[ExecutionResult] - Results from each step
        - final_result: str - Aggregated final result
    """
```

**Example Usage**:

```python
# Basic usage
result = agent.run(task="Analyze sales data and create report")

# With context
result = agent.run(
    task="Generate quarterly report",
    context={
        "data_source": "sales_db",
        "quarter": "Q4 2024",
        "format": "PDF"
    }
)

# Access results
plan = result["plan"]
for step in plan:
    print(f"Step {step['step']}: {step['action']}")

validation = result["validation_result"]
print(f"Validation status: {validation['status']}")

execution = result["execution_results"]
for exec_result in execution:
    print(f"Step {exec_result['step']}: {exec_result['status']}")

print(f"Final result: {result['final_result']}")
```

### Validation Modes

**strict**:
- Enforces complete plan validation
- Fails if plan is incomplete or invalid
- Triggers replanning if enabled

**warn**:
- Logs warnings for invalid plans
- Continues execution with warnings
- Does not trigger replanning

**off**:
- Skips validation entirely
- Executes plan without checks
- Fastest but least safe

**Example**:

```python
# Strict mode (default)
agent = PlanningAgent(validation_mode="strict")
result = agent.run(task="Complex multi-step task")
# Validation failure triggers replanning

# Warn mode
agent = PlanningAgent(validation_mode="warn")
result = agent.run(task="Complex multi-step task")
# Validation warnings logged, execution continues

# Off mode (not recommended)
agent = PlanningAgent(validation_mode="off")
result = agent.run(task="Complex multi-step task")
# No validation, immediate execution
```

### Replanning

**When Enabled**:
- Automatically replans on validation failures
- Limits replanning attempts to `max_retries`
- Preserves original task context

**Example**:

```python
# Enable replanning (default)
agent = PlanningAgent(
    enable_replanning=True,
    max_retries=3
)

result = agent.run(task="Complex task")
# If validation fails, agent replans up to 3 times

# Disable replanning
agent = PlanningAgent(enable_replanning=False)
result = agent.run(task="Complex task")
# Validation failure raises error instead of replanning
```

---

## PEVAgent API

### Overview

Planner-Executor-Verifier agent with iterative refinement loops.

**Pattern**: Plan → Execute → Verify → Refine (iterative)

**Location**: `src/kaizen/agents/specialized/pev.py`

```python
from kaizen.agents import PEVAgent

# Zero-config
agent = PEVAgent()
result = agent.run(task="Generate code and verify it works")
print(result["final_result"])
print(f"Iterations: {len(result['refinements'])}")

# With configuration
agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_iterations=10,
    verification_strictness="strict",
    enable_error_recovery=True
)
```

### Class Definition

```python
class PEVAgent(BaseAgent):
    """
    Production-ready PEV (Planner-Executor-Verifier) agent.

    Pattern: Plan → Execute → Verify → Refine (iterative loop)

    Differs from other agents:
    - ReAct: Observation-based adaptation (no explicit verification)
    - Planning: Single plan execution (no verification loop)
    - PEV: Explicit verification with iterative refinement

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Iterative plan-execute-verify-refine cycle
    - Configurable verification strictness
    - Error recovery and refinement
    - Max iterations to prevent infinite loops
    - Built-in error handling and logging
    """
```

### Constructor

```python
def __init__(
    self,
    llm_provider: str = "openai",
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    max_iterations: int = 5,
    verification_strictness: str = "medium",
    enable_error_recovery: bool = True,
    timeout: int = 30,
    max_retries: int = 3,
    provider_config: Dict[str, Any] = None,
    **kwargs
):
    """
    Initialize PEV Agent.

    Args:
        llm_provider: LLM provider (openai, ollama, anthropic)
        model: Model name (gpt-4, llama3.2:1b, claude-3-opus)
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum tokens for response
        max_iterations: Maximum refinement iterations (prevents infinite loops)
        verification_strictness: Verification strictness (strict, medium, lenient)
        enable_error_recovery: Allow error recovery and refinement
        timeout: Execution timeout in seconds
        max_retries: Maximum retry attempts
        provider_config: Provider-specific configuration
    """
```

### Methods

#### run()

Execute task with PEV workflow.

```python
def run(
    self,
    task: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Run PEV workflow: Plan → Execute → Verify → Refine (iterative).

    Args:
        task: Task to execute iteratively

    Returns:
        Dict with:
        - plan: PEVPlan - Current execution plan
        - execution_result: PEVExecutionResult - Latest execution result
        - verification: PEVVerificationResult - Verification results
        - refinements: List[str] - Refinement history
        - final_result: str - Final verified result
    """
```

**Example Usage**:

```python
# Basic usage
result = agent.run(task="Generate Python function with tests")

# Access results
print(result["plan"]["description"])
print(f"Verified: {result['verification']['passed']}")
print(f"Iterations: {len(result['refinements'])}")

# Iterative refinement
for i, refinement in enumerate(result["refinements"]):
    print(f"Refinement {i+1}: {refinement}")

print(f"Final result: {result['final_result']}")
```

### Verification Strictness

**strict**:
- Rigorous verification checks
- Fails on any issue found
- Requires multiple refinement iterations

**medium** (default):
- Balanced verification
- Minor issues trigger warnings
- Major issues trigger refinement

**lenient**:
- Minimal verification
- Accepts results with minor issues
- Faster but less quality control

**Example**:

```python
# Strict verification
agent = PEVAgent(verification_strictness="strict")
result = agent.run(task="Generate production code")
# Will iterate until all issues resolved

# Medium verification (default)
agent = PEVAgent(verification_strictness="medium")
result = agent.run(task="Generate code")
# Balanced quality vs speed

# Lenient verification
agent = PEVAgent(verification_strictness="lenient")
result = agent.run(task="Generate prototype code")
# Faster, accepts minor issues
```

### Iteration Limits

**Purpose**: Prevent infinite refinement loops

**Example**:

```python
# Default: 5 iterations
agent = PEVAgent(max_iterations=5)
result = agent.run(task="Complex task")

# More iterations for complex tasks
agent = PEVAgent(max_iterations=10)
result = agent.run(task="Very complex task")

# Check iteration count
print(f"Iterations used: {len(result['refinements'])}")
```

### Error Recovery

**When Enabled**:
- Catches execution errors
- Refines plan based on error
- Continues iteration loop

**Example**:

```python
# Enable error recovery (default)
agent = PEVAgent(enable_error_recovery=True)
result = agent.run(task="Generate code and verify")
# Errors trigger refinement instead of failure

# Disable error recovery
agent = PEVAgent(enable_error_recovery=False)
result = agent.run(task="Generate code and verify")
# Errors raise exceptions immediately
```

---

## Signatures

### PlanningSignature

**Location**: `src/kaizen/agents/specialized/planning.py:157`

```python
class PlanningSignature(Signature):
    """
    Planning signature for structured plan-validate-execute pattern.

    Implements three-phase workflow:
    1. Plan: Generate detailed execution plan
    2. Validate: Check plan feasibility and completeness
    3. Execute: Execute validated plan step-by-step

    Input Fields:
    - task: The task to plan and execute
    - context: Additional context for planning

    Output Fields:
    - plan: Detailed execution plan (list of steps)
    - validation_result: Plan validation results
    - execution_results: Results from each step execution
    - final_result: Aggregated final result
    """

    # Input fields
    task: str = InputField(desc="Task to plan and execute")
    context: dict = InputField(desc="Additional context for planning", default={})

    # Output fields
    plan: List[PlanStep] = OutputField(desc="Detailed execution plan steps")
    validation_result: ValidationResult = OutputField(desc="Plan validation results")
    execution_results: List[ExecutionResult] = OutputField(
        desc="Results from each step"
    )
    final_result: str = OutputField(desc="Aggregated final result")
```

### PlanGenerationSignature

**Location**: `src/kaizen/agents/specialized/planning.py:134`

```python
class PlanGenerationSignature(Signature):
    """
    Internal signature for plan generation phase only.

    Used by _generate_plan() to ask LLM for just the plan.
    Compatible with OpenAI Structured Outputs API strict mode.

    Input Fields:
    - task: The task to plan
    - context: Additional context for planning

    Output Fields:
    - plan: Detailed execution plan (list of steps)
    """

    # Input fields
    task: str = InputField(desc="Task to plan and execute")
    context: dict = InputField(desc="Additional context for planning", default={})

    # Output field - only plan for this phase
    plan: List[PlanStep] = OutputField(desc="Detailed execution plan steps")
```

### PEVSignature

**Location**: `src/kaizen/agents/specialized/pev.py:125`

```python
class PEVSignature(Signature):
    """
    PEV signature for Plan-Execute-Verify-Refine pattern.

    Implements iterative improvement cycle:
    1. Plan: Create execution plan
    2. Execute: Execute the plan
    3. Verify: Check result quality
    4. Refine: Improve plan based on verification feedback
    (Repeat until verified or max iterations)

    Input Fields:
    - task: The task to execute iteratively

    Output Fields:
    - plan: Current plan
    - execution_result: Execution result
    - verification: Verification result with issues
    - refinements: List of refinements made
    - final_result: Final verified result
    """

    # Input fields
    task: str = InputField(desc="Task to execute iteratively")

    # Output fields
    plan: PEVPlan = OutputField(desc="Current execution plan")
    execution_result: PEVExecutionResult = OutputField(desc="Execution result")
    verification: PEVVerificationResult = OutputField(
        desc="Verification result with issues"
    )
    refinements: List[str] = OutputField(desc="Refinements made")
    final_result: str = OutputField(desc="Final verified result")
```

---

## Configuration

### PlanningConfig

**Location**: `src/kaizen/agents/specialized/planning.py:103`

```python
@dataclass
class PlanningConfig:
    """
    Configuration for Planning Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-4"))
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.7"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "2000"))
    )

    # Planning-specific configuration
    max_plan_steps: int = 10
    validation_mode: str = "strict"  # strict, warn, off
    enable_replanning: bool = True
    timeout: int = 30
    max_retries: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)
```

### PEVAgentConfig

**Location**: `src/kaizen/agents/specialized/pev.py:43`

```python
@dataclass
class PEVAgentConfig:
    """
    Configuration for PEV Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-4"))
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.7"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "2000"))
    )

    # PEV-specific configuration
    max_iterations: int = 5
    verification_strictness: str = "medium"  # strict, medium, lenient
    enable_error_recovery: bool = True
    timeout: int = 30
    max_retries: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)
```

### Environment Variables

Both agents support environment variable configuration:

```bash
# .env file
KAIZEN_LLM_PROVIDER=openai
KAIZEN_MODEL=gpt-4
KAIZEN_TEMPERATURE=0.7
KAIZEN_MAX_TOKENS=2000
```

```python
# Agent automatically reads from .env
agent = PlanningAgent()  # Uses environment variables
```

---

## TypedDict Structures

### PlanStep

**Location**: `src/kaizen/agents/specialized/planning.py:44`

```python
class PlanStep(TypedDict):
    """
    TypedDict for plan step structure.

    Required fields:
    - step: Step number (int)
    - action: Action to take (str)
    - description: Detailed description (str)

    Optional fields:
    - tools: Tools needed (list)
    - dependencies: Step dependencies (list)
    """

    step: int  # Required
    action: str  # Required
    description: str  # Required
    tools: NotRequired[list]  # Optional
    dependencies: NotRequired[list]  # Optional
```

**Example**:

```python
plan_step: PlanStep = {
    "step": 1,
    "action": "Load data",
    "description": "Load sales data from PostgreSQL database",
    "tools": ["PostgreSQL", "pandas"],
    "dependencies": []
}
```

### ValidationResult

**Location**: `src/kaizen/agents/specialized/planning.py:65`

```python
class ValidationResult(TypedDict):
    """
    TypedDict for plan validation result structure.

    Required fields:
    - status: Validation status ("valid", "invalid", "warnings", "skipped")

    Optional fields:
    - reason: Explanation if invalid or skipped (str)
    - warnings: List of warning messages (list)
    """

    status: str  # Required
    reason: NotRequired[str]  # Optional
    warnings: NotRequired[list]  # Optional
```

**Example**:

```python
validation: ValidationResult = {
    "status": "valid",
    "reason": None,
    "warnings": []
}

validation_with_warnings: ValidationResult = {
    "status": "warnings",
    "warnings": ["Step 3 has no dependencies specified"]
}

validation_invalid: ValidationResult = {
    "status": "invalid",
    "reason": "Plan exceeds max_plan_steps (10 steps max)"
}
```

### ExecutionResult

**Location**: `src/kaizen/agents/specialized/planning.py:82`

```python
class ExecutionResult(TypedDict):
    """
    TypedDict for execution result structure.

    Required fields:
    - step: Step number that was executed (int)
    - status: Execution status ("success", "failed", "skipped")

    Optional fields:
    - output: Result from execution (str)
    - error: Error message if failed (str)
    - details: Additional execution details (dict)
    """

    step: int  # Required
    status: str  # Required
    output: NotRequired[str]  # Optional
    error: NotRequired[str]  # Optional
    details: NotRequired[dict]  # Optional
```

**Example**:

```python
execution: ExecutionResult = {
    "step": 1,
    "status": "success",
    "output": "Loaded 1000 rows from database",
    "details": {"rows": 1000, "columns": 5}
}

execution_failed: ExecutionResult = {
    "step": 2,
    "status": "failed",
    "error": "Database connection timeout"
}
```

### PEVPlan

**Location**: `src/kaizen/agents/specialized/pev.py:74`

```python
class PEVPlan(TypedDict, total=False):
    """
    TypedDict for PEV plan structure.

    Optional fields:
    - description: Plan description (str)
    - steps: List of steps (list)
    - refinements: List of refinement history (list)
    """

    description: str
    steps: list
    refinements: list
```

### PEVExecutionResult

**Location**: `src/kaizen/agents/specialized/pev.py:89`

```python
class PEVExecutionResult(TypedDict):
    """
    TypedDict for PEV execution result structure.

    Required fields:
    - status: Execution status ("success", "failed")

    Optional fields:
    - output: Result output (str)
    - error: Error message if failed (str)
    - details: Additional details (dict)
    """

    status: str  # Required
    output: NotRequired[str]  # Optional
    error: NotRequired[str]  # Optional
    details: NotRequired[dict]  # Optional
```

### PEVVerificationResult

**Location**: `src/kaizen/agents/specialized/pev.py:108`

```python
class PEVVerificationResult(TypedDict):
    """
    TypedDict for PEV verification result structure.

    Required fields:
    - passed: Whether verification passed (bool)

    Optional fields:
    - issues: List of issues found (list)
    - feedback: Feedback for refinement (str)
    """

    passed: bool  # Required
    issues: NotRequired[list]  # Optional
    feedback: NotRequired[str]  # Optional
```

**Example**:

```python
verification_passed: PEVVerificationResult = {
    "passed": True,
    "issues": [],
    "feedback": "All tests passed successfully"
}

verification_failed: PEVVerificationResult = {
    "passed": False,
    "issues": ["Test case 3 failed", "Performance regression"],
    "feedback": "Optimize algorithm for large datasets"
}
```

---

## Complete Examples

### PlanningAgent with Structured Outputs

```python
from kaizen.agents import PlanningAgent
from kaizen.core.structured_output import create_structured_output_config
from kaizen.agents.specialized.planning import PlanGenerationSignature

# Enable structured outputs for 100% JSON compliance
provider_config = create_structured_output_config(
    signature=PlanGenerationSignature(),
    strict=True,
    name="plan_generation"
)

agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",  # Required for structured outputs
    temperature=0.3,
    max_plan_steps=10,
    validation_mode="strict",
    enable_replanning=True,
    provider_config=provider_config  # Enable structured outputs
)

result = agent.run(
    task="Create quarterly sales analysis report",
    context={
        "quarter": "Q4 2024",
        "database": "sales_db",
        "format": "PDF"
    }
)

# Access structured plan
for step in result["plan"]:
    print(f"Step {step['step']}: {step['action']}")
    print(f"  Description: {step['description']}")
    if "tools" in step:
        print(f"  Tools: {', '.join(step['tools'])}")

# Check validation
if result["validation_result"]["status"] == "valid":
    print("Plan validated successfully")
else:
    print(f"Validation failed: {result['validation_result']['reason']}")

# View execution results
for exec_result in result["execution_results"]:
    if exec_result["status"] == "success":
        print(f"Step {exec_result['step']}: ✓ {exec_result['output']}")
    else:
        print(f"Step {exec_result['step']}: ✗ {exec_result['error']}")

print(f"Final result: {result['final_result']}")
```

### PEVAgent with Error Recovery

```python
from kaizen.agents import PEVAgent

agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_iterations=10,
    verification_strictness="strict",
    enable_error_recovery=True
)

result = agent.run(task="Generate Python web scraper with error handling")

# View iterative refinement
print(f"Plan: {result['plan']['description']}")
print(f"\nIterations: {len(result['refinements'])}")

for i, refinement in enumerate(result["refinements"], 1):
    print(f"\nRefinement {i}:")
    print(f"  {refinement}")

# Check verification
if result["verification"]["passed"]:
    print("\n✓ Verification passed")
else:
    print(f"\n✗ Verification failed:")
    for issue in result["verification"]["issues"]:
        print(f"  - {issue}")
    print(f"Feedback: {result['verification']['feedback']}")

print(f"\nFinal result:\n{result['final_result']}")
```

---

## Testing

**Location**: `tests/e2e/autonomy/planning/`

**Test Coverage**:
- Multi-step plan creation with validation
- Plan execution with real tool calls
- Plan adaptation on errors
- Iterative refinement with verification

**Example Test**:

```python
import pytest
from kaizen.agents import PlanningAgent

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_planning_agent_multi_step():
    """Test planning agent creates and executes multi-step plan."""

    agent = PlanningAgent(
        llm_provider="openai",
        model="gpt-4o-2024-08-06",
        max_plan_steps=5,
        validation_mode="strict"
    )

    result = agent.run(task="Analyze sales data and create report")

    # Verify plan structure
    assert "plan" in result
    assert isinstance(result["plan"], list)
    assert len(result["plan"]) <= 5

    # Verify validation
    assert result["validation_result"]["status"] == "valid"

    # Verify execution
    assert len(result["execution_results"]) == len(result["plan"])
    for exec_result in result["execution_results"]:
        assert exec_result["status"] == "success"

    # Verify final result
    assert result["final_result"]
```

---

## See Also

- [BaseAgent Architecture Guide](../guides/baseagent-architecture.md) - Agent lifecycle
- [Multi-Agent Coordination Guide](../guides/multi-agent-coordination.md) - Multi-agent patterns
- [Structured Outputs Guide](../guides/signature-programming.md#structured-outputs-with-openai-api-v063) - 100% JSON compliance
- [Planning E2E Tests](../../tests/e2e/autonomy/planning/test_planning_agent_e2e.py) - Test examples
