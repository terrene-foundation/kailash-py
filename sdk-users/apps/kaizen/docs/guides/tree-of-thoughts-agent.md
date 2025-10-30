# Tree-of-Thoughts Agent - Multi-Path Exploration Pattern

## What is the Tree-of-Thoughts (ToT) Agent?

The Tree-of-Thoughts Agent implements **parallel path exploration** (Generate N paths → Evaluate → Select Best → Execute) where multiple reasoning paths are explored simultaneously and the best one is selected based on evaluation scores. This "Explore Multiple Paths" approach ensures the best solution is found through comprehensive exploration.

**Pattern**: Generate multiple independent reasoning paths → Evaluate each path → Select highest-scoring path → Execute only the best

## When to Use

Use Tree-of-Thoughts Agent when:
- **Multiple valid approaches** exist and you need to explore alternatives
- **Strategic decision-making** where different perspectives improve outcomes
- **Creative problem-solving** that benefits from diverse solutions
- **Uncertainty about optimal path** requires exploration of alternatives
- **Trade-off analysis** where different paths have different strengths
- **Quality through diversity** where exploring alternatives finds better solutions

**Ideal for**:
- Strategic business decisions
- Creative content generation
- System design alternatives
- Problem-solving with multiple solutions
- Trade-off analysis
- Competitive analysis

## When NOT to Use

Avoid Tree-of-Thoughts Agent when:
- **Single path obviously best** (use SimpleQA or Planning instead)
- **Real-time constraints** where generating N paths is too slow (use single-shot patterns)
- **Simple deterministic tasks** where multiple paths don't add value
- **High cost sensitivity** (generating N paths is N× more expensive)
- **Linear workflows** where sequential execution is clearer (use Planning instead)

## Complete Working Example

```python
"""
Tree-of-Thoughts Agent Example - Strategic Decision Making

Demonstrates Generate → Evaluate → Select → Execute workflow for multi-path exploration.
"""

import os
from dotenv import load_dotenv
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig

# Load environment variables
load_dotenv()

# Configuration
config = ToTAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.9,  # Higher temperature for diversity
    num_paths=5,  # Generate 5 alternative paths
    max_paths=20,  # Safety limit
    evaluation_criteria="quality",  # quality, speed, or creativity
    parallel_execution=True,  # Generate paths in parallel
    timeout=30,
    max_retries=3
)

# Create agent
agent = ToTAgent(config=config)

# Task: Strategic decision requiring multiple perspectives
task = """
A startup has $500K in seed funding and needs to decide on the best
go-to-market strategy. Options include:

A) Enterprise B2B sales (high value, long sales cycle)
B) Consumer B2C freemium model (viral growth, monetization challenge)
C) Platform/marketplace approach (network effects, chicken-egg problem)
D) Vertical integration (control but capital-intensive)

Consider:
- Market size and competition
- Time to revenue
- Resource requirements
- Scalability potential
- Risk factors

Recommend the best strategy with detailed reasoning.
"""

# Execute multi-path exploration
print(f"Generating {config.num_paths} reasoning paths...")
result = agent.run(task=task)

# Display all paths and evaluations

# Path Exploration
print("=" * 80)
print(f"PATH EXPLORATION ({len(result['paths'])} paths)")
print("=" * 80)
for i, evaluation in enumerate(result["evaluations"], 1):
    score = evaluation.get("score", 0.0)
    path = evaluation.get("path", {})
    reasoning_preview = path.get("reasoning", "")[:100]

    print(f"\nPath {i}:")
    print(f"  Score: {score:.2f} {'⭐' * int(score * 5)}")
    print(f"  Preview: {reasoning_preview}...")

# Best Path Selection
print("\n" + "=" * 80)
print("BEST PATH SELECTED")
print("=" * 80)
best_path = result["best_path"]
print(f"Score: {best_path.get('score', 0.0):.2f}")
print(f"Reasoning: {best_path.get('reasoning', 'See details below')}")

# Final Recommendation
print("\n" + "=" * 80)
print("FINAL RECOMMENDATION")
print("=" * 80)
print(result["final_result"])

# Score Distribution Analysis
print("\n" + "=" * 80)
print("SCORE DISTRIBUTION")
print("=" * 80)
scores = [eval.get("score", 0.0) for eval in result["evaluations"]]
print(f"Min Score: {min(scores):.2f}")
print(f"Max Score: {max(scores):.2f}")
print(f"Avg Score: {sum(scores)/len(scores):.2f}")
print(f"Range: {max(scores) - min(scores):.2f}")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Paths Explored: {len(result['paths'])}")
print(f"Best Score: {best_path.get('score', 0.0):.2f}")
print(f"Evaluation Criteria: {config.evaluation_criteria}")
print(f"Temperature: {config.temperature} (higher = more diverse)")
print(f"Parallel Execution: {'Enabled' if config.parallel_execution else 'Disabled'}")

# Error handling
if "error" in result:
    print(f"\nError: {result['error']}")
```

