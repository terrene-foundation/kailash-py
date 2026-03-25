# Multi-LLM Routing Developer Guide

The Multi-LLM Routing system (TODO-194) provides intelligent model selection based on task requirements, optimizing for cost, performance, and capability.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Task Input                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    TaskAnalyzer                              │
│    Complexity Detection | Type Classification | Requirements │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLMRouter                                 │
│       Explicit Rules | Capability Match | Cost Optimization  │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  Claude 3.5   │    │   GPT-4o      │    │   Gemini      │
│   Sonnet      │    │               │    │   1.5 Pro     │
└───────────────┘    └───────────────┘    └───────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FallbackRouter                            │
│           Automatic Fallback on Errors/Limits                │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### LLMCapabilities

Describes what a model can do:

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class LLMCapabilities:
    """Capabilities of an LLM model."""

    model_id: str
    provider: str  # "openai", "anthropic", "google"

    # Context
    max_context_tokens: int
    max_output_tokens: int

    # Features
    supports_vision: bool = False
    supports_audio: bool = False
    supports_function_calling: bool = False
    supports_json_mode: bool = False
    supports_streaming: bool = True

    # Performance
    typical_latency_ms: int = 1000
    throughput_tokens_per_second: int = 50

    # Cost
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0

    # Quality indicators
    reasoning_score: float = 0.8  # 0-1
    coding_score: float = 0.8
    creativity_score: float = 0.8
```

### TaskAnalyzer

Analyzes tasks to determine requirements:

```python
from kaizen.runtime.routing import TaskAnalyzer

analyzer = TaskAnalyzer()

# Analyze a task
analysis = await analyzer.analyze("Fix the bug in src/main.py")

print(f"Type: {analysis.task_type}")           # "coding"
print(f"Complexity: {analysis.complexity}")    # "medium"
print(f"Needs vision: {analysis.needs_vision}") # False
print(f"Context needed: {analysis.estimated_context_tokens}") # 4000
print(f"Output expected: {analysis.estimated_output_tokens}") # 2000
```

### Analysis Results

```python
@dataclass
class TaskAnalysis:
    """Result of task analysis."""

    task_type: str  # "coding", "reasoning", "creative", "qa", "analysis"
    complexity: str  # "simple", "medium", "complex"

    # Requirements
    needs_vision: bool = False
    needs_audio: bool = False
    needs_function_calling: bool = False
    needs_json_output: bool = False
    needs_long_context: bool = False

    # Estimates
    estimated_context_tokens: int = 0
    estimated_output_tokens: int = 0

    # Quality requirements
    min_reasoning_score: float = 0.0
    min_coding_score: float = 0.0
    min_creativity_score: float = 0.0
```

## LLMRouter

### Basic Usage

```python
from kaizen.runtime.routing import LLMRouter

router = LLMRouter()

# Register models
router.register_model(LLMCapabilities(
    model_id="gpt-4o",
    provider="openai",
    max_context_tokens=128000,
    reasoning_score=0.95,
    coding_score=0.9,
    cost_per_1k_input_tokens=2.5,
    cost_per_1k_output_tokens=10.0,
))

router.register_model(LLMCapabilities(
    model_id="claude-3-5-sonnet-20241022",
    provider="anthropic",
    max_context_tokens=200000,
    reasoning_score=0.92,
    coding_score=0.95,
    cost_per_1k_input_tokens=3.0,
    cost_per_1k_output_tokens=15.0,
))

router.register_model(LLMCapabilities(
    model_id="gpt-4o-mini",
    provider="openai",
    max_context_tokens=128000,
    reasoning_score=0.8,
    coding_score=0.75,
    cost_per_1k_input_tokens=0.15,
    cost_per_1k_output_tokens=0.6,
))

# Route a task
model = await router.route("Explain quantum computing simply")
print(f"Selected: {model.model_id}")  # Might select gpt-4o-mini (cost-effective for simple explanation)
```

### Routing Strategies

```python
# Cost-optimized (default)
model = await router.route(task, strategy="cost_optimized")

