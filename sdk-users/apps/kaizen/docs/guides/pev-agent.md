# PEV Agent - Plan, Execute, Verify, Refine Pattern

## What is the PEV Agent?

The PEV Agent implements an **iterative improvement loop** (Plan → Execute → Verify → Refine) where each execution is verified and refined until quality criteria are met. This "Iterative Refinement with Verification" approach ensures high-quality outputs through continuous improvement.

**Pattern**: Create plan → Execute plan → Verify result quality → Refine plan based on feedback (repeat until verified)

## When to Use

Use PEV Agent when:
- **Quality-critical outputs** that benefit from iterative refinement (code generation, document writing, data transformation)
- **Verification-driven workflows** where output quality can be measured and improved
- **Iterative improvement needed** to reach target quality level
- **Incremental refinement** better than single-shot execution
- **Feedback-based optimization** where verification feedback guides improvements

**Ideal for**:
- Code generation with testing
- Document writing with quality checks
- Data transformation with validation
- Content generation with style verification
- Configuration generation with compliance checks

## When NOT to Use

Avoid PEV Agent when:
- **Single execution sufficient** (use Planning or SimpleQA instead)
- **No clear verification criteria** (verification requires measurable quality metrics)
- **Real-time constraints** where iteration time isn't acceptable (use single-shot patterns instead)
- **Exploratory tasks** where path forward is unclear (use Tree-of-Thoughts instead)
- **Simple tasks** where refinement overhead isn't justified (use SimpleQA instead)

## Complete Working Example

```python
"""
PEV Agent Example - Iterative Code Generation with Verification

Demonstrates Plan → Execute → Verify → Refine workflow for quality-driven tasks.
"""

import os
from dotenv import load_dotenv
from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig

# Load environment variables
load_dotenv()

# Configuration
config = PEVAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_iterations=5,  # Maximum refinement cycles
    verification_strictness="medium",  # strict, medium, or lenient
    enable_error_recovery=True,  # Recover from execution errors
    timeout=30,
    max_retries=3
)

# Create agent
agent = PEVAgent(config=config)

# Task: Generate production-ready code
task = """
Generate a Python function that:
1. Accepts a list of numbers
2. Filters out negative numbers
3. Returns the sum of positive numbers
4. Includes error handling for empty lists and non-numeric values
5. Has proper docstring and type hints

The function should be production-ready and well-tested.
"""

# Execute iterative refinement
result = agent.run(task=task)

# Access results from each cycle

# Initial Plan
print("=" * 80)
print("INITIAL PLAN")
print("=" * 80)
print(result["plan"])

# Verification Results
print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)
verification = result["verification"]
print(f"Status: {'✓ Passed' if verification['passed'] else '✗ Failed'}")
print(f"Issues: {len(verification.get('issues', []))}")
for issue in verification.get("issues", []):
    print(f"  - {issue}")
print(f"Feedback: {verification.get('feedback', 'None')}")

# Refinement History
print("\n" + "=" * 80)
print("REFINEMENT HISTORY")
print("=" * 80)
print(f"Total Iterations: {len(result['refinements'])}/{config.max_iterations}")
for i, refinement in enumerate(result["refinements"], 1):
    print(f"\nIteration {i}:")
    print(f"  {refinement}")

# Final Result
print("\n" + "=" * 80)
print("FINAL RESULT")
print("=" * 80)
print(result["final_result"])

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Iterations: {len(result['refinements'])}/{config.max_iterations}")
print(f"Verification: {'✓ Passed' if verification['passed'] else '✗ Failed'}")
print(f"Strictness: {config.verification_strictness}")
print(f"Error Recovery: {'Enabled' if config.enable_error_recovery else 'Disabled'}")

# Error handling
if "error" in result:
    print(f"\nError: {result['error']}")
```

**Output Example**:
```
================================================================================
INITIAL PLAN
================================================================================
{'description': 'Generate Python function with validation', 'steps': []}

================================================================================
VERIFICATION
================================================================================
Status: ✓ Passed
Issues: 0
Feedback: No issues found

================================================================================
REFINEMENT HISTORY
================================================================================
Total Iterations: 2/5

Iteration 1:
  Iteration 1: Generate more detailed output

Iteration 2:
  Iteration 2: Fix execution errors

================================================================================
FINAL RESULT
================================================================================
def sum_positive(numbers: list[float]) -> float:
    """
    Calculate the sum of positive numbers in a list.

    Args:
        numbers: List of numeric values

    Returns:
        Sum of positive numbers

    Raises:
        ValueError: If list is empty or contains non-numeric values
    """
    if not numbers:
        raise ValueError("Cannot process empty list")

    positive_sum = 0.0
    for num in numbers:
        if not isinstance(num, (int, float)):
            raise ValueError(f"Non-numeric value: {num}")
        if num > 0:
            positive_sum += num

    return positive_sum

================================================================================
SUMMARY
================================================================================
Iterations: 2/5
Verification: ✓ Passed
Strictness: medium
Error Recovery: Enabled
```

