# DebatePattern Documentation

**Status**: ✅ Production Ready
**Test Coverage**: 100/100 tests passing (100%)
**Version**: 1.0.0

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Usage Examples](#usage-examples)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Best Practices](#best-practices)
8. [Use Cases](#use-cases)
9. [Debate Strategies](#debate-strategies)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The **DebatePattern** is a multi-agent coordination pattern that enables adversarial reasoning through structured debate. A proponent argues FOR a position, an opponent argues AGAINST, and a judge evaluates both sides to make the final decision.

### Key Features

- ✅ **Zero-Config**: Works out-of-the-box with sensible defaults
- ✅ **Progressive Configuration**: Override only what you need
- ✅ **Multi-Round Debates**: Support for initial arguments + rebuttals
- ✅ **Shared Memory Coordination**: Tag-based message routing
- ✅ **Confidence Scoring**: Judge decision confidence (0.0-1.0)
- ✅ **Adversarial Reasoning**: Structured FOR/AGAINST argumentation
- ✅ **Production Ready**: Comprehensive test coverage and validation

### When to Use

**Ideal For**:
- Technical design decisions
- Build vs buy evaluations
- Technology stack selections
- Strategic planning debates
- Policy decision making
- Trade-off analysis

**Not Ideal For**:
- Simple yes/no decisions (use single agent instead)
- Decisions requiring >2 perspectives (use ConsensusPattern instead)
- Collaborative brainstorming (not adversarial)

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                      DebatePattern                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐                                           │
│  │  Proponent   │  ← Argues FOR position                     │
│  └──────┬───────┘                                           │
│         │                                                     │
│         ↓                                                     │
│  ┌─────────────────────────────────────┐                    │
│  │      SharedMemoryPool               │                    │
│  │  ┌─────────────┐  ┌───────────┐    │                    │
│  │  │  Arguments  │  │ Judgments │    │                    │
│  │  └─────────────┘  └───────────┘    │                    │
│  └─────────────────────────────────────┘                    │
│         ↑           ↓                                         │
│  ┌──────┴───────────┴──────┐                                │
│  │      Opponent            │  ← Argues AGAINST position     │
│  └──────────────────────────┘                                │
│               ↓                                               │
│        ┌──────────────┐                                      │
│        │    Judge     │  ← Evaluates and decides             │
│        └──────────────┘                                      │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Coordination Flow

1. **Topic Defined** → User provides debate topic
2. **Round 1: Arguments** → Proponent argues FOR, Opponent argues AGAINST
3. **Shared Memory** → Arguments written with tags: `["argument", position, debate_id]`
4. **Round 2+: Rebuttals** → Each agent rebuts opponent's argument
5. **Judgment** → Judge reads all arguments, evaluates both sides
6. **Decision** → Judge makes final decision (for/against/tie) with confidence
7. **Result** → Judgment returned to user

### Agents

#### ProponentAgent
- **Role**: Argue FOR the position
- **Responsibilities**:
  - Construct compelling arguments supporting the position
  - Provide key points and evidence
  - Rebut opponent's arguments
  - Write arguments to shared memory

#### OpponentAgent
- **Role**: Argue AGAINST the position
- **Responsibilities**:
  - Construct compelling counter-arguments
  - Identify weaknesses in proponent's position
  - Rebut proponent's arguments
  - Write arguments to shared memory

#### JudgeAgent
- **Role**: Evaluate and decide
- **Responsibilities**:
  - Read all arguments from both sides
  - Evaluate strength of each position
  - Make final decision (for/against/tie)
  - Provide reasoning and confidence level

---

## Quick Start

### Installation

```bash
# Install Kaizen (includes all dependencies)
pip install kailash-kaizen
```

### Minimal Example (Zero-Config)

```python
from kaizen.agents.coordination import create_debate_pattern

# Create pattern with defaults (gpt-3.5-turbo)
pattern = create_debate_pattern()

# Run debate (1 round = initial arguments only)
result = pattern.debate(
    topic="Should AI be regulated?",
    context="Important policy decision",
    rounds=1
)

# Get judgment
judgment = pattern.get_judgment(result['debate_id'])
print(f"Decision: {judgment['decision']}")  # "for" or "against" or "tie"
print(f"Winner: {judgment['winner']}")
print(f"Confidence: {judgment['confidence']}")
print(f"Reasoning: {judgment['reasoning']}")
```

### 30-Second Setup

```python
# 1. Create pattern (one line)
pattern = create_debate_pattern()

# 2. Run debate (one line)
result = pattern.debate("Adopt microservices?", rounds=2)

# 3. Get decision (one line)
judgment = pattern.get_judgment(result["debate_id"])
```

---

## Usage Examples

We provide 4 comprehensive examples demonstrating different aspects of the pattern:

### 1. Basic Usage (`09_debate_pattern_basic.py`)
**What it covers**:
- Zero-config pattern creation
- Structured debate flow
- Adversarial reasoning
- Judgment and decision-making

**Run it**:
```bash
python examples/coordination/09_debate_pattern_basic.py
```

### 2. Progressive Configuration (`10_debate_pattern_configuration.py`)
**What it covers**:
- Custom models and parameters
- Multi-round debate configuration
- Separate configs per agent type
- Environment variable usage

**Run it**:
```bash
python examples/coordination/10_debate_pattern_configuration.py
```

### 3. Advanced Usage (`11_debate_pattern_advanced.py`)
**What it covers**:
- Multi-round debates with rebuttals
- Tie scenario handling
- Confidence analysis across rounds
- Debate isolation and memory management

**Run it**:
```bash
python examples/coordination/11_debate_pattern_advanced.py
```

### 4. Real-World Technical Decisions (`12_debate_pattern_technical_decision.py`)
**What it covers**:
- Technical design debates
- Multi-decision session management
- Decision report generation
- Action item extraction

**Run it**:
```bash
python examples/coordination/12_debate_pattern_technical_decision.py
```

---

## API Reference

### Factory Function

#### `create_debate_pattern()`

Creates a complete DebatePattern with all agents initialized.

**Signature**:
```python
def create_debate_pattern(
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    shared_memory: Optional[SharedMemoryPool] = None,
    proponent_config: Optional[Dict[str, Any]] = None,
    opponent_config: Optional[Dict[str, Any]] = None,
    judge_config: Optional[Dict[str, Any]] = None
) -> DebatePattern
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_provider` | `Optional[str]` | `None` | LLM provider (uses `KAIZEN_LLM_PROVIDER` env var if not set) |
| `model` | `Optional[str]` | `None` | Model name (uses `KAIZEN_MODEL` env var if not set) |
| `temperature` | `Optional[float]` | `None` | Temperature (uses `KAIZEN_TEMPERATURE` env var if not set) |
| `max_tokens` | `Optional[int]` | `None` | Max tokens (uses `KAIZEN_MAX_TOKENS` env var if not set) |
| `shared_memory` | `Optional[SharedMemoryPool]` | `None` | Custom shared memory (creates new if not provided) |
| `proponent_config` | `Optional[Dict]` | `None` | Config dict for proponent (overrides basic params) |
| `opponent_config` | `Optional[Dict]` | `None` | Config dict for opponent (overrides basic params) |
| `judge_config` | `Optional[Dict]` | `None` | Config dict for judge (overrides basic params) |

**Returns**: `DebatePattern` instance

**Environment Variables** (used if parameters not provided):
- `KAIZEN_LLM_PROVIDER` - Default LLM provider
- `KAIZEN_MODEL` - Default model
- `KAIZEN_TEMPERATURE` - Default temperature
- `KAIZEN_MAX_TOKENS` - Default max tokens

### Pattern Class

#### `DebatePattern`

Main pattern class extending `BaseMultiAgentPattern`.

**Attributes**:
```python
@dataclass
class DebatePattern(BaseMultiAgentPattern):
    proponent: ProponentAgent
    opponent: OpponentAgent
    judge: JudgeAgent
    shared_memory: SharedMemoryPool
```

**Methods**:

##### `debate(topic: str, context: str = "", rounds: int = 1) -> Dict[str, Any]`
Run structured debate.

**Parameters**:
- `topic` (str): Debate topic
- `context` (str): Additional context (optional)
- `rounds` (int): Number of rounds (default: 1)
  - 1 round = initial arguments only
  - 2+ rounds = initial arguments + rebuttals

**Returns**: Dictionary with debate_id, rounds, arguments

**Example**:
```python
result = pattern.debate(
    "Should we adopt GraphQL?",
    context="Current REST API has performance issues",
    rounds=2
)
```

##### `get_judgment(debate_id: str) -> Dict[str, Any]`
Get judge's decision.

**Parameters**:
- `debate_id` (str): Debate ID from debate() result

**Returns**: Dictionary with decision, winner, confidence, reasoning

**Example**:
```python
judgment = pattern.get_judgment(debate_id)
if judgment['decision'] == 'for':
    print("Proponent wins!")
```

##### `get_agents() -> List[BaseAgent]`
Get all agents in pattern.

**Returns**: List containing [proponent, opponent, judge]

##### `get_agent_ids() -> List[str]`
Get all agent IDs.

**Returns**: List of agent ID strings

##### `validate_pattern() -> bool`
Validate pattern initialization.

**Returns**: True if valid, False otherwise

##### `clear_shared_memory()`
Clear all insights from shared memory.

**Example**:
```python
pattern.clear_shared_memory()  # Reset for next debate
```

### Agent APIs

#### ProponentAgent

```python
class ProponentAgent(BaseAgent):
    def construct_argument(
        self,
        topic: str,
        context: str = ""
    ) -> Dict[str, Any]:
        """Construct argument FOR position."""

    def rebut(
        self,
        opponent_argument: Dict[str, Any],
        topic: str
    ) -> Dict[str, Any]:
        """Rebut opponent's argument."""
```

**Argument Returns**:
```python
{
    "argument_id": "unique_id",
    "debate_id": "debate_id",
    "position": "for",
    "topic": "debate topic",
    "argument": "constructed argument text",
    "key_points": ["point1", "point2", ...],
    "evidence": "supporting evidence"
}
```

**Rebuttal Returns**:
```python
{
    "rebuttal_id": "unique_id",
    "debate_id": "debate_id",
    "position": "for",
    "rebuttal": "counter-argument text",
    "counterpoints": ["counter1", "counter2", ...],
    "strength": 0.0-1.0  # rebuttal strength
}
```

#### OpponentAgent

```python
class OpponentAgent(BaseAgent):
    def construct_argument(
        self,
        topic: str,
        context: str = ""
    ) -> Dict[str, Any]:
        """Construct argument AGAINST position."""

    def rebut(
        self,
        proponent_argument: Dict[str, Any],
        topic: str
    ) -> Dict[str, Any]:
        """Rebut proponent's argument."""
```

**Same return structure as ProponentAgent, but with `position="against"`**

#### JudgeAgent

```python
class JudgeAgent(BaseAgent):
    def judge_debate(self, debate_id: str) -> Dict[str, Any]:
        """Evaluate debate and make decision."""

    def get_arguments(self, debate_id: str) -> Dict[str, Any]:
        """Retrieve all arguments for debate."""
```

**Judgment Returns**:
```python
{
    "judgment_id": "unique_id",
    "debate_id": "debate_id",
    "decision": "for" | "against" | "tie",
    "winner": "proponent" | "opponent" | "tie",
    "reasoning": "decision reasoning",
    "confidence": 0.0-1.0  # decision confidence
}
```

---

## Configuration

### Configuration Levels

The pattern supports 4 levels of configuration, from simplest to most control:

#### Level 1: Zero-Config
```python
# Uses all defaults and environment variables
pattern = create_debate_pattern()
```

#### Level 2: Custom Model
```python
# Override model for all agents
pattern = create_debate_pattern(
    model="gpt-4",
    temperature=0.7
)
```

#### Level 3: Separate Agent Configs
```python
# Different configs for different agents
pattern = create_debate_pattern(
    proponent_config={'model': 'gpt-4', 'temperature': 0.7},
    opponent_config={'model': 'gpt-4', 'temperature': 0.7},
    judge_config={'model': 'gpt-4', 'temperature': 0.3}
)
```

#### Level 4: Full Control
```python
from kaizen.memory import SharedMemoryPool

# Custom shared memory + full configs
shared_memory = SharedMemoryPool()

pattern = create_debate_pattern(
    shared_memory=shared_memory,
    proponent_config={
        'model': 'gpt-4',
        'temperature': 0.7,
        'max_tokens': 2000
    },
    opponent_config={
        'model': 'gpt-4',
        'temperature': 0.7,
        'max_tokens': 2000
    },
    judge_config={
        'model': 'gpt-4',
        'temperature': 0.3,
        'max_tokens': 1500
    }
)
```

### Recommended Configurations

#### Cost-Optimized
```python
pattern = create_debate_pattern(
    model="gpt-3.5-turbo",
    # Use 1 round for cost savings
)
result = pattern.debate(topic, rounds=1)
```

#### Quality-Optimized
```python
pattern = create_debate_pattern(
    proponent_config={'model': 'gpt-4', 'temperature': 0.7},
    opponent_config={'model': 'gpt-4', 'temperature': 0.7},
    judge_config={'model': 'gpt-4', 'temperature': 0.3}
)
# Use 3 rounds for thorough exploration
result = pattern.debate(topic, rounds=3)
```

#### Balanced
```python
pattern = create_debate_pattern(
    model="gpt-4",
    temperature=0.6
)
# Use 2 rounds for good balance
result = pattern.debate(topic, rounds=2)
```

---

## Best Practices

### 1. Round Count Selection

**Guideline**: Match rounds to decision importance

```python
# Quick decisions (low stakes)
result = pattern.debate(topic, rounds=1)  # Initial arguments only

# Standard decisions (medium stakes)
result = pattern.debate(topic, rounds=2)  # Arguments + 1 rebuttal round

# Critical decisions (high stakes)
result = pattern.debate(topic, rounds=3)  # Arguments + 2 rebuttal rounds
```

### 2. Model Selection for Agents

**Guideline**: Use better models for complex reasoning

```python
# For technical/complex debates
pattern = create_debate_pattern(
    proponent_config={'model': 'gpt-4'},
    opponent_config={'model': 'gpt-4'},
    judge_config={'model': 'gpt-4'}
)

# For simple debates (cost-optimized)
pattern = create_debate_pattern(model="gpt-3.5-turbo")
```

### 3. Confidence Analysis

**Guideline**: Use confidence to gauge decision quality

```python
judgment = pattern.get_judgment(debate_id)

if judgment['confidence'] > 0.8:
    print("Very high confidence - clear winner")
elif judgment['confidence'] > 0.6:
    print("High confidence - proceed with decision")
elif judgment['confidence'] > 0.4:
    print("Moderate confidence - monitor implementation")
else:
    print("Low confidence - consider more rounds or research")
```

### 4. Context Provision

**Guideline**: Provide rich context for better arguments

```python
# Good: Rich context
context = """
Current situation:
- System handles 10k req/sec
- Team size: 5 engineers
- Budget: $50k/month
- Timeline: 3 months

Constraints:
- Must maintain uptime
- Limited DevOps resources
"""

result = pattern.debate(topic, context=context)

# Poor: No context
result = pattern.debate(topic)  # Arguments will be generic
```

### 5. Memory Management

**Guideline**: Clear memory between unrelated debates

```python
# Debate 1
result1 = pattern.debate("Topic 1")
judgment1 = pattern.get_judgment(result1['debate_id'])

# Clear before Debate 2
pattern.clear_shared_memory()

# Debate 2
result2 = pattern.debate("Topic 2")
judgment2 = pattern.get_judgment(result2['debate_id'])
```

---

## Use Cases

### 1. Technical Design Decisions

**Scenario**: Choose between architectural approaches

```python
pattern = create_debate_pattern(model="gpt-4")

result = pattern.debate(
    topic="Database: PostgreSQL vs MongoDB",
    context="E-commerce platform, 100k daily transactions",
    rounds=2
)

judgment = pattern.get_judgment(result['debate_id'])
print(f"Decision: {judgment['winner']}")
```

### 2. Build vs Buy Evaluations

**Scenario**: Decide whether to build in-house or buy solution

```python
result = pattern.debate(
    topic="Build custom CRM vs Buy Salesforce",
    context="Team size: 3 devs, Budget: $200k, Timeline: 6 months",
    rounds=3
)
```

### 3. Technology Stack Selection

**Scenario**: Choose technology for new project

```python
result = pattern.debate(
    topic="React vs Vue.js for new web app",
    context="Team experience: 2 years React, 0 years Vue",
    rounds=2
)
```

### 4. Policy Decision Making

**Scenario**: Decide on company policies

```python
result = pattern.debate(
    topic="Remote-first vs Hybrid work policy",
    context="Company size: 50 employees, Industry: Tech",
    rounds=2
)
```

---

## Debate Strategies

### Single-Round Debate

**When**: Quick decisions, low complexity
**Format**: Initial arguments only
**Duration**: ~2-3 LLM calls
**Best For**: Tactical decisions

```python
result = pattern.debate("Quick decision?", rounds=1)
```

### Two-Round Debate

**When**: Standard decisions, medium complexity
**Format**: Initial arguments + 1 rebuttal round
**Duration**: ~4-5 LLM calls
**Best For**: Most technical decisions

```python
result = pattern.debate("Standard decision?", rounds=2)
```

### Multi-Round Debate (3+)

**When**: Critical decisions, high complexity
**Format**: Initial arguments + multiple rebuttal rounds
**Duration**: ~6+ LLM calls
**Best For**: Strategic, irreversible decisions

```python
result = pattern.debate("Critical decision?", rounds=3)
```

### Decision Confidence Thresholds

Set thresholds for automated decision-making:

```python
judgment = pattern.get_judgment(debate_id)

# Auto-approve high confidence decisions
if judgment['confidence'] > 0.8:
    approve_decision(judgment)

# Require human review for low confidence
elif judgment['confidence'] < 0.5:
    escalate_to_human(judgment)

# Standard process for moderate confidence
else:
    implement_with_monitoring(judgment)
```

---

## Troubleshooting

### Common Issues

#### Issue 1: Judge always chooses same side

**Symptom**: Judge consistently picks FOR or AGAINST regardless of topic

**Cause**: Biased context or leading questions

**Solution**:
```python
# Bad: Leading question
topic = "Why microservices are better than monoliths"  # Biased

# Good: Neutral question
topic = "Should we adopt microservices architecture?"  # Neutral

# Provide balanced context
context = """
Microservices pros: scaling, independence
Microservices cons: complexity, overhead
Monolith pros: simplicity, easier debugging
Monolith cons: scaling limitations
"""
```

#### Issue 2: Low confidence decisions

**Symptom**: Judge confidence consistently <0.5

**Cause**: Insufficient rounds or unclear topic

**Solution**:
```python
# Option 1: Add more rounds
result = pattern.debate(topic, rounds=3)  # Instead of 1

# Option 2: Provide more context
context = """
Detailed situation:
- Current state
- Requirements
- Constraints
- Success criteria
"""
result = pattern.debate(topic, context=context)
```

#### Issue 3: Tie decisions frequently

**Symptom**: Judge declares ties often

**Cause**: Truly balanced arguments or ambiguous topic

**Solution**:
```python
judgment = pattern.get_judgment(debate_id)

if judgment['decision'] == 'tie':
    # Option 1: Run additional round
    pattern.clear_shared_memory()
    result = pattern.debate(topic, context=enhanced_context, rounds=3)

    # Option 2: Use tiebreaker criteria
    # - Performance implications
    # - Cost considerations
    # - Team expertise
    # - Timeline constraints
```

#### Issue 4: Arguments not retrieved

**Symptom**: `get_judgment()` can't find arguments

**Cause**: Wrong debate_id or memory cleared

**Solution**:
```python
# Ensure correct debate_id
result = pattern.debate(topic)
debate_id = result['debate_id']  # Save this!

# Don't clear memory before getting judgment
judgment = pattern.get_judgment(debate_id)  # Use saved ID

# Only clear after judgment retrieved
pattern.clear_shared_memory()
```

### Debug Mode

Enable debug logging to diagnose issues:

```python
import logging

# Enable Kaizen debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('kaizen.agents.coordination')
logger.setLevel(logging.DEBUG)

# Now see detailed coordination logs
pattern = create_debate_pattern()
result = pattern.debate("Test topic")
```

### Validation Checklist

Before deploying to production, verify:

- [ ] Pattern validates: `pattern.validate_pattern() == True`
- [ ] All agents initialized: `len(pattern.get_agents()) == 3`
- [ ] Shared memory configured: `pattern.shared_memory is not None`
- [ ] Debate creates result: `debate()` returns valid dict
- [ ] Debate ID present: `'debate_id' in result`
- [ ] Judgment retrievable: `get_judgment(debate_id)` returns valid dict
- [ ] Decision valid: `judgment['decision'] in ['for', 'against', 'tie']`
- [ ] Confidence valid: `0.0 <= judgment['confidence'] <= 1.0`
- [ ] Memory clears properly: `clear_shared_memory()` works

---

## Advanced Topics

### Custom Debate Formats

Extend DebatePattern for custom formats:

```python
from kaizen.agents.coordination import DebatePattern

class OxfordDebatePattern(DebatePattern):
    """Oxford-style debate with opening/closing statements."""

    def debate_oxford_style(self, topic: str, rounds: int = 4) -> Dict[str, Any]:
        # Round 1: Opening statements (longer)
        # Round 2-3: Rebuttals
        # Round 4: Closing statements
        pass
```

### Evidence-Based Scoring

Add evidence scoring to arguments:

```python
# Extend judgment logic
class EvidenceJudge(JudgeAgent):
    def judge_with_evidence_scoring(self, debate_id: str) -> Dict[str, Any]:
        arguments = self.get_arguments(debate_id)

        # Score based on evidence quality
        proponent_score = self.score_evidence(arguments['proponent'])
        opponent_score = self.score_evidence(arguments['opponent'])

        # Make decision weighted by evidence
        ...
```

### Integration with Other Patterns

Combine with ConsensusPattern for multi-judge debates:

```python
# Use DebatePattern to generate arguments
debate_pattern = create_debate_pattern()
result = debate_pattern.debate(topic)

# Use ConsensusPattern for multiple judges
consensus_pattern = create_consensus_pattern(
    num_voters=5,
    voter_perspectives=["technical", "business", "legal", "ux", "security"]
)

# Judges vote on debate winner
proposal = consensus_pattern.create_proposal(
    topic=f"Vote on debate winner: {topic}",
    context=f"Arguments: {result}"
)
```

---

## Further Reading

- **Implementation Details**: See implementation file
- **Test Suite**: See `tests/unit/agents/coordination/test_debate_pattern.py`
- **Validation Report**: See validation documentation
- **Other Patterns**: See `examples/coordination/` for related patterns

---

## Support and Contribution

### Reporting Issues

Found a bug or have a feature request? Please:
1. Check existing issues
2. Create a new issue with:
   - Pattern version
   - Python version
   - Minimal reproduction code
   - Expected vs actual behavior

### Contributing

Contributions welcome! To contribute:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

### Getting Help

- **Documentation**: This README
- **Examples**: `examples/coordination/` directory (examples 09-12)
- **Tests**: `tests/unit/agents/coordination/` for usage patterns
- **Community**: [Link to community forum/chat]

---

**Last Updated**: 2025-10-04
**Pattern Version**: 1.0.0
**Status**: ✅ Production Ready
