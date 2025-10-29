# Planning Agent - Plan Before You Act Pattern

## What is the Planning Agent?

The Planning Agent implements a **three-phase workflow** (Plan → Validate → Execute) where a complete plan is created upfront before any execution begins. This "Plan Before You Act" approach ensures structured, well-validated execution paths.

**Pattern**: Generate complete plan → Validate plan feasibility → Execute validated plan step-by-step

## When to Use

Use Planning Agent when:
- **Complex multi-step tasks** that benefit from upfront planning (research reports, project workflows, data processing pipelines)
- **Critical operations** where validation before execution is essential
- **Structured deliverables** with clear steps and dependencies
- **Resource planning** where you need to check feasibility before committing
- **Audit requirements** where you need a validated plan before execution

**Ideal for**:
- Research and report generation
- Data processing workflows
- Project planning and execution
- Compliance workflows
- Configuration management

## When NOT to Use

Avoid Planning Agent when:
- **Dynamic environments** where plans quickly become outdated (use ReAct instead)
- **Exploration tasks** where the path forward isn't clear upfront (use Tree-of-Thoughts instead)
- **Simple single-step tasks** where planning overhead isn't justified (use SimpleQA instead)
- **Iterative refinement** needed with verification loops (use PEV instead)
- **Real-time adaptation** required based on observations (use ReAct instead)

## Complete Working Example

```python
"""
Planning Agent Example - Research Report Generation

Demonstrates Plan → Validate → Execute workflow for structured tasks.
"""

import os
from dotenv import load_dotenv
from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig

# Load environment variables
load_dotenv()

# Configuration
config = PlanningConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.3,  # Low temperature for consistent planning
    max_plan_steps=5,  # Limit plan to 5 steps
    validation_mode="strict",  # strict, warn, or off
    enable_replanning=True,  # Replan on validation failure
    timeout=30,
    max_retries=3
)

# Create agent
agent = PlanningAgent(config=config)

# Task with context
task = "Create a comprehensive research report on AI ethics"
context = {
    "max_sources": 5,
    "report_length": "2000 words",
    "audience": "general public",
    "focus_areas": ["privacy", "bias", "transparency"]
}

# Execute three-phase workflow
result = agent.run(task=task, context=context)

# Access results from each phase

# Phase 1: Plan
print("=" * 80)
print("PHASE 1: PLAN")
print("=" * 80)
for step in result["plan"]:
    print(f"Step {step['step']}: {step['action']}")
    print(f"  Description: {step['description']}")
    if "dependencies" in step:
        print(f"  Dependencies: {step['dependencies']}")

# Phase 2: Validation
print("\n" + "=" * 80)
print("PHASE 2: VALIDATION")
print("=" * 80)
validation = result["validation_result"]
print(f"Status: {validation['status']}")
if validation['status'] == "warnings":
    for warning in validation.get("warnings", []):
        print(f"  WARNING: {warning}")

# Phase 3: Execution
print("\n" + "=" * 80)
print("PHASE 3: EXECUTION")
print("=" * 80)
for exec_result in result["execution_results"]:
    print(f"Step {exec_result['step']}: {exec_result['status']}")
    print(f"  Output: {exec_result.get('output', 'N/A')[:100]}...")

# Final Result
print("\n" + "=" * 80)
print("FINAL RESULT")
print("=" * 80)
print(result["final_result"])

# Error handling
if "error" in result:
    print(f"\nError: {result['error']}")
```

**Output Example**:
```
================================================================================
PHASE 1: PLAN
================================================================================
Step 1: Research AI ethics frameworks
  Description: Gather information from academic sources on AI ethics
Step 2: Analyze privacy concerns
  Description: Examine data privacy issues in AI systems
  Dependencies: [1]
Step 3: Investigate bias and fairness
  Description: Research algorithmic bias and fairness measures
  Dependencies: [1]
Step 4: Compile findings
  Description: Organize research into structured sections
  Dependencies: [2, 3]
Step 5: Write final report
  Description: Create comprehensive 2000-word report
  Dependencies: [4]

================================================================================
PHASE 2: VALIDATION
================================================================================
Status: valid

================================================================================
PHASE 3: EXECUTION
================================================================================
Step 1: completed
  Output: Executed: Gather information from academic sources on AI ethics
Step 2: completed
  Output: Executed: Examine data privacy issues in AI systems
... (continues for all steps)

================================================================================
FINAL RESULT
================================================================================
Research report completed with all 5 steps executed successfully.
Comprehensive analysis of AI ethics covering privacy, bias, and transparency.
```

