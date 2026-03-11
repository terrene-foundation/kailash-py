# Planning System Guide

**Version**: v0.6.3+
**Audience**: Developers building autonomous agents with explicit planning capabilities

## Table of Contents

1. [Introduction](#introduction)
2. [When to Use Planning Agents](#when-to-use-planning-agents)
3. [PlanningAgent: Plan → Validate → Execute](#planningagent-plan--validate--execute)
4. [PEVAgent: Plan → Execute → Verify → Refine](#pevagent-plan--execute--verify--refine)
5. [Configuration & Customization](#configuration--customization)
6. [Production Patterns](#production-patterns)
7. [Testing Planning Agents](#testing-planning-agents)
8. [Troubleshooting](#troubleshooting)

---

## Introduction

The **Planning System** provides two specialized agent patterns for tasks requiring explicit multi-step planning:

- **PlanningAgent**: Generates a complete plan upfront, validates it, then executes steps sequentially
- **PEVAgent**: Executes with iterative refinement through Plan → Execute → Verify → Refine loops

Both agents are built on `BaseAgent` and support the same features (tool calling, memory, hooks, checkpoints, interrupts).

### Key Concepts

**Explicit Planning**: Unlike reactive agents that respond step-by-step, planning agents create a detailed execution plan before taking action.

**Validation**: Plans are validated for structure, feasibility, and completeness before execution.

**Execution Tracking**: Each step's execution is tracked with success/failure status and intermediate results.

**Refinement** (PEVAgent only): Failed or incomplete executions trigger plan refinement and retry loops.

---

## When to Use Planning Agents

### Use PlanningAgent When

- **Complex multi-step tasks**: Research reports, data analysis pipelines, content generation workflows
- **Dependencies between steps**: Later steps require results from earlier steps
- **Need upfront validation**: Validate entire plan before committing resources
- **Predictable workflows**: Tasks with well-defined step sequences
- **Resource constraints**: Want to estimate cost/time before execution

**Example Tasks**:
- Research and summarize a technical topic with sources
- Analyze dataset, generate visualizations, write summary report
- Build software: plan → implement → test → document
- Create content: outline → draft → revise → publish

### Use PEVAgent When

- **Iterative refinement needed**: Quality improves through multiple iterations
- **Verification is critical**: Each execution must be verified for correctness
- **Error recovery required**: Failures should trigger plan adjustments
- **Exploration beneficial**: Multiple attempts can improve final result
- **Incremental improvement**: Each iteration builds on previous work

**Example Tasks**:
- Code generation with correctness verification and refinement
- Content creation with quality checks and revisions
- Design iterations (UI mockups, architecture diagrams)
- Scientific experiments with hypothesis testing and adjustments

### Use BaseAgent (No Planning) When

- **Simple single-step tasks**: Q&A, classification, extraction
- **Reactive workflows**: Respond to real-time events
- **Minimal overhead required**: Planning adds latency and cost
- **No multi-step dependencies**: Each operation is independent

---

## PlanningAgent: Plan → Validate → Execute

### Pattern Overview

```
┌─────────────┐
│   PHASE 1   │  Generate Plan
│   PLANNING  │  - LLM creates step-by-step plan
└──────┬──────┘  - Each step: number, action, description
       │
       ▼
┌─────────────┐
│   PHASE 2   │  Validate Plan
│ VALIDATION  │  - Check structure (steps have required fields)
└──────┬──────┘  - Check feasibility (steps are actionable)
       │         - Check completeness (achieves goal)
       ▼
┌─────────────┐
│   PHASE 3   │  Execute Plan
│  EXECUTION  │  - Execute each step sequentially
└──────┬──────┘  - Track results and status
       │         - Stop on failure (strict mode)
       ▼
┌─────────────┐
│   PHASE 4   │  Aggregate Results
│ AGGREGATION │  - Combine step results
└─────────────┘  - Return final output
```

### Basic Usage

```python
from kaizen.agents.specialized.planning import PlanningAgent

# Create planning agent
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    max_plan_steps=10,
    validation_mode="strict",
    enable_replanning=True
)

# Execute task with automatic planning
result = agent.run(task="Research AI safety and write a summary report")

# Access plan and results
print("Plan:")
for step in result["plan"]:
    print(f"  {step['step']}. {step['description']}")

print("\nExecution Results:")
for step_result in result["execution_results"]:
    print(f"  Step {step_result['step']}: {step_result['status']}")

print(f"\nFinal Result:\n{result['final_result']}")
```

**Result Structure:**

```python
{
    "plan": [
        {"step": 1, "action": "research_topic", "description": "Search for AI safety resources"},
        {"step": 2, "action": "analyze_sources", "description": "Read and analyze key papers"},
        {"step": 3, "action": "synthesize_findings", "description": "Synthesize insights"},
        {"step": 4, "action": "write_report", "description": "Write comprehensive summary"}
    ],
    "validation_result": {
        "valid": True,
        "errors": [],
        "warnings": []
    },
    "execution_results": [
        {"step": 1, "status": "success", "result": {...}, "duration_ms": 5000},
        {"step": 2, "status": "success", "result": {...}, "duration_ms": 8000},
        {"step": 3, "status": "success", "result": {...}, "duration_ms": 3000},
        {"step": 4, "status": "success", "result": {...}, "duration_ms": 6000}
    ],
    "final_result": "AI safety is a rapidly evolving field focused on ensuring that artificial intelligence systems are developed and deployed in ways that are beneficial to humanity..."
}
```

### Advanced Configuration

```python
from kaizen.agents.specialized.planning import PlanningAgent

agent = PlanningAgent(
    # LLM configuration
    llm_provider="openai",
    model="gpt-4",
    temperature=0.3,  # Low for consistent planning
    max_tokens=4096,

    # Planning configuration
    max_plan_steps=10,              # Max steps in plan
    min_plan_steps=2,                # Min steps required
    validation_mode="strict",        # strict, warn, off
    enable_replanning=True,          # Retry if validation fails

    # Execution configuration
    max_retries_per_step=3,          # Retry failed steps
    continue_on_step_failure=False,  # Stop on first failure (strict)
    step_timeout=30.0,               # Max seconds per step

    # Output configuration
    include_intermediate_results=True,  # Include step results
    aggregate_results=True              # Combine into final result
)
```

**Configuration Parameters:**

- **validation_mode**:
  - `"strict"`: Plan must pass all validation checks
  - `"warn"`: Log warnings but proceed with invalid plan
  - `"off"`: Skip validation (not recommended)

- **enable_replanning**: If `True`, retry planning if validation fails (max 3 attempts)

- **continue_on_step_failure**: If `True`, continue executing remaining steps after failure

### Validation Rules

Plans are validated against these rules:

**Structure Validation:**
- Each step must have: `step` (number), `action` (verb), `description` (details)
- Steps must be numbered sequentially (1, 2, 3, ...)
- No duplicate step numbers

**Feasibility Validation:**
- Actions must be actionable (avoid vague verbs like "think", "consider")
- Steps must have sufficient detail for execution
- No circular dependencies

**Completeness Validation:**
- Plan must have at least `min_plan_steps` steps
- Plan must not exceed `max_plan_steps` steps
- Final step should achieve the stated goal

### Handling Planning Failures

```python
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    validation_mode="strict",
    enable_replanning=True  # Retry up to 3 times
)

result = agent.run(task="Complex task requiring detailed planning")

# Check validation
if not result["validation_result"]["valid"]:
    print("Plan validation failed:")
    for error in result["validation_result"]["errors"]:
        print(f"  - {error}")

    # If replanning disabled or all retries exhausted
    if not result.get("final_result"):
        print("Task could not be completed due to planning failure")
        return

# Check execution
failed_steps = [r for r in result["execution_results"] if r["status"] == "failed"]
if failed_steps:
    print(f"{len(failed_steps)} steps failed:")
    for step_result in failed_steps:
        print(f"  Step {step_result['step']}: {step_result['error']}")
```

---

## PEVAgent: Plan → Execute → Verify → Refine

### Pattern Overview

```
┌─────────────┐
│   PHASE 1   │  Initial Plan
│   PLANNING  │  - Create execution plan
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   PHASE 2   │  Execute Plan
│  EXECUTION  │  - Perform planned actions
└──────┬──────┘  - Track intermediate results
       │
       ▼
┌─────────────┐
│   PHASE 3   │  Verify Results
│ VERIFICATION│  - Check correctness/quality
└──────┬──────┘  - Identify issues
       │
       ▼
   ┌───────┐
   │Passed?│
   └───┬───┘
       │ No
       ▼
┌─────────────┐
│   PHASE 4   │  Refine Plan
│ REFINEMENT  │  - Adjust plan based on issues
└──────┬──────┘  - Improve approach
       │
       └─────► (Loop back to PHASE 2)
       │
       │ Yes
       ▼
┌─────────────┐
│   FINAL     │  Return Result
│   RESULT    │
└─────────────┘
```

### Basic Usage

```python
from kaizen.agents.specialized.pev import PEVAgent

# Create PEV agent
agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    max_iterations=10,
    verification_strictness="strict",
    enable_error_recovery=True
)

# Execute task with iterative refinement
result = agent.run(task="Generate Python code to calculate fibonacci numbers and verify it works")

# Check if verification passed
if result["verification"]["passed"]:
    print("Task completed successfully")
    print(f"Iterations: {len(result['refinements'])}")
    print(f"Final Result:\n{result['final_result']}")
else:
    print("Task failed verification after max iterations")
    print(f"Issues: {result['verification']['issues']}")
```

**Result Structure:**

```python
{
    "plan": {
        "steps": [
            {"step": 1, "action": "write_code", "description": "Implement fibonacci function"},
            {"step": 2, "action": "test_code", "description": "Test with sample inputs"}
        ]
    },
    "execution_result": {
        "code": "def fibonacci(n): ...",
        "test_results": {...}
    },
    "verification": {
        "passed": True,
        "score": 95,
        "issues": [],
        "suggestions": []
    },
    "refinements": [
        {
            "iteration": 1,
            "changes": "Fixed edge case for n=0",
            "verification_score": 85
        },
        {
            "iteration": 2,
            "changes": "Optimized with memoization",
            "verification_score": 95
        }
    ],
    "final_result": "def fibonacci(n):\n    if n <= 1:\n        return n\n    ..."
}
```

### Advanced Configuration

```python
from kaizen.agents.specialized.pev import PEVAgent

agent = PEVAgent(
    # LLM configuration
    llm_provider="openai",
    model="gpt-4",
    temperature=0.5,  # Medium for exploration

    # PEV configuration
    max_iterations=10,                    # Max refinement loops
    min_verification_score=80,            # Min score to pass (0-100)
    verification_strictness="medium",     # strict, medium, lenient
    enable_error_recovery=True,           # Continue after errors

    # Refinement strategy
    refinement_strategy="incremental",    # incremental, full_replan
    max_refinements_per_iteration=3,      # Max changes per iteration
    early_stopping=True,                  # Stop if score plateaus

    # Verification configuration
    include_verification_details=True,    # Include detailed feedback
    aggregate_refinements=True            # Track all refinements
)
```

**Configuration Parameters:**

- **verification_strictness**:
  - `"strict"`: Score must be ≥ 90, zero critical issues
  - `"medium"`: Score must be ≥ 80, at most 1 critical issue
  - `"lenient"`: Score must be ≥ 70, at most 2 critical issues

- **refinement_strategy**:
  - `"incremental"`: Apply small changes to existing plan/result
  - `"full_replan"`: Create entirely new plan if verification fails

- **early_stopping**: Stop if verification score doesn't improve for 2 consecutive iterations

### Verification Process

Verification checks are customizable via the signature:

```python
from kaizen.signatures import Signature, InputField, OutputField

class CodeVerificationSignature(Signature):
    """Signature for code verification."""

    code: str = InputField(description="Code to verify")
    requirements: str = InputField(description="Requirements to check")

    passed: bool = OutputField(description="Whether verification passed")
    score: int = OutputField(description="Quality score 0-100")
    issues: list = OutputField(description="List of issues found")
    suggestions: list = OutputField(description="Improvement suggestions")

# Use custom signature
agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    verification_signature=CodeVerificationSignature()
)
```

### Handling Iterative Refinement

```python
agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    max_iterations=10,
    verification_strictness="strict",
    early_stopping=True
)

result = agent.run(task="Create a data visualization dashboard")

# Track refinement progress
print(f"Total iterations: {len(result['refinements'])}")

for i, refinement in enumerate(result['refinements'], 1):
    print(f"\nIteration {i}:")
    print(f"  Changes: {refinement['changes']}")
    print(f"  Score: {refinement['verification_score']}")

# Check final verification
verification = result["verification"]
if verification["passed"]:
    print(f"\nCompleted successfully (score: {verification['score']})")
else:
    print(f"\nFailed verification after {len(result['refinements'])} iterations")
    print(f"Remaining issues: {verification['issues']}")
```

---

## Configuration & Customization

### Environment Variables

Both PlanningAgent and PEVAgent support environment variable configuration:

```bash
# Planning configuration
KAIZEN_MAX_PLAN_STEPS=10
KAIZEN_VALIDATION_MODE=strict
KAIZEN_ENABLE_REPLANNING=true

# PEV configuration
KAIZEN_MAX_ITERATIONS=10
KAIZEN_VERIFICATION_STRICTNESS=medium
KAIZEN_MIN_VERIFICATION_SCORE=80

# LLM configuration (shared)
KAIZEN_LLM_PROVIDER=openai
KAIZEN_MODEL=gpt-4
KAIZEN_TEMPERATURE=0.3
KAIZEN_MAX_TOKENS=4096
```

Priority: **Constructor args** > **Environment variables** > **Defaults**

### Custom Signatures

Both agents use default signatures but support customization:

```python
from kaizen.signatures import Signature, InputField, OutputField

class ResearchPlanningSignature(Signature):
    """Custom signature for research tasks."""

    topic: str = InputField(description="Research topic")
    depth: str = InputField(description="Research depth: surface, moderate, deep")

    plan: list = OutputField(description="Research plan with steps")
    sources: list = OutputField(description="Recommended sources")
    timeline: str = OutputField(description="Estimated timeline")

agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    signature=ResearchPlanningSignature()
)

result = agent.run(topic="Quantum computing", depth="deep")
print(f"Timeline: {result['timeline']}")
print(f"Sources: {result['sources']}")
```

### Tool Integration

Planning agents can use tools during execution:

```python
from kaizen.agents.specialized.planning import PlanningAgent
from kaizen.tools.builtin import WebSearchTool, FileReadTool

# Create agent with tools
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    tools=[
        WebSearchTool(),    # Search web during research steps
        FileReadTool()      # Read files during analysis steps
    ],
    enable_tool_use=True
)

# Tools are automatically available during plan execution
result = agent.run(task="Research recent AI developments and summarize")

# Check tool usage
for step_result in result["execution_results"]:
    if "tools_used" in step_result:
        print(f"Step {step_result['step']} used: {step_result['tools_used']}")
```

### Memory Integration

Planning agents support 3-tier memory system:

```python
from kaizen.agents.specialized.planning import PlanningAgent
from kaizen.memory.enterprise import EnterpriseMemorySystem
from kaizen.memory.backends import DataFlowBackend
from dataflow import DataFlow

# Setup memory
db = DataFlow(db_url="postgresql://localhost/memory_db")
backend = DataFlowBackend(db)
memory = EnterpriseMemorySystem(backend=backend)

# Create agent with memory
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    memory=memory,
    enable_memory=True
)

# Memory automatically stores:
# - Plans created
# - Execution results
# - Validation outcomes
result = agent.run(task="Analyze quarterly sales data")

# Retrieve from memory
past_plans = memory.search(query="sales analysis", limit=5)
```

---

## Production Patterns

### Pattern 1: Research & Reporting

```python
from kaizen.agents.specialized.planning import PlanningAgent

class ResearchReportAgent(PlanningAgent):
    """Specialized agent for research and reporting tasks."""

    def __init__(self):
        super().__init__(
            llm_provider="openai",
            model="gpt-4",
            max_plan_steps=8,
            validation_mode="strict",
            enable_replanning=True,

            # Add research tools
            tools=[WebSearchTool(), FileReadTool(), WriteFileTool()],
            enable_tool_use=True,

            # Enable checkpointing for long tasks
            enable_checkpoints=True,
            checkpoint_frequency=2  # Checkpoint after every 2 steps
        )

    def research_and_report(self, topic: str, depth: str = "moderate") -> dict:
        """Research topic and generate comprehensive report."""
        task = f"Research '{topic}' with {depth} depth and write a comprehensive report"
        result = self.run(task=task)

        # Save report to file (last step result)
        if result["execution_results"][-1]["status"] == "success":
            report_path = result["execution_results"][-1]["result"]["file_path"]
            print(f"Report saved to: {report_path}")

        return result

# Usage
agent = ResearchReportAgent()
result = agent.research_and_report(
    topic="Renewable Energy Trends 2025",
    depth="deep"
)
```

### Pattern 2: Code Generation with Verification

```python
from kaizen.agents.specialized.pev import PEVAgent

class CodeGenerationAgent(PEVAgent):
    """Specialized agent for code generation with verification."""

    def __init__(self):
        super().__init__(
            llm_provider="openai",
            model="gpt-4",
            max_iterations=5,
            verification_strictness="strict",
            enable_error_recovery=True,

            # Custom verification
            min_verification_score=90,
            refinement_strategy="incremental",

            # Add code execution tools
            tools=[BashTool(), FileWriteTool()],
            enable_tool_use=True
        )

    def generate_and_verify(self, spec: str, language: str = "python") -> dict:
        """Generate code from spec and verify it works."""
        task = f"Generate {language} code:\n{spec}\n\nVerify it compiles and passes basic tests"
        result = self.run(task=task)

        # Check verification
        if result["verification"]["passed"]:
            print(f"✓ Code verified (score: {result['verification']['score']})")
            print(f"  Iterations: {len(result['refinements'])}")
        else:
            print(f"✗ Verification failed after {len(result['refinements'])} iterations")
            print(f"  Issues: {result['verification']['issues']}")

        return result

# Usage
agent = CodeGenerationAgent()
result = agent.generate_and_verify(
    spec="Function to parse CSV file and return list of dicts",
    language="python"
)
```

### Pattern 3: Multi-Agent Planning Pipeline

```python
from kaizen.agents.specialized.planning import PlanningAgent
from kaizen.agents.specialized.pev import PEVAgent
from kaizen.orchestration.pipeline import Pipeline

# Agent 1: Planning (create plan)
planner = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    agent_id="planner",
    max_plan_steps=10
)

# Agent 2: Execution (execute with refinement)
executor = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    agent_id="executor",
    max_iterations=5
)

# Create sequential pipeline
pipeline = Pipeline.sequential([planner, executor])

# Execute pipeline
result = pipeline.run(task="Design and implement a REST API for user management")

# Result contains outputs from both agents
print(f"Plan: {result['planner']['plan']}")
print(f"Execution: {result['executor']['final_result']}")
print(f"Refinements: {len(result['executor']['refinements'])}")
```

### Pattern 4: Checkpoint & Resume for Long Tasks

```python
from kaizen.agents.specialized.planning import PlanningAgent
from kaizen.core.autonomy.state import StateManager, FilesystemStorage

# Setup state manager
storage = FilesystemStorage(base_dir="./checkpoints")
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=1,  # Checkpoint after each step
    retention_count=100
)

# Create agent with checkpointing
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    agent_id="research_agent",
    max_plan_steps=20,  # Long task

    # Enable checkpointing
    state_manager=state_manager,
    enable_checkpoints=True
)

# Start long task
try:
    result = agent.run(task="Comprehensive analysis of global climate data")
except InterruptedError as e:
    print(f"Task interrupted: {e.reason.message}")
    checkpoint_id = e.reason.metadata["checkpoint_id"]

    # Resume from checkpoint
    print(f"Resuming from checkpoint: {checkpoint_id}")
    resumed_state = await state_manager.load_checkpoint(checkpoint_id)

    # Continue execution
    result = agent.resume_from_state(resumed_state)
```

---

## Testing Planning Agents

### Unit Testing: Plan Generation

```python
import pytest
from kaizen.agents.specialized.planning import PlanningAgent

class TestPlanningAgent:
    """Unit tests for PlanningAgent."""

    @pytest.mark.asyncio
    async def test_plan_generation(self):
        """Test agent generates valid plan."""
        agent = PlanningAgent(
            llm_provider="openai",
            model="gpt-4-turbo",
            max_plan_steps=5
        )

        result = agent.run(task="Analyze sales data and create report")

        # Verify plan structure
        assert "plan" in result
        assert isinstance(result["plan"], list)
        assert len(result["plan"]) > 0

        # Verify each step has required fields
        for step in result["plan"]:
            assert "step" in step
            assert "action" in step
            assert "description" in step

    @pytest.mark.asyncio
    async def test_plan_validation(self):
        """Test plan validation catches invalid plans."""
        agent = PlanningAgent(
            llm_provider="openai",
            model="gpt-4-turbo",
            validation_mode="strict",
            max_plan_steps=5,
            min_plan_steps=2
        )

        result = agent.run(task="Simple task")

        # Verify validation result
        assert "validation_result" in result
        validation = result["validation_result"]
        assert "valid" in validation
        assert isinstance(validation["valid"], bool)

        if not validation["valid"]:
            assert "errors" in validation
            assert len(validation["errors"]) > 0
```

### Integration Testing: Full Execution

```python
import pytest
from kaizen.agents.specialized.planning import PlanningAgent
from kaizen.tools.builtin import WebSearchTool

@pytest.mark.integration
@pytest.mark.asyncio
async def test_planning_agent_with_tools():
    """Integration test: PlanningAgent with real tool execution."""
    agent = PlanningAgent(
        llm_provider="openai",
        model="gpt-4",
        tools=[WebSearchTool()],
        enable_tool_use=True,
        max_plan_steps=5
    )

    result = agent.run(task="Search for Python best practices and summarize")

    # Verify plan created
    assert len(result["plan"]) > 0

    # Verify execution completed
    assert "execution_results" in result
    assert len(result["execution_results"]) == len(result["plan"])

    # Verify at least one step used web search
    tools_used = [
        r.get("tools_used", [])
        for r in result["execution_results"]
    ]
    assert any("web_search" in tools for tools in tools_used)

    # Verify final result
    assert "final_result" in result
    assert len(result["final_result"]) > 0
```

### E2E Testing: PEVAgent Refinement

```python
import pytest
from kaizen.agents.specialized.pev import PEVAgent

@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_pev_agent_refinement_loop():
    """E2E test: PEVAgent iterative refinement with real LLM."""
    agent = PEVAgent(
        llm_provider="openai",
        model="gpt-4",
        max_iterations=5,
        verification_strictness="medium",
        enable_error_recovery=True
    )

    result = agent.run(
        task="Write a function to calculate prime numbers up to N and verify it works correctly"
    )

    # Verify verification occurred
    assert "verification" in result
    verification = result["verification"]
    assert "passed" in verification
    assert "score" in verification

    # Verify refinements tracked
    assert "refinements" in result
    assert isinstance(result["refinements"], list)

    # If verification passed, should have final result
    if verification["passed"]:
        assert "final_result" in result
        assert len(result["final_result"]) > 0
        print(f"Completed in {len(result['refinements'])} iterations")
        print(f"Final score: {verification['score']}")
```

---

## Troubleshooting

### Issue: Plan Validation Always Fails

**Symptoms:**
```python
result["validation_result"]["valid"] == False
# Errors: ["Plan has only 1 step, minimum is 2"]
```

**Cause**: Task is too simple or LLM generated insufficient steps

**Solution**:
```python
# Option 1: Reduce min_plan_steps
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    min_plan_steps=1  # Allow single-step plans
)

# Option 2: Provide more complex task
result = agent.run(
    task="Research topic X, analyze findings, and write comprehensive report with citations"
)

# Option 3: Use validation_mode="warn" (not recommended for production)
agent = PlanningAgent(validation_mode="warn")
```

---

### Issue: PEVAgent Never Passes Verification

**Symptoms:**
```python
# After max_iterations, verification still fails
result["verification"]["passed"] == False
result["refinements"]  # Has max_iterations entries
```

**Cause**: Verification criteria too strict or task too complex

**Solution**:
```python
# Option 1: Reduce strictness
agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    verification_strictness="lenient",  # Lower threshold
    min_verification_score=70            # Reduce minimum score
)

# Option 2: Increase max iterations
agent = PEVAgent(max_iterations=20)

# Option 3: Simplify task
result = agent.run(
    task="Write simple function (not full application)"
)

# Option 4: Check verification feedback
for refinement in result["refinements"]:
    print(f"Iteration {refinement['iteration']}: score {refinement['verification_score']}")
    # Look for patterns in why verification fails
```

---

### Issue: Steps Take Too Long to Execute

**Symptoms:**
```python
# Steps exceed step_timeout
result["execution_results"][2]["status"] == "timeout"
```

**Cause**: Step timeout too short for LLM inference + tool execution

**Solution**:
```python
# Increase step timeout
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    step_timeout=60.0  # Allow 60s per step (default: 30s)
)

# Or disable timeout for very long steps
agent = PlanningAgent(step_timeout=None)
```

---

### Issue: Plans Are Too Generic

**Symptoms:**
```python
# Plan has vague steps like:
# Step 1: Think about the problem
# Step 2: Consider various approaches
```

**Cause**: Temperature too high or prompt needs more specificity

**Solution**:
```python
# Lower temperature for focused planning
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.1  # Very low for deterministic planning
)

# Provide more specific task description
result = agent.run(
    task="""
    Analyze Q4 sales data using these steps:
    1. Load data from CSV file
    2. Calculate metrics (revenue, growth rate, top products)
    3. Generate visualizations (time series, product breakdown)
    4. Write executive summary with recommendations
    """
)
```

---

### Issue: Refinement Loops Don't Improve Quality

**Symptoms:**
```python
# Refinement scores stay flat or decrease
# [85, 85, 84, 85, 83]
```

**Cause**: Refinements not targeting actual issues

**Solution**:
```python
# Enable detailed verification feedback
agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    include_verification_details=True  # Provide specific feedback
)

# Use custom verification signature with detailed issues
class DetailedVerificationSignature(Signature):
    code: str = InputField(description="Code to verify")

    passed: bool = OutputField(description="Passed verification")
    score: int = OutputField(description="Quality score 0-100")
    issues: list = OutputField(description="Specific issues with line numbers")
    suggestions: list = OutputField(description="Actionable improvement suggestions")

agent = PEVAgent(
    llm_provider="openai",
    model="gpt-4",
    verification_signature=DetailedVerificationSignature()
)
```

---

## Related Documentation

- **[Planning Agents API Reference](../reference/planning-agents-api.md)** - Complete API documentation
- **[BaseAgent Architecture](baseagent-architecture.md)** - Understanding agent foundations
- **[Coordination API](../reference/coordination-api.md)** - Multi-agent pipelines with planning
- **[Checkpoint API](../reference/checkpoint-api.md)** - State persistence for long-running plans
- **[Interrupts API](../reference/interrupts-api.md)** - Graceful shutdown during execution

---

**Complete User Guide for Kaizen Planning System (PlanningAgent & PEVAgent)**