**Output Example**:
```
Generating 5 reasoning paths...
================================================================================
PATH EXPLORATION (5 paths)
================================================================================

Path 1:
  Score: 0.85 ⭐⭐⭐⭐
  Preview: Recommend B2B enterprise sales strategy for sustainable revenue with $500K seed funding. High-...

Path 2:
  Score: 0.72 ⭐⭐⭐
  Preview: Freemium B2C approach offers fastest market penetration but monetization risks are high for...

Path 3:
  Score: 0.90 ⭐⭐⭐⭐⭐
  Preview: Platform marketplace provides strongest long-term position through network effects and defensi...

Path 4:
  Score: 0.65 ⭐⭐⭐
  Preview: Vertical integration requires $2M+ capital, exceeds current funding. Not viable with $500K...

Path 5:
  Score: 0.80 ⭐⭐⭐⭐
  Preview: Hybrid approach: Start B2C for user acquisition, pivot to B2B for monetization. Best of both...

================================================================================
BEST PATH SELECTED
================================================================================
Score: 0.90
Reasoning: Platform marketplace strategy selected

================================================================================
FINAL RECOMMENDATION
================================================================================
Recommended Strategy: Platform/Marketplace Approach

Rationale:
1. Network Effects: Creates defensible moat as platform grows
2. Scalability: Can handle both supply and demand sides
3. Resource Fit: $500K sufficient for MVP marketplace
4. Market Timing: Emerging markets favor platform plays
5. Risk Mitigation: Multiple revenue streams reduce risk

Implementation Plan:
1. Month 1-3: Build core marketplace infrastructure
2. Month 4-6: Acquire seed users on supply side
3. Month 7-9: Launch demand side with marketing push
4. Month 10-12: Optimize matching and retention

Key Metrics:
- GMV (Gross Merchandise Value)
- Take rate (platform commission)
- User acquisition cost vs. LTV
- Supply/demand balance

================================================================================
SCORE DISTRIBUTION
================================================================================
Min Score: 0.65
Max Score: 0.90
Avg Score: 0.78
Range: 0.25

================================================================================
SUMMARY
================================================================================
Paths Explored: 5
Best Score: 0.90
Evaluation Criteria: quality
Temperature: 0.9 (higher = more diverse)
Parallel Execution: Enabled
```

## Configuration Options

### Core LLM Configuration
```python
config = ToTAgentConfig(
    # LLM Provider Settings
    llm_provider="openai",     # "openai", "anthropic", "ollama"
    model="gpt-4",             # Provider-specific model
    temperature=0.9,           # 0.0-1.0 (HIGH for path diversity)
    max_tokens=2000,           # Maximum response tokens
)
```

### ToT-Specific Configuration
```python
config = ToTAgentConfig(
    # Path Control
    num_paths=5,               # Number of paths to generate (1-20)
    max_paths=20,              # Safety limit to prevent explosion

    # Evaluation Control
    evaluation_criteria="quality",  # "quality", "speed", "creativity"

    # Execution Control
    parallel_execution=True,   # Generate paths in parallel (faster)

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

**Evaluation Criteria**:
- `quality`: Evaluates completeness, error-free execution, structured reasoning
- `speed`: Prioritizes faster paths (useful for time-sensitive decisions)
- `creativity`: Favors novel, creative approaches

**Critical**: Use `temperature=0.9` (high) for path diversity. Low temperature generates similar paths.

### Environment Variable Support
```bash
# .env file configuration (auto-loaded)
KAIZEN_LLM_PROVIDER=openai
KAIZEN_MODEL=gpt-4
KAIZEN_TEMPERATURE=0.9
KAIZEN_MAX_TOKENS=2000
```

```python
# Uses environment variables by default
agent = ToTAgent()  # Zero-config usage
```

## Common Pitfalls & Gotchas

### 1. Low Temperature Reduces Diversity
**Problem**: Using low temperature generates nearly identical paths.

**Solution**: Use high temperature (0.8-1.0) for diversity.

```python
# ❌ WRONG: Low temperature = similar paths
config = ToTAgentConfig(temperature=0.3, num_paths=10)  # 10 similar paths

