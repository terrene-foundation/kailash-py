# Budget-Limited Execution Example

## Overview

Production-ready example demonstrating automatic cost-based interruption for autonomous agents with real-time budget monitoring, 80% warning alerts, detailed cost breakdown, and checkpoint preservation before budget exhaustion. Essential for cost-controlled production deployments.

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE - demonstrates $0.00 execution)
- **Kailash Kaizen** installed (`pip install kailash-kaizen`)

## Installation

```bash
# 1. Install Ollama
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai

# 2. Start Ollama service
ollama serve

# 3. Pull model (first time only)
ollama pull llama3.1:8b-instruct-q8_0

# 4. Install dependencies
pip install kailash-kaizen
```

## Usage

```bash
cd examples/autonomy/interrupts
python 03_budget_interrupt.py
```

The agent will automatically stop when the budget limit is reached. With Ollama (FREE), the cost is $0.00, but the example demonstrates the monitoring pattern for production use with OpenAI or other paid APIs.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│         BUDGET-LIMITED EXECUTION                         │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────┐      ┌────────────────────┐   │
│  │ Budget Monitoring  │◄────►│ Budget Handler     │   │
│  │ Hook (Real-time)   │      │ - Track costs      │   │
│  │ - 80% warning      │      │ - Auto-stop        │   │
│  │ - Cost breakdown   │      │ - Graceful mode    │   │
│  └────────────────────┘      └────────────────────┘   │
│          │                            │                 │
│          ▼                            ▼                 │
│  ┌─────────────────────────────────────────────────┐  │
│  │       BaseAutonomousAgent                       │  │
│  │  - Execute with budget tracking                 │  │
│  │  - Check budget before each operation           │  │
│  │  - Interrupt when limit exceeded                │  │
│  │  - Save checkpoint before stop                  │  │
│  └─────────────────────────────────────────────────┘  │
│          │                            │                 │
│          ▼                            ▼                 │
│  ┌──────────────────┐      ┌───────────────────┐     │
│  │ Cost Breakdown   │      │ Checkpoint System │     │
│  │ JSONL Log        │      │ - Pre-exhaustion  │     │
│  └──────────────────┘      │ - Compressed      │     │
│                             │ - Retention       │     │
│                             └───────────────────┘     │
│                                                        │
└────────────────────────────────────────────────────────┘
```

## Features

### 1. Budget Handler

Automatically interrupts execution when cost exceeds limit:
- **Real-time monitoring**: Tracks costs during execution
- **Graceful shutdown**: Completes current cycle before stopping
- **Checkpoint preservation**: Saves state before exit
- **Resume capability**: Continue from checkpoint later

### 2. Budget Monitoring Hook

Custom hook for comprehensive cost tracking:
- **Operation-level tracking**: Cost per LLM call tracked
- **80% warning alert**: Proactive warning before exhaustion
- **Cost breakdown**: Detailed analysis by operation type
- **JSONL logging**: Audit trail for compliance
- **Average cost calculation**: Per-operation metrics

**JSONL Log Format**:
```json
{"timestamp": "2025-11-03T12:34:56", "event": "budget_monitoring_start", "budget_limit": 0.10, "agent_id": "autonomous_agent"}
{"timestamp": "2025-11-03T12:35:45", "event": "budget_monitoring_end", "total_cost": 0.0, "budget_limit": 0.10, "budget_remaining": 0.10, "operations": 10, "cost_by_operation": {"llm_call_cycle_1": 0.0, "llm_call_cycle_2": 0.0}, "agent_id": "autonomous_agent"}
```

### 3. Cost Breakdown

Detailed cost analysis with:
- **Total cost**: Sum of all operations
- **Budget remaining**: Unused budget
- **Budget used percentage**: Utilization rate
- **Operation count**: Total operations executed
- **Average cost**: Per-operation average
- **Cost by operation**: Breakdown by operation type with percentages

### 4. Warning Alerts

Proactive alerts when approaching budget limit:
- **80% threshold**: Warning when 80% of budget used
- **Real-time logging**: Warnings logged to console and file
- **Configurable**: Adjust threshold in production

## Expected Output

```
============================================================
💰 BUDGET-LIMITED EXECUTION EXAMPLE
============================================================
📂 Checkpoint Dir: .kaizen/checkpoints/budget_example
🔧 LLM: ollama/llama3.1:8b-instruct-q8_0 (FREE)
💵 Budget Limit: $0.1000
⚡ Features:
  ✅ Real-time cost tracking
  ✅ Budget monitoring hook
  ✅ 80% budget warning alert
  ✅ Cost breakdown by operation
  ✅ Graceful auto-stop at limit
  ✅ Checkpoint before exhaustion