## Configuration Options

### Core LLM Configuration
```python
config = PlanningConfig(
    # LLM Provider Settings
    llm_provider="openai",     # "openai", "anthropic", "ollama"
    model="gpt-4",             # Provider-specific model
    temperature=0.3,           # 0.0-1.0 (low for consistency)
    max_tokens=2000,           # Maximum response tokens
)
```

### Planning-Specific Configuration
```python
config = PlanningConfig(
    # Plan Control
    max_plan_steps=10,         # Maximum steps in plan (prevents over-planning)

    # Validation Control
    validation_mode="strict",  # "strict", "warn", "off"
    enable_replanning=True,    # Replan on validation failure

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

**Validation Modes**:
- `strict`: Fails immediately on any validation issue
- `warn`: Logs warnings but continues execution
- `off`: Skips validation entirely

### Environment Variable Support
```bash
# .env file configuration (auto-loaded)
KAIZEN_LLM_PROVIDER=openai
KAIZEN_MODEL=gpt-4
KAIZEN_TEMPERATURE=0.3
KAIZEN_MAX_TOKENS=2000
```

```python
# Uses environment variables by default
agent = PlanningAgent()  # Zero-config usage
```

## Common Pitfalls & Gotchas

### 1. Over-Planning Complex Tasks
**Problem**: Planning agent generates 50+ steps for a simple task, making it unmanageable.

**Solution**: Set `max_plan_steps` appropriately for task complexity.

```python
# ❌ WRONG: No step limit
config = PlanningConfig()  # Defaults to 10, might be too many

# ✅ CORRECT: Limit steps based on task
config = PlanningConfig(max_plan_steps=5)  # Simple tasks
config = PlanningConfig(max_plan_steps=15)  # Complex workflows
```

### 2. Validation Mode Mismatch
**Problem**: Using `strict` validation for dynamic tasks causes excessive replanning failures.

**Solution**: Choose validation mode based on task predictability.

```python
# ❌ WRONG: Strict validation for unpredictable tasks
config = PlanningConfig(validation_mode="strict")

# ✅ CORRECT: Use "warn" for flexible tasks
config = PlanningConfig(validation_mode="warn")  # Allows minor issues

# ✅ CORRECT: Use "strict" only for critical workflows
config = PlanningConfig(validation_mode="strict")  # Compliance-critical
```

### 3. Circular Dependencies Not Caught
**Problem**: Plan has step 3 depending on step 5, creating logical impossibility.

**Solution**: Enable strict validation and review validation results.

```python
# ❌ WRONG: Skipping validation
config = PlanningConfig(validation_mode="off")

# ✅ CORRECT: Enable validation to catch circular deps
config = PlanningConfig(
    validation_mode="strict",  # Catches circular dependencies
    enable_replanning=True     # Replan if validation fails
)

# Check validation results
result = agent.run(task=task)
if result["validation_result"]["status"] == "invalid":
    print(f"Plan invalid: {result['validation_result']['reason']}")
```

### 4. Forgetting Context for Planning
**Problem**: Agent creates generic plan without task-specific details.

**Solution**: Always provide rich context for better planning.

```python
# ❌ WRONG: Vague task, no context
result = agent.run(task="Create report")

# ✅ CORRECT: Detailed task with context
task = "Create a comprehensive research report on AI ethics"
context = {
    "max_sources": 5,
    "report_length": "2000 words",
    "audience": "general public",
    "focus_areas": ["privacy", "bias", "transparency"]
}
result = agent.run(task=task, context=context)
```

### 5. Not Handling Replanning Failures
**Problem**: Validation fails, replanning fails, but code doesn't handle it.

**Solution**: Check for errors and handle replanning scenarios.

```python
# ❌ WRONG: Assuming execution always succeeds
result = agent.run(task=task)
print(result["final_result"])  # Might be empty!

# ✅ CORRECT: Check for errors
result = agent.run(task=task)
if "error" in result:
    if result["error"] == "VALIDATION_FAILED":
        print("Plan validation failed, consider simplifying task")
    elif result["error"] == "REPLANNING_FAILED":
        print("Replanning failed, try with fewer constraints")
    else:
        print(f"Error: {result['error']}")
else:
    print(result["final_result"])
