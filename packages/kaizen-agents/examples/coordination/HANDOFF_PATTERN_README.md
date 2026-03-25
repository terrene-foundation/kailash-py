# Handoff Pattern

**Multi-agent coordination pattern for dynamic tier-based routing with automatic escalation**

## Overview

The Handoff Pattern enables you to route tasks dynamically to appropriate expertise tiers based on complexity. Agents automatically evaluate if they can handle a task and escalate to higher tiers when needed, creating intelligent tier-based systems.

### Key Features

- **Dynamic Routing**: Agents evaluate task complexity and decide if they can handle it
- **Automatic Escalation**: Tasks escalate to higher tiers when too complex for current tier
- **Tier Tracking**: All handoff decisions stored in shared memory with full audit trail
- **Expertise Discovery**: Pattern finds right tier level during execution
- **Max Tier Limit**: Configurable limits prevent infinite escalation
- **Zero-Config**: Works out-of-the-box with 3 default tiers
- **Progressive Configuration**: 4 levels from zero-config to full control

### When to Use

✅ **Use Handoff Pattern when**:
- You need tier-based escalation (L1 → L2 → L3 support)
- Task complexity determines required expertise level
- Automatic routing based on evaluation needed
- Escalation audit trail required
- Different expertise levels should handle different complexity

❌ **Don't use Handoff Pattern when**:
- All tasks go through same workflow (use Sequential Pipeline)
- Tasks execute in parallel (use SupervisorWorker)
- Fixed routing without evaluation (use Sequential Pipeline)
- Multiple perspectives needed (use Consensus)

### Pattern Type

**Coordination Style**: Dynamic Tier-Based Routing
**Agent Count**: 2+ (unlimited tiers)
**Execution Model**: Sequential with conditional escalation
**Memory Model**: Shared memory with handoff tracking

---

## Architecture

### Component Diagram

```
Task → [Tier 1 Agent] → Evaluate Complexity
              ↓ (if can handle)
          Execute & Return
              ↓ (if too complex)
       [Tier 2 Agent] → Evaluate Complexity
              ↓ (if can handle)
          Execute & Return
              ↓ (if too complex)
       [Tier 3 Agent] → Execute & Return

          [Shared Memory Pool]
          - Handoff decisions
          - Escalation trail
          - Tier evaluations
```

### Core Components

#### 1. HandoffAgent

Agent that evaluates tasks and executes or escalates.

```python
class HandoffAgent(BaseAgent):
    """
    Tier agent that evaluates task complexity and decides whether to handle or escalate.

    Features:
    - Extends BaseAgent
    - Uses TaskEvaluationSignature and TaskExecutionSignature
    - Evaluates if task matches tier capability
    - Executes task if within capability
    - Escalates if too complex
    """
```

**Responsibilities**:
- Evaluate task complexity
- Decide if tier can handle task
- Execute task if capable
- Generate handoff decision
- Track escalation reasoning

#### 2. TaskEvaluationSignature

Defines task complexity evaluation structure.

```python
class TaskEvaluationSignature(Signature):
    task: str = InputField(desc="Task description")
    tier_level: int = InputField(desc="Current tier level")
    context: str = InputField(desc="Additional context", default="")
    can_handle: str = OutputField(desc="yes or no")
    complexity_score: float = OutputField(desc="Complexity 0.0-1.0", default=0.5)
    reasoning: str = OutputField(desc="Why can/cannot handle")
    requires_tier: int = OutputField(desc="Required tier level")
```

#### 3. TaskExecutionSignature

Defines task execution structure.

```python
class TaskExecutionSignature(Signature):
    task: str = InputField(desc="Task to execute")
    tier_level: int = InputField(desc="Current tier level")
    context: str = InputField(desc="Additional context", default="")
    result: str = OutputField(desc="Task result")
    confidence: float = OutputField(desc="Result confidence 0.0-1.0")
    execution_metadata: str = OutputField(desc="Metadata (JSON)", default="{}")
```

#### 4. HandoffPattern

Container for tier agents and handoff logic.

```python
@dataclass
class HandoffPattern(BaseMultiAgentPattern):
    tiers: Dict[int, HandoffAgent] = field(default_factory=dict)
    shared_memory: SharedMemoryPool = field(default_factory=SharedMemoryPool)

    def execute_with_handoff(self, task: str, context: str = "", max_tier: int = 3) -> Dict[str, Any]
    def add_tier(self, agent: HandoffAgent, tier_level: int) -> None
    def get_handoff_history(self, execution_id: str) -> List[Dict[str, Any]]
```

