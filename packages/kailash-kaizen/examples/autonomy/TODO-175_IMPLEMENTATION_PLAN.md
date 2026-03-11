# TODO-175: Example Gallery Implementation Plan

**Status**: Phase 1 Complete (Tool Calling), Phase 2-7 In Progress
**Last Updated**: 2025-11-03

---

## ✅ Completed (Phase 1)

### Tool Calling Examples (3/3 COMPLETE)

1. **Code Review Agent** ✅
   - File: `tool-calling/code-review-agent/code_review_agent.py` (200 lines)
   - README: Complete with architecture diagram
   - Features: File tools, permission policies, progress reporting
   - Status: Production-ready

2. **Data Analysis Agent** ✅
   - File: `tool-calling/data-analysis-agent/data_analysis_agent.py` (250 lines)
   - README: Complete with use cases
   - Features: HTTP tools, statistical analysis, checkpoints
   - Status: Production-ready

3. **DevOps Agent** ✅
   - File: `tool-calling/devops-agent/devops_agent.py` (300 lines)
   - README: Complete with danger levels
   - Features: Bash tools, danger-level approval, audit trail
   - Status: Production-ready

---

## 🔄 Phase 2: Planning Examples (0/3)

### 2.1 Research Assistant (PlanningAgent)
**File**: `planning/research-assistant/research_assistant.py`

**Core Pattern**:
```python
from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig

agent = PlanningAgent(PlanningConfig(
    max_plan_steps=5,
    validation_mode="strict",
    enable_replanning=True
))

result = agent.run(
    task="Research quantum computing applications",
    context={"sources": 5, "depth": "comprehensive"}
)
```

**Features**:
- Multi-step research plan generation
- Plan validation before execution
- Web search with custom tools
- Memory persistence (hot/warm tiers)
- Interrupt handling for long tasks

**Expected Output**:
```
RESEARCH PLAN:
1. Search academic papers on quantum computing
2. Analyze top 10 papers for applications
3. Identify key use cases
4. Generate summary report
5. Create recommendations

VALIDATION: ✅ All steps feasible
EXECUTION: [Progress bar 1/5, 2/5, ...]
REPORT: 2000-word comprehensive analysis
```

**README Structure** (150 lines):
- Overview
- Prerequisites
- Usage example
- Architecture diagram
- Expected output
- Troubleshooting

---

### 2.2 Content Creator (PEVAgent)
**File**: `planning/content-creator/content_creator.py`

**Core Pattern**:
```python
from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig

agent = PEVAgent(PEVAgentConfig(
    max_iterations=5,
    verification_strictness="medium",
    enable_error_recovery=True
))

result = agent.run(
    task="Create blog post on AI ethics",
    context={"length": "1000 words", "tone": "professional"}
)
```

**Features**:
- Plan → Execute → Verify → Refine loop
- Quality verification (grammar, style, facts)
- Iterative refinement (max 5 iterations)
- Final output export (Markdown, HTML, PDF)

**Iterative Refinement Flow**:
```
ITERATION 1: Draft → Verify (score: 0.6) → Refine
ITERATION 2: Draft → Verify (score: 0.75) → Refine
ITERATION 3: Draft → Verify (score: 0.92) → ✅ Complete
```

---

### 2.3 Problem Solver (Tree-of-Thoughts Agent)
**File**: `planning/problem-solver/problem_solver.py`

**Core Pattern**:
```python
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig

agent = ToTAgent(ToTAgentConfig(
    num_paths=5,
    temperature=0.9,  # HIGH for diversity
    evaluation_criteria="quality",
    parallel_execution=True
))

result = agent.run(
    task="Optimize database query performance"
)
```

**Features**:
- Multi-path exploration (5 alternatives)
- Path evaluation and selection
- Best solution execution
- Decision rationale logging

**Multi-Path Output**:
```
PATH 1: Index optimization (score: 0.85)
PATH 2: Query rewrite (score: 0.92) ← SELECTED
PATH 3: Caching layer (score: 0.78)
PATH 4: Database sharding (score: 0.65)
PATH 5: Hardware upgrade (score: 0.55)

EXECUTING: Path 2 (Query rewrite)
RESULT: 10x performance improvement
```

