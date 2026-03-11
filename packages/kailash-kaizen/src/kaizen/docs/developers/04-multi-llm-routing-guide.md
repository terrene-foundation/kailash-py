# Multi-LLM Routing Guide

This guide covers the Multi-LLM Routing system for Kaizen agents, enabling intelligent model selection based on task requirements, cost optimization, and fallback chains.

## Overview

The Multi-LLM Routing system provides:

- **Task Analysis**: Automatic detection of task complexity and type
- **Intelligent Routing**: Route tasks to optimal models based on requirements
- **Cost Optimization**: Minimize costs while meeting quality requirements
- **Fallback Chains**: Automatic failover when providers are unavailable

**Important**: Multi-LLM routing ONLY works with LocalKaizenAdapter. External runtimes (Claude Code, OpenAI Codex, Gemini CLI) are locked to their native models.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      LLMRouter                              │
│  route(task, strategy, requirements) -> RoutingDecision     │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  TaskAnalyzer   │  │ MODEL_REGISTRY  │  │  RoutingRules   │
│ (complexity,    │  │ (capabilities,  │  │ (explicit       │
│  type, reqs)    │  │  costs, specs)  │  │  overrides)     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ FallbackRouter  │
                    │ (retry, chain)  │
                    └─────────────────┘
```

## Quick Start

```python
from kaizen.llm.routing import (
    LLMRouter,
    RoutingStrategy,
    FallbackRouter,
    create_fallback_router,
)

# Simple routing
router = LLMRouter(
    available_models=["gpt-4", "gpt-3.5-turbo", "claude-3-opus"],
    default_model="gpt-4",
)

# Route a task
decision = router.route(
    task="Write a Python function to sort a list",
    strategy=RoutingStrategy.BALANCED,
)
print(f"Selected model: {decision.model}")
print(f"Reasoning: {decision.reasoning}")

# With fallback support
fallback_router = create_fallback_router(
    primary_model="gpt-4",
    fallback_models=["claude-3-opus", "gpt-3.5-turbo"],
)

result = await fallback_router.route_with_fallback(
    task="Complex reasoning task",
    execute_fn=lambda model: llm_provider.chat(model=model, messages=[...]),
)

if result.success:
    print(f"Response from {result.model_used}: {result.result}")
```

## Model Registry

### LLMCapabilities

Each model has a capabilities profile:

```python
from kaizen.llm.routing import LLMCapabilities, register_model, get_model_capabilities

# Get pre-registered model
caps = get_model_capabilities("gpt-4")
print(f"Quality: {caps.quality_score}")
print(f"Cost per 1k tokens: ${caps.cost_per_1k_output}")
print(f"Specialties: {caps.specialties}")

# Check capabilities
if caps.supports_vision and caps.supports_tool_calling:
    print("Supports multimodal with tools")

# Estimate cost
estimated_cost = caps.estimate_cost(input_tokens=1000, output_tokens=500)
print(f"Estimated cost: ${estimated_cost:.4f}")

# Check requirements
if caps.matches_requirements(
    requires_vision=True,
    requires_tools=True,
    min_quality=0.9,
    min_context=100000,
):
    print("Model meets all requirements")
```

### Pre-Registered Models

The registry includes major models:

| Provider | Models | Specialties |
|----------|--------|-------------|
| OpenAI | gpt-4, gpt-4-turbo, gpt-4o, gpt-4o-mini, gpt-3.5-turbo, o1, o1-mini | reasoning, code |
| Anthropic | claude-3-opus, claude-3-sonnet, claude-3.5-sonnet, claude-3-haiku, claude-3.5-haiku | reasoning, code, analysis |
| Google | gemini-pro, gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash | multimodal, long-context |
| Ollama | llama3.2, codellama, mistral, deepseek-coder, qwen2.5-coder | local, code |

### Registering Custom Models

```python
from kaizen.llm.routing import LLMCapabilities, register_model

custom_model = LLMCapabilities(
    provider="custom",
    model="my-fine-tuned-model",
    supports_vision=False,
    supports_tool_calling=True,
    max_context=32000,
    max_output=4096,
    cost_per_1k_input=0.001,
    cost_per_1k_output=0.002,
    quality_score=0.88,
    specialties=["domain-specific", "code"],
)

register_model(custom_model)
```

### Listing Models

```python
from kaizen.llm.routing import list_models

# All models
all_models = list_models()

# Filter by provider
openai_models = list_models(provider="openai")

# Filter by capability
vision_models = list_models(supports_vision=True)

# Filter by quality
high_quality = list_models(min_quality=0.9)

# Filter by specialty
code_specialists = list_models(specialty="code")

# Combined filters
fast_code = list_models(
    provider="ollama",
    supports_tools=True,
    specialty="code",
)
```

## Task Analysis

### Automatic Analysis

The TaskAnalyzer automatically detects:

```python
from kaizen.llm.routing import TaskAnalyzer, TaskType, TaskComplexity

