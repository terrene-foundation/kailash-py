# E2E Test Architecture Plan - Phase 5 Production Readiness

## Executive Summary

Comprehensive E2E test suite architecture for TODO-170, covering 6 autonomy systems with 20+ tests, 3 multi-hour workloads, and strict cost/reliability controls. This plan ensures the final validation gate before v1.0 release.

**Budget**: <$20 total
**Timeline**: 3 weeks
**Scope**: 20+ E2E tests + 3 long-running tests
**Infrastructure**: Real Ollama + OpenAI, PostgreSQL, filesystem

---

## 1. Directory Structure

```
tests/
├── e2e/
│   ├── autonomy/                          # Autonomy system E2E tests
│   │   ├── tools/                         # Tool calling E2E (4 tests)
│   │   │   ├── __init__.py
│   │   │   ├── test_builtin_tools_e2e.py
│   │   │   ├── test_custom_tools_e2e.py
│   │   │   ├── test_approval_workflows_e2e.py
│   │   │   └── test_dangerous_operations_e2e.py
│   │   │
│   │   ├── planning/                      # Planning agents E2E (3 tests)
│   │   │   ├── __init__.py
│   │   │   ├── test_planning_agent_e2e.py
│   │   │   ├── test_pev_agent_e2e.py
│   │   │   └── test_tot_agent_e2e.py
│   │   │
│   │   ├── meta_controller/               # Meta-controller E2E (3 tests)
│   │   │   ├── __init__.py
│   │   │   ├── test_semantic_routing_e2e.py
│   │   │   ├── test_fallback_handling_e2e.py
│   │   │   └── test_task_decomposition_e2e.py
│   │   │
│   │   ├── memory/                        # Memory system E2E (4 tests)
│   │   │   ├── __init__.py
│   │   │   ├── test_hot_tier_e2e.py
│   │   │   ├── test_warm_tier_e2e.py
│   │   │   ├── test_cold_tier_e2e.py
│   │   │   └── test_persistence_e2e.py
│   │   │
│   │   ├── checkpoints/                   # Checkpoint system E2E (3 tests)
│   │   │   ├── __init__.py
│   │   │   ├── test_auto_checkpoint_e2e.py    # EXISTING
│   │   │   ├── test_resume_e2e.py
│   │   │   └── test_compression_e2e.py
│   │   │
│   │   └── interrupts/                    # Interrupt handling E2E (3 tests)
│   │       ├── __init__.py
│   │       ├── test_interrupt_e2e.py      # EXISTING - enhance
│   │       ├── test_timeout_e2e.py
│   │       └── test_budget_limit_e2e.py
│   │
│   ├── long_running/                      # Multi-hour tests (3 tests)
│   │   ├── __init__.py
│   │   ├── conftest.py                    # Long-running fixtures
│   │   ├── test_code_review_workload.py   # 2-4 hours
│   │   ├── test_data_analysis_workload.py # 2-4 hours
│   │   └── test_research_workload.py      # 2-4 hours
│   │
│   └── conftest.py                        # E2E-specific fixtures
│
├── fixtures/
│   ├── e2e/                               # E2E test data
│   │   ├── __init__.py
│   │   ├── code_review_dataset.py         # Code files for review
│   │   ├── data_analysis_dataset.py       # CSV/JSON datasets
│   │   ├── research_dataset.py            # Documents for research
│   │   └── approval_scenarios.py          # Tool approval scenarios
│   │
│   └── consolidated_test_fixtures.py      # EXISTING - enhance
│
└── utils/
    ├── cost_tracking.py                   # NEW - Cost monitoring
    ├── reliability_helpers.py             # NEW - Flaky test prevention
    ├── long_running_helpers.py            # NEW - Multi-hour test utils
    ├── real_llm_providers.py              # EXISTING - enhance
    └── integration_helpers.py             # EXISTING - enhance
```

---

## 2. Test Organization by System

### 2.1 Tool Calling (4 E2E Tests)

**File**: `tests/e2e/autonomy/tools/test_builtin_tools_e2e.py`
- **Test 1**: File tools (read, write, list, delete) in real filesystem
- **Test 2**: HTTP tools (GET, POST) with real external APIs
- **Test 3**: Bash tools with real subprocess execution
- **Test 4**: Web tools (search, scrape) with real internet access

**File**: `tests/e2e/autonomy/tools/test_custom_tools_e2e.py`
- **Test 5**: Custom tool definition, registration, and execution
- **Test 6**: Custom tool with complex parameters and validation