# Quality-first
model = await router.route(task, strategy="quality_first")

# Latency-optimized
model = await router.route(task, strategy="latency_optimized")

# Balanced
model = await router.route(task, strategy="balanced")
```

### Strategy Comparison

| Strategy | Optimizes For | Use Case |
|----------|---------------|----------|
| `cost_optimized` | Lowest cost | Budget-conscious apps |
| `quality_first` | Highest capability | Critical tasks |
| `latency_optimized` | Fastest response | Real-time apps |
| `balanced` | Cost-quality balance | General use |

## RoutingRule

Explicit rules for specific scenarios:

```python
from kaizen.runtime.routing import RoutingRule

# Always use Claude for coding
router.add_rule(RoutingRule(
    name="coding_to_claude",
    condition=lambda analysis: analysis.task_type == "coding",
    model_id="claude-3-5-sonnet-20241022",
    priority=100,  # Higher = checked first
))

# Use GPT-4o for vision tasks
router.add_rule(RoutingRule(
    name="vision_to_gpt4o",
    condition=lambda analysis: analysis.needs_vision,
    model_id="gpt-4o",
    priority=90,
))

# Use mini for simple questions
router.add_rule(RoutingRule(
    name="simple_to_mini",
    condition=lambda analysis: analysis.complexity == "simple",
    model_id="gpt-4o-mini",
    priority=50,
))
```

### Rule Evaluation Order

Rules are evaluated by priority (highest first):

```
1. Check explicit rules (by priority)
2. If no rule matches, use strategy-based selection
3. Apply capability filters
4. Select best match
```

## FallbackRouter

Automatic fallback when primary model fails:

```python
from kaizen.runtime.routing import FallbackRouter

fallback = FallbackRouter()

# Define fallback chains
fallback.set_chain("coding", [
    "claude-3-5-sonnet-20241022",  # Primary
    "gpt-4o",                       # First fallback
    "gpt-4o-mini",                  # Last resort
])

fallback.set_chain("vision", [
    "gpt-4o",
    "gemini-1.5-pro",
])

# Use with router
router = LLMRouter(fallback_router=fallback)
```

### Fallback Triggers

Fallback occurs on:
- **Rate limiting** - Model is throttled
- **Timeout** - Model too slow
- **Error** - Model returns error
- **Capability mismatch** - Model can't handle task

```python
# Configure fallback behavior
fallback = FallbackRouter(
    max_retries=3,
    retry_delay_seconds=1.0,
    escalate_on_rate_limit=True,
    escalate_on_timeout=True,
)
```

## Integration with Agents

### Using Router with Agent

```python
from kaizen.agent import Agent
from kaizen.runtime.routing import LLMRouter

router = LLMRouter()
# ... register models ...

agent = Agent(
    router=router,
    execution_mode="autonomous",
)

# Router selects model for each task
await agent.run("Write a Python function")  # Claude (coding)
await agent.run("What is 2+2?")             # gpt-4o-mini (simple)
```

### Per-Task Override

```python
# Force specific model for a task
await agent.run("Critical task", model="gpt-4o")

# Let router decide
await agent.run("Some task")
```

## Cost Tracking

### Track Spending

```python
# Get cost statistics
stats = router.get_cost_stats()
print(f"Total cost: ${stats.total_cost:.4f}")
print(f"Requests: {stats.total_requests}")
print(f"Tokens: {stats.total_tokens}")

# Per-model breakdown
for model_id, cost in stats.by_model.items():
    print(f"  {model_id}: ${cost:.4f}")
```

### Budget Limits

```python
router = LLMRouter(
    budget_limit=10.0,  # Max $10 total
    per_request_limit=0.50,  # Max $0.50 per request
)

# Check remaining budget
remaining = router.get_remaining_budget()
print(f"Budget remaining: ${remaining:.2f}")
```

## Custom Task Analyzer

### Extend Analysis

```python
from kaizen.runtime.routing import TaskAnalyzer, TaskAnalysis