analyzer = TaskAnalyzer()

# Analyze a task
analysis = analyzer.analyze(
    task="Implement a REST API with authentication",
    context={"has_tools": True},
)

print(f"Type: {analysis.type}")           # TaskType.CODE
print(f"Complexity: {analysis.complexity}") # TaskComplexity.MEDIUM
print(f"Requires tools: {analysis.requires_tools}")
print(f"Specialties needed: {analysis.specialties_needed}")
print(f"Estimated tokens: {analysis.estimated_tokens}")
```

### Task Types

| Type | Description | Indicators |
|------|-------------|------------|
| SIMPLE_QA | Simple questions | what is, define, short questions |
| CODE | Code generation/debugging | function, class, implement, debug |
| ANALYSIS | Data analysis, evaluation | analyze, evaluate, compare, study |
| CREATIVE | Writing, content generation | write, compose, create, story |
| STRUCTURED | JSON/YAML output | json, yaml, format, extract |
| REASONING | Complex logical reasoning | prove, derive, step by step |
| MULTIMODAL | Image/audio processing | Context: has_images, has_audio |

### Complexity Levels

| Level | Description | Model Selection |
|-------|-------------|-----------------|
| TRIVIAL | One-word answers | Cheapest model (0.6+ quality) |
| LOW | Basic Q&A | Budget models (0.7+ quality) |
| MEDIUM | Moderate tasks | Standard models (0.8+ quality) |
| HIGH | Multi-step reasoning | Premium models (0.9+ quality) |
| EXPERT | Domain expertise | Top-tier models (0.95+ quality) |

## Routing Strategies

### Available Strategies

```python
from kaizen.llm.routing import LLMRouter, RoutingStrategy

router = LLMRouter(available_models=["gpt-4", "gpt-3.5-turbo", "claude-3-opus"])

# RULES: Apply explicit rules only
decision = router.route(task, strategy=RoutingStrategy.RULES)

# TASK_COMPLEXITY: Route by analyzed complexity
decision = router.route(task, strategy=RoutingStrategy.TASK_COMPLEXITY)

# COST_OPTIMIZED: Minimize cost
decision = router.route(task, strategy=RoutingStrategy.COST_OPTIMIZED)

# QUALITY_OPTIMIZED: Maximize quality
decision = router.route(task, strategy=RoutingStrategy.QUALITY_OPTIMIZED)

# BALANCED (recommended): Balance cost, quality, and specialties
decision = router.route(task, strategy=RoutingStrategy.BALANCED)
```

### Strategy Recommendations

| Use Case | Recommended Strategy |
|----------|---------------------|
| Development/Testing | QUALITY_OPTIMIZED |
| Production (general) | BALANCED |
| High-volume/Budget | COST_OPTIMIZED |
| Critical tasks | RULES with explicit model |

### Balanced Scoring

The BALANCED strategy uses weighted scoring:
- 40% Quality (normalized 0-1)
- 30% Cost efficiency (inverted, lower cost = higher score)
- 30% Specialty bonus (matching task specialties)

## Routing Rules

### Adding Rules

```python
from kaizen.llm.routing import LLMRouter, TaskType, TaskComplexity

router = LLMRouter()

# Custom condition rule
router.add_rule(
    name="production_critical",
    condition=lambda task, ctx: ctx.get("is_production", False),
    model="gpt-4",
    priority=100,  # Higher priority evaluated first
    description="Use GPT-4 for production",
)

# Keyword-based rule
router.add_keyword_rule(
    keywords=["simple", "quick", "basic"],
    model="gpt-3.5-turbo",
    priority=5,
)

# Task type rule
router.add_type_rule(
    task_type=TaskType.CODE,
    model="claude-3.5-sonnet",
    priority=10,
)

# Complexity threshold rule
router.add_complexity_rule(
    min_complexity=TaskComplexity.EXPERT,
    model="o1",
    priority=20,
)
```

### Rule Priority

Rules are evaluated in priority order (highest first). First matching rule wins:

```python
# High priority always wins
router.add_rule("always_use_gpt4", lambda t, c: True, "gpt-4", priority=100)
router.add_rule("never_matches", lambda t, c: True, "gpt-3.5-turbo", priority=1)

decision = router.route("any task", strategy=RoutingStrategy.RULES)
assert decision.model == "gpt-4"  # High priority rule matched
```

## Capability Requirements

### Automatic Requirements

Requirements are detected from task analysis:

```python
decision = router.route(
    task="Describe this image",
    context={"has_images": True},  # Vision detected
)
# Router filters to vision-capable models
```

### Explicit Requirements

Override detected requirements:

```python
decision = router.route(
    task="Any task",
    required_capabilities={
        "vision": True,
        "tools": True,
        "structured": True,
    },
)
```

## Fallback Routing

### Basic Fallback

```python
from kaizen.llm.routing import FallbackRouter