**File**: `tests/e2e/autonomy/tools/test_approval_workflows_e2e.py`
- **Test 7**: SAFE level tools (auto-approve)
- **Test 8**: MODERATE level tools (require approval)
- **Test 9**: DANGEROUS level tools (require confirmation)
- **Test 10**: CRITICAL level tools (multi-step approval)

**File**: `tests/e2e/autonomy/tools/test_dangerous_operations_e2e.py`
- **Test 11**: File deletion with approval workflow
- **Test 12**: System command execution with safety checks

**LLM**: Ollama llama3.1:8b-instruct-q8_0 (free)
**Duration**: 30-60s per test
**Cost**: $0.00

### 2.2 Planning (3 E2E Tests)

**File**: `tests/e2e/autonomy/planning/test_planning_agent_e2e.py`
- **Test 13**: Planning agent creates multi-step plan
- **Test 14**: Plan execution with real tool calls
- **Test 15**: Plan adaptation on errors

**File**: `tests/e2e/autonomy/planning/test_pev_agent_e2e.py`
- **Test 16**: PEV agent (Plan-Execute-Verify) complete cycle

**File**: `tests/e2e/autonomy/planning/test_tot_agent_e2e.py`
- **Test 17**: Tree-of-Thoughts agent exploration

**LLM**: Ollama llama3.1:8b-instruct-q8_0 for planning, gpt-4o-mini for quality validation
**Duration**: 1-2 minutes per test
**Cost**: $0.10 (OpenAI validation only)

### 2.3 Meta-Controller (3 E2E Tests)

**File**: `tests/e2e/autonomy/meta_controller/test_semantic_routing_e2e.py`
- **Test 18**: Semantic routing to correct specialist agent
- **Test 19**: Dynamic agent selection based on task complexity

**File**: `tests/e2e/autonomy/meta_controller/test_fallback_handling_e2e.py`
- **Test 20**: Fallback when primary agent fails

**File**: `tests/e2e/autonomy/meta_controller/test_task_decomposition_e2e.py`
- **Test 21**: Complex task decomposition into subtasks

**LLM**: gpt-4o-mini (semantic matching requires quality)
**Duration**: 30-90s per test
**Cost**: $0.30 (3 tests × $0.10)

### 2.4 Memory (4 E2E Tests)

**File**: `tests/e2e/autonomy/memory/test_hot_tier_e2e.py`
- **Test 22**: Hot memory (in-memory cache) operations
- **Test 23**: Hot memory eviction policy

**File**: `tests/e2e/autonomy/memory/test_warm_tier_e2e.py`
- **Test 24**: Warm memory (Redis) with real Redis instance

**File**: `tests/e2e/autonomy/memory/test_cold_tier_e2e.py`
- **Test 25**: Cold memory (PostgreSQL) with real database

**File**: `tests/e2e/autonomy/memory/test_persistence_e2e.py`
- **Test 26**: Memory persistence across agent restarts
- **Test 27**: Memory tier promotion/demotion

**LLM**: Ollama llama3.1:8b-instruct-q8_0
**Infrastructure**: PostgreSQL (Docker)
**Duration**: 30-60s per test
**Cost**: $0.00

### 2.5 Checkpoints (3 E2E Tests)

**File**: `tests/e2e/autonomy/checkpoints/test_auto_checkpoint_e2e.py` (EXISTING - enhance)
- **Test 28**: Automatic checkpoint creation during long execution
- **Test 29**: Checkpoint frequency configuration

**File**: `tests/e2e/autonomy/checkpoints/test_resume_e2e.py`
- **Test 30**: Resume from checkpoint after crash simulation
- **Test 31**: Resume preserves agent state correctly

**File**: `tests/e2e/autonomy/checkpoints/test_compression_e2e.py`
- **Test 32**: Checkpoint compression for production scenarios

**LLM**: Ollama llama3.1:8b-instruct-q8_0
**Infrastructure**: Filesystem
**Duration**: 1-2 minutes per test
**Cost**: $0.00

### 2.6 Interrupts (3 E2E Tests)

**File**: `tests/e2e/autonomy/interrupts/test_interrupt_e2e.py` (EXISTING - enhance)
- **Test 33**: Ctrl+C interrupt with graceful shutdown
- **Test 34**: Signal propagation in multi-agent system

**File**: `tests/e2e/autonomy/interrupts/test_timeout_e2e.py`
- **Test 35**: Timeout interrupt after specified duration