# ✅ CORRECT: High temperature = diverse paths
config = ToTAgentConfig(temperature=0.9, num_paths=5)  # 5 diverse paths
```

### 2. Too Many Paths Increases Cost
**Problem**: Generating 20 paths costs 20× single-path execution.

**Solution**: Balance path count with cost and time constraints.

```python
# ❌ WRONG: Too many paths for simple task
config = ToTAgentConfig(num_paths=20)  # Expensive!

# ✅ CORRECT: Appropriate path count
simple_config = ToTAgentConfig(num_paths=3)    # Simple decisions
strategic_config = ToTAgentConfig(num_paths=7) # Strategic decisions
critical_config = ToTAgentConfig(num_paths=10) # Mission-critical
```

### 3. Serial Execution Bottleneck
**Problem**: Serial path generation takes N× longer than parallel.

**Solution**: Enable parallel execution for faster results.

```python
# ❌ WRONG: Serial execution
config = ToTAgentConfig(
    num_paths=10,
    parallel_execution=False  # 10× slower!
)

# ✅ CORRECT: Parallel execution
config = ToTAgentConfig(
    num_paths=10,
    parallel_execution=True  # 10 paths in parallel
)
```

### 4. Not Analyzing Score Distribution
**Problem**: Accepting best path without checking if other paths scored similarly.

**Solution**: Analyze score distribution to understand path quality variance.

```python
# ❌ WRONG: Only checking best path
result = agent.run(task=task)
best = result["best_path"]
print(best["score"])

# ✅ CORRECT: Analyze distribution
result = agent.run(task=task)
scores = [eval["score"] for eval in result["evaluations"]]

# Check if best path is significantly better
best_score = max(scores)
second_best = sorted(scores, reverse=True)[1]
margin = best_score - second_best

if margin < 0.1:
    print(f"WARNING: Best path margin is only {margin:.2f}")
    print("Consider reviewing top 2-3 paths, not just #1")
```

### 5. Ignoring Low-Scoring Paths
**Problem**: Low scores might indicate important risks or constraints.

**Solution**: Review low-scoring paths for risk identification.

```python
# ❌ WRONG: Only looking at best path
best_path = result["best_path"]
recommendation = best_path["path"]["reasoning"]

# ✅ CORRECT: Review all paths for insights
print("HIGH SCORING PATHS (opportunities):")
for eval in sorted(result["evaluations"], key=lambda e: e["score"], reverse=True)[:2]:
    print(f"  Score {eval['score']:.2f}: {eval['path']['reasoning'][:100]}...")

print("\nLOW SCORING PATHS (risks):")
for eval in sorted(result["evaluations"], key=lambda e: e["score"])[:2]:
    print(f"  Score {eval['score']:.2f}: {eval['path']['reasoning'][:100]}...")
```

### 6. Exceeding max_paths Limit
**Problem**: Setting num_paths > max_paths causes validation error.

**Solution**: Ensure num_paths ≤ max_paths.

```python
# ❌ WRONG: num_paths exceeds max_paths
config = ToTAgentConfig(num_paths=25, max_paths=20)  # ValueError!

# ✅ CORRECT: num_paths within limit
config = ToTAgentConfig(num_paths=15, max_paths=20)

