# Planning Agents User Guide

**Version**: 1.0.0
**Status**: Production Ready
**Last Updated**: 2025-11-03

---

## Executive Summary

Planning Agents implement explicit planning phases before execution, providing structured workflows for complex tasks. Kaizen provides two production-ready planning agents: **PlanningAgent** (Plan → Validate → Execute) and **PEVAgent** (Plan → Execute → Verify → Refine).

**Key Benefits:**
- Explicit planning phase reduces execution errors
- Validation catches infeasible plans before execution
- Iterative refinement improves output quality
- Structured workflow for complex multi-step tasks
- Zero-config with sensible defaults

---

## Table of Contents

1. [What are Planning Agents?](#what-are-planning-agents)
2. [The Two Planning Agents](#the-two-planning-agents)
3. [When to Use Each Agent](#when-to-use-each-agent)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [Advanced Usage](#advanced-usage)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## What are Planning Agents?

**Planning agents** create explicit plans before execution, differing from reactive agents that interleave thinking and action.

### Comparison with Other Agent Patterns

| Agent Type | Pattern | Planning Phase | Validation | Use Case |
|------------|---------|---------------|------------|----------|
| **SimpleQA** | Question → Answer | No | No | Direct Q&A |
| **ChainOfThought** | Step-by-step reasoning | No | No | Linear reasoning |
| **ReAct** | Reason → Act → Observe | No | No | Reactive tasks |
| **PlanningAgent** | Plan → Validate → Execute | Yes | Yes | Complex tasks |
| **PEVAgent** | Plan → Execute → Verify → Refine | Yes | Yes (iterative) | Quality-critical tasks |

### Why Use Planning?

**Without Planning (ReAct Pattern):**
```
Cycle 1: Observe "Need to create report" → Act: Write introduction
Cycle 2: Observe "Missing research" → Act: Search for data
Cycle 3: Observe "Data found" → Act: Analyze data
Cycle 4: Observe "Need citations" → Act: Add citations
Cycle 5: Observe "Report incomplete" → Act: Add conclusions
```
**Total: 5 cycles, reactive, no upfront structure**

**With Planning (PlanningAgent):**
```
PLAN PHASE:
  Step 1: Research topic and gather sources
  Step 2: Analyze data and create outline
  Step 3: Write introduction and conclusions
  Step 4: Add citations and formatting

VALIDATION PHASE:
  ✅ All steps feasible
  ✅ Logical sequence confirmed
  ✅ Resources available

EXECUTION PHASE:
  Execute Step 1 → Step 2 → Step 3 → Step 4
```
**Total: 1 planning cycle + 4 execution cycles, structured, validated**

**Benefits:**
- Fewer wasted cycles (no backtracking)
- Catches infeasible plans early
- Clear progress tracking
- Better resource utilization

---

## The Two Planning Agents

### 1. PlanningAgent

**Pattern**: Plan → Validate → Execute (Three-Phase)

**Workflow:**
```
┌─────────────┐
│   PLAN      │  Generate detailed execution plan
│  (Phase 1)  │  Output: List of steps with actions
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  VALIDATE   │  Check plan feasibility
│  (Phase 2)  │  Output: Validation status + warnings
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  EXECUTE    │  Execute validated plan step-by-step
│  (Phase 3)  │  Output: Results from each step
└──────┬──────┘
       │
       ▼
  Final Result
```

**Use Cases:**
- Research reports
- Project planning
- Multi-step workflows
- Tasks with clear phases

**Example:**
```python
from kaizen.agents import PlanningAgent

agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    max_plan_steps=10,
    validation_mode="strict"
)

result = agent.run(task="Create a comprehensive research report on AI ethics")

print(f"Plan: {result['plan']}")                      # Detailed steps
print(f"Validation: {result['validation_result']}")   # Validation status
print(f"Results: {result['execution_results']}")      # Step-by-step results
print(f"Final: {result['final_result']}")             # Aggregated result
```

### 2. PEVAgent

**Pattern**: Plan → Execute → Verify → Refine (Iterative Loop)

**Workflow:**
```
┌─────────────┐
│   PLAN      │  Create execution plan
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  EXECUTE    │  Execute the plan
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   VERIFY    │  Check result quality
└──────┬──────┘
       │
       ├─── Issues? ──┐
       │              │
       No            Yes
       │              │
       ▼              ▼
  Final Result   ┌─────────────┐
                 │   REFINE    │  Improve plan based on issues
                 └──────┬──────┘
                        │
                        └──────── (Loop back to EXECUTE)
```

**Use Cases:**
- Code generation with testing
- Content creation with quality checks
- Iterative optimization tasks
- Tasks requiring refinement

**Example:**
```python
from kaizen.agents import PEVAgent

agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    max_iterations=10,
    verification_strictness="strict"
)

result = agent.run(task="Generate Python code with passing tests")

print(f"Plan: {result['plan']}")                      # Current plan
print(f"Refinements: {len(result['refinements'])}")   # Number of refinements
print(f"Verified: {result['verification']['passed']}")  # Verification status
print(f"Final: {result['final_result']}")             # Final verified result
```

---

## When to Use Each Agent

### Use PlanningAgent When:

✅ **Clear Task Decomposition**
- Task can be broken into sequential steps
- Example: "Create marketing campaign with research, content, and distribution phases"

✅ **One-Shot Execution**
- Plan should work on first attempt
- Example: "Generate project timeline with dependencies"

✅ **Validation Critical**
- Need to catch infeasible plans before execution
- Example: "Plan deployment with resource constraints"

✅ **Progress Tracking**
- Need clear milestones and progress indicators
- Example: "Multi-week project plan with checkpoints"

### Use PEVAgent When:

✅ **Quality Requirements**
- Output must meet specific quality criteria
- Example: "Generate code that passes all tests"

✅ **Iterative Improvement**
- Initial attempt may need refinement
- Example: "Write article that meets editorial standards"

✅ **Verification Needed**
- Output requires explicit verification
- Example: "Generate report with fact-checking"

✅ **Unknown Complexity**
- Task complexity unknown upfront
- Example: "Solve bug that may require multiple attempts"

### Decision Matrix

| Requirement | PlanningAgent | PEVAgent |
|-------------|--------------|----------|
| One-shot execution | ✅ Best | ⚠️ Overkill |
| Iterative refinement | ⚠️ Limited | ✅ Best |
| Strict validation before execution | ✅ Built-in | ⚠️ After execution |
| Quality verification | ⚠️ Manual | ✅ Automatic |
| Complex multi-step tasks | ✅ Excellent | ⚠️ May over-iterate |
| Code generation + testing | ⚠️ Manual testing | ✅ Integrated |
| Research reports | ✅ Structured | ⚠️ May over-refine |
| Bug fixing | ⚠️ Manual retry | ✅ Auto-retry |

---

## Quick Start

### PlanningAgent: Basic Usage

```python
from kaizen.agents import PlanningAgent

# Zero-config (simplest)
agent = PlanningAgent()
result = agent.run(task="Create research report on quantum computing")

# With configuration
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.3,              # Low for consistent planning
    max_plan_steps=5,             # Limit plan complexity
    validation_mode="strict",     # Strict validation
    enable_replanning=True        # Retry on validation failure
)

# With context
result = agent.run(
    task="Organize tech conference",
    context={
        "budget": "$50,000",
        "attendees": 500,
        "duration": "2 days"
    }
)

# Access results
print(result["plan"])                      # List of plan steps
print(result["validation_result"])         # Validation status
print(result["execution_results"])         # Step-by-step results
print(result["final_result"])              # Aggregated result
```

### PEVAgent: Basic Usage

```python
from kaizen.agents import PEVAgent

# Zero-config (simplest)
agent = PEVAgent()
result = agent.run(task="Generate working Python code with tests")

# With configuration
agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,                    # Higher for creativity
    max_iterations=10,                  # Max refinement loops
    verification_strictness="strict",   # Strict quality checks
    enable_error_recovery=True          # Continue on errors
)

# Execute with refinement
result = agent.run(task="Write article meeting editorial standards")

# Access results
print(result["plan"])                       # Current plan
print(result["execution_result"])           # Execution output
print(result["verification"])               # Verification status
print(f"Refinements: {len(result['refinements'])}")  # Iterations
print(result["final_result"])               # Final verified result
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
from dotenv import load_dotenv
from kaizen.agents import PlanningAgent

load_dotenv()  # Load from .env

# Uses environment variables automatically
agent = PlanningAgent()
```

---

## Configuration

### PlanningAgent Configuration

```python
from kaizen.agents import PlanningAgent, PlanningConfig

config = PlanningConfig(
    # LLM Configuration
    llm_provider="openai",           # LLM provider (openai, anthropic, ollama)
    model="gpt-4",                   # Model name
    temperature=0.3,                 # Sampling temperature (0.0-1.0)
    max_tokens=2000,                 # Maximum tokens per request

    # Planning Configuration
    max_plan_steps=10,               # Maximum steps in plan
    validation_mode="strict",        # Validation strictness (strict, warn, off)
    enable_replanning=True,          # Enable replanning on validation failure
    timeout=30,                      # Request timeout (seconds)
    max_retries=3,                   # Retry attempts on failure
    provider_config={}               # Additional provider-specific config
)

agent = PlanningAgent(config=config)
```

**Configuration Options:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_provider` | str | "openai" | LLM provider (openai, anthropic, ollama) |
| `model` | str | "gpt-4" | Model name |
| `temperature` | float | 0.7 | Sampling temperature (0.0-1.0) |
| `max_tokens` | int | 2000 | Maximum tokens per request |
| `max_plan_steps` | int | 10 | Maximum steps in plan |
| `validation_mode` | str | "strict" | Validation strictness (strict, warn, off) |
| `enable_replanning` | bool | True | Enable replanning on validation failure |
| `timeout` | int | 30 | Request timeout (seconds) |
| `max_retries` | int | 3 | Retry attempts on failure |
| `provider_config` | dict | {} | Additional provider-specific config |

### PEVAgent Configuration

```python
from kaizen.agents import PEVAgent, PEVAgentConfig

config = PEVAgentConfig(
    # LLM Configuration
    llm_provider="openai",           # LLM provider (openai, anthropic, ollama)
    model="gpt-4",                   # Model name
    temperature=0.7,                 # Sampling temperature (0.0-1.0)
    max_tokens=2000,                 # Maximum tokens per request

    # PEV Configuration
    max_iterations=5,                # Maximum refinement iterations
    verification_strictness="medium", # Verification strictness (strict, medium, lenient)
    enable_error_recovery=True,      # Continue execution on errors
    timeout=30,                      # Request timeout (seconds)
    max_retries=3,                   # Retry attempts on failure
    provider_config={}               # Additional provider-specific config
)

agent = PEVAgent(config=config)
```

**Configuration Options:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_provider` | str | "openai" | LLM provider (openai, anthropic, ollama) |
| `model` | str | "gpt-4" | Model name |
| `temperature` | float | 0.7 | Sampling temperature (0.0-1.0) |
| `max_tokens` | int | 2000 | Maximum tokens per request |
| `max_iterations` | int | 5 | Maximum refinement iterations |
| `verification_strictness` | str | "medium" | Verification strictness (strict, medium, lenient) |
| `enable_error_recovery` | bool | True | Continue execution on errors |
| `timeout` | int | 30 | Request timeout (seconds) |
| `max_retries` | int | 3 | Retry attempts on failure |
| `provider_config` | dict | {} | Additional provider-specific config |

---

## Advanced Usage

### PlanningAgent: Custom Validation

```python
from kaizen.agents import PlanningAgent

# Strict validation (recommended for production)
agent = PlanningAgent(validation_mode="strict")

result = agent.run(task="Deploy application to production")

# Check validation
if result["validation_result"]["status"] == "passed":
    print("Plan validated successfully")
    # Proceed with execution results
else:
    print(f"Validation failed: {result['validation_result']['reason']}")
    # Handle replanning or abort
```

**Validation Modes:**

- **strict**: Fail on any validation issue, require replanning
- **warn**: Log warnings but continue execution
- **off**: Skip validation (not recommended)

### PlanningAgent: Replanning on Failure

```python
from kaizen.agents import PlanningAgent

agent = PlanningAgent(
    enable_replanning=True,  # Enable automatic replanning
    max_retries=3            # Max replanning attempts
)

result = agent.run(task="Complex multi-step task")

# Check if replanning occurred
if "replanning_count" in result:
    print(f"Replanned {result['replanning_count']} times")
```

### PEVAgent: Verification Strictness

```python
from kaizen.agents import PEVAgent

# Strict verification (highest quality)
agent_strict = PEVAgent(verification_strictness="strict")

# Medium verification (balanced)
agent_medium = PEVAgent(verification_strictness="medium")

# Lenient verification (faster)
agent_lenient = PEVAgent(verification_strictness="lenient")

result = agent_strict.run(task="Generate production-ready code")

# Check verification
if result["verification"]["passed"]:
    print("Verification passed")
else:
    print(f"Issues: {result['verification']['issues']}")
    print(f"Refinements: {len(result['refinements'])}")
```

**Verification Strictness:**

- **strict**: Reject any quality issues, continue refining until perfect
- **medium**: Accept minor issues, refine major issues
- **lenient**: Accept most issues, minimal refinement

### PEVAgent: Error Recovery

```python
from kaizen.agents import PEVAgent

agent = PEVAgent(
    enable_error_recovery=True,  # Continue on errors
    max_iterations=10            # Allow multiple recovery attempts
)

result = agent.run(task="Generate code with complex dependencies")

# Check error recovery
if "errors_recovered" in result:
    print(f"Recovered from {len(result['errors_recovered'])} errors")
```

### Progressive Configuration

Both agents support progressive configuration (override defaults as needed):

```python
from kaizen.agents import PlanningAgent, PEVAgent

# Override only what you need
agent1 = PlanningAgent(model="gpt-3.5-turbo")  # Use cheaper model

agent2 = PlanningAgent(
    model="gpt-4",
    temperature=0.3,            # Override temperature
    max_plan_steps=5            # Override max steps
)

agent3 = PEVAgent(
    verification_strictness="strict",  # Override verification only
)
```

---

## Best Practices

### 1. Choose the Right Agent

✅ **DO**: Use PlanningAgent for structured tasks
```python
agent = PlanningAgent()
result = agent.run(task="Create project timeline with milestones")
```

✅ **DO**: Use PEVAgent for quality-critical tasks
```python
agent = PEVAgent()
result = agent.run(task="Generate code that passes all tests")
```

❌ **DON'T**: Use PEVAgent for simple tasks (overkill)
```python
# WRONG: Simple Q&A doesn't need iterative refinement
agent = PEVAgent()
result = agent.run(task="What is 2+2?")
```

### 2. Set Appropriate Limits

✅ **DO**: Match limits to task complexity
```python
# Simple task: Low limits
agent = PlanningAgent(max_plan_steps=3)

# Complex task: Higher limits
agent = PlanningAgent(max_plan_steps=10)

# Iterative refinement: Allow iterations
agent = PEVAgent(max_iterations=10)
```

❌ **DON'T**: Use excessive limits for simple tasks
```python
# WRONG: Overkill for simple task
agent = PlanningAgent(max_plan_steps=50)
result = agent.run(task="Write a paragraph")
```

### 3. Use Strict Validation for Production

✅ **DO**: Enable strict validation for production
```python
agent = PlanningAgent(
    validation_mode="strict",    # Catch issues early
    enable_replanning=True       # Auto-retry on failure
)
```

❌ **DON'T**: Disable validation in production
```python
# WRONG: Skips critical validation
agent = PlanningAgent(validation_mode="off")
```

### 4. Provide Context for Better Plans

✅ **DO**: Provide relevant context
```python
result = agent.run(
    task="Organize conference",
    context={
        "budget": "$50,000",
        "attendees": 500,
        "venue": "Convention Center",
        "date": "2025-12-01"
    }
)
```

❌ **DON'T**: Omit critical context
```python
# WRONG: Missing critical constraints
result = agent.run(task="Organize conference")
```

### 5. Monitor Refinement Iterations

✅ **DO**: Track refinement progress
```python
agent = PEVAgent(max_iterations=10)
result = agent.run(task="Generate code")

# Monitor iterations
refinement_count = len(result["refinements"])
if refinement_count > 5:
    print(f"Warning: Required {refinement_count} refinements")
```

### 6. Use Environment Variables for Configuration

✅ **DO**: Use .env for configuration
```bash
# .env file
KAIZEN_LLM_PROVIDER=openai
KAIZEN_MODEL=gpt-4
KAIZEN_TEMPERATURE=0.3
```

```python
from dotenv import load_dotenv
from kaizen.agents import PlanningAgent

load_dotenv()
agent = PlanningAgent()  # Uses .env automatically
```

### 7. Handle Errors Gracefully

✅ **DO**: Check for errors in result
```python
result = agent.run(task="Complex task")

if "error" in result:
    print(f"Error: {result['error']}")
    # Handle error appropriately
else:
    # Process successful result
    print(result["final_result"])
```

---

## Troubleshooting

### Issue 1: Validation Fails Repeatedly

**Symptom**: PlanningAgent validation fails after multiple replanning attempts

**Causes**:
1. Task too vague or underspecified
2. Conflicting constraints in context
3. max_plan_steps set too low

**Solutions**:

```python
# Solution 1: Provide more specific task description
result = agent.run(
    task="Create detailed research report on AI ethics (2000 words, 5+ sources, academic style)",
    context={"deadline": "2025-12-01", "audience": "researchers"}
)

# Solution 2: Increase max_plan_steps
agent = PlanningAgent(max_plan_steps=15)  # Was 5

# Solution 3: Use lenient validation mode (temporary)
agent = PlanningAgent(validation_mode="warn")  # Debug mode
```

### Issue 2: PEVAgent Never Converges

**Symptom**: PEVAgent uses all max_iterations without verification passing

**Causes**:
1. Verification strictness too high
2. Task requirements unrealistic
3. max_iterations too low

**Solutions**:

```python
# Solution 1: Lower verification strictness
agent = PEVAgent(verification_strictness="medium")  # Was "strict"

# Solution 2: Increase max_iterations
agent = PEVAgent(max_iterations=20)  # Was 5

# Solution 3: Simplify task requirements
result = agent.run(task="Generate simple Python function with basic tests")
# Instead of: "Generate enterprise-grade production code with 100% coverage"
```

### Issue 3: Plans Too Generic

**Symptom**: Generated plans lack specific details

**Causes**:
1. Temperature too high (randomness)
2. Insufficient context
3. Model not powerful enough

**Solutions**:

```python
# Solution 1: Lower temperature
agent = PlanningAgent(temperature=0.2)  # Was 0.7

# Solution 2: Provide detailed context
result = agent.run(
    task="Create deployment plan",
    context={
        "infrastructure": "AWS ECS",
        "database": "PostgreSQL RDS",
        "regions": ["us-east-1", "eu-west-1"],
        "rollout_strategy": "blue-green",
        "monitoring": "CloudWatch + Datadog"
    }
)

# Solution 3: Use more capable model
agent = PlanningAgent(model="gpt-4")  # Was gpt-3.5-turbo
```

### Issue 4: Execution Takes Too Long

**Symptom**: Agent execution exceeds expected time

**Causes**:
1. max_plan_steps or max_iterations too high
2. Network timeout too long
3. Complex LLM calls

**Solutions**:

```python
# Solution 1: Reduce limits
agent = PlanningAgent(max_plan_steps=5)  # Was 20
agent = PEVAgent(max_iterations=3)        # Was 10

# Solution 2: Set timeout
agent = PlanningAgent(timeout=15)  # 15 seconds per request

# Solution 3: Use faster model
agent = PlanningAgent(
    llm_provider="ollama",       # Local inference
    model="llama2"               # Faster than GPT-4
)
```

### Issue 5: API Rate Limits

**Symptom**: Errors about API rate limits or quota exceeded

**Causes**:
1. Too many LLM calls
2. max_retries set too high
3. Multiple agents running concurrently

**Solutions**:

```python
# Solution 1: Reduce retries
agent = PlanningAgent(max_retries=1)  # Was 3

# Solution 2: Add delays between requests
import time
results = []
for task in tasks:
    result = agent.run(task=task)
    results.append(result)
    time.sleep(2)  # 2-second delay

# Solution 3: Use local model (Ollama)
agent = PlanningAgent(
    llm_provider="ollama",
    model="llama2"  # No API limits
)
```

---

## Examples

Working examples are available in `examples/1-single-agent/planning-agent/`:

1. **`basic_planning.py`** - Basic PlanningAgent usage with research task
2. **`pev_code_generation.py`** - PEVAgent for iterative code generation (coming soon)
3. **`replanning_demo.py`** - Demonstration of automatic replanning (coming soon)
4. **`verification_demo.py`** - Demonstration of PEVAgent verification (coming soon)

---

## Summary

**Planning Agents** provide structured workflows for complex tasks:

**PlanningAgent:**
- ✅ Three-phase workflow (Plan → Validate → Execute)
- ✅ Upfront validation catches infeasible plans
- ✅ One-shot execution for structured tasks
- ✅ Progress tracking with clear milestones

**PEVAgent:**
- ✅ Iterative refinement loop (Plan → Execute → Verify → Refine)
- ✅ Quality verification with automatic refinement
- ✅ Error recovery and retry mechanisms
- ✅ Ideal for quality-critical tasks

**Key Differences:**

| Feature | PlanningAgent | PEVAgent |
|---------|--------------|----------|
| Workflow | Three-phase | Iterative loop |
| Validation | Before execution | After execution |
| Refinement | Manual (replanning) | Automatic |
| Best For | Structured tasks | Quality-critical tasks |
| Iterations | 1 (+ replanning) | Multiple (configurable) |

**When to Use:**
- **PlanningAgent**: Research reports, project planning, multi-step workflows
- **PEVAgent**: Code generation, content creation, iterative optimization

---

**Framework**: Kaizen AI Framework built on Kailash Core SDK
**License**: MIT
**Location**: `kaizen.agents.specialized.planning`, `kaizen.agents.specialized.pev`
**Tests**: `tests/unit/agents/specialized/test_planning.py`, `tests/unit/agents/specialized/test_pev.py`