```

## Comparison with Similar Patterns

### Planning vs ReAct
| Aspect | Planning Agent | ReAct Agent |
|--------|---------------|-------------|
| **Planning Phase** | Complete plan upfront | No explicit planning phase |
| **Execution Style** | Sequential step execution | Interleaved reasoning + action |
| **Adaptation** | Replanning on failure | Real-time adaptation |
| **Validation** | Pre-execution validation | Post-action observation |
| **Best For** | Structured, predictable tasks | Dynamic, exploratory tasks |
| **Overhead** | Higher (planning + validation) | Lower (direct execution) |
| **Audit Trail** | Complete plan + validation | Reasoning traces |

**When to Switch**:
- **Planning → ReAct**: Task becomes unpredictable or requires real-time adaptation
- **ReAct → Planning**: Task benefits from upfront structure and validation

### Planning vs PEV
| Aspect | Planning Agent | PEV Agent |
|--------|---------------|-----------|
| **Verification** | Pre-execution validation | Post-execution verification |
| **Iteration** | Replanning on validation failure | Iterative refinement loop |
| **Cycles** | Single plan-execute cycle | Multiple refine cycles |
| **Quality Focus** | Plan quality | Output quality |
| **Best For** | Critical pre-validation | Iterative improvement |
| **Failure Mode** | Replanning or abort | Refine until verified |

**When to Switch**:
- **Planning → PEV**: Need iterative improvement with quality verification
- **PEV → Planning**: Single execution cycle sufficient, no refinement needed

### Planning vs Chain-of-Thought (CoT)
| Aspect | Planning Agent | CoT Agent |
|--------|---------------|-----------|
| **Structure** | Explicit plan steps | Step-by-step reasoning |
| **Phases** | Three distinct phases | Single reasoning chain |
| **Validation** | Plan validation before execution | No explicit validation |
| **Output** | Plan + validation + execution | Final reasoning result |
| **Best For** | Multi-step workflows | Complex reasoning tasks |
| **Transparency** | Complete plan visibility | Reasoning transparency |

**When to Switch**:
- **Planning → CoT**: Task is reasoning-heavy, not workflow-based
- **CoT → Planning**: Need explicit plan structure and validation

## Best Practices

### 1. Set Appropriate Plan Step Limits
```python
# Match max_plan_steps to task complexity
simple_config = PlanningConfig(max_plan_steps=3)    # Simple tasks
medium_config = PlanningConfig(max_plan_steps=7)    # Medium complexity
complex_config = PlanningConfig(max_plan_steps=15)  # Complex workflows
```

### 2. Use Strict Validation for Critical Workflows
```python
# Critical workflows (compliance, finance)
critical_config = PlanningConfig(
    validation_mode="strict",
    enable_replanning=False  # Don't auto-replan, require manual review
)

# Flexible workflows (research, content)
flexible_config = PlanningConfig(
    validation_mode="warn",
    enable_replanning=True  # Auto-replan on minor issues
)
```

### 3. Provide Rich Context for Better Planning
```python
# Detailed context improves plan quality
context = {
    "constraints": ["Must complete in 2 hours", "Budget limit: $100"],
    "resources": {"compute": "4 cores", "memory": "16GB"},
    "dependencies": ["database must be ready", "API keys configured"],
    "quality_requirements": "95% accuracy, <100ms latency"
}
result = agent.run(task=task, context=context)
```

### 4. Log and Review Validation Results
```python
import logging

# Enable logging
logging.basicConfig(level=logging.INFO)

# Run with logging
result = agent.run(task=task)

# Review validation
validation = result["validation_result"]
if validation["status"] == "warnings":
    logging.warning(f"Plan warnings: {validation['warnings']}")
```

### 5. Handle Replanning Gracefully
```python
# Attempt planning with replanning enabled
config = PlanningConfig(
    enable_replanning=True,
    max_retries=3
)
agent = PlanningAgent(config=config)

result = agent.run(task=task)

if "error" in result:
    if result["error"] == "REPLANNING_FAILED":
        # Fallback: Try with simplified task
        simplified_task = simplify(task)
        result = agent.run(task=simplified_task)
```

### 6. Combine with Other Patterns for Complex Workflows
```python
# Use Planning Agent within multi-agent coordination
from kaizen.orchestration.patterns import SupervisorWorkerPattern

# Planning agent as a worker in supervisor-worker pattern
planning_agent = PlanningAgent(config=PlanningConfig())
execution_agent = ExecutionAgent(config=ExecutionConfig())

pattern = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[planning_agent, execution_agent],
    coordinator=coordinator,
    shared_pool=shared_pool
)