## Configuration Options

### Core LLM Configuration
```python
config = PEVAgentConfig(
    # LLM Provider Settings
    llm_provider="openai",     # "openai", "anthropic", "ollama"
    model="gpt-4",             # Provider-specific model
    temperature=0.7,           # 0.0-1.0 (moderate for balanced output)
    max_tokens=2000,           # Maximum response tokens
)
```

### PEV-Specific Configuration
```python
config = PEVAgentConfig(
    # Iteration Control
    max_iterations=5,          # Maximum refinement cycles (prevents infinite loops)

    # Verification Control
    verification_strictness="medium",  # "strict", "medium", "lenient"
    enable_error_recovery=True,        # Recover from execution errors

    # Error Handling
    timeout=30,                # Request timeout (seconds)
    max_retries=3,             # Retry attempts on failure

    # Advanced
    provider_config={          # Provider-specific options
        "timeout": 30,
        "max_retries": 3
    }
)
```

**Verification Strictness Levels**:
- `strict`: Pass only if no issues detected (0 issues required)
- `medium`: Pass with up to 1 minor issue (1 issue allowed)
- `lenient`: Pass if execution didn't fail (any issues allowed)

### Environment Variable Support
```bash
# .env file configuration (auto-loaded)
KAIZEN_LLM_PROVIDER=openai
KAIZEN_MODEL=gpt-4
KAIZEN_TEMPERATURE=0.7
KAIZEN_MAX_TOKENS=2000
```

```python
# Uses environment variables by default
agent = PEVAgent()  # Zero-config usage
```

## Common Pitfalls & Gotchas

### 1. Infinite Refinement Loops
**Problem**: Verification never passes, agent iterates until max_iterations exhausted.

**Solution**: Set appropriate `max_iterations` and use lenient verification for non-critical tasks.

```python
# ❌ WRONG: Too many iterations without clear verification criteria
config = PEVAgentConfig(max_iterations=50)  # Might loop forever

# ✅ CORRECT: Reasonable iteration limit
config = PEVAgentConfig(
    max_iterations=5,  # 5 iterations typical
    verification_strictness="medium"  # Allow minor issues
)
```

### 2. Verification Criteria Too Strict
**Problem**: Using "strict" verification for subjective quality tasks causes failures.

**Solution**: Match strictness to task verifiability.

```python
# ❌ WRONG: Strict verification for subjective tasks
config = PEVAgentConfig(verification_strictness="strict")  # Code style is subjective

# ✅ CORRECT: Use "medium" for subjective quality
config = PEVAgentConfig(verification_strictness="medium")

# ✅ CORRECT: Use "strict" only for objective criteria
config = PEVAgentConfig(verification_strictness="strict")  # Syntax errors are objective
```

### 3. Disabling Error Recovery Prematurely
**Problem**: Single execution error causes entire workflow to fail.

**Solution**: Enable error recovery for production workflows.

```python
# ❌ WRONG: Error recovery disabled
config = PEVAgentConfig(enable_error_recovery=False)  # Fails on first error

# ✅ CORRECT: Error recovery enabled
config = PEVAgentConfig(
    enable_error_recovery=True,  # Recovers from errors
    max_iterations=5  # Allows multiple recovery attempts
)
```

### 4. Not Checking Verification Status
**Problem**: Using final_result without checking if verification passed.

**Solution**: Always check verification status before using result.

```python
# ❌ WRONG: Assuming verification passed
result = agent.run(task=task)
code = result["final_result"]  # Might be low quality!

# ✅ CORRECT: Check verification status
result = agent.run(task=task)
if result["verification"]["passed"]:
    code = result["final_result"]
    print("Quality verified!")
else:
    print(f"Verification failed with {len(result['verification']['issues'])} issues")
    for issue in result["verification"]["issues"]:
        print(f"  - {issue}")
```

### 5. Ignoring Refinement History
**Problem**: Not reviewing refinement history to understand improvement process.

**Solution**: Log and analyze refinements for debugging and optimization.

```python
# ❌ WRONG: Ignoring refinement history
result = agent.run(task=task)
print(result["final_result"])

# ✅ CORRECT: Review refinement history
result = agent.run(task=task)
print(f"Iterations: {len(result['refinements'])}")
for i, refinement in enumerate(result["refinements"], 1):
    print(f"Iteration {i}: {refinement}")

# Analyze patterns
if len(result["refinements"]) >= config.max_iterations - 1:
    print("WARNING: Hit max iterations, consider adjusting verification criteria")
```

