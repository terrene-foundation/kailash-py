# Advanced Autonomy Patterns Guide

**Status**: Production-Ready
**Complexity**: Advanced
**Prerequisites**: Planning Agents, Meta-Controller, Memory System
**Estimated Reading Time**: 15-20 minutes

---

## Table of Contents

1. [Overview](#overview)
2. [Multi-Agent Coordination Patterns](#multi-agent-coordination-patterns)
3. [Complex Workflow Orchestration](#complex-workflow-orchestration)
4. [Advanced Memory Strategies](#advanced-memory-strategies)
5. [Error Recovery and Resilience](#error-recovery-and-resilience)
6. [Performance Optimization](#performance-optimization)
7. [Production Deployment Patterns](#production-deployment-patterns)
8. [Best Practices](#best-practices)

---

## Overview

This guide covers advanced patterns for building sophisticated autonomous systems with Kaizen. These patterns combine multiple autonomy features (planning, memory, interrupts, checkpoints) to create robust, production-grade applications.

### When to Use Advanced Patterns

- **Multi-step workflows** requiring coordination between specialized agents
- **Long-running processes** that must survive restarts and failures
- **Resource-constrained environments** requiring optimization
- **Production systems** with strict reliability requirements
- **Complex decision-making** requiring multiple perspectives

---

## Multi-Agent Coordination Patterns

### Pattern 1: Hierarchical Planning with Specialized Executors

Combine meta-controller routing with planning agents for complex task decomposition.

```python
from kaizen.agents import PlanningAgent
from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.patterns.meta_controller import Pipeline
from kaizen.signatures import Signature, InputField, OutputField

# 1. Define specialized agents
class CodeGenerationSignature(Signature):
    task: str = InputField(description="Coding task description")
    code: str = OutputField(description="Generated code")
    tests: str = OutputField(description="Unit tests")

code_expert = BaseAgent(
    config={"llm_provider": "openai", "model": "gpt-4"},
    signature=CodeGenerationSignature()
)

class DataAnalysisSignature(Signature):
    data_description: str = InputField(description="Data analysis task")
    analysis: str = OutputField(description="Analysis results")
    visualizations: list = OutputField(description="Chart specs")

data_expert = BaseAgent(
    config={"llm_provider": "openai", "model": "gpt-4"},
    signature=DataAnalysisSignature()
)

# 2. Create planning coordinator
planning_coordinator = PlanningAgent(
    llm_provider="openai",
    model="gpt-4",
    max_plan_steps=10,
    validation_mode="strict"
)

# 3. Route to specialists via meta-controller
pipeline = Pipeline.router(
    agents=[code_expert, data_expert],
    routing_strategy="semantic",  # A2A capability matching
    error_handling="graceful"
)

# 4. Execute complex task
task = """
Analyze user engagement data from database,
generate insights report, and create dashboard code.
"""

# Planning coordinator creates execution plan
plan_result = planning_coordinator.run(task=task)

# Specialists execute plan steps
for step in plan_result["plan"]["steps"]:
    step_result = pipeline.run(task=step["description"], input=step.get("inputs"))
    print(f"✓ {step['description']}: {step_result['status']}")
```

**Use Cases**:
- Software development workflows (design → code → test → review)
- Research projects (plan → collect data → analyze → report)
- Enterprise automation (assess → plan → execute → verify)

---

### Pattern 2: Consensus-Building with Multiple Perspectives

Achieve high-confidence decisions through multi-agent consensus.

```python
from kaizen.agents.coordination import ConsensusPattern
from kaizen.core.base_agent import BaseAgent

# Create agents with different "personalities"
conservative_agent = BaseAgent(
    config={"llm_provider": "openai", "model": "gpt-4", "temperature": 0.2},
    signature=AnalysisSignature()
)

innovative_agent = BaseAgent(
    config={"llm_provider": "openai", "model": "gpt-4", "temperature": 0.9},
    signature=AnalysisSignature()
)

balanced_agent = BaseAgent(
    config={"llm_provider": "openai", "model": "gpt-4", "temperature": 0.5},
    signature=AnalysisSignature()
)

# Consensus pattern
consensus = ConsensusPattern(
    agents=[conservative_agent, innovative_agent, balanced_agent],
    consensus_threshold=0.66,  # 2 out of 3 must agree
    max_rounds=3
)

# Execute with consensus requirement
decision = consensus.run(
    task="Should we migrate to microservices architecture?",
    context={"current_system": "monolith", "team_size": 15}
)

print(f"Consensus reached: {decision['consensus_achieved']}")
print(f"Final recommendation: {decision['final_decision']}")
print(f"Confidence: {decision['confidence_score']:.2%}")
```

**Use Cases**:
- Architecture decisions requiring multiple perspectives
- Risk assessment needing conservative + optimistic views
- Content moderation with balanced perspectives

---

## Complex Workflow Orchestration

### Pattern 3: Checkpoint-Driven Long-Running Processes

Build fault-tolerant workflows that survive restarts.

```python
from kaizen.core.autonomy.state import StateManager, AgentState, FilesystemStorage
from kaizen.core.autonomy.hooks import HookManager, HookEvent
from kaizen.agents import PEVAgent
import asyncio

# 1. Setup state management
storage = FilesystemStorage(base_dir="./checkpoints/etl_pipeline")
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,  # Every 5 steps
    retention_count=50
)

# 2. Define long-running workflow
async def etl_pipeline(resume_from_checkpoint=None):
    """
    Multi-hour ETL pipeline with automatic checkpointing.
    """
    # Restore state or start fresh
    if resume_from_checkpoint:
        state = await state_manager.load_checkpoint(resume_from_checkpoint)
        current_step = state.step_number
        processed_records = state.custom_state.get("processed_records", 0)
        print(f"✓ Resumed from step {current_step}, {processed_records} records processed")
    else:
        current_step = 0
        processed_records = 0

    # Create PEV agent for iterative refinement
    agent = PEVAgent(
        llm_provider="openai",
        model="gpt-4",
        max_iterations=10,
        verification_strictness="strict"
    )

    # Pipeline steps
    steps = [
        "Extract data from 10 sources",
        "Transform and validate 1M records",
        "Load into data warehouse",
        "Generate analytics reports",
        "Update dashboards"
    ]

    for i, step in enumerate(steps[current_step:], start=current_step):
        # Execute step
        result = agent.run(task=step)
        processed_records += result.get("record_count", 0)

        # Save checkpoint
        agent_state = AgentState(
            agent_id="etl_pipeline",
            step_number=i + 1,
            status="running",
            conversation_history=[],
            memory_contents={},
            budget_spent_usd=0.0,
            custom_state={
                "processed_records": processed_records,
                "last_step": step,
                "result": result
            }
        )
        checkpoint_id = await state_manager.save_checkpoint(agent_state)
        print(f"✓ Step {i + 1}/{len(steps)}: {step} (checkpoint: {checkpoint_id})")

    return {"total_records": processed_records, "status": "complete"}

# Execute with fault tolerance
try:
    result = asyncio.run(etl_pipeline())
except KeyboardInterrupt:
    print("\n⚠️  Pipeline interrupted - progress saved")
    # Resume later with: etl_pipeline(resume_from_checkpoint="latest_id")
```

**Key Benefits**:
- ✅ Survive server restarts, crashes, deployments
- ✅ Resume from exact failure point (no duplicate work)
- ✅ Audit trail of every step
- ✅ Rollback to any previous checkpoint

---

### Pattern 4: Budget-Aware Multi-Stage Processing

Optimize costs while maintaining quality.

```python
from kaizen.core.autonomy.interrupts.handlers import BudgetInterruptHandler
from kaizen.agents.autonomous.base import BaseAutonomousAgent
from kaizen.agents.autonomous.config import AutonomousConfig

# 1. Configure budget-aware agent
config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",  # Expensive model
    enable_interrupts=True,
    checkpoint_on_interrupt=True
)

agent = BaseAutonomousAgent(config=config, signature=MySignature())

# 2. Add budget constraint
budget_handler = BudgetInterruptHandler(
    max_budget_usd=5.0,  # $5 limit
    checkpoint_before_stop=True
)
agent.interrupt_manager.add_handler(budget_handler)

# 3. Implement fallback strategy
async def budget_aware_processing(data_batch):
    """
    Start with expensive model, fallback to cheaper if budget exceeded.
    """
    try:
        # Try with GPT-4 first
        result = await agent.run_autonomous(task=f"Process {len(data_batch)} items")
        return result

    except InterruptedError as e:
        if "budget" in e.reason.message.lower():
            print("⚠️  Budget limit reached, switching to GPT-3.5-turbo")

            # Switch to cheaper model
            agent.config.model = "gpt-3.5-turbo"
            agent.interrupt_manager.remove_handler(budget_handler)

            # Add higher budget for cheaper model
            budget_handler_cheap = BudgetInterruptHandler(max_budget_usd=10.0)
            agent.interrupt_manager.add_handler(budget_handler_cheap)

            # Resume processing
            checkpoint_id = e.reason.metadata.get("checkpoint_id")
            result = await agent.resume_from_checkpoint(checkpoint_id)
            return result

# Process large dataset with cost controls
batch_result = asyncio.run(budget_aware_processing(large_dataset))
```

**Use Cases**:
- Large-scale data processing with cost caps
- Multi-tier service offerings (premium vs. standard)
- Development environments with budget constraints

---

## Advanced Memory Strategies

### Pattern 5: Context-Aware Tier Management

Automatically optimize memory placement based on access patterns.

```python
from kaizen.memory import PersistentBufferMemory
from kaizen.memory.backends import DataFlowBackend
from kaizen.memory.tiers import TierManager, HotMemoryTier
from kaizen.memory.persistent_tiers import WarmMemoryTier
from dataflow import DataFlow

# 1. Setup multi-tier memory system
db = DataFlow(database_url="postgresql://localhost/kaizen_memory")

@db.model
class ConversationMemory:
    id: str
    session_id: str
    content: str
    metadata: dict
    access_count: int = 0
    last_accessed: datetime = None

# 2. Configure tier manager
tier_manager = TierManager(config={
    "hot_promotion_threshold": 5,    # Access 5+ times → hot tier
    "warm_promotion_threshold": 2,   # Access 2+ times → warm tier
    "access_window_seconds": 3600,   # 1 hour window
    "auto_optimize": True            # Auto tier management
})

# 3. Create memory system
backend = DataFlowBackend(db, model_name="ConversationMemory")
memory = PersistentBufferMemory(
    backend=backend,
    tier_manager=tier_manager,
    max_turns=100
)

# 4. Memory automatically optimizes itself
session_id = "customer_123"

# First access (cold tier - database)
context_1 = memory.load_context(session_id)  # ~50ms (database query)

# Second access (warm tier - promoted)
context_2 = memory.load_context(session_id)  # ~5ms (disk cache)

# Fifth access (hot tier - promoted)
context_5 = memory.load_context(session_id)  # <1ms (memory cache)

# Tier manager automatically demotes rarely-used data
await tier_manager.optimize_tiers()  # Run periodically
```

**Performance Impact**:
- Hot tier: <1ms access (100x faster than database)
- Warm tier: <10ms access (5x faster than database)
- Auto-demotion prevents memory bloat

---

## Error Recovery and Resilience

### Pattern 6: Multi-Level Fallback Strategy

Gracefully degrade through multiple fallback layers.

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.agents import PlanningAgent
import asyncio

async def resilient_execution(task: str):
    """
    Try multiple strategies with automatic fallback.

    Strategy hierarchy:
    1. Complex planning with GPT-4 (best quality)
    2. Simple planning with GPT-3.5 (good quality, lower cost)
    3. Direct execution with Ollama (acceptable quality, free)
    4. Return error guidance (failure, but helpful)
    """

    # Level 1: Best quality (GPT-4 planning)
    try:
        planner = PlanningAgent(
            llm_provider="openai",
            model="gpt-4",
            max_plan_steps=10,
            validation_mode="strict",
            timeout=30
        )
        result = planner.run(task=task)
        return {"status": "success", "quality": "high", "result": result}

    except Exception as e:
        print(f"⚠️  Level 1 failed: {e}, trying Level 2...")

    # Level 2: Good quality (GPT-3.5 planning)
    try:
        planner = PlanningAgent(
            llm_provider="openai",
            model="gpt-3.5-turbo",
            max_plan_steps=5,
            validation_mode="warn",
            timeout=20
        )
        result = planner.run(task=task)
        return {"status": "success", "quality": "medium", "result": result}

    except Exception as e:
        print(f"⚠️  Level 2 failed: {e}, trying Level 3...")

    # Level 3: Acceptable quality (Ollama direct)
    try:
        agent = BaseAgent(
            config={"llm_provider": "ollama", "model": "llama3.2:1b"},
            signature=DirectExecutionSignature()
        )
        result = agent.run(task=task)
        return {"status": "success", "quality": "basic", "result": result}

    except Exception as e:
        print(f"❌ All levels failed: {e}")

    # Level 4: Return structured error
    return {
        "status": "error",
        "message": "All execution strategies failed",
        "suggestions": [
            "Simplify the task into smaller steps",
            "Check API credentials and quotas",
            "Verify network connectivity"
        ]
    }

# Execute with automatic fallback
result = asyncio.run(resilient_execution(complex_task))
print(f"Quality level: {result.get('quality', 'N/A')}")
```

**Use Cases**:
- Production systems requiring high availability
- Cost-sensitive applications
- Multi-cloud deployments with provider failover

---

## Performance Optimization

### Pattern 7: Parallel Execution with Dependency Management

Execute independent tasks in parallel while respecting dependencies.

```python
from kaizen.orchestration.pipeline import Pipeline
from kaizen.core.base_agent import BaseAgent
import asyncio

# Create specialized agents
data_fetcher = BaseAgent(config=data_config, signature=FetchSignature())
data_transformer = BaseAgent(config=transform_config, signature=TransformSignature())
data_validator = BaseAgent(config=validate_config, signature=ValidateSignature())
report_generator = BaseAgent(config=report_config, signature=ReportSignature())

# Define parallel execution groups
async def parallel_data_pipeline(sources: list):
    """
    Execute data pipeline with parallel fetching, sequential transformation.
    """

    # Step 1: Fetch from all sources in parallel (independent)
    fetch_tasks = [
        data_fetcher.run(source=source)
        for source in sources
    ]
    fetched_data = await asyncio.gather(*fetch_tasks)
    print(f"✓ Fetched from {len(sources)} sources in parallel")

    # Step 2: Transform each dataset in parallel (independent)
    transform_tasks = [
        data_transformer.run(data=dataset)
        for dataset in fetched_data
    ]
    transformed_data = await asyncio.gather(*transform_tasks)
    print(f"✓ Transformed {len(transformed_data)} datasets in parallel")

    # Step 3: Validate sequentially (dependent on all transforms)
    validation_result = await data_validator.run(
        datasets=transformed_data
    )
    print(f"✓ Validated all datasets: {validation_result['status']}")

    # Step 4: Generate report (dependent on validation)
    report = await report_generator.run(
        validated_data=validation_result['data']
    )
    print(f"✓ Generated report: {report['summary']}")

    return report

# Execute pipeline
sources = ["api1", "api2", "api3", "database", "s3_bucket"]
result = asyncio.run(parallel_data_pipeline(sources))
```

**Performance Gains**:
- 5 sources fetched in parallel: ~5x speedup
- 5 datasets transformed in parallel: ~5x speedup
- Total pipeline: ~10x faster than sequential

---

## Production Deployment Patterns

### Pattern 8: Observable Autonomous Systems

Implement comprehensive observability for production systems.

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookContext, HookResult
from kaizen.agents.autonomous.base import BaseAutonomousAgent
import time
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. Performance tracking hook
async def performance_monitoring_hook(context: HookContext) -> HookResult:
    """Track execution time and log slow operations."""
    if context.event == HookEvent.PRE_AGENT_LOOP:
        context.metadata["start_time"] = time.time()

    elif context.event == HookEvent.POST_AGENT_LOOP:
        duration = time.time() - context.metadata.get("start_time", time.time())

        if duration > 5.0:  # Log slow operations
            logger.warning(
                f"Slow operation detected",
                extra={
                    "agent_id": context.agent_id,
                    "duration_seconds": duration,
                    "loop_iteration": context.metadata.get("iteration", 0)
                }
            )

        # Send to monitoring system
        metrics_client.gauge("agent.loop_duration", duration, tags=[
            f"agent:{context.agent_id}"
        ])

    return HookResult(success=True)

# 2. Error tracking hook
async def error_tracking_hook(context: HookContext) -> HookResult:
    """Capture and report errors to monitoring system."""
    if context.event == HookEvent.ON_ERROR:
        error = context.metadata.get("error")

        # Log to application monitoring
        logger.error(
            f"Agent error: {error}",
            extra={
                "agent_id": context.agent_id,
                "error_type": type(error).__name__,
                "traceback": context.metadata.get("traceback")
            }
        )

        # Send to error tracking service
        sentry.capture_exception(error, extra={
            "agent_id": context.agent_id,
            "context": context.metadata
        })

    return HookResult(success=True)

# 3. Audit trail hook
async def audit_trail_hook(context: HookContext) -> HookResult:
    """Log all agent actions for compliance."""
    if context.event in [HookEvent.POST_AGENT_LOOP, HookEvent.POST_CHECKPOINT_SAVE]:
        audit_log.write({
            "timestamp": context.timestamp,
            "agent_id": context.agent_id,
            "event": context.event.value,
            "metadata": context.metadata,
            "user_id": context.metadata.get("user_id")
        })

    return HookResult(success=True)

# 4. Setup agent with all hooks
hook_manager = HookManager()
hook_manager.register(HookEvent.PRE_AGENT_LOOP, performance_monitoring_hook)
hook_manager.register(HookEvent.POST_AGENT_LOOP, performance_monitoring_hook)
hook_manager.register(HookEvent.ON_ERROR, error_tracking_hook)
hook_manager.register(HookEvent.POST_AGENT_LOOP, audit_trail_hook)
hook_manager.register(HookEvent.POST_CHECKPOINT_SAVE, audit_trail_hook)

agent = BaseAutonomousAgent(
    config=config,
    signature=signature,
    hook_manager=hook_manager
)
```

**Observability Coverage**:
- ✅ Performance metrics (latency, throughput)
- ✅ Error tracking and alerting
- ✅ Audit trails for compliance
- ✅ Resource utilization monitoring

---

## Best Practices

### 1. Design for Failure

**Always assume**:
- Network calls will fail
- LLM providers will be unavailable
- Memory will run out
- Processes will be killed

**Mitigation**:
```python
# Use checkpoints + interrupts for fault tolerance
config = AutonomousConfig(
    enable_interrupts=True,
    checkpoint_frequency=10,
    checkpoint_on_interrupt=True,
    graceful_shutdown_timeout=30.0
)
```

### 2. Optimize for Cost

**Strategies**:
- Use cheaper models (Ollama, GPT-3.5) for simple tasks
- Implement budget constraints with `BudgetInterruptHandler`
- Cache frequent queries in hot tier memory
- Use parallel execution to minimize wall-clock time

```python
# Cost-optimized configuration
config = {
    "llm_provider": "ollama",  # Free for simple tasks
    "fallback_provider": "openai",  # Paid for complex tasks
    "fallback_model": "gpt-3.5-turbo",  # Cheaper than GPT-4
    "max_budget_usd": 10.0
}
```

### 3. Monitor Everything

**Essential metrics**:
- Loop execution time
- LLM token usage and costs
- Memory tier distribution
- Error rates and types
- Checkpoint save/load times

```python
# Comprehensive monitoring
hook_manager.register_all([
    performance_hook,
    cost_tracking_hook,
    error_tracking_hook,
    audit_trail_hook
])
```

### 4. Test with Real Infrastructure

**NO MOCKING** in Tier 2/3 tests:
- Use real Ollama for integration tests
- Use real databases (SQLite, PostgreSQL)
- Test checkpoint restore from actual files
- Validate interrupt handling with real signals

```python
# Real infrastructure test
@pytest.mark.e2e
async def test_checkpoint_restore():
    # Create real agent with real state manager
    storage = FilesystemStorage(base_dir="./test_checkpoints")
    state_manager = StateManager(storage=storage)

    # Save actual checkpoint
    checkpoint_id = await state_manager.save_checkpoint(agent_state)

    # Simulate crash + restart
    new_agent = create_agent()  # Fresh instance

    # Restore from real checkpoint file
    restored_state = await state_manager.load_checkpoint(checkpoint_id)
    assert restored_state.step_number == agent_state.step_number
```

### 5. Plan for Scale

**Design considerations**:
- Use database-backed memory for >10K conversations
- Implement tier demotion to control memory growth
- Add horizontal scaling with shared state (PostgreSQL)
- Use message queues for async processing

```python
# Scalable architecture
memory_backend = DataFlowBackend(
    db=PostgreSQLDataFlow("postgresql://prod_db"),
    model_name="ConversationMemory"
)

tier_manager = TierManager(config={
    "auto_optimize": True,  # Auto tier management
    "cold_demotion_threshold": 86400,  # Demote after 24h inactivity
})
```

---

## Summary

Advanced autonomy patterns enable building production-grade systems by combining:

| Pattern | Key Benefit | Use Case |
|---------|-------------|----------|
| Hierarchical Planning | Task decomposition | Complex workflows |
| Consensus Building | High-confidence decisions | Critical decisions |
| Checkpoint-Driven | Fault tolerance | Long-running processes |
| Budget-Aware | Cost optimization | Large-scale processing |
| Context-Aware Memory | Performance | High-throughput systems |
| Multi-Level Fallback | Resilience | Production systems |
| Parallel Execution | Speed | Data pipelines |
| Observable Systems | Ops visibility | Production deployments |

### Next Steps

1. **Start simple**: Begin with one pattern (e.g., checkpoint-driven workflows)
2. **Add observability**: Implement hooks before deploying to production
3. **Test thoroughly**: Use real infrastructure in Tier 2/3 tests
4. **Monitor costs**: Add budget constraints early
5. **Scale gradually**: Start single-threaded, add parallelism as needed

### Related Guides

- [Planning Agents Guide](planning-agents-guide.md) - Task planning and validation
- [Meta-Controller Routing Guide](meta-controller-routing-guide.md) - Agent coordination
- [Memory and Learning System](memory-and-learning-system.md) - Tier management
- [State Persistence Guide](state-persistence-guide.md) - Checkpoints and recovery
- [Interrupt Mechanism Guide](interrupt-mechanism-guide.md) - Graceful shutdown
- [Hooks System Guide](hooks-system-guide.md) - Observability patterns

---

**Framework**: Kaizen AI Framework
**Version**: 1.0.0
**Last Updated**: 2025-11-04