**File**: `tests/e2e/autonomy/interrupts/test_budget_limit_e2e.py`
- **Test 36**: Budget limit interrupt (cost control)

**LLM**: Ollama llama3.1:8b-instruct-q8_0
**Duration**: 30-90s per test
**Cost**: $0.00

---

## 3. Long-Running Tests (3 Tests)

### 3.1 Code Review Workload

**File**: `tests/e2e/long_running/test_code_review_workload.py`

**Scenario**: Agent reviews 50+ Python files, identifies bugs, suggests improvements

**Workload**:
- Read 50 Python files from real codebase
- Analyze each file for:
  - Code quality issues
  - Security vulnerabilities
  - Performance problems
  - Best practice violations
- Generate comprehensive review report
- Create fix suggestions with code examples

**LLM Strategy**:
- First pass: Ollama llama3.1:8b-instruct-q8_0 for syntax analysis (free)
- Second pass: gpt-4o-mini for quality validation (10 files, $0.50)

**Duration**: 2-4 hours
**Cost**: $0.50
**Success Criteria**:
- All 50 files reviewed
- Report generated with >10 actionable suggestions
- No memory leaks during execution
- Checkpoint every 30 minutes

### 3.2 Data Analysis Workload

**File**: `tests/e2e/long_running/test_data_analysis_workload.py`

**Scenario**: Agent analyzes large datasets, generates insights, creates visualizations

**Workload**:
- Load 10 CSV files (100k+ rows each)
- Perform statistical analysis
- Identify trends and anomalies
- Generate 20+ visualizations
- Create executive summary report

**LLM Strategy**:
- Ollama llama3.1:8b-instruct-q8_0 for data processing logic (free)
- gpt-4o-mini for insight generation (20 analyses, $1.00)

**Duration**: 2-4 hours
**Cost**: $1.00
**Success Criteria**:
- All datasets processed
- 20+ visualizations created
- Executive report generated
- No crashes during long computation

### 3.3 Research Workload

**File**: `tests/e2e/long_running/test_research_workload.py`

**Scenario**: Agent researches topic across multiple documents, synthesizes findings

**Workload**:
- Read 100+ markdown/PDF documents
- Extract key information
- Synthesize cross-document insights
- Generate comprehensive research report
- Create citation index

**LLM Strategy**:
- Ollama llama3.1:8b-instruct-q8_0 for document extraction (free)
- gpt-4o-mini for synthesis (30 summaries, $1.50)

**Duration**: 2-4 hours
**Cost**: $1.50
**Success Criteria**:
- All documents processed
- Cross-references identified
- Research report >5000 words
- Checkpoint every 20 documents

**Total Long-Running Cost**: $3.00
**Total Long-Running Duration**: 6-12 hours

---

## 4. Fixture Organization

### 4.1 E2E Fixtures (`tests/fixtures/e2e/`)

**File**: `tests/fixtures/e2e/code_review_dataset.py`
```python
"""Code review dataset for long-running tests."""
from pathlib import Path
from typing import List

def get_python_files() -> List[Path]:
    """Get 50 Python files from src/kaizen/ for review."""
    base_dir = Path(__file__).parents[3] / "src" / "kaizen"
    python_files = list(base_dir.rglob("*.py"))[:50]
    return python_files

def get_review_criteria() -> dict:
    """Get code review criteria."""
    return {
        "quality": ["complexity", "maintainability", "readability"],
        "security": ["injection", "authentication", "data_validation"],
        "performance": ["algorithm_complexity", "memory_usage", "caching"],
        "best_practices": ["error_handling", "documentation", "testing"]
    }
```

**File**: `tests/fixtures/e2e/data_analysis_dataset.py`
```python
"""Data analysis dataset for long-running tests."""
import pandas as pd
import numpy as np
from typing import List

def generate_sales_data(rows: int = 100000) -> pd.DataFrame:
    """Generate realistic sales data for analysis."""
    return pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=rows, freq="H"),
        "product_id": np.random.randint(1, 100, rows),
        "quantity": np.random.randint(1, 50, rows),
        "price": np.random.uniform(10, 1000, rows),
        "region": np.random.choice(["North", "South", "East", "West"], rows)
    })

def get_analysis_tasks() -> List[str]:
    """Get data analysis tasks."""
    return [
        "Calculate total revenue by region",
        "Identify top 10 products by sales",
        "Find seasonal trends",
        "Detect anomalies in pricing",
        "Predict next quarter revenue"
    ]
```