# ✅ CORRECT: Increase max_paths if needed
config = ToTAgentConfig(num_paths=25, max_paths=30)
```

## Comparison with Similar Patterns

### ToT vs Chain-of-Thought (CoT)
| Aspect | Tree-of-Thoughts | Chain-of-Thought |
|--------|------------------|------------------|
| **Reasoning Paths** | Multiple parallel paths | Single linear path |
| **Exploration** | Explores N alternatives | Single reasoning chain |
| **Selection** | Best path selected | No selection needed |
| **Cost** | N× higher (N paths) | 1× (single path) |
| **Best For** | Alternative exploration | Step-by-step reasoning |
| **Diversity** | High (via temperature) | Low (single chain) |

**When to Switch**:
- **ToT → CoT**: Single path sufficient, cost is concern
- **CoT → ToT**: Need alternatives, multiple valid approaches exist

### ToT vs ReAct
| Aspect | Tree-of-Thoughts | ReAct |
|--------|------------------|-------|
| **Path Generation** | Parallel upfront | Sequential as needed |
| **Adaptation** | Path selection | Real-time observation |
| **Exploration** | All paths at once | One path with branching |
| **Evaluation** | Score-based selection | Observation-based |
| **Best For** | Strategic decisions | Dynamic problem-solving |
| **Transparency** | All alternatives visible | Reasoning+action trace |

**When to Switch**:
- **ToT → ReAct**: Need real-time adaptation, not upfront exploration
- **ReAct → ToT**: Have clear alternatives, want comprehensive exploration

### ToT vs PEV
| Aspect | Tree-of-Thoughts | PEV |
|--------|------------------|-----|
| **Exploration** | Multiple parallel paths | Single path, refined |
| **Improvement** | Path selection | Iterative refinement |
| **Cycles** | Single generation + evaluation | Multiple refine cycles |
| **Quality** | Diversity-driven | Verification-driven |
| **Best For** | Alternative exploration | Quality refinement |
| **Overhead** | Higher (N paths) | Moderate (K iterations) |

**When to Switch**:
- **ToT → PEV**: Single path sufficient, need quality refinement
- **PEV → ToT**: Need alternatives, not iterative improvement

## Best Practices

### 1. Tune Path Count Based on Task
```python
# Simple decisions - few paths
simple = ToTAgentConfig(num_paths=3)

# Strategic decisions - moderate paths
strategic = ToTAgentConfig(num_paths=7)

# Mission-critical - many paths
critical = ToTAgentConfig(num_paths=12)
```

### 2. Use High Temperature for Diversity
```python
# Ensure path diversity
config = ToTAgentConfig(
    temperature=0.9,  # 0.8-1.0 for diversity
    num_paths=5
)

# Lower temperature only if similar paths desired
config = ToTAgentConfig(
    temperature=0.5,  # Less diverse, more focused
    num_paths=3
)
```

### 3. Enable Parallel Execution
```python
# Production configuration
production_config = ToTAgentConfig(
    num_paths=7,
    parallel_execution=True,  # Much faster!
    timeout=30  # Per-path timeout
)
```

### 4. Analyze Score Distribution
```python
result = agent.run(task=task)