============================================================

ℹ️  Agent will automatically stop when cost exceeds $0.1000.

2025-11-03 12:34:50 - INFO - Budget handler configured: $0.10 maximum cost
2025-11-03 12:34:51 - INFO - Starting autonomous execution with budget tracking...

CYCLE 1: Writing introduction paragraph...
CYCLE 2: Expanding on AI history...
CYCLE 3: Discussing machine learning...
...
CYCLE 10: Concluding essay...

✅ Task completed within budget!

   Cycles: 10
   Cost: $0.0000 / $0.1000
   Remaining budget: $0.1000

============================================================
💰 COST BREAKDOWN
============================================================
Total Cost: $0.0000
Budget Limit: $0.1000
Budget Remaining: $0.1000
Budget Used: 0.0%

Operations:
  Total: 10
  Avg Cost: $0.0000

Cost by Operation:
  llm_call_cycle_1: $0.0000 (0.0%)
  llm_call_cycle_2: $0.0000 (0.0%)
  llm_call_cycle_3: $0.0000 (0.0%)
  ...
  llm_call_cycle_10: $0.0000 (0.0%)
============================================================

📊 Budget monitoring log: .kaizen/checkpoints/budget_example/budget_monitoring.jsonl
   View detailed metrics: cat .kaizen/checkpoints/budget_example/budget_monitoring.jsonl
```

### With Real Budget Exceeded (OpenAI API)

```
...
CYCLE 5: Analyzing deep learning...

2025-11-03 12:35:30 - WARNING - ⚠️  Budget warning: 82.3% used ($0.0823 / $0.1000)

CYCLE 6: Discussing neural networks...

💰 Budget limit reached: $0.1015
   Graceful shutdown completed and checkpoint saved.

   Source: SYSTEM
   Mode: GRACEFUL
   Message: Budget limit exceeded
   Timestamp: 2025-11-03T12:35:45.123456

   Checkpoint: checkpoint_20251103_123545.jsonl.gz
   Cycles completed: 6

============================================================
💰 COST BREAKDOWN
============================================================
Total Cost: $0.1015
Budget Limit: $0.1000
Budget Remaining: $0.0000
Budget Used: 101.5%

Operations:
  Total: 6
  Avg Cost: $0.0169

Cost by Operation:
  llm_call_cycle_1: $0.0145 (14.3%)
  llm_call_cycle_2: $0.0167 (16.5%)
  llm_call_cycle_3: $0.0178 (17.5%)
  llm_call_cycle_4: $0.0189 (18.6%)
  llm_call_cycle_5: $0.0172 (16.9%)
  llm_call_cycle_6: $0.0164 (16.2%)
============================================================
```

## Key Patterns

### 1. Budget Handler Configuration

```python
from kaizen.core.autonomy.interrupts.handlers import BudgetInterruptHandler

# Set budget limit
MAX_COST = 10.0  # $10 limit for production

# Create budget handler
budget_handler = BudgetInterruptHandler(
    interrupt_manager=interrupt_manager,
    budget_usd=MAX_COST
)

# Handler automatically tracks costs and triggers interrupt when exceeded
```

### 2. Budget Monitoring Hook

```python
class BudgetMonitoringHook:
    """Custom hook for real-time budget monitoring."""

    def track_operation_cost(self, operation: str, cost: float) -> None:
        """Track cost for specific operation."""
        self.total_cost += cost
        self.operation_count += 1
        self.cost_by_operation[operation] = (
            self.cost_by_operation.get(operation, 0.0) + cost
        )

        # 80% warning threshold
        budget_used_percentage = (self.total_cost / self.budget_limit) * 100
        if budget_used_percentage >= 80 and budget_used_percentage < 100:
            logger.warning(
                f"⚠️  Budget warning: {budget_used_percentage:.1f}% used"
            )

    def get_cost_breakdown(self) -> Dict[str, Any]:
        """Get detailed cost breakdown."""
        return {
            "total_cost": self.total_cost,
            "budget_remaining": max(0, self.budget_limit - self.total_cost),
            "budget_used_percentage": (self.total_cost / self.budget_limit) * 100,
            "operations": self.operation_count,
            "cost_by_operation": self.cost_by_operation,
            "avg_cost_per_operation": (
                self.total_cost / self.operation_count if self.operation_count > 0 else 0
            )
        }