---

## 🔄 Phase 3: Meta-Controller Examples (0/2)

### 3.1 Multi-Specialist Coding
**File**: `meta-controller/multi-specialist-coding/multi_specialist_coding.py`

**Core Pattern**:
```python
from kaizen.orchestration.pipeline import Pipeline

# 3 specialists
code_expert = CodeGenerationAgent(config)
test_expert = TestGenerationAgent(config)
docs_expert = DocumentationAgent(config)

# Semantic routing via A2A
router = Pipeline.router(
    agents=[code_expert, test_expert, docs_expert],
    routing_strategy="semantic"
)

result = router.run(task="Create REST API endpoint")
# Routes to code_expert
```

**Features**:
- A2A capability-based routing
- Task decomposition and delegation
- Results aggregation
- No hardcoded if/else logic

---

### 3.2 Complex Data Pipeline
**File**: `meta-controller/complex-data-pipeline/complex_data_pipeline.py`

**Core Pattern**:
```python
# Pipeline stages: extract, transform, load
blackboard = Pipeline.blackboard(
    specialists=[extractor, transformer, loader],
    controller=controller_agent,
    selection_mode="semantic",
    max_iterations=5
)

result = blackboard.run(task="Process 1M customer records")
```

**Features**:
- Multi-stage data processing
- Intelligent routing between stages
- Error recovery with retry logic
- Progress monitoring with hooks

---

## 🔄 Phase 4: Memory Examples (0/2)

### 4.1 Long-Running Research
**File**: `memory/long-running-research/long_running_research.py`

**Core Pattern**:
```python
from kaizen.memory import PersistentBufferMemory
from dataflow import DataFlow

db = DataFlow(database_type="sqlite")

memory = PersistentBufferMemory(
    db=db,
    agent_id="research_agent",
    buffer_size=100,  # Hot tier
    auto_persist_interval=10,  # Warm tier
    enable_compression=True
)

# 30+ hour research session
for i in range(1000):
    finding = agent.research(query=queries[i])
    memory.add_message(role="finding", content=finding)
    # Auto-persists every 10 messages
```

**Features**:
- Hot tier: Recent findings (< 1ms access)
- Warm tier: Session history (< 10ms access)
- Cold tier: Full archive (< 100ms access)
- Automatic tier promotion/demotion
- DataFlow backend integration

---

### 4.2 Customer Support Agent
**File**: `memory/customer-support/customer_support_agent.py`

**Core Pattern**:
```python
class SupportAgent(SimpleQAAgent):
    def __init__(self, config, db):
        super().__init__(config)
        self.memory = PersistentBufferMemory(
            db=db, agent_id=self.agent_id, buffer_size=50
        )
        self.memory.load_from_db()  # Load history

    def respond(self, message: str):
        self.memory.add_message(role="user", content=message)
        history = self.memory.get_history(limit=10)
        response = self.run(question=message, context=history)
        self.memory.add_message(role="assistant", content=response["answer"])
        return response

# Conversation persists across sessions
agent = SupportAgent(config, db)
agent.respond("What's my previous ticket?")  # Remembers!
```

**Features**:
- Conversation persistence across sessions
- PersistentBufferMemory with DataFlow
- Auto-persist every 10 messages
- JSONL compression (60% reduction)
- User preference learning

---

## 🔄 Phase 5: Checkpoint Examples (0/2)

### 5.1 Resume Interrupted Research
**File**: `checkpoints/resume-interrupted-research/resume_interrupted_research.py`

**Core Pattern**:
```python
config = AutonomousConfig(
    checkpoint_frequency=10,  # Every 10 steps
    resume_from_checkpoint=True
)

agent = BaseAutonomousAgent(config, signature, state_manager)

# Run 1: Interrupted at step 47
try:
    result = await agent.run_autonomous(task="Analyze 100 papers")
except KeyboardInterrupt:
    print("Checkpoint saved at step 47")

# Run 2: Resume from checkpoint
agent2 = BaseAutonomousAgent(config, signature, state_manager)
result = await agent2.run_autonomous(task="Analyze 100 papers")
# Resumes from step 47, completes 48-100
```