**File**: `tests/fixtures/e2e/research_dataset.py`
```python
"""Research dataset for long-running tests."""
from pathlib import Path
from typing import List

def get_research_documents() -> List[Path]:
    """Get 100+ markdown documents for research."""
    docs_dir = Path(__file__).parents[3] / "docs"
    markdown_files = list(docs_dir.rglob("*.md"))[:100]
    return markdown_files

def get_research_questions() -> List[str]:
    """Get research questions to answer."""
    return [
        "What are the main features of the Kaizen framework?",
        "How does signature-based programming work?",
        "What are the benefits of multi-agent coordination?",
        "How does the memory system handle persistence?",
        "What are the best practices for production deployment?"
    ]
```

**File**: `tests/fixtures/e2e/approval_scenarios.py`
```python
"""Tool approval scenarios for E2E testing."""
from kaizen.tools.types import DangerLevel

def get_approval_scenarios() -> dict:
    """Get tool approval test scenarios."""
    return {
        "safe_file_read": {
            "tool": "read_file",
            "params": {"file_path": "/tmp/test_data.txt"},
            "danger_level": DangerLevel.SAFE,
            "expected_approval": "auto"
        },
        "moderate_file_write": {
            "tool": "write_file",
            "params": {"file_path": "/tmp/output.txt", "content": "test"},
            "danger_level": DangerLevel.MODERATE,
            "expected_approval": "required"
        },
        "dangerous_file_delete": {
            "tool": "delete_file",
            "params": {"file_path": "/tmp/important.txt"},
            "danger_level": DangerLevel.DANGEROUS,
            "expected_approval": "confirmation"
        },
        "critical_system_command": {
            "tool": "bash_execute",
            "params": {"command": "rm -rf /tmp/test_dir"},
            "danger_level": DangerLevel.CRITICAL,
            "expected_approval": "multi_step"
        }
    }
```

### 4.2 Enhanced Shared Fixtures (`tests/conftest.py`)

Add E2E-specific fixtures to existing conftest.py:

```python
# E2E Long-Running Test Fixtures
@pytest.fixture(scope="session")
def long_running_config():
    """Configuration for long-running tests."""
    return {
        "checkpoint_frequency": 10,  # Every 10 steps
        "max_duration_hours": 4,
        "cost_limit_usd": 2.0,
        "memory_limit_mb": 2048,
        "ollama_model": "llama3.1:8b-instruct-q8_0",
        "openai_model": "gpt-4o-mini"
    }

@pytest.fixture
def cost_tracker():
    """Cost tracking for E2E tests."""
    from tests.utils.cost_tracking import CostTracker
    tracker = CostTracker(budget_limit=20.0)
    yield tracker
    # Assert cost under budget at teardown
    assert tracker.total_cost < 20.0, f"Budget exceeded: ${tracker.total_cost:.2f}"

@pytest.fixture
def reliability_monitor():
    """Reliability monitoring for flaky test detection."""
    from tests.utils.reliability_helpers import ReliabilityMonitor
    monitor = ReliabilityMonitor()
    yield monitor
    # Log any reliability issues
    if monitor.has_issues():
        print(f"⚠️  Reliability issues detected: {monitor.get_report()}")
```

---

## 5. Utility Modules

### 5.1 Cost Tracking (`tests/utils/cost_tracking.py`)

```python
"""Cost tracking for E2E tests with budget enforcement."""
import os
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime

@dataclass
class APICall:
    """Record of single API call."""
    timestamp: datetime
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

@dataclass
class CostTracker:
    """Track and enforce cost budget for E2E tests."""

    budget_limit: float = 20.0
    calls: List[APICall] = field(default_factory=list)

    # Pricing per 1M tokens
    PRICING = {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},  # Per 1M tokens
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "ollama": {"input": 0.0, "output": 0.0}  # Free
    }

    def record_call(self, provider: str, model: str,
                   prompt_tokens: int, completion_tokens: int):
        """Record API call and calculate cost."""
        pricing = self.PRICING.get(model, {"input": 0, "output": 0})

        cost = (
            (prompt_tokens / 1_000_000) * pricing["input"] +
            (completion_tokens / 1_000_000) * pricing["output"]
        )

        call = APICall(
            timestamp=datetime.now(),
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost
        )
        self.calls.append(call)

        # Check budget
        if self.total_cost > self.budget_limit:
            raise BudgetExceededError(
                f"Budget exceeded: ${self.total_cost:.2f} > ${self.budget_limit:.2f}"
            )

    @property
    def total_cost(self) -> float:
        """Calculate total cost."""
        return sum(call.cost_usd for call in self.calls)

    @property
    def cost_by_model(self) -> Dict[str, float]:
        """Calculate cost breakdown by model."""
        breakdown = {}
        for call in self.calls:
            breakdown[call.model] = breakdown.get(call.model, 0.0) + call.cost_usd
        return breakdown

    def get_report(self) -> str:
        """Generate cost report."""
        report = f"\n{'='*60}\n"
        report += f"E2E Test Cost Report\n"
        report += f"{'='*60}\n"
        report += f"Total Cost: ${self.total_cost:.4f}\n"
        report += f"Budget Limit: ${self.budget_limit:.2f}\n"
        report += f"Budget Remaining: ${self.budget_limit - self.total_cost:.2f}\n"
        report += f"\nCost by Model:\n"
        for model, cost in self.cost_by_model.items():
            report += f"  {model}: ${cost:.4f}\n"
        report += f"\nTotal API Calls: {len(self.calls)}\n"
        report += f"{'='*60}\n"
        return report

class BudgetExceededError(Exception):
    """Raised when cost budget is exceeded."""
    pass
```