```

### 3. Agent Configuration

```python
# Enable checkpoint before budget exhaustion
config = AutonomousConfig(
    llm_provider="openai",          # Use OpenAI for real costs
    model="gpt-4o-mini",            # Cost-effective model
    checkpoint_frequency=5,          # Checkpoint every 5 cycles
    checkpoint_on_interrupt=True    # Save before budget stop
)

# Compressed storage
storage = FilesystemStorage(base_dir=str(checkpoint_dir), compress=True)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,
    retention_count=20
)
```

## Troubleshooting

### Issue: Budget handler not working

**Symptom**: Agent continues execution beyond budget limit

**Solutions**:
1. Verify budget handler is registered with interrupt manager
2. Ensure agent._interrupt_manager is properly set
3. Check that costs are being tracked (see logs)
4. Verify budget_usd is set to correct value

### Issue: No warning alert at 80%

**Symptom**: Budget exhausted without warning

**Solutions**:
1. Check if monitoring hook is registered correctly
2. Verify track_operation_cost() is being called
3. Ensure logging level is INFO or WARNING
4. Adjust warning threshold if needed (default 80%)

### Issue: Cost tracking inaccurate

**Symptom**: Reported costs don't match actual API costs

**Solutions**:
1. Ensure using real LLM provider (not Ollama) for cost tracking
2. Check provider's pricing tier (varies by model)
3. Verify cost calculation includes input + output tokens
4. Add buffer to budget (5-10%) for estimation errors

### Issue: Checkpoint not saved before stop

**Symptom**: Resume fails because no checkpoint exists

**Solutions**:
1. Verify `checkpoint_on_interrupt=True` in config
2. Check checkpoint directory permissions
3. Ensure graceful shutdown completes (not immediate)
4. Increase `graceful_shutdown_timeout` if needed

## Production Notes

### Cost Control Strategies

1. **Model Selection**: Use cost-effective models (gpt-4o-mini, gpt-3.5-turbo)
2. **Buffer Budget**: Add 10% buffer for estimation errors
3. **Tiered Limits**: Different budgets for dev ($1), staging ($10), prod ($100+)
4. **Cost Alerts**: Set up 50%, 80%, 90% warning thresholds
5. **Auto-Retry**: Resume from checkpoint with increased budget if needed

### Budget Monitoring Best Practices

```python
# Production configuration
BUDGET_TIERS = {
    "dev": 1.0,      # $1 for development
    "staging": 10.0, # $10 for staging tests
    "prod": 100.0    # $100 for production
}

# Warning thresholds
WARNING_THRESHOLDS = [0.5, 0.8, 0.9]  # 50%, 80%, 90%

# Cost tracking frequency
CHECKPOINT_FREQUENCY = 10  # Save every 10 operations
```

### Multi-Agent Budget Allocation

For multi-agent systems, allocate budgets to individual agents:

```python
# Total budget: $100
TOTAL_BUDGET = 100.0

# Allocate per agent
supervisor_budget = TOTAL_BUDGET * 0.2   # 20% ($20)
worker1_budget = TOTAL_BUDGET * 0.3      # 30% ($30)
worker2_budget = TOTAL_BUDGET * 0.3      # 30% ($30)
worker3_budget = TOTAL_BUDGET * 0.2      # 20% ($20)

# Create handlers for each
supervisor_handler = BudgetInterruptHandler(manager, supervisor_budget)
worker1_handler = BudgetInterruptHandler(manager1, worker1_budget)
# ... etc
```

## Related Examples

- **01_ctrl_c_interrupt.py** - Ctrl+C graceful shutdown
- **02_timeout_interrupt.py** - Timeout-based interrupts
- **checkpoints/resume-interrupted-research/** - Resume from checkpoint
- **full-integration/autonomous-research-agent/** - All systems integrated

## References

- [Interrupt Mechanism Guide](../../../../docs/guides/interrupt-mechanism-guide.md)
- [Budget Handler API](../../../../docs/reference/api-reference.md#budgetinterrupthandler)
- [Hooks System Guide](../../../../docs/guides/hooks-system-guide.md)
- [ADR-016: Interrupt Mechanism](../../../../docs/architecture/adr/ADR-016-interrupt-mechanism.md)

---

**Example Type**: Budget Control
**Systems**: Interrupts, Budget Tracking, Hooks, Checkpoints
**Cost**: $0.00 (FREE with Ollama, demonstrates pattern for OpenAI)
**Complexity**: Intermediate
**Production-Ready**: ✅ Yes