**Features**:
- Automatic checkpoint every N steps
- Graceful interrupt handling (Ctrl+C)
- Resume from latest checkpoint
- State preservation (history, budget, progress)

---

### 5.2 Multi-Day Project
**File**: `checkpoints/multi-day-project/multi_day_project.py`

**Core Pattern**:
```python
storage = FilesystemStorage(base_dir="./checkpoints", compress=True)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,
    retention_count=20  # Keep last 20 checkpoints
)

# Day 1: Work on project
agent.run_project(day=1)  # Checkpoint created

# Day 2: Continue
agent.run_project(day=2)  # Resumes from day 1

# Fork for experimentation
forked_state = state_manager.fork_from_checkpoint(checkpoint_id)
agent_experimental.restore_state(forked_state)
```

**Features**:
- Checkpoint compression (50%+ reduction)
- Retention policy (keep last N checkpoints)
- Fork checkpoint for experimentation
- Daily progress snapshots

---

## 🔄 Phase 6: Enhance Interrupt Examples (0/2)

### 6.1 Enhance ctrl_c_interrupt.py
**Enhancements**:
- Comprehensive error handling (try/except/finally)
- Progress reporting before exit
- Checkpoint preservation with metadata
- Graceful cleanup (close connections, save state)
- Production logging (structured JSON)

**Add to existing file**:
```python
# Production error handling
try:
    result = await agent.run_autonomous(task)
except KeyboardInterrupt:
    print("⚠️  Ctrl+C detected - saving checkpoint...")
    await agent.state_manager.save_state(agent.get_current_state())
    print("✅ Checkpoint saved - safe to exit")
except Exception as e:
    print(f"❌ Error: {e}")
    await agent.state_manager.save_state(agent.get_current_state())
finally:
    await agent.cleanup()  # Close connections
```

---

### 6.2 Enhance budget_interrupt.py
**Enhancements**:
- Real-time budget monitoring (progress bar)
- Prometheus metrics integration
- Alert on 80% budget threshold
- Cost breakdown logging (per tool, per cycle)
- Budget forecasting

**Add to existing file**:
```python
# Real-time monitoring
from prometheus_client import Gauge, Counter

budget_gauge = Gauge("agent_budget_used", "Budget used in USD")
budget_counter = Counter("agent_tool_cost", "Cost per tool call", ["tool_name"])

# Update metrics after each tool call
budget_gauge.set(agent.exec_context.budget_used)
budget_counter.labels(tool_name="read_file").inc(0.001)

# Alert at 80% threshold
if agent.exec_context.budget_used / agent.exec_context.budget_limit > 0.8:
    print("⚠️  WARNING: 80% budget threshold reached!")
```

---

## 🔄 Phase 7: Full Integration Example (0/1)

### 7.1 Autonomous Research Agent
**File**: `full-integration/autonomous-research-agent/autonomous_research_agent.py`

**All 6 Autonomy Subsystems**:
```python
from kaizen.agents.autonomous.base import BaseAutonomousAgent
from kaizen.core.autonomy.hooks.builtin import MetricsHook, TracingHook
from kaizen.memory import PersistentBufferMemory
from kaizen.core.autonomy.state import StateManager
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler

class AutonomousResearchAgent(BaseAutonomousAgent):
    def __init__(self, config, db):
        super().__init__(config, signature)

        # 1. Hooks - Monitoring
        self._hook_manager.register_hook(MetricsHook())
        self._hook_manager.register_hook(TracingHook())

        # 2. Memory - 3-tier storage
        self.memory = PersistentBufferMemory(db, agent_id, buffer_size=100)

        # 3. Checkpoints - State persistence
        self.state_manager = StateManager(storage, checkpoint_frequency=15)

        # 4. Interrupts - Graceful shutdown
        timeout_handler = TimeoutInterruptHandler(timeout_seconds=3600)
        self.interrupt_manager.add_handler(timeout_handler)

        # 5. Tools - Web search, file operations
        # MCP auto-connect provides 12 builtin tools

        # 6. Meta-controller - Route to specialists
        self.specialists = [code_expert, data_expert, writing_expert]
```