# Supervisor routes planning tasks to planning_agent
result = pattern.execute_task("Plan and execute data migration")
```

## Performance Characteristics

- **Planning Latency**: 2-5 seconds for typical plans (5-10 steps)
- **Validation Latency**: <100ms for plan structure validation
- **Execution Latency**: Depends on step complexity (typically 1-3s per step)
- **Total Latency**: Planning + Validation + (Execution × num_steps)
- **Memory Usage**: ~50MB for typical workflows
- **Concurrent Planning**: Supports parallel planning for independent tasks

**Optimization Tips**:
- Use lower temperature (0.1-0.3) for faster, more consistent planning
- Limit `max_plan_steps` to reduce planning time
- Cache plans for repeated tasks
- Use `validation_mode="off"` only for non-critical workflows

## Integration Examples

### With Core SDK Workflows
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from kaizen.agents.specialized.planning import PlanningAgent

# Create planning agent
agent = PlanningAgent()

# Generate plan
result = agent.run(task="Process customer data")

# Convert plan to Core SDK workflow
workflow = WorkflowBuilder()
for step in result["plan"]:
    workflow.add_node("PythonCodeNode", f"step_{step['step']}", {
        "code": f"# {step['action']}\nprint('{step['description']}')"
    })

# Execute via Core SDK
runtime = LocalRuntime()
runtime.execute(workflow.build())
```

### With DataFlow for Database Operations
```python
from dataflow import DataFlow
from kaizen.agents.specialized.planning import PlanningAgent

db = DataFlow()
agent = PlanningAgent()

# Generate database migration plan
task = "Plan migration from MySQL to PostgreSQL"
result = agent.run(task=task)

# Use plan steps to guide DataFlow operations
for step in result["plan"]:
    if "schema" in step["action"].lower():
        # Execute schema migration
        db.execute_migration(step["description"])
    elif "data" in step["action"].lower():
        # Execute data migration
        db.migrate_data(step["description"])
```

### With Nexus for Multi-Channel Deployment
```python
from nexus import Nexus
from kaizen.agents.specialized.planning import PlanningAgent

# Create agent
agent = PlanningAgent()

# Convert to workflow for Nexus deployment
agent_workflow = agent.to_workflow()

# Deploy via Nexus (API + CLI + MCP)
nexus = Nexus()
nexus.register("planning_agent", agent_workflow.build())

# Available on all channels:
# - API: POST /workflows/planning_agent
# - CLI: nexus run planning_agent --task "Plan deployment"
# - MCP: planning_agent tool for AI assistants
```

## Testing Planning Agent

```python
import pytest
from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig

def test_planning_agent_basic():
    """Test basic plan-validate-execute workflow"""
    config = PlanningConfig(
        llm_provider="mock",  # Use mock for unit tests
        max_plan_steps=3
    )
    agent = PlanningAgent(config=config)

    result = agent.run(task="Create simple test plan")

    # Verify all three phases
    assert "plan" in result
    assert "validation_result" in result
    assert "execution_results" in result
    assert "final_result" in result

    # Verify plan structure
    assert len(result["plan"]) <= 3  # Respects max_plan_steps
    for step in result["plan"]:
        assert "step" in step
        assert "action" in step
        assert "description" in step

def test_planning_agent_validation_strict():
    """Test strict validation mode"""
    config = PlanningConfig(
        llm_provider="mock",
        validation_mode="strict"
    )
    agent = PlanningAgent(config=config)

    # Empty task should fail validation
    result = agent.run(task="")
    assert result["error"] == "INVALID_INPUT"

def test_planning_agent_replanning():
    """Test replanning on validation failure"""
    config = PlanningConfig(
        llm_provider="mock",
        enable_replanning=True
    )
    agent = PlanningAgent(config=config)

    result = agent.run(task="Complex task requiring replanning")

    # Should not error even if initial plan fails validation
    assert "error" not in result or result["error"] != "VALIDATION_FAILED"
```

## See Also

- **[PEV Agent Guide](./pev-agent.md)** - Iterative refinement with verification
- **[Tree-of-Thoughts Guide](./tree-of-thoughts-agent.md)** - Multi-path exploration
- **[Single-Agent Patterns Overview](./single-agent-patterns.md)** - All patterns comparison
- **[Multi-Agent Coordination](./multi-agent-coordination.md)** - Combining agents
- **[API Reference](../reference/api-reference.md)** - Complete API documentation