#### 5. Factory Function

Zero-config pattern creation.

```python
def create_handoff_pattern(
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    shared_memory: Optional[SharedMemoryPool] = None,
    tier_configs: Optional[Dict[int, Dict[str, Any]]] = None,
    tiers: Optional[Dict[int, HandoffAgent]] = None,
    num_tiers: Optional[int] = 3
) -> HandoffPattern
```

---

## Quick Start

### Basic Usage (Zero-Config)

```python
from kaizen.agents.coordination import create_handoff_pattern

# 1. Create pattern (3 tiers automatically)
handoff = create_handoff_pattern()

# 2. Execute with automatic routing
result = handoff.execute_with_handoff(
    task="Debug complex distributed system issue",
    context="Production incident",
    max_tier=3
)

# 3. Check which tier handled it
print(f"Tier: {result['final_tier']}")
print(f"Escalations: {result['escalation_count']}")

# 4. Get handoff trail
history = handoff.get_handoff_history(result['execution_id'])
for decision in history:
    print(f"Tier {decision['tier_level']}: {decision['handoff_decision']}")
```

### With Custom Configuration

```python
# Create 5-tier system with tier-specific models
handoff = create_handoff_pattern(
    tier_configs={
        1: {'model': 'gpt-3.5-turbo', 'temperature': 0.3},
        2: {'model': 'gpt-4', 'temperature': 0.5},
        3: {'model': 'gpt-4', 'temperature': 0.7},
        4: {'model': 'gpt-4-turbo', 'temperature': 0.8},
        5: {'model': 'gpt-4-turbo', 'temperature': 0.9}
    }
)

# Execute
result = handoff.execute_with_handoff(
    task="Optimize query performance for 1B+ row database",
    max_tier=5
)
```

---

## Usage Examples

### Example 17: Basic Usage
- **File**: `17_handoff_pattern_basic.py`
- **Focus**: Zero-config creation, automatic routing, escalation
- **Time**: 5 minutes
- **Learning**: Pattern creation, tier routing, handoff history

### Example 18: Configuration
- **File**: `18_handoff_pattern_configuration.py`
- **Focus**: Progressive configuration options
- **Time**: 5 minutes
- **Learning**: Tier configs, custom models, pre-built agents

### Example 19: Advanced Features
- **File**: `19_handoff_pattern_advanced.py`
- **Focus**: Escalation analytics, optimization, edge cases
- **Time**: 10 minutes
- **Learning**: Metrics, performance optimization, workload-specific configs

### Example 20: Real-World Customer Support
- **File**: `20_handoff_pattern_customer_support.py`
- **Focus**: Production tier-based support system
- **Time**: 15 minutes
- **Learning**: Support routing, tier utilization, escalation analytics

---

## API Reference

### Factory Function

#### `create_handoff_pattern()`

Create Handoff Pattern with zero-config or progressive configuration.

**Parameters**:
- `llm_provider` (str, optional): LLM provider (default: "openai" or KAIZEN_LLM_PROVIDER)
- `model` (str, optional): Model name (default: "gpt-3.5-turbo" or KAIZEN_MODEL)
- `temperature` (float, optional): Temperature 0.0-1.0 (default: 0.7 or KAIZEN_TEMPERATURE)
- `max_tokens` (int, optional): Max tokens (default: 1000 or KAIZEN_MAX_TOKENS)
- `shared_memory` (SharedMemoryPool, optional): Shared memory instance (default: creates new)
- `tier_configs` (Dict[int, Dict], optional): Per-tier configurations (default: uses basic params)
- `tiers` (Dict[int, HandoffAgent], optional): Pre-built tier agents (default: creates from tier_configs)
- `num_tiers` (int, optional): Number of tiers to create (default: 3)

**Returns**: `HandoffPattern` instance

**Example**:
```python
# Zero-config (3 tiers)
handoff = create_handoff_pattern()

# Custom tier count
handoff = create_handoff_pattern(num_tiers=5)

# Tier-specific configs
handoff = create_handoff_pattern(
    tier_configs={
        1: {'model': 'gpt-3.5-turbo'},
        2: {'model': 'gpt-4'},
        3: {'model': 'gpt-4-turbo'}
    }
)
```

