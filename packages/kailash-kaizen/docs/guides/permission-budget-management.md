# Permission System Budget Management Guide

**Version**: 1.0
**Last Updated**: 2025-10-25
**Focus**: Cost Control & Resource Management

---

## Table of Contents

1. [Overview](#overview)
2. [Budget Architecture](#budget-architecture)
3. [Cost Estimation](#cost-estimation)
4. [Budget Enforcement](#budget-enforcement)
5. [Usage Tracking](#usage-tracking)
6. [Budget Strategies](#budget-strategies)
7. [Multi-Agent Budgets](#multi-agent-budgets)
8. [Cost Optimization](#cost-optimization)
9. [Monitoring & Alerts](#monitoring--alerts)
10. [Case Studies](#case-studies)

---

## Overview

The **Budget Management** system provides fine-grained cost control for autonomous agent operations with:

- **Pre-Execution Cost Estimation**: Check budgets BEFORE tool execution
- **Real-Time Usage Tracking**: Monitor actual costs as operations complete
- **Conservative Estimates**: 20% buffer for unknown tools prevents overruns
- **Thread-Safe Accounting**: Concurrent execution with lock-based synchronization
- **Performance**: <1ms budget operations (ADR-012 NFR-2)

### Key Concepts

```
Budget Lifecycle:
    ↓
1. Set Budget Limit (BaseAgentConfig.budget_limit_usd)
    ↓
2. Estimate Cost (BudgetEnforcer.estimate_cost)
    ↓
3. Check Budget (ExecutionContext.has_budget)
    ↓
4. Execute Tool (if budget available)
    ↓
5. Record Actual Usage (BudgetEnforcer.record_usage)
    ↓
6. Update Budget Used (ExecutionContext.budget_used)
```

---

## Budget Architecture

### Components

```
┌──────────────────────────────────────┐
│   BaseAgentConfig                     │
│   - budget_limit_usd: Optional[float]│  ← Budget limit configuration
└──────────────┬───────────────────────┘
               │
               ↓
┌──────────────────────────────────────┐
│   ExecutionContext                    │
│   - budget_limit: Optional[float]     │  ← Current budget state
│   - budget_used: float                │  ← Cumulative usage
│   - has_budget(cost) → bool           │  ← Budget check
└──────────────┬───────────────────────┘
               │
               ↓
┌──────────────────────────────────────┐
│   BudgetEnforcer (Static Utility)     │
│   - estimate_cost() → float           │  ← Cost estimation
│   - record_usage()                    │  ← Usage recording
│   - get_actual_cost() → float         │  ← Actual cost extraction
│   - TOOL_COSTS: Dict[str, float]      │  ← Fixed cost table
└───────────────────────────────────────┘
```

### Budget Flow in execute_tool()

```python
# BaseAgent.execute_tool() permission flow
async def execute_tool(self, tool_name: str, params: dict) -> Any:
    # STEP 1: Estimate cost
    estimated_cost = BudgetEnforcer.estimate_cost(tool_name, params)

    # STEP 2: Check permissions (includes budget check in Layer 2)
    allowed, reason = self.permission_policy.check_permission(
        tool_name, params, estimated_cost
    )

    if allowed is False:
        raise PermissionDeniedError(reason)

    # STEP 3: Request approval if needed (skipped if budget denied)
    # ...

    # STEP 4: Execute tool
    result = await self._tool_executor.execute(tool_name, params)

    # STEP 5: Record actual usage
    actual_cost = BudgetEnforcer.get_actual_cost(result)
    BudgetEnforcer.record_usage(self.execution_context, tool_name, actual_cost)

    return result
```

---

## Cost Estimation

### Fixed Cost Tools

```python
from kaizen.core.autonomy.permissions.budget_enforcer import BudgetEnforcer

# Fixed costs (BudgetEnforcer.TOOL_COSTS)
TOOL_COSTS = {
    "Read": 0.001,      # $0.001 (file read)
    "Write": 0.005,     # $0.005 (file write)
    "Edit": 0.005,      # $0.005 (file edit)
    "Bash": 0.01,       # $0.01 (system command)
    "PythonCode": 0.01, # $0.01 (code execution)
    "Delete": 0.002,    # $0.002 (file deletion)
    "Grep": 0.001,      # $0.001 (file search)
    "Glob": 0.001,      # $0.001 (pattern matching)
    "HTTP": 0.005,      # $0.005 (HTTP request)
    "WebFetch": 0.01,   # $0.01 (web scraping)
    "Workflow": 0.05,   # $0.05 (sub-workflow)
    "Agent": 0.1,       # $0.10 (sub-agent)
    "MCP": 0.02,        # $0.02 (MCP tool call)
}

# Usage
estimated_cost = BudgetEnforcer.estimate_cost("Read", {"file_path": "/tmp/data.txt"})
print(f"Estimated cost: ${estimated_cost}")  # $0.001
```

### Token-Based Tools (LLM, AgentNode)

```python
# LLM tool cost estimation
def estimate_llm_cost(tool_input: dict) -> float:
    # Extract text from prompt or messages
    if "prompt" in tool_input:
        text = tool_input["prompt"]
    elif "messages" in tool_input:
        text = " ".join([m.get("content", "") for m in tool_input["messages"]])
    else:
        return 0.0001  # Minimum cost

    # Estimate tokens (rough: 1 token ≈ 4 characters)
    estimated_tokens = len(text) // 4

    # Cost estimate (based on GPT-3.5 pricing: $0.50 per 1M tokens)
    cost_per_token = 0.50 / 1_000_000
    estimated_cost = estimated_tokens * cost_per_token

    # Minimum cost: $0.0001 (safety buffer)
    return max(estimated_cost, 0.0001)

# Example
tool_input = {"prompt": "Explain quantum mechanics in detail"}
cost = BudgetEnforcer.estimate_cost("LLM", tool_input)
print(f"Estimated cost: ${cost:.4f}")  # $0.0001 (short prompt)

tool_input_long = {"prompt": "Explain" * 10000}  # 70K chars ≈ 17.5K tokens
cost_long = BudgetEnforcer.estimate_cost("LLM", tool_input_long)
print(f"Estimated cost: ${cost_long:.4f}")  # $0.0088
```

### Unknown Tools (Conservative Estimate)

```python
# Unknown tool: 20% buffer over standard tool cost
unknown_cost = BudgetEnforcer.estimate_cost("CustomTool", {"param": "value"})
print(f"Unknown tool cost: ${unknown_cost}")  # $0.01 (conservative)

# Why conservative?
# - Prevents budget exhaustion from unexpected tools
# - Ensures budget checks remain safe
# - Can be refined with actual cost tracking
```

---

## Budget Enforcement

### Setting Budget Limits

```python
from kaizen.core.config import BaseAgentConfig

# Conservative development budget
dev_config = BaseAgentConfig(
    budget_limit_usd=10.0  # $10 limit
)

# Production budget with monitoring
prod_config = BaseAgentConfig(
    budget_limit_usd=50.0  # $50 limit
)

# Unlimited budget (for trusted environments)
unlimited_config = BaseAgentConfig(
    budget_limit_usd=None  # No limit
)
```

### Budget Check (Pre-Execution)

```python
# ExecutionContext.has_budget() checks BEFORE execution
class ExecutionContext:
    def has_budget(self, estimated_cost: float) -> bool:
        """
        Check if budget allows execution.

        Args:
            estimated_cost: Estimated cost for operation

        Returns:
            True if budget allows, False if exceeded
        """
        if self.budget_limit is None:
            return True  # Unlimited budget

        with self._lock:  # Thread-safe check
            return (self.budget_used + estimated_cost) <= self.budget_limit

# Usage in permission policy (Layer 2)
if not context.has_budget(estimated_cost):
    return False, f"Insufficient budget: estimated ${estimated_cost:.2f} but only ${remaining:.2f} remaining"
```

### Budget Exceeded Error

```python
from kaizen.core.autonomy.permissions.types import PermissionDeniedError

# Example: Budget exceeded
config = BaseAgentConfig(
    budget_limit_usd=0.05  # $0.05 limit
)

agent = BaseAgent(config=config, signature=TaskSignature())

try:
    # This will fail: estimated cost $0.10 > remaining $0.05
    await agent.execute_tool("Agent", {"task": "Complex task"})
except PermissionDeniedError as e:
    print(f"Budget error: {e}")
    # Output: "Insufficient budget: estimated $0.10 but only $0.05 remaining"
```

---

## Usage Tracking

### Recording Actual Usage

```python
# BudgetEnforcer.record_usage() updates budget_used
@staticmethod
def record_usage(context: ExecutionContext, tool_name: str, actual_cost: float) -> None:
    """
    Record actual tool usage cost.

    Args:
        context: Execution context
        tool_name: Tool name
        actual_cost: Actual cost (from result metadata or estimated)
    """
    with context._lock:  # Thread-safe update
        context.budget_used += actual_cost

    logger.info(f"Budget updated: tool={tool_name}, cost=${actual_cost:.3f}, total=${context.budget_used:.3f}")

# Automatic tracking in execute_tool()
actual_cost = BudgetEnforcer.get_actual_cost(result)  # Extract from result
BudgetEnforcer.record_usage(self.execution_context, tool_name, actual_cost)
```

### Actual Cost Extraction

```python
# BudgetEnforcer.get_actual_cost() extracts cost from result
@staticmethod
def get_actual_cost(result: Any) -> float:
    """
    Extract actual cost from tool result.

    Checks result object for cost_usd attribute.
    Falls back to 0.0 if not available (estimation used instead).

    Args:
        result: Tool execution result

    Returns:
        Actual cost in USD
    """
    if hasattr(result, "cost_usd") and result.cost_usd is not None:
        return result.cost_usd  # Use actual cost from LLM provider

    return 0.0  # No cost metadata → use estimated cost

# Example: LLM result with actual cost
result = await agent.execute_tool("LLM", {"prompt": "Hello"})
# result.cost_usd = 0.0002 (from OpenAI response metadata)

# Budget updated with ACTUAL cost (0.0002), not estimated (0.0001)
```

### Budget Queries

```python
# Get current budget state
ctx = agent.execution_context

print(f"Budget limit: ${ctx.budget_limit}")
print(f"Budget used: ${ctx.budget_used:.3f}")

# Calculate remaining
if ctx.budget_limit is not None:
    remaining = ctx.budget_limit - ctx.budget_used
    usage_percent = (ctx.budget_used / ctx.budget_limit) * 100

    print(f"Remaining: ${remaining:.3f}")
    print(f"Usage: {usage_percent:.1f}%")
else:
    print("Unlimited budget")

# Check if specific cost is affordable
if ctx.has_budget(estimated_cost=1.0):
    print("Can afford $1.00 operation")
else:
    print("Insufficient budget for $1.00 operation")
```

---

## Budget Strategies

### Strategy 1: Per-Session Budgets

```python
# Each agent session gets fixed budget
async def create_session_agent(user_id: str) -> BaseAgent:
    config = BaseAgentConfig(
        budget_limit_usd=5.0,  # $5 per session
        permission_mode=PermissionMode.DEFAULT
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    logger.info(f"Created agent for user {user_id} with $5 budget")

    return agent

# Usage
agent = await create_session_agent("user123")

# Session ends when budget exhausted or user disconnects
```

### Strategy 2: Per-Operation Budgets

```python
# Each operation gets granular budget
async def execute_with_budget(agent: BaseAgent, tool_name: str, params: dict, max_cost: float):
    """
    Execute tool with per-operation budget limit.

    Args:
        agent: Agent instance
        tool_name: Tool to execute
        params: Tool parameters
        max_cost: Maximum allowed cost for this operation

    Raises:
        PermissionDeniedError: If operation exceeds max_cost
    """
    # Estimate cost
    estimated_cost = BudgetEnforcer.estimate_cost(tool_name, params)

    if estimated_cost > max_cost:
        raise PermissionDeniedError(
            f"Operation cost ${estimated_cost:.2f} exceeds limit ${max_cost:.2f}"
        )

    # Execute
    result = await agent.execute_tool(tool_name, params)

    return result

# Usage
try:
    result = await execute_with_budget(
        agent, "LLM", {"prompt": "..."}, max_cost=0.10
    )
except PermissionDeniedError as e:
    print(f"Operation too expensive: {e}")
```

### Strategy 3: Tiered Budgets by Priority

```python
# Different budgets for different task priorities
class BudgetTier(Enum):
    LOW = 1.0       # $1 for low-priority tasks
    MEDIUM = 5.0    # $5 for medium-priority tasks
    HIGH = 20.0     # $20 for high-priority tasks
    CRITICAL = 100.0  # $100 for critical tasks

async def create_agent_by_priority(priority: BudgetTier) -> BaseAgent:
    config = BaseAgentConfig(
        budget_limit_usd=priority.value
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    logger.info(f"Created {priority.name} priority agent with ${priority.value} budget")

    return agent

# Usage
low_priority_agent = await create_agent_by_priority(BudgetTier.LOW)
critical_agent = await create_agent_by_priority(BudgetTier.CRITICAL)
```

### Strategy 4: Dynamic Budget Adjustment

```python
# Adjust budget based on remaining balance
async def adjust_budget_dynamically(agent: BaseAgent, account_balance: float):
    """
    Adjust agent budget based on account balance.

    Allocates 10% of account balance to agent budget.

    Args:
        agent: Agent instance
        account_balance: User's account balance
    """
    new_budget = account_balance * 0.10  # 10% of balance

    # Update budget limit (requires new context)
    agent.execution_context.budget_limit = new_budget

    logger.info(f"Budget adjusted: ${new_budget:.2f} (10% of ${account_balance:.2f})")

# Usage
agent = BaseAgent(config=BaseAgentConfig(budget_limit_usd=10.0), signature=TaskSignature())

# User adds funds
account_balance = 500.0
await adjust_budget_dynamically(agent, account_balance)

# Agent now has $50 budget (10% of $500)
```

### Strategy 5: Budget Pooling (Multi-Agent)

```python
# Multiple agents share budget pool
class BudgetPool:
    def __init__(self, total_budget: float):
        self.total_budget = total_budget
        self.used_budget = 0.0
        self._lock = threading.Lock()

    def allocate(self, amount: float) -> bool:
        """
        Allocate budget from pool.

        Returns:
            True if allocated, False if insufficient
        """
        with self._lock:
            if self.used_budget + amount <= self.total_budget:
                self.used_budget += amount
                return True
            return False

    def release(self, amount: float):
        """Release unused budget back to pool."""
        with self._lock:
            self.used_budget -= amount

# Create pool
pool = BudgetPool(total_budget=100.0)

# Create agents sharing pool
async def create_pooled_agent(pool: BudgetPool, agent_id: str) -> BaseAgent:
    # Each agent gets unlimited budget
    # Pool manages global budget
    config = BaseAgentConfig(
        budget_limit_usd=None  # Unlimited per-agent
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    # Override execute_tool to check pool
    original_execute = agent.execute_tool

    async def pooled_execute(tool_name: str, params: dict):
        # Estimate cost
        estimated_cost = BudgetEnforcer.estimate_cost(tool_name, params)

        # Check pool
        if not pool.allocate(estimated_cost):
            raise PermissionDeniedError(f"Pool budget exhausted: ${estimated_cost} needed")

        try:
            # Execute
            result = await original_execute(tool_name, params)

            # Release unused budget
            actual_cost = BudgetEnforcer.get_actual_cost(result)
            pool.release(estimated_cost - actual_cost)

            return result
        except Exception as e:
            # Release on error
            pool.release(estimated_cost)
            raise

    agent.execute_tool = pooled_execute

    return agent

# Usage
agent1 = await create_pooled_agent(pool, "agent1")
agent2 = await create_pooled_agent(pool, "agent2")

# Both agents share $100 pool
```

---

## Multi-Agent Budgets

### Supervisor-Worker Pattern

```python
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Supervisor allocates budget to workers
class BudgetedSupervisor:
    def __init__(self, total_budget: float):
        self.total_budget = total_budget
        self.worker_budgets = {}

    def allocate_to_worker(self, worker_id: str, budget: float):
        """Allocate budget to worker."""
        if sum(self.worker_budgets.values()) + budget > self.total_budget:
            raise ValueError("Insufficient supervisor budget")

        self.worker_budgets[worker_id] = budget

    def create_worker(self, worker_id: str, budget: float) -> BaseAgent:
        """Create worker with allocated budget."""
        self.allocate_to_worker(worker_id, budget)

        config = BaseAgentConfig(
            budget_limit_usd=budget
        )

        worker = BaseAgent(config=config, signature=TaskSignature())

        logger.info(f"Worker {worker_id} created with ${budget} budget")

        return worker

# Usage
supervisor = BudgetedSupervisor(total_budget=50.0)

worker1 = supervisor.create_worker("data_analyst", budget=20.0)
worker2 = supervisor.create_worker("code_writer", budget=20.0)
worker3 = supervisor.create_worker("reviewer", budget=10.0)

# Total: $50 (20 + 20 + 10)
```

### Hierarchical Budgets

```python
# Parent agent delegates budget to children
class HierarchicalBudget:
    def __init__(self, parent_agent: BaseAgent):
        self.parent = parent_agent
        self.children = []

    def create_child(self, budget_percent: float) -> BaseAgent:
        """
        Create child agent with percentage of parent budget.

        Args:
            budget_percent: Percentage of parent budget (0.0-1.0)

        Returns:
            Child agent
        """
        parent_budget = self.parent.execution_context.budget_limit

        if parent_budget is None:
            raise ValueError("Parent has unlimited budget")

        child_budget = parent_budget * budget_percent

        config = BaseAgentConfig(
            budget_limit_usd=child_budget
        )

        child = BaseAgent(config=config, signature=TaskSignature())

        self.children.append(child)

        logger.info(f"Child agent created with ${child_budget:.2f} ({budget_percent*100}% of parent)")

        return child

# Usage
parent_agent = BaseAgent(
    config=BaseAgentConfig(budget_limit_usd=100.0),
    signature=TaskSignature()
)

hierarchy = HierarchicalBudget(parent_agent)

child1 = hierarchy.create_child(budget_percent=0.30)  # $30 (30% of $100)
child2 = hierarchy.create_child(budget_percent=0.50)  # $50 (50% of $100)
child3 = hierarchy.create_child(budget_percent=0.20)  # $20 (20% of $100)
```

---

## Cost Optimization

### Technique 1: Tool Selection by Cost

```python
# Choose cheaper tools when possible
async def read_file_optimized(agent: BaseAgent, file_path: str) -> str:
    """
    Read file with cost optimization.

    Uses Read ($0.001) instead of Bash ($0.01) for file reading.
    """
    # Option 1: Read tool ($0.001)
    result_read = await agent.execute_tool("Read", {"file_path": file_path})

    # Option 2: Bash tool ($0.01) - 10x more expensive!
    # result_bash = await agent.execute_tool("Bash", {"command": f"cat {file_path}"})

    return result_read["content"]

# Savings: $0.009 per read operation
```

### Technique 2: Batch Operations

```python
# Batch multiple operations to reduce overhead
async def batch_writes_optimized(agent: BaseAgent, files: List[Tuple[str, str]]):
    """
    Batch file writes to reduce cost.

    Single PythonCode call ($0.01) instead of multiple Write calls ($0.005 each).
    """
    # Option 1: Multiple Write calls
    # Cost: len(files) * $0.005 = 10 files * $0.005 = $0.05

    # Option 2: Single PythonCode batch (OPTIMIZED)
    # Cost: $0.01
    batch_code = "\n".join([
        f"with open('{path}', 'w') as f: f.write({content!r})"
        for path, content in files
    ])

    await agent.execute_tool("PythonCode", {"code": batch_code})

# Savings: $0.04 for 10 files (80% reduction)
```

### Technique 3: Result Caching

```python
# Cache expensive LLM results
class ResultCache:
    def __init__(self):
        self.cache = {}

    def get_cache_key(self, tool_name: str, params: dict) -> str:
        """Generate cache key from tool and params."""
        import hashlib
        import json

        key_data = json.dumps({"tool": tool_name, "params": params}, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    async def execute_with_cache(self, agent: BaseAgent, tool_name: str, params: dict) -> Any:
        """Execute tool with result caching."""
        cache_key = self.get_cache_key(tool_name, params)

        # Check cache
        if cache_key in self.cache:
            logger.info(f"Cache hit for {tool_name}, cost saved: ${BudgetEnforcer.estimate_cost(tool_name, params):.3f}")
            return self.cache[cache_key]

        # Execute
        result = await agent.execute_tool(tool_name, params)

        # Cache result
        self.cache[cache_key] = result

        return result

# Usage
cache = ResultCache()

# First call: Executes LLM, costs $0.002
result1 = await cache.execute_with_cache(agent, "LLM", {"prompt": "Hello"})

# Second call: Cache hit, costs $0 (100% savings)
result2 = await cache.execute_with_cache(agent, "LLM", {"prompt": "Hello"})
```

### Technique 4: Model Selection

```python
# Use cheaper models when appropriate
async def execute_by_complexity(agent: BaseAgent, prompt: str, complexity: str):
    """
    Select model based on task complexity.

    - Simple tasks: gpt-3.5-turbo ($0.50 per 1M tokens)
    - Complex tasks: gpt-4 ($30 per 1M tokens)
    """
    if complexity == "simple":
        # Use GPT-3.5 (60x cheaper!)
        model = "gpt-3.5-turbo"
    else:
        # Use GPT-4 for complex reasoning
        model = "gpt-4"

    result = await agent.execute_tool("LLM", {
        "prompt": prompt,
        "model": model
    })

    return result

# Savings: Up to 98% for simple tasks
```

---

## Monitoring & Alerts

### Real-Time Budget Monitoring

```python
import logging

logger = logging.getLogger("kaizen.budget")

async def monitor_budget(agent: BaseAgent, check_interval: float = 60.0):
    """
    Monitor budget usage in real-time.

    Args:
        agent: Agent to monitor
        check_interval: Check interval in seconds
    """
    import asyncio

    while True:
        ctx = agent.execution_context

        if ctx.budget_limit is not None:
            usage_percent = (ctx.budget_used / ctx.budget_limit) * 100

            if usage_percent >= 90:
                logger.critical(f"Budget 90% exhausted: ${ctx.budget_used:.2f} / ${ctx.budget_limit:.2f}")
            elif usage_percent >= 75:
                logger.warning(f"Budget 75% used: ${ctx.budget_used:.2f} / ${ctx.budget_limit:.2f}")
            elif usage_percent >= 50:
                logger.info(f"Budget 50% used: ${ctx.budget_used:.2f} / ${ctx.budget_limit:.2f}")

        await asyncio.sleep(check_interval)

# Usage
asyncio.create_task(monitor_budget(agent, check_interval=30.0))
```

### Cost Per Operation Logging

```python
# Log cost for each operation
async def execute_with_cost_logging(agent: BaseAgent, tool_name: str, params: dict):
    """Execute tool with detailed cost logging."""
    # Record initial budget
    initial_budget = agent.execution_context.budget_used

    # Execute
    result = await agent.execute_tool(tool_name, params)

    # Calculate actual cost
    actual_cost = agent.execution_context.budget_used - initial_budget

    # Log
    logger.info(f"Tool executed: {tool_name}, cost: ${actual_cost:.3f}, total: ${agent.execution_context.budget_used:.3f}")

    return result
```

### Budget Alerts

```python
# Alert when budget thresholds crossed
class BudgetAlerter:
    def __init__(self, agent: BaseAgent, thresholds: List[float]):
        """
        Create budget alerter.

        Args:
            agent: Agent to monitor
            thresholds: Alert thresholds (e.g., [0.5, 0.75, 0.9] for 50%, 75%, 90%)
        """
        self.agent = agent
        self.thresholds = sorted(thresholds)
        self.alerted = set()

    def check(self):
        """Check budget and send alerts."""
        ctx = self.agent.execution_context

        if ctx.budget_limit is None:
            return

        usage_percent = ctx.budget_used / ctx.budget_limit

        for threshold in self.thresholds:
            if usage_percent >= threshold and threshold not in self.alerted:
                self.send_alert(threshold, ctx.budget_used, ctx.budget_limit)
                self.alerted.add(threshold)

    def send_alert(self, threshold: float, used: float, limit: float):
        """Send alert notification."""
        logger.warning(f"⚠️ Budget Alert: {threshold*100}% threshold crossed - ${used:.2f} / ${limit:.2f}")

        # Send to monitoring system (e.g., Slack, PagerDuty)
        # send_slack_alert(f"Budget {threshold*100}% used: ${used:.2f} / ${limit:.2f}")

# Usage
alerter = BudgetAlerter(agent, thresholds=[0.5, 0.75, 0.9])

# After each operation
alerter.check()
```

---

## Case Studies

### Case Study 1: E-Commerce Product Description Generator

**Scenario**: Generate product descriptions for 1,000 products

**Naive Approach**:
```python
# Cost per description: $0.01 (GPT-4)
# Total cost: 1,000 * $0.01 = $10.00

for product in products:
    description = await agent.execute_tool("LLM", {
        "prompt": f"Write description for {product.name}",
        "model": "gpt-4"
    })
```

**Optimized Approach**:
```python
# 1. Use cheaper model (GPT-3.5)
# Cost per description: $0.0001
# Total cost: 1,000 * $0.0001 = $0.10 (99% savings!)

# 2. Batch 10 products per call
# Calls: 1,000 / 10 = 100
# Cost: 100 * $0.001 = $0.10

for batch in chunks(products, size=10):
    descriptions = await agent.execute_tool("LLM", {
        "prompt": f"Write descriptions for: {[p.name for p in batch]}",
        "model": "gpt-3.5-turbo"
    })
```

**Savings**: $9.90 (99% reduction)

---

### Case Study 2: Code Review Workflow

**Scenario**: Review 50 files with budget limit

**Configuration**:
```python
# Budget: $5.00
# Estimated cost per file: $0.15 (GPT-4 review)
# Total estimated: 50 * $0.15 = $7.50 (EXCEEDS BUDGET!)

config = BaseAgentConfig(
    budget_limit_usd=5.0
)

agent = BaseAgent(config=config, signature=ReviewSignature())
```

**Strategy**: Prioritize files by complexity

```python
# 1. Sort files by size (proxy for complexity)
files_sorted = sorted(files, key=lambda f: f.size, reverse=True)

# 2. Review until budget exhausted
reviewed = []
for file in files_sorted:
    estimated_cost = BudgetEnforcer.estimate_cost("LLM", {"prompt": file.content})

    if not agent.execution_context.has_budget(estimated_cost):
        logger.warning(f"Budget exhausted after {len(reviewed)} files")
        break

    review = await agent.execute_tool("LLM", {
        "prompt": f"Review this code: {file.content}"
    })

    reviewed.append((file, review))

# Result: Reviewed 33 largest files (66% coverage) within budget
```

---

### Case Study 3: Multi-Agent Data Pipeline

**Scenario**: Data extraction → transformation → loading with 3 agents

**Budget Allocation**:
```python
# Total budget: $20
# Extraction (expensive): $12 (60%)
# Transformation (moderate): $6 (30%)
# Loading (cheap): $2 (10%)

extractor = BaseAgent(config=BaseAgentConfig(budget_limit_usd=12.0), signature=ExtractSignature())
transformer = BaseAgent(config=BaseAgentConfig(budget_limit_usd=6.0), signature=TransformSignature())
loader = BaseAgent(config=BaseAgentConfig(budget_limit_usd=2.0), signature=LoadSignature())

# Execute pipeline
data = await extractor.execute_tool("WebFetch", {"url": "..."})  # $10 actual
transformed = await transformer.execute_tool("PythonCode", {"code": "..."})  # $5 actual
await loader.execute_tool("Write", {"file_path": "...", "content": transformed})  # $1 actual

# Total actual: $16 (under budget!)
```

---

## Summary

**Budget Management Best Practices**:

1. ✅ **Set realistic budgets**: Based on expected workload + 20% buffer
2. ✅ **Monitor usage**: Real-time alerts at 50%, 75%, 90% thresholds
3. ✅ **Optimize tool selection**: Use cheaper alternatives when possible
4. ✅ **Batch operations**: Reduce per-operation overhead
5. ✅ **Cache results**: Avoid redundant expensive operations
6. ✅ **Prioritize tasks**: Review critical items first when budget-constrained
7. ✅ **Log costs**: Track per-operation costs for analysis
8. ✅ **Test estimates**: Validate cost estimates against actual usage

**Next Steps**:

- **[Permission System User Guide](permission-system-user-guide.md)** - Complete usage guide
- **[Approval Workflow Guide](permission-approval-workflows.md)** - Custom approval patterns
- **[Troubleshooting Guide](permission-troubleshooting.md)** - Common budget issues

---

**© 2025 Kailash Kaizen | Budget Management v1.0**