router = FallbackRouter(
    available_models=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
    fallback_chain=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
    max_retries=2,
    retry_delay_seconds=1.0,
    exponential_backoff=True,
)

# Async execution with fallback
result = await router.route_with_fallback(
    task="Complex task",
    execute_fn=async_llm_call,
)

if result.success:
    print(f"Model used: {result.model_used}")
    print(f"Attempts: {result.attempts}")
else:
    print(f"All models failed: {result.error}")
    for event in result.fallback_events:
        print(f"  {event.original_model} -> {event.fallback_model}: {event.error_type}")

# Sync version
result = router.route_with_fallback_sync(
    task="Task",
    execute_fn=sync_llm_call,
)
```

### Error Classification

Fallback triggers for transient errors:
- Rate limits
- Timeouts
- Service unavailable
- Connection errors

Fallback does NOT trigger for:
- Authentication errors
- Permission denied
- Invalid request

### Chain Management

```python
# Set fallback chain
router.set_fallback_chain(["gpt-4", "claude-3-opus", "gemini-1.5-pro"])

# Add to chain
router.add_to_fallback_chain("gpt-3.5-turbo")
router.add_to_fallback_chain("llama3.2", position=2)

# Remove from chain
router.remove_from_fallback_chain("old-model")

# View fallback events
for event in router.fallback_events:
    print(f"{event.original_model} failed: {event.error_type}")

router.clear_fallback_events()
```

### Quick Fallback Router

```python
from kaizen.llm.routing import create_fallback_router

# Simple setup with sensible defaults
router = create_fallback_router(
    primary_model="gpt-4",
    fallback_models=["claude-3-opus", "gpt-3.5-turbo"],
    max_retries=2,
)
```

## Routing Decision

The `RoutingDecision` contains complete routing information:

```python
decision = router.route(task, strategy=RoutingStrategy.BALANCED)

# Selected model
print(f"Model: {decision.model}")

# Strategy used
print(f"Strategy: {decision.strategy}")

# Rule that matched (if any)
if decision.rule_name:
    print(f"Matched rule: {decision.rule_name}")

# Task analysis (if performed)
if decision.analysis:
    print(f"Task type: {decision.analysis.type}")
    print(f"Complexity: {decision.analysis.complexity}")

# Explanation
print(f"Reasoning: {decision.reasoning}")

# Alternative models
print(f"Alternatives: {decision.alternatives}")

# Serialize
data = decision.to_dict()
```

## Integration Example

### With LocalKaizenAdapter

```python
from kaizen.runtime import LocalKaizenAdapter
from kaizen.llm.routing import LLMRouter, FallbackRouter, RoutingStrategy

# Create router
router = FallbackRouter(
    available_models=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
    fallback_chain=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
)

# Add routing rules
router.add_keyword_rule(
    keywords=["simple", "quick"],
    model="gpt-3.5-turbo",
    priority=10,
)

# In your adapter
class RoutedKaizenAdapter(LocalKaizenAdapter):
    def __init__(self, router: LLMRouter, **kwargs):
        super().__init__(**kwargs)
        self._router = router

    async def _select_model(self, task: str, context: dict) -> str:
        decision = self._router.route(
            task=task,
            context=context,
            strategy=RoutingStrategy.BALANCED,
        )
        return decision.model

    async def _think_phase(self, state):
        # Get task from state
        task = state.current_task

        # Route to optimal model
        model = await self._select_model(task, {"session_id": state.session_id})

        # Execute with selected model
        # ...
```

## Best Practices

### 1. Start with Balanced Strategy

The BALANCED strategy provides good defaults:

```python
router = LLMRouter(default_model="gpt-4")
decision = router.route(task, strategy=RoutingStrategy.BALANCED)
```

### 2. Use Rules for Special Cases

Override routing for specific needs:

```python
# Always use premium for production
router.add_rule(
    "production",
    lambda t, ctx: ctx.get("env") == "production",
    "gpt-4",
    priority=100,
)
```

### 3. Set Up Fallback Chains

Always have fallbacks for resilience:

```python
router = FallbackRouter(
    fallback_chain=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
)
```

### 4. Register Custom Models

Add your fine-tuned or self-hosted models:

```python
register_model(LLMCapabilities(
    provider="self-hosted",
    model="fine-tuned-v1",
    # ... capabilities
))
```

### 5. Monitor Fallback Events

Track provider reliability:

```python
# After operations
for event in router.fallback_events:
    log_metric("llm_fallback", {
        "original": event.original_model,
        "fallback": event.fallback_model,
        "error": event.error_type,
    })
```

## See Also

- [Memory Provider Guide](03-memory-provider-guide.md) - Memory for autonomous agents
- [LocalKaizenAdapter Guide](02-local-kaizen-adapter-guide.md) - TAOD loop implementation
- [Runtime Abstraction Guide](01-runtime-abstraction-guide.md) - Multi-runtime support