class CustomTaskAnalyzer(TaskAnalyzer):
    """Custom analyzer with domain-specific logic."""

    async def analyze(self, task: str) -> TaskAnalysis:
        # Start with base analysis
        analysis = await super().analyze(task)

        # Add custom logic
        if "medical" in task.lower():
            analysis.min_reasoning_score = 0.95
            analysis.task_type = "medical_reasoning"

        if "legal" in task.lower():
            analysis.complexity = "complex"
            analysis.min_reasoning_score = 0.9

        return analysis

router = LLMRouter(analyzer=CustomTaskAnalyzer())
```

## Model Registry

### Pre-configured Models

```python
from kaizen.runtime.routing import ModelRegistry

# Get pre-configured models
registry = ModelRegistry.default()

# Access specific model
gpt4o = registry.get("gpt-4o")
claude = registry.get("claude-3-5-sonnet-20241022")

# Register all with router
router = LLMRouter()
for model in registry.all():
    router.register_model(model)
```

### Update Model Capabilities

```python
# Update capabilities (e.g., after price change)
registry.update("gpt-4o", LLMCapabilities(
    model_id="gpt-4o",
    cost_per_1k_input_tokens=2.0,  # Updated price
    # ... other fields
))
```

## Testing Routing

```python
import pytest
from kaizen.runtime.routing import LLMRouter, TaskAnalyzer, LLMCapabilities

@pytest.fixture
def router():
    r = LLMRouter()
    r.register_model(LLMCapabilities(
        model_id="model-a",
        provider="test",
        max_context_tokens=100000,
        reasoning_score=0.9,
        coding_score=0.9,
        cost_per_1k_input_tokens=1.0,
    ))
    r.register_model(LLMCapabilities(
        model_id="model-b",
        provider="test",
        max_context_tokens=100000,
        reasoning_score=0.7,
        coding_score=0.6,
        cost_per_1k_input_tokens=0.1,
    ))
    return r

@pytest.mark.asyncio
async def test_routes_simple_to_cheaper(router):
    model = await router.route("What is 2+2?", strategy="cost_optimized")
    assert model.model_id == "model-b"  # Cheaper model

@pytest.mark.asyncio
async def test_routes_complex_to_better(router):
    model = await router.route(
        "Implement a distributed consensus algorithm",
        strategy="quality_first"
    )
    assert model.model_id == "model-a"  # Higher capability
```

## Observability

### Routing Metrics

```python
# Enable metrics collection
router = LLMRouter(enable_metrics=True)

# Get routing statistics
metrics = router.get_metrics()
print(f"Total routes: {metrics.total_routes}")
print(f"Rule matches: {metrics.rule_matches}")
print(f"Fallbacks: {metrics.fallback_count}")
print(f"Avg latency: {metrics.avg_routing_latency_ms}ms")
```

### Logging

```python
import logging
logging.getLogger("kaizen.routing").setLevel(logging.DEBUG)

# Now see detailed routing decisions
# [DEBUG] Analyzing task: "Write a Python function..."
# [DEBUG] Analysis: type=coding, complexity=medium
# [DEBUG] Checking rule: coding_to_claude (priority=100)
# [DEBUG] Rule matched, selecting claude-3-5-sonnet-20241022
```

## Best Practices

1. **Register multiple models** - Enable cost/capability tradeoffs
2. **Use explicit rules** for critical tasks - Don't leave important decisions to heuristics
3. **Set budget limits** - Protect against runaway costs
4. **Configure fallbacks** - Handle rate limits and errors gracefully
5. **Monitor routing decisions** - Enable logging during development
6. **Update capabilities** - Keep model capabilities current

```python
# Good: Comprehensive routing setup
router = LLMRouter(
    analyzer=TaskAnalyzer(),
    fallback_router=FallbackRouter(),
    budget_limit=100.0,
    enable_metrics=True,
)

# Register models
for model in ModelRegistry.default().all():
    router.register_model(model)

# Add critical rules
router.add_rule(RoutingRule(
    name="always_premium_for_production",
    condition=lambda a: os.environ.get("ENV") == "production",
    model_id="gpt-4o",
    priority=200,
))
```