**Complete Workflow**:
- Tool calling: Web search, file operations (12 builtin tools)
- Planning: Multi-step research plan
- Memory: 3-tier storage for findings
- Checkpoints: Auto-save every 15 minutes
- Interrupts: Graceful shutdown on Ctrl+C or timeout
- Meta-controller: Route to specialist sub-agents
- Hooks: Distributed tracing + Prometheus metrics
- Control Protocol: Progress updates to CLI

**Expected Output** (shows all 6 subsystems working together):
```
🤖 AUTONOMOUS RESEARCH AGENT
============================================================
🔧 Subsystems:
  ✅ Tool Calling (12 builtin tools)
  ✅ Planning (5-step research plan)
  ✅ Memory (3-tier: hot/warm/cold)
  ✅ Checkpoints (every 15 min)
  ✅ Interrupts (Ctrl+C, timeout)
  ✅ Meta-Controller (3 specialists)
  ✅ Hooks (metrics, tracing)
  ✅ Control Protocol (progress updates)

📊 Research Progress:
  [Step 1/5] Web search: quantum computing ✅
  [Step 2/5] Analyzing 10 papers... ✅
  [Checkpoint] Saved at 15:00 ✅
  [Step 3/5] Routing to data_expert... ✅
  [Ctrl+C] Graceful shutdown initiated ⚠️
  [Checkpoint] Final state saved ✅

📈 Results:
  - Papers analyzed: 47
  - Insights generated: 12
  - Checkpoints: 3
  - Budget used: $2.45
  - Duration: 42 minutes
```

---

## 📝 Phase 8: Example Gallery Documentation

### File: `docs/examples/EXAMPLE_GALLERY.md` (300+ lines)

**Structure**:

```markdown
# Kaizen Example Gallery

## Overview
[Introduction to gallery organization]

## Learning Paths

### Beginner (30 minutes)
1. Tool Calling Basics (code-review-agent)
2. Planning Agent (research-assistant)
3. Memory System (customer-support)

### Intermediate (2 hours)
1. Meta-Controller Routing (multi-specialist-coding)
2. Checkpoint Resume (resume-interrupted-research)
3. Interrupt Handling (enhanced ctrl_c)

### Advanced (4 hours)
1. Full Integration (autonomous-research-agent)
2. Complex Data Pipeline (meta-controller)
3. Multi-Day Project (checkpoints)

## Example Categories

### 1. Tool Calling (3 examples)
- Code Review Agent - File tools
- Data Analysis Agent - HTTP tools
- DevOps Agent - Bash tools

### 2. Planning (3 examples)
- Research Assistant - PlanningAgent
- Content Creator - PEVAgent
- Problem Solver - Tree-of-Thoughts

### 3. Meta-Controller (2 examples)
- Multi-Specialist Coding - Semantic routing
- Complex Data Pipeline - Blackboard pattern

### 4. Memory (2 examples)
- Long-Running Research - 3-tier storage
- Customer Support - Persistent conversations

### 5. Checkpoints (2 examples)
- Resume Interrupted Research - Auto-resume
- Multi-Day Project - Compression, forking

### 6. Interrupts (2 examples)
- Enhanced Ctrl+C - Production patterns
- Enhanced Budget - Real-time monitoring

### 7. Full Integration (1 example)
- Autonomous Research Agent - All 6 subsystems

## Quick Start Guide

### Your First Autonomous Agent (< 30 minutes)

[Step-by-step tutorial using Code Review Agent]

## Production Patterns

### 1. Error Handling
[Examples from all agents]

### 2. Monitoring
[Hooks, metrics, tracing]

### 3. Security
[Permission policies, audit trails]

### 4. Scaling
[Multi-agent coordination]

## Cross-References

[Links to main documentation]
```

---

## 🧪 Phase 9: CI Integration

### File: `.github/workflows/example-validation.yml`