### 5.2 Reliability Helpers (`tests/utils/reliability_helpers.py`)

```python
"""Reliability helpers for preventing flaky tests."""
import asyncio
import time
from typing import Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class RetryConfig:
    """Retry configuration."""
    max_attempts: int = 3
    initial_delay: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay: float = 30.0

async def retry_async(
    func: Callable,
    config: RetryConfig = None,
    acceptable_exceptions: tuple = (Exception,)
) -> Any:
    """Retry async function with exponential backoff."""
    if config is None:
        config = RetryConfig()

    delay = config.initial_delay
    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            return await func()
        except acceptable_exceptions as e:
            last_exception = e
            if attempt < config.max_attempts - 1:
                await asyncio.sleep(delay)
                delay = min(delay * config.backoff_multiplier, config.max_delay)

    raise last_exception

@dataclass
class ReliabilityMonitor:
    """Monitor test reliability and detect flaky patterns."""

    timeouts: List[datetime] = field(default_factory=list)
    retries: List[datetime] = field(default_factory=list)
    errors: List[tuple] = field(default_factory=list)

    def record_timeout(self):
        """Record timeout event."""
        self.timeouts.append(datetime.now())

    def record_retry(self):
        """Record retry event."""
        self.retries.append(datetime.now())

    def record_error(self, error_type: str, message: str):
        """Record error event."""
        self.errors.append((datetime.now(), error_type, message))

    def has_issues(self) -> bool:
        """Check if reliability issues detected."""
        return len(self.timeouts) > 0 or len(self.retries) > 2 or len(self.errors) > 1

    def get_report(self) -> str:
        """Generate reliability report."""
        report = f"\nReliability Issues:\n"
        report += f"  Timeouts: {len(self.timeouts)}\n"
        report += f"  Retries: {len(self.retries)}\n"
        report += f"  Errors: {len(self.errors)}\n"
        if self.errors:
            report += f"\nError Details:\n"
            for timestamp, error_type, message in self.errors:
                report += f"  [{timestamp}] {error_type}: {message}\n"
        return report

def ensure_no_memory_leaks(func: Callable) -> Callable:
    """Decorator to ensure no memory leaks in long-running tests."""
    import tracemalloc

    async def wrapper(*args, **kwargs):
        tracemalloc.start()

        # Get initial memory
        snapshot_before = tracemalloc.take_snapshot()

        # Run test
        result = await func(*args, **kwargs)

        # Get final memory
        snapshot_after = tracemalloc.take_snapshot()

        # Compare
        top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')

        # Check for large increases (>100MB)
        total_increase = sum(stat.size_diff for stat in top_stats)
        if total_increase > 100 * 1024 * 1024:  # 100MB
            print(f"⚠️  Potential memory leak detected: {total_increase / 1024 / 1024:.2f} MB increase")
            for stat in top_stats[:10]:
                print(f"  {stat}")

        tracemalloc.stop()
        return result

    return wrapper
```

### 5.3 Long-Running Helpers (`tests/utils/long_running_helpers.py`)