---

### HandoffPattern Class

#### `execute_with_handoff(task: str, context: str = "", max_tier: int = 3) -> Dict[str, Any]`

Execute task with automatic tier-based routing and escalation.

**Parameters**:
- `task` (str): Task description
- `context` (str, optional): Additional context (default: "")
- `max_tier` (int, optional): Maximum tier level (default: 3)

**Returns**: Dictionary containing:
```python
{
    'execution_id': str,       # Unique execution ID
    'final_tier': int,         # Tier that handled task
    'escalation_count': int,   # Number of escalations
    'result': str,             # Task result
    'confidence': float        # Result confidence 0.0-1.0
}
```

**Behavior**:
- Starts at lowest tier (tier 1)
- Evaluates if current tier can handle task
- If yes: Executes and returns
- If no: Escalates to next tier
- Continues until max_tier or task handled
- Stores all decisions in shared memory

**Example**:
```python
result = handoff.execute_with_handoff(
    task="Complex system architecture design",
    context="Enterprise application",
    max_tier=5
)

print(f"Tier: {result['final_tier']}")
print(f"Escalations: {result['escalation_count']}")
```

---

#### `add_tier(agent: HandoffAgent, tier_level: int) -> None`

Add tier agent to pattern.

**Parameters**:
- `agent` (HandoffAgent): Tier agent to add
- `tier_level` (int): Tier level number

**Example**:
```python
tier_agent = HandoffAgent(
    config=BaseAgentConfig(),
    shared_memory=handoff.shared_memory,
    tier_level=4,
    agent_id="tier_4"
)

handoff.add_tier(tier_agent, 4)
```

---

#### `get_handoff_history(execution_id: str) -> List[Dict[str, Any]]`

Retrieve handoff decision history.

**Parameters**:
- `execution_id` (str): Execution ID from execute_with_handoff()

**Returns**: List of dictionaries, each containing:
```python
{
    'execution_id': str,
    'tier_level': int,
    'agent_id': str,
    'can_handle': str,          # 'yes' or 'no'
    'complexity_score': float,
    'reasoning': str,
    'requires_tier': int,
    'handoff_decision': str,    # 'escalate' or 'execute'
    'timestamp': str
}
```

**Example**:
```python
history = handoff.get_handoff_history(result['execution_id'])

for decision in history:
    print(f"Tier {decision['tier_level']}: {decision['handoff_decision']}")
```

---

## Configuration

### Configuration Levels

#### Level 1: Zero-Config (Fastest)

```python
handoff = create_handoff_pattern()
```

Creates 3 default tiers using environment variables or defaults.

---

#### Level 2: Custom Tier Count

```python
handoff = create_handoff_pattern(num_tiers=5)
```

Creates N tiers with same configuration.

---

#### Level 3: Tier-Specific Configs

```python
handoff = create_handoff_pattern(
    tier_configs={
        1: {'model': 'gpt-3.5-turbo', 'temperature': 0.3, 'max_tokens': 500},
        2: {'model': 'gpt-4', 'temperature': 0.5, 'max_tokens': 1000},
        3: {'model': 'gpt-4-turbo', 'temperature': 0.7, 'max_tokens': 1500}
    }
)
```

Different configuration for each tier.

---

#### Level 4: Pre-Built Tier Agents

```python
# Create custom tier agents
tier1 = HandoffAgent(
    config=BaseAgentConfig(model="gpt-3.5-turbo"),
    shared_memory=shared_memory,
    tier_level=1,
    agent_id="junior_support"
)

tier2 = HandoffAgent(
    config=BaseAgentConfig(model="gpt-4"),
    shared_memory=shared_memory,
    tier_level=2,
    agent_id="senior_support"
)

# Create pattern
handoff = create_handoff_pattern(tiers={1: tier1, 2: tier2})
```

Full control over tier agents.

---

## Best Practices

### Tier Configuration

#### 1. Match Model to Tier Complexity

```python
# ✅ GOOD: Fast model for simple tiers, powerful for complex
tier_configs={
    1: {'model': 'gpt-3.5-turbo'},  # Simple tasks
    2: {'model': 'gpt-4'},          # Moderate tasks
    3: {'model': 'gpt-4-turbo'}     # Complex tasks
}

# ❌ BAD: Same powerful model for all tiers (costly)
tier_configs={
    1: {'model': 'gpt-4-turbo'},
    2: {'model': 'gpt-4-turbo'},
    3: {'model': 'gpt-4-turbo'}
}
```