### 6. Task Without Clear Verification Criteria
**Problem**: Task is too vague for meaningful verification.

**Solution**: Provide explicit quality criteria in task description.

```python
# ❌ WRONG: Vague task
task = "Generate some code"

# ✅ CORRECT: Explicit quality criteria
task = """
Generate Python code that:
1. Implements the Fibonacci sequence
2. Includes type hints
3. Has docstring with examples
4. Handles n < 0 with ValueError
5. Passes mypy type checking
"""
result = agent.run(task=task)
```

## Comparison with Similar Patterns

### PEV vs Planning
| Aspect | PEV Agent | Planning Agent |
|--------|-----------|----------------|
| **Verification** | Post-execution verification | Pre-execution validation |
| **Iteration** | Multiple refine cycles | Single execution cycle (with optional replanning) |
| **Quality Focus** | Output quality | Plan quality |
| **Use Case** | Iterative improvement | Structured execution |
| **Cycles** | Multiple (until verified) | Single (or replan) |
| **Overhead** | Higher (multiple cycles) | Lower (single execution) |

**When to Switch**:
- **PEV → Planning**: Single execution sufficient, no refinement needed
- **Planning → PEV**: Need iterative quality improvement

### PEV vs ReAct
| Aspect | PEV Agent | ReAct Agent |
|--------|-----------|-------------|
| **Verification** | Explicit verification step | Observation-based |
| **Adaptation** | Refinement based on feedback | Real-time based on observations |
| **Cycles** | Fixed verification cycles | Variable action-observation cycles |
| **Quality Focus** | Output verification | Task completion |
| **Best For** | Quality-driven refinement | Dynamic problem-solving |
| **Transparency** | Verification results | Reasoning traces |

**When to Switch**:
- **PEV → ReAct**: Need real-time adaptation, not post-execution verification
- **ReAct → PEV**: Have clear verification criteria, need quality refinement

### PEV vs Tree-of-Thoughts (ToT)
| Aspect | PEV Agent | ToT Agent |
|--------|-----------|-----------|
| **Exploration** | Single path, iteratively refined | Multiple parallel paths |
| **Selection** | Iterative improvement | Best path selection |
| **Cycles** | Sequential refinement cycles | Parallel path generation |
| **Quality** | Verification-driven | Evaluation-driven |
| **Best For** | Incremental improvement | Alternative exploration |
| **Overhead** | Moderate (5 iterations typical) | Higher (N paths generated) |

**When to Switch**:
- **PEV → ToT**: Need multiple alternatives, not iterative refinement
- **ToT → PEV**: Single path sufficient, need quality refinement

## Best Practices

### 1. Set Iteration Limits Based on Task Complexity
```python
# Simple tasks - low iteration limit
simple_config = PEVAgentConfig(max_iterations=3)

# Moderate tasks - standard limit
moderate_config = PEVAgentConfig(max_iterations=5)

# Complex tasks - higher limit
complex_config = PEVAgentConfig(max_iterations=10)
```

### 2. Use Strictness Levels Appropriately
```python
# Strict for objective criteria (syntax, compliance)
strict_config = PEVAgentConfig(
    verification_strictness="strict",
    max_iterations=3  # Fewer iterations, strict criteria
)

# Medium for balanced quality (code quality, style)
medium_config = PEVAgentConfig(
    verification_strictness="medium",
    max_iterations=5
)

# Lenient for subjective quality (creative content)
lenient_config = PEVAgentConfig(
    verification_strictness="lenient",
    max_iterations=7  # More iterations, lenient criteria
)
```

### 3. Enable Error Recovery for Production
```python
# Production configuration
production_config = PEVAgentConfig(
    enable_error_recovery=True,
    max_iterations=5,
    max_retries=3
)

# Development configuration (fail fast)
dev_config = PEVAgentConfig(
    enable_error_recovery=False,  # Fail fast for debugging
    max_iterations=2
)
```

### 4. Provide Explicit Quality Criteria
```python
# Explicit criteria in task description
task = """
Generate Python function with requirements:
1. Type hints for all parameters and return value
2. Docstring with Args, Returns, Raises sections
3. Error handling for edge cases
4. Input validation
5. Passes pylint with score > 9.0

Verification will check all 5 requirements.
"""
result = agent.run(task=task)
```

### 5. Monitor Refinement Patterns
```python
import logging

# Enable logging
logging.basicConfig(level=logging.INFO)

# Run with monitoring
result = agent.run(task=task)

# Analyze refinement patterns
if len(result["refinements"]) > 3:
    logging.warning("High iteration count, consider simplifying task")

if not result["verification"]["passed"]:
    logging.error(f"Verification failed: {result['verification']['issues']}")
```