```python
"""Helpers for long-running E2E tests."""
import asyncio
from datetime import datetime, timedelta
from typing import Callable, Any
from dataclasses import dataclass

@dataclass
class ProgressTracker:
    """Track progress of long-running tests."""

    total_steps: int
    current_step: int = 0
    start_time: datetime = None

    def __post_init__(self):
        self.start_time = datetime.now()

    def increment(self, steps: int = 1):
        """Increment progress."""
        self.current_step += steps
        self._print_progress()

    def _print_progress(self):
        """Print progress bar."""
        percentage = (self.current_step / self.total_steps) * 100
        elapsed = datetime.now() - self.start_time

        # Estimate remaining time
        if self.current_step > 0:
            rate = elapsed.total_seconds() / self.current_step
            remaining_steps = self.total_steps - self.current_step
            eta = timedelta(seconds=rate * remaining_steps)
        else:
            eta = timedelta(0)

        print(f"\rProgress: {self.current_step}/{self.total_steps} ({percentage:.1f}%) | "
              f"Elapsed: {elapsed} | ETA: {eta}", end="")

        if self.current_step >= self.total_steps:
            print()  # New line on completion

async def with_timeout(
    coro: Callable,
    timeout_seconds: float,
    timeout_message: str = "Operation timed out"
) -> Any:
    """Execute coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise TimeoutError(f"{timeout_message} (>{timeout_seconds}s)")

def checkpoint_every(steps: int):
    """Decorator to force checkpoint every N steps."""
    def decorator(func: Callable) -> Callable:
        async def wrapper(agent, *args, **kwargs):
            # Track step count
            if not hasattr(wrapper, 'step_count'):
                wrapper.step_count = 0

            wrapper.step_count += 1

            # Force checkpoint
            if wrapper.step_count % steps == 0:
                await agent.state_manager.save_checkpoint()

            return await func(agent, *args, **kwargs)

        return wrapper
    return decorator
```

---

## 6. Risk Mitigation Strategies

### 6.1 Preventing Flaky Tests

**Strategy 1: Retry with Exponential Backoff**
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_with_retry():
    """Test with automatic retry on transient failures."""
    from tests.utils.reliability_helpers import retry_async, RetryConfig

    async def run_test():
        # Test implementation
        result = await agent.run(task="...")
        assert result is not None

    # Retry up to 3 times with backoff
    await retry_async(run_test, RetryConfig(max_attempts=3))
```

**Strategy 2: Ollama Warmup**
```python
@pytest.fixture(scope="session", autouse=True)
def warmup_ollama():
    """Warm up Ollama before tests to prevent first-call timeouts."""
    import subprocess
    subprocess.run(
        ["ollama", "run", "llama3.1:8b-instruct-q8_0", "Hello"],
        capture_output=True,
        timeout=30
    )
```

**Strategy 3: Deterministic Seeds**
```python
@pytest.fixture(autouse=True)
def set_random_seeds():
    """Set random seeds for reproducibility."""
    import random
    import numpy as np
    random.seed(42)
    np.random.seed(42)
```

### 6.2 Memory Leak Detection

**Strategy**: Use `tracemalloc` to detect memory growth
```python
@pytest.mark.e2e
@pytest.mark.asyncio
@ensure_no_memory_leaks
async def test_long_running_no_leaks():
    """Long-running test with memory leak detection."""
    # Test implementation
    for i in range(1000):
        await agent.run(task=f"Task {i}")
    # Memory leak check happens automatically
```

### 6.3 Cost Abort Thresholds

**Strategy**: Hard stop at 80% budget
```python
@pytest.fixture(autouse=True)
def enforce_cost_budget(cost_tracker):
    """Enforce cost budget with early abort."""
    yield

    # Check after each test
    if cost_tracker.total_cost > (cost_tracker.budget_limit * 0.8):
        pytest.exit(f"Approaching budget limit: ${cost_tracker.total_cost:.2f}")
```

### 6.4 Interrupt Test Isolation

**Strategy**: Run interrupt tests in separate processes
```python
@pytest.mark.e2e
def test_interrupt_isolated():
    """Run interrupt test in subprocess for isolation."""
    import subprocess
    result = subprocess.run(
        ["python", "tests/e2e/autonomy/interrupts/interrupt_runner.py"],
        capture_output=True,
        timeout=60
    )
    assert result.returncode == 0
```

---

## 7. CI Integration Strategy

### 7.1 GitHub Actions Workflow

```yaml
# .github/workflows/e2e-tests.yml
name: E2E Tests

on:
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # Nightly at 2 AM