---

#### 2. Use Appropriate Tier Count

```python
# ✅ GOOD: 2-3 tiers for simple workflows
handoff = create_handoff_pattern(num_tiers=2)  # Fast, cost-effective

# ✅ GOOD: 4-5 tiers for complex workflows
handoff = create_handoff_pattern(num_tiers=5)  # Granular routing

# ❌ BAD: Too many tiers for simple tasks
handoff = create_handoff_pattern(num_tiers=10)  # Overhead, slow
```

---

#### 3. Set Reasonable Max Tier

```python
# ✅ GOOD: Limit escalation to available tiers
result = handoff.execute_with_handoff(task, max_tier=3)

# ❌ BAD: Max tier exceeds available tiers
result = handoff.execute_with_handoff(task, max_tier=10)  # Wastes evaluations
```

---

### Performance Optimization

#### 1. Optimize Tier 1 Resolution

```python
# ✅ GOOD: Strong Tier 1 resolves more tasks
tier_configs={
    1: {
        'model': 'gpt-4',           # Good model for Tier 1
        'temperature': 0.3,
        'max_tokens': 800
    },
    # ... other tiers
}

# Goal: >60% resolution at Tier 1
```

---

#### 2. Use Temperature Appropriately

```python
# ✅ GOOD: Lower temp for deterministic tiers, higher for creative
tier_configs={
    1: {'temperature': 0.3},  # Deterministic evaluation
    2: {'temperature': 0.5},  # Balanced
    3: {'temperature': 0.7}   # Creative problem-solving
}
```

---

## Use Cases

### 1. Customer Support System

**Scenario**: Tier 1 → Tier 2 → Tier 3 support escalation

```python
handoff = create_handoff_pattern(
    tier_configs={
        1: {'model': 'gpt-3.5-turbo', 'temperature': 0.3},  # FAQ, basic
        2: {'model': 'gpt-4', 'temperature': 0.5},          # Technical help
        3: {'model': 'gpt-4-turbo', 'temperature': 0.7}     # Engineering
    }
)

result = handoff.execute_with_handoff(
    task=support_ticket,
    context=f"Priority: {priority}, Category: {category}",
    max_tier=3
)
```

**Benefits**:
- Automatic complexity-based routing
- Audit trail for escalations
- Optimized cost (most tickets at Tier 1)
- Expert resources used only when needed

---

### 2. IT Helpdesk

**Scenario**: L1 → L2 → L3 technical support

```python
handoff = create_handoff_pattern(num_tiers=3)

result = handoff.execute_with_handoff(
    task=it_ticket,
    context="System: Production, SLA: 4hrs",
    max_tier=3
)
```

**Benefits**:
- Efficient tier utilization
- SLA compliance tracking
- Knowledge transfer between tiers

---

### 3. Medical Diagnosis

**Scenario**: General Practitioner → Specialist → Expert

```python
handoff = create_handoff_pattern(
    tier_configs={
        1: {'temperature': 0.3},  # GP: Standard diagnosis
        2: {'temperature': 0.5},  # Specialist: Focused expertise
        3: {'temperature': 0.7}   # Expert: Rare conditions
    }
)
```

---

### 4. Content Moderation

**Scenario**: Automated → Human → Expert Review

```python
handoff = create_handoff_pattern(
    tier_configs={
        1: {'model': 'gpt-3.5-turbo'},  # Automated: Clear violations
        2: {'model': 'gpt-4'},          # Human: Borderline cases
        3: {'model': 'gpt-4-turbo'}     # Expert: Appeals, complex
    }
)
```

---

## Advanced Topics

### Escalation Analytics

Track and analyze escalation patterns:

```python
def analyze_escalations(history: List[Dict]) -> Dict:
    return {
        "tiers_involved": list(set(d['tier_level'] for d in history)),
        "escalations": sum(1 for d in history if d['can_handle'] == 'no'),
        "avg_complexity": sum(d['complexity_score'] for d in history) / len(history),
        "final_tier": history[-1]['tier_level']
    }

result = handoff.execute_with_handoff(task)
history = handoff.get_handoff_history(result['execution_id'])
metrics = analyze_escalations(history)
```