# Calculate statistics
scores = [eval["score"] for eval in result["evaluations"]]
mean = sum(scores) / len(scores)
std_dev = (sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5

print(f"Mean: {mean:.2f}, StdDev: {std_dev:.2f}")

# High std_dev = diverse quality
# Low std_dev = similar quality
if std_dev < 0.1:
    print("WARNING: All paths scored similarly, diversity may be low")
```

### 5. Review Top N Paths, Not Just Best
```python
# Consider top 3 paths for final decision
top_3 = sorted(result["evaluations"], key=lambda e: e["score"], reverse=True)[:3]

print("TOP 3 PATHS:")
for i, eval in enumerate(top_3, 1):
    print(f"\n{i}. Score: {eval['score']:.2f}")
    print(f"   {eval['path']['reasoning'][:200]}...")
```

### 6. Use Appropriate Evaluation Criteria
```python
# Quality-focused (default)
quality_config = ToTAgentConfig(evaluation_criteria="quality")

# Time-sensitive decisions
speed_config = ToTAgentConfig(evaluation_criteria="speed")

# Creative tasks
creative_config = ToTAgentConfig(evaluation_criteria="creativity")
```

## Performance Characteristics

- **Path Generation Latency**: 1-3 seconds per path
  - Serial: N × 1-3s (N paths sequentially)
  - Parallel: 1-3s (N paths concurrently, limited by semaphore to max 5 concurrent)
- **Evaluation Latency**: <200ms per path
- **Selection Latency**: <10ms (argmax over scores)
- **Total Latency**:
  - Parallel: ~5-10 seconds (5-10 paths)
  - Serial: ~15-30 seconds (5-10 paths)
- **Memory Usage**: ~50MB × num_paths (250MB for 5 paths)
- **Cost**: N× single-path execution (5 paths = 5× cost)

**Optimization Tips**:
- Use parallel execution (10× faster for 10 paths)
- Limit num_paths to essential alternatives (3-7 typical)
- Use lower temperature if diversity not needed
- Cache path evaluations for repeated tasks

## Integration Examples

### With Core SDK for Workflow Selection
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent

# Generate multiple workflow alternatives
agent = ToTAgent(ToTAgentConfig(num_paths=5))
task = "Design data processing pipeline for customer analytics"
result = agent.run(task=task)

# Implement best workflow
best_workflow_description = result["final_result"]

# Create Core SDK workflow from best path
workflow = WorkflowBuilder()
# Parse best path and add nodes
# ... (workflow construction logic)

# Execute best workflow
runtime = LocalRuntime()
runtime.execute(workflow.build())
```

### With DataFlow for Schema Alternatives
```python
from dataflow import DataFlow
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent

db = DataFlow()
agent = ToTAgent(ToTAgentConfig(num_paths=4))

# Explore schema design alternatives
task = "Design database schema for multi-tenant SaaS platform"
result = agent.run(task=task)

# Review top 2 schemas before selecting
top_2 = sorted(result["evaluations"], key=lambda e: e["score"], reverse=True)[:2]
for i, eval in enumerate(top_2, 1):
    print(f"Schema Option {i} (score {eval['score']:.2f}):")
    print(eval["path"]["reasoning"])

# Implement best schema
best_schema = result["final_result"]
db.execute_schema(best_schema)
```

### With Multi-Agent for Decision Committee
```python
from kaizen.orchestration.patterns import EnsemblePattern
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent

# Create ToT agents with different evaluation criteria
quality_agent = ToTAgent(ToTAgentConfig(evaluation_criteria="quality", num_paths=5))
speed_agent = ToTAgent(ToTAgentConfig(evaluation_criteria="speed", num_paths=5))
creative_agent = ToTAgent(ToTAgentConfig(evaluation_criteria="creativity", num_paths=5))

# Use ensemble to synthesize perspectives
pattern = EnsemblePattern(
    agents=[quality_agent, speed_agent, creative_agent],
    synthesizer=synthesis_agent
)

# Each ToT agent explores alternatives, synthesizer combines
result = pattern.run(task="Strategic product decision")
```

## Testing Tree-of-Thoughts Agent

```python
import pytest
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig

def test_tot_agent_basic():
    """Test basic multi-path exploration"""
    config = ToTAgentConfig(
        llm_provider="mock",
        num_paths=3,
        parallel_execution=False  # Serial for deterministic testing
    )
    agent = ToTAgent(config=config)

    result = agent.run(task="Make a decision")

    # Verify all components
    assert "paths" in result
    assert "evaluations" in result
    assert "best_path" in result
    assert "final_result" in result

    # Verify path count
    assert len(result["paths"]) == 3
    assert len(result["evaluations"]) == 3

def test_tot_agent_path_limit():
    """Test num_paths limit enforcement"""
    config = ToTAgentConfig(
        llm_provider="mock",
        num_paths=5,
        max_paths=20
    )
    agent = ToTAgent(config=config)

    result = agent.run(task="Decision task")

    # Should generate exactly num_paths
    assert len(result["paths"]) == 5

def test_tot_agent_best_path_selection():
    """Test best path has highest score"""
    config = ToTAgentConfig(
        llm_provider="mock",
        num_paths=5
    )
    agent = ToTAgent(config=config)

    result = agent.run(task="Decision task")

    # Best path should have max score
    best_score = result["best_path"]["score"]
    all_scores = [eval["score"] for eval in result["evaluations"]]

    assert best_score == max(all_scores)

def test_tot_agent_parallel_execution():
    """Test parallel path generation"""
    config = ToTAgentConfig(
        llm_provider="mock",
        num_paths=5,
        parallel_execution=True
    )
    agent = ToTAgent(config=config)

    import time
    start = time.time()
    result = agent.run(task="Decision task")
    duration = time.time() - start

    # Parallel should be faster than serial
    # (Actual timing depends on mock implementation)
    assert len(result["paths"]) == 5

def test_tot_agent_max_paths_validation():
    """Test max_paths validation"""
    with pytest.raises(ValueError):
        # Should fail: num_paths > max_paths
        ToTAgentConfig(num_paths=25, max_paths=20)
```

## See Also

- **[Planning Agent Guide](./planning-agent.md)** - Upfront planning with validation
- **[PEV Agent Guide](./pev-agent.md)** - Iterative refinement with verification
- **[Single-Agent Patterns Overview](./single-agent-patterns.md)** - All patterns comparison
- **[Multi-Agent Coordination](./multi-agent-coordination.md)** - Combining agents
- **[API Reference](../reference/api-reference.md)** - Complete API documentation