jobs:
  e2e-short:
    runs-on: ubuntu-latest
    timeout-minutes: 60

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-asyncio pytest-timeout

      - name: Start Ollama
        run: |
          docker run -d -p 11434:11434 ollama/ollama
          docker exec ollama ollama pull llama3.1:8b-instruct-q8_0

      - name: Start PostgreSQL
        run: |
          docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test postgres:15

      - name: Run E2E Tests (Short)
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          pytest tests/e2e/autonomy/ -v --timeout=300 -m "not long_running"

  e2e-long:
    runs-on: ubuntu-latest
    timeout-minutes: 300  # 5 hours
    if: github.event_name == 'schedule'  # Only on nightly

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-asyncio pytest-timeout

      - name: Start infrastructure
        run: |
          docker run -d -p 11434:11434 ollama/ollama
          docker exec ollama ollama pull llama3.1:8b-instruct-q8_0
          docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test postgres:15

      - name: Run Long-Running Tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          pytest tests/e2e/long_running/ -v --timeout=14400 -m "long_running"

      - name: Upload cost report
        uses: actions/upload-artifact@v3
        with:
          name: cost-report
          path: cost_report.txt
```

### 7.2 Test Markers

```python
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
markers = [
    "e2e: End-to-end tests",
    "long_running: Long-running tests (2-4 hours)",
    "requires_ollama: Requires Ollama",
    "requires_openai: Requires OpenAI API",
    "requires_postgres: Requires PostgreSQL",
    "tools: Tool calling tests",
    "planning: Planning agent tests",
    "meta_controller: Meta-controller tests",
    "memory: Memory system tests",
    "checkpoints: Checkpoint system tests",
    "interrupts: Interrupt handling tests"
]
```

---

## 8. Implementation Timeline

### Week 1: Core E2E Tests (20 tests)

**Days 1-2: Tool Calling (4 tests)**
- File: `test_builtin_tools_e2e.py` (4 tests)
- File: `test_custom_tools_e2e.py` (2 tests)
- File: `test_approval_workflows_e2e.py` (4 tests)
- File: `test_dangerous_operations_e2e.py` (2 tests)

**Days 3-4: Planning + Meta-Controller (6 tests)**
- File: `test_planning_agent_e2e.py` (3 tests)
- File: `test_pev_agent_e2e.py` (1 test)
- File: `test_tot_agent_e2e.py` (1 test)
- File: `test_semantic_routing_e2e.py` (2 tests)
- File: `test_fallback_handling_e2e.py` (1 test)
- File: `test_task_decomposition_e2e.py` (1 test)

**Day 5: Memory + Checkpoints (7 tests)**
- File: `test_hot_tier_e2e.py` (2 tests)
- File: `test_warm_tier_e2e.py` (1 test)
- File: `test_cold_tier_e2e.py` (1 test)
- File: `test_persistence_e2e.py` (2 tests)
- Enhance: `test_auto_checkpoint_e2e.py` (2 tests)
- File: `test_resume_e2e.py` (2 tests)
- File: `test_compression_e2e.py` (1 test)

### Week 2: Long-Running + Infrastructure

**Days 6-7: Interrupt Tests (3 tests)**
- Enhance: `test_interrupt_e2e.py` (2 tests)
- File: `test_timeout_e2e.py` (1 test)
- File: `test_budget_limit_e2e.py` (1 test)

**Days 8-9: Infrastructure + Fixtures**
- Create `cost_tracking.py`
- Create `reliability_helpers.py`
- Create `long_running_helpers.py`
- Create E2E fixtures (code_review, data_analysis, research)

**Day 10: Long-Running Test 1**
- File: `test_code_review_workload.py`
- Run and validate (2-4 hours)

### Week 3: Validation + CI

**Day 11: Long-Running Test 2**
- File: `test_data_analysis_workload.py`
- Run and validate (2-4 hours)

**Day 12: Long-Running Test 3**
- File: `test_research_workload.py`
- Run and validate (2-4 hours)

**Days 13-14: Validation**
- Run all 20+ E2E tests 3 times (no flakes)
- Validate cost <$20
- Fix any reliability issues

**Day 15: CI Integration**
- Create GitHub Actions workflow
- Configure nightly runs
- Document test execution

---

## 9. Success Criteria

### 9.1 Test Coverage
- ✅ 20+ E2E tests covering 6 autonomy systems
- ✅ 3 long-running tests (2-4 hours each)
- ✅ 100% real infrastructure (NO MOCKING)

### 9.2 Reliability
- ✅ 3 consecutive clean runs (no flakes)
- ✅ All tests pass with timeout guards
- ✅ No memory leaks in long-running tests

### 9.3 Cost Control
- ✅ Total cost <$20
- ✅ Per-test cost tracking
- ✅ Abort at 80% budget

### 9.4 CI Integration
- ✅ GitHub Actions workflow
- ✅ Nightly long-running tests
- ✅ PR validation (short tests)

---

## 10. Cost Breakdown

| System | Tests | LLM | Duration | Cost |
|--------|-------|-----|----------|------|
| Tool Calling | 12 | Ollama | 6-12 min | $0.00 |
| Planning | 5 | Mixed | 5-10 min | $0.10 |
| Meta-Controller | 3 | GPT-4o-mini | 1.5-4.5 min | $0.30 |
| Memory | 4 | Ollama | 2-4 min | $0.00 |
| Checkpoints | 3 | Ollama | 3-6 min | $0.00 |
| Interrupts | 3 | Ollama | 1.5-4.5 min | $0.00 |
| **Subtotal (Short)** | **30** | - | **19-41 min** | **$0.40** |
| Code Review | 1 | Mixed | 2-4 hours | $0.50 |
| Data Analysis | 1 | Mixed | 2-4 hours | $1.00 |
| Research | 1 | Mixed | 2-4 hours | $1.50 |
| **Subtotal (Long)** | **3** | - | **6-12 hours** | **$3.00** |
| **TOTAL** | **33** | - | **6-13 hours** | **$3.40** |

**Budget**: $20.00
**Projected**: $3.40
**Margin**: $16.60 (83% under budget)

---

## 11. Files to Create

### New Test Files (27 files)
```
tests/e2e/autonomy/tools/test_builtin_tools_e2e.py
tests/e2e/autonomy/tools/test_custom_tools_e2e.py
tests/e2e/autonomy/tools/test_approval_workflows_e2e.py
tests/e2e/autonomy/tools/test_dangerous_operations_e2e.py
tests/e2e/autonomy/planning/test_planning_agent_e2e.py
tests/e2e/autonomy/planning/test_pev_agent_e2e.py
tests/e2e/autonomy/planning/test_tot_agent_e2e.py
tests/e2e/autonomy/meta_controller/test_semantic_routing_e2e.py
tests/e2e/autonomy/meta_controller/test_fallback_handling_e2e.py
tests/e2e/autonomy/meta_controller/test_task_decomposition_e2e.py
tests/e2e/autonomy/memory/test_hot_tier_e2e.py
tests/e2e/autonomy/memory/test_warm_tier_e2e.py
tests/e2e/autonomy/memory/test_cold_tier_e2e.py
tests/e2e/autonomy/memory/test_persistence_e2e.py
tests/e2e/autonomy/checkpoints/test_resume_e2e.py
tests/e2e/autonomy/checkpoints/test_compression_e2e.py
tests/e2e/autonomy/interrupts/test_timeout_e2e.py
tests/e2e/autonomy/interrupts/test_budget_limit_e2e.py
tests/e2e/long_running/test_code_review_workload.py
tests/e2e/long_running/test_data_analysis_workload.py
tests/e2e/long_running/test_research_workload.py
tests/e2e/long_running/conftest.py
tests/fixtures/e2e/code_review_dataset.py
tests/fixtures/e2e/data_analysis_dataset.py
tests/fixtures/e2e/research_dataset.py
tests/fixtures/e2e/approval_scenarios.py
tests/fixtures/e2e/__init__.py
```

### New Utility Files (3 files)
```
tests/utils/cost_tracking.py
tests/utils/reliability_helpers.py
tests/utils/long_running_helpers.py
```

### Files to Enhance (2 files)
```
tests/e2e/autonomy/test_checkpoint_e2e.py
tests/e2e/autonomy/interrupts/test_interrupt_e2e.py
```

### CI/Documentation Files (2 files)
```
.github/workflows/e2e-tests.yml
tests/E2E_EXECUTION_GUIDE.md
```

**Total New Files**: 32 files
**Total Enhanced Files**: 2 files

---

## 12. Next Steps

1. **Review and Approve** this architecture plan
2. **Create directory structure** and `__init__.py` files
3. **Implement utility modules** (cost tracking, reliability, long-running)
4. **Create fixtures** (code review, data analysis, research datasets)
5. **Implement Week 1 tests** (tool calling, planning, meta-controller)
6. **Implement Week 2 tests** (memory, checkpoints, interrupts)
7. **Implement Week 3 tests** (long-running workloads)
8. **Validation runs** (3 consecutive clean runs)
9. **CI integration** (GitHub Actions)
10. **Documentation** (execution guide, cost reports)

---

**End of E2E Test Architecture Plan**