---

### Workload-Specific Optimization

Different patterns for different workloads:

```python
# High-volume, simple tasks (2 tiers, fast models)
support_handoff = create_handoff_pattern(
    num_tiers=2,
    tier_configs={
        1: {'model': 'gpt-3.5-turbo', 'temperature': 0.3},
        2: {'model': 'gpt-4', 'temperature': 0.5}
    }
)

# Complex, low-volume tasks (5 tiers, powerful models)
research_handoff = create_handoff_pattern(
    num_tiers=5,
    tier_configs={
        # ... progressive complexity
        5: {'model': 'gpt-4-turbo', 'temperature': 0.9}
    }
)
```

---

## Troubleshooting

### Issue: Excessive escalations

**Symptom**: Most tasks escalate to highest tier

**Causes**:
1. Tier 1 too weak (model or config)
2. Tasks genuinely complex
3. Complexity evaluation too conservative

**Solution**:
```python
# Strengthen Tier 1
tier_configs={
    1: {'model': 'gpt-4', 'temperature': 0.5, 'max_tokens': 1200},  # Better model
    2: {'model': 'gpt-4-turbo', 'temperature': 0.7},
    3: {'model': 'gpt-4-turbo', 'temperature': 0.9}
}

# Monitor metrics
history = handoff.get_handoff_history(execution_id)
tier1_resolved = sum(1 for d in history if d['tier_level'] == 1 and d['can_handle'] == 'yes')
```

---

### Issue: Tasks stuck at low tier

**Symptom**: Complex tasks handled by Tier 1 (low confidence)

**Causes**:
1. max_tier set too low
2. Evaluation not detecting complexity
3. No higher tiers available

**Solution**:
```python
# Increase max_tier
result = handoff.execute_with_handoff(task, max_tier=5)  # Instead of 3

# Check confidence
if result['confidence'] < 0.6:
    print(f"⚠️  Low confidence ({result['confidence']}) at tier {result['final_tier']}")
```

---

### Issue: No escalation happening

**Symptom**: All tasks resolve at Tier 1

**Causes**:
1. Tasks are actually simple
2. Tier 1 incorrectly evaluating as capable
3. Empty higher tiers

**Solution**:
```python
# Verify tiers exist
print(f"Tiers: {sorted(handoff.tiers.keys())}")

# Check evaluation logic
history = handoff.get_handoff_history(execution_id)
for decision in history:
    print(f"Tier {decision['tier_level']}: can_handle={decision['can_handle']}, complexity={decision['complexity_score']}")
```

---

## Pattern Comparison

### Handoff vs Sequential Pipeline

| Feature | Handoff | Sequential Pipeline |
|---------|---------|---------------------|
| Execution | Conditional (escalate if needed) | Always linear (all stages) |
| Routing | Dynamic based on evaluation | Fixed sequence |
| Use Case | Tier-based support | Multi-stage processing |
| When to Use | Expertise discovery needed | Known workflow steps |

---

### Handoff vs SupervisorWorker

| Feature | Handoff | SupervisorWorker |
|---------|---------|------------------|
| Routing | Sequential with escalation | Parallel delegation |
| Task Type | Same task, different tiers | Different tasks |
| Use Case | Complexity-based routing | Parallel execution |

---

## Summary

The Handoff Pattern provides:

✅ **Dynamic tier-based routing** with automatic escalation
✅ **Complexity evaluation** for intelligent routing decisions
✅ **Escalation audit trail** for full transparency
✅ **Zero-config** with progressive configuration options
✅ **Production-ready** for support systems, helpdesks, and tier-based workflows

### Quick Reference

```python
# Create
handoff = create_handoff_pattern(num_tiers=3)

# Execute
result = handoff.execute_with_handoff(task, context="...", max_tier=3)

# Get history
history = handoff.get_handoff_history(result['execution_id'])

# Analyze
tier = result['final_tier']
escalations = result['escalation_count']
```

### Next Steps

- Try **Example 17**: Basic usage
- Try **Example 18**: Configuration options
- Try **Example 19**: Advanced features
- Try **Example 20**: Real-world customer support

---

**Version**: 1.0
**Last Updated**: 2025-10-04
**Pattern Type**: Multi-Agent Coordination
**Production Ready**: ✅ YES