```yaml
name: Example Validation

on: [push, pull_request]

jobs:
  validate-examples:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.8", "3.9", "3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install Ollama
        run: |
          curl -fsSL https://ollama.ai/install.sh | sh
          ollama serve &
          sleep 5
          ollama pull llama3.1:8b-instruct-q8_0

      - name: Install dependencies
        run: |
          pip install kailash-kaizen pytest

      - name: Validate Tool Calling Examples
        run: |
          pytest tests/examples/test_tool_calling_examples.py -v

      - name: Validate Planning Examples
        run: |
          pytest tests/examples/test_planning_examples.py -v

      - name: Validate Meta-Controller Examples
        run: |
          pytest tests/examples/test_meta_controller_examples.py -v

      - name: Validate Memory Examples
        run: |
          pytest tests/examples/test_memory_examples.py -v

      - name: Validate Checkpoint Examples
        run: |
          pytest tests/examples/test_checkpoint_examples.py -v

      - name: Validate Interrupt Examples
        run: |
          pytest tests/examples/test_interrupt_examples.py -v

      - name: Validate Full Integration Example
        run: |
          pytest tests/examples/test_full_integration_example.py -v
```

---

## 🧪 Phase 10: Validation Tests

### Files: `tests/examples/test_*_examples.py`

Each test file validates that examples:
1. Import successfully
2. Execute without errors
3. Produce expected output structure
4. Use Ollama (FREE - no API costs)

**Example Test Structure**:
```python
import pytest
import subprocess
import sys

@pytest.mark.asyncio
async def test_code_review_agent():
    """Validate code review agent runs successfully."""
    # Run example
    result = subprocess.run(
        [sys.executable, "examples/autonomy/tool-calling/code-review-agent/code_review_agent.py", "."],
        capture_output=True,
        text=True,
        timeout=60
    )

    # Validate output
    assert result.returncode == 0
    assert "CODE REVIEW REPORT" in result.stdout
    assert "Issues Found:" in result.stdout
    assert "$0.00" in result.stdout  # FREE with Ollama
```

---

## 📊 Progress Summary

| Phase | Status | Examples | READMEs | Tests |
|-------|--------|----------|---------|-------|
| 1. Tool Calling | ✅ COMPLETE | 3/3 | 3/3 | 0/3 |
| 2. Planning | 🔄 PENDING | 0/3 | 0/3 | 0/3 |
| 3. Meta-Controller | 🔄 PENDING | 0/2 | 0/2 | 0/2 |
| 4. Memory | 🔄 PENDING | 0/2 | 0/2 | 0/2 |
| 5. Checkpoints | 🔄 PENDING | 0/2 | 0/2 | 0/2 |
| 6. Interrupts (Enhance) | 🔄 PENDING | 0/2 | 0/2 | 0/2 |
| 7. Full Integration | 🔄 PENDING | 0/1 | 0/1 | 0/1 |
| 8. Gallery Docs | 🔄 PENDING | - | 1/1 | - |
| 9. CI Integration | 🔄 PENDING | - | - | 1/1 |
| **TOTAL** | **7% COMPLETE** | **3/15** | **4/16** | **0/15** |

---

## 🎯 Next Steps

1. **Continue Phase 2**: Create Planning examples (3 examples)
2. **Create READMEs**: Short, focused READMEs (100-150 lines)
3. **Create Validation Tests**: One test per example
4. **Manual Smoke Testing**: Run each example once
5. **Create Gallery Documentation**: Comprehensive guide (300+ lines)
6. **Set up CI**: GitHub Actions workflow

**Estimated Time Remaining**: 4-6 hours

---

## 📝 Implementation Notes

### Code Quality Requirements
- ✅ Comprehensive error handling
- ✅ Type hints for all functions
- ✅ Docstrings for classes/methods
- ✅ Black formatter compliance
- ✅ Production-ready patterns

### README Requirements
- Overview (2-3 sentences)
- Prerequisites
- Installation
- Usage
- Architecture diagram (ASCII)
- Expected output
- Troubleshooting (3-5 common issues)
- Production notes
- Related examples

### Test Requirements
- Import validation
- Execution validation (no errors)
- Output structure validation
- Use Ollama (FREE - no API costs)
- Timeout protection (60s max)

---

**End of Implementation Plan**