### 6. Combine Verification with Automated Testing
```python
# Generate code with PEV
task = "Generate function to parse CSV with error handling"
result = agent.run(task=task)

if result["verification"]["passed"]:
    # Extract generated code
    code = result["final_result"]

    # Run automated tests
    import pytest
    exec(code)  # Execute generated code
    pytest.main(["-v", "tests/generated/"])  # Run tests on generated code

    # If tests pass, use code in production
```

## Performance Characteristics

- **Planning Latency**: 1-3 seconds for initial plan
- **Execution Latency**: 1-3 seconds per iteration
- **Verification Latency**: <500ms per verification
- **Total Latency**: (Planning + Execution + Verification) × iterations
  - Typical: 5-15 seconds (5 iterations @ 1-3s each)
  - Worst case: 30-50 seconds (10 iterations @ 3-5s each)
- **Memory Usage**: ~100MB for typical workflows
- **Concurrent Refinement**: Not parallelized (sequential by design)

**Optimization Tips**:
- Use lower max_iterations (3-5) for faster results
- Use "lenient" verification for non-critical tasks
- Cache verified results for repeated tasks
- Monitor iteration counts and adjust verification criteria

## Integration Examples

### With Core SDK for Workflow Validation
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from kaizen.agents.specialized.pev import PEVAgent

# Generate workflow with PEV
agent = PEVAgent()
task = "Generate workflow to process customer orders"
result = agent.run(task=task)

if result["verification"]["passed"]:
    # Create workflow from verified result
    workflow = WorkflowBuilder()
    # Parse result and add nodes
    # ... (workflow construction logic)

    # Execute verified workflow
    runtime = LocalRuntime()
    runtime.execute(workflow.build())
```

### With DataFlow for Schema Generation
```python
from dataflow import DataFlow
from kaizen.agents.specialized.pev import PEVAgent

db = DataFlow()
agent = PEVAgent(PEVAgentConfig(verification_strictness="strict"))

# Generate schema with verification
task = "Generate database schema for e-commerce platform"
result = agent.run(task=task)

if result["verification"]["passed"]:
    # Apply verified schema
    schema = result["final_result"]
    db.execute_schema(schema)
```

### With Nexus for API Specification
```python
from nexus import Nexus
from kaizen.agents.specialized.pev import PEVAgent

agent = PEVAgent()

# Generate API specification with refinement
task = "Generate OpenAPI spec for user management API"
result = agent.run(task=task)

if result["verification"]["passed"]:
    # Deploy verified API spec
    nexus = Nexus()
    nexus.load_openapi_spec(result["final_result"])
```

## Testing PEV Agent

```python
import pytest
from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig

def test_pev_agent_basic():
    """Test basic plan-execute-verify-refine workflow"""
    config = PEVAgentConfig(
        llm_provider="mock",
        max_iterations=3,
        verification_strictness="medium"
    )
    agent = PEVAgent(config=config)

    result = agent.run(task="Generate simple code")

    # Verify all components
    assert "plan" in result
    assert "execution_result" in result
    assert "verification" in result
    assert "refinements" in result
    assert "final_result" in result

    # Verify iteration control
    assert len(result["refinements"]) <= 3

def test_pev_agent_verification_strict():
    """Test strict verification mode"""
    config = PEVAgentConfig(
        llm_provider="mock",
        verification_strictness="strict"
    )
    agent = PEVAgent(config=config)

    result = agent.run(task="Generate code")

    # Strict mode requires zero issues
    if result["verification"]["passed"]:
        assert len(result["verification"].get("issues", [])) == 0

def test_pev_agent_error_recovery():
    """Test error recovery capability"""
    config = PEVAgentConfig(
        llm_provider="mock",
        enable_error_recovery=True,
        max_iterations=5
    )
    agent = PEVAgent(config=config)

    # Even with errors, should attempt recovery
    result = agent.run(task="Complex task with errors")

    # Should have refinements showing recovery attempts
    assert "refinements" in result

def test_pev_agent_max_iterations():
    """Test iteration limit enforcement"""
    config = PEVAgentConfig(
        llm_provider="mock",
        max_iterations=2
    )
    agent = PEVAgent(config=config)

    result = agent.run(task="Task requiring many iterations")

    # Should not exceed max_iterations
    assert len(result["refinements"]) <= 2
```

## See Also

- **[Planning Agent Guide](./planning-agent.md)** - Upfront planning with validation
- **[Tree-of-Thoughts Guide](./tree-of-thoughts-agent.md)** - Multi-path exploration
- **[Single-Agent Patterns Overview](./single-agent-patterns.md)** - All patterns comparison
- **[Multi-Agent Coordination](./multi-agent-coordination.md)** - Combining agents
- **[API Reference](../reference/api-reference.md)** - Complete API documentation
