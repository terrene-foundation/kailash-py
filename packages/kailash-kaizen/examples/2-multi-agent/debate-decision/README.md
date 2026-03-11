# Debate-Decision Multi-Agent Pattern

## Overview

The **Debate-Decision** pattern implements adversarial reasoning for critical decisions using multi-agent collaboration. This pattern leverages dialectic debate to improve decision quality by ensuring all sides of an argument are thoroughly examined before reaching a conclusion.

**Pattern Type**: Multi-Agent Coordination (Adversarial Reasoning)

**Key Innovation**: Structured debate with proponent, opponent, and judge roles ensures comprehensive evaluation of critical decisions through adversarial reasoning and objective evaluation.

**Use Cases**:
- Critical business decisions requiring multiple perspectives
- Risk assessment and mitigation planning
- Strategic planning with devil's advocate methodology
- Technology adoption decisions (frameworks, architectures, tools)
- Architecture Decision Records (ADRs) with formal debate structure
- Investment decisions requiring risk/benefit analysis
- Policy decisions requiring comprehensive impact assessment

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Decision Question                         │
│            "Should we adopt AI-powered code review?"        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 ROUND 1: Initial Arguments                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │ ProponentAgent   │         │ OpponentAgent    │         │
│  │                  │         │                  │         │
│  │ Argues FOR       │         │ Argues AGAINST   │         │
│  │ the decision     │         │ the decision     │         │
│  │                  │         │                  │         │
│  │ • Argument       │         │ • Argument       │         │
│  │ • Evidence       │         │ • Risks          │         │
│  │ • Confidence     │         │ • Confidence     │         │
│  └────────┬─────────┘         └────────┬─────────┘         │
│           │                            │                    │
│           ▼                            ▼                    │
│  ┌─────────────────────────────────────────────┐           │
│  │       SharedMemoryPool (segment: debate)     │           │
│  │  tags: ["argument", "proponent", "round1"]   │           │
│  │  tags: ["argument", "opponent", "round1"]    │           │
│  │  importance: 0.9                              │           │
│  └─────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  ROUND 2: Rebuttals                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │ ProponentAgent   │         │ OpponentAgent    │         │
│  │                  │         │                  │         │
│  │ Rebuts opponent's│         │ Rebuts proponent │         │
│  │ argument         │         │ argument         │         │
│  │                  │         │                  │         │
│  │ • Rebuttal       │         │ • Rebuttal       │         │
│  │ • Evidence       │         │ • Risks          │         │
│  │ • Confidence     │         │ • Confidence     │         │
│  └────────┬─────────┘         └────────┬─────────┘         │
│           │                            │                    │
│           ▼                            ▼                    │
│  ┌─────────────────────────────────────────────┐           │
│  │       SharedMemoryPool (segment: debate)     │           │
│  │  tags: ["rebuttal", "proponent", "round2"]   │           │
│  │  tags: ["rebuttal", "opponent", "round2"]    │           │
│  │  importance: 0.9                              │           │
│  └─────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                ROUND 3: Judge Evaluation                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│                    ┌──────────────────┐                     │
│                    │   JudgeAgent     │                     │
│                    │                  │                     │
│                    │ Reads:           │                     │
│                    │ • All arguments  │                     │
│                    │ • All rebuttals  │                     │
│                    │                  │                     │
│                    │ Evaluates:       │                     │
│                    │ • Strength       │                     │
│                    │ • Evidence       │                     │
│                    │ • Risk/Benefit   │                     │
│                    │                  │                     │
│                    │ Decides:         │                     │
│                    │ • approve/reject │                     │
│                    │ • Winner         │                     │
│                    │ • Reasoning      │                     │
│                    │ • Confidence     │                     │
│                    └────────┬─────────┘                     │
│                             │                               │
│                             ▼                               │
│            ┌─────────────────────────────────┐             │
│            │  SharedMemoryPool (decisions)    │             │
│            │  tags: ["decision", "final"]     │             │
│            │  importance: 1.0                 │             │
│            └─────────────────────────────────┘             │
│                             │                               │
└─────────────────────────────┼───────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Final Decision  │
                    │                  │
                    │  • Decision      │
                    │  • Winner        │
                    │  • Reasoning     │
                    │  • Confidence    │
                    └──────────────────┘
```

## Agents

### 1. ProponentAgent

**Role**: Argues FOR the decision

**Responsibilities**:
- Receive decision question
- Present compelling case FOR the decision
- Provide evidence supporting the position
- Read opponent's arguments from shared memory
- Rebut opponent's case with counter-arguments
- Maintain confidence scores throughout debate

**Signature**:
```python
class ProponentSignature(Signature):
    question: str = InputField(desc="Decision question")
    opponent_argument: str = InputField(desc="Opponent's argument (for rebuttal)", default="")

    argument: str = OutputField(desc="Argument supporting the decision")
    evidence: str = OutputField(desc="Evidence supporting argument")
    confidence: str = OutputField(desc="Confidence score 0-1")
```

**Methods**:
- `argue(question: str) -> Dict[str, Any]`: Present initial case FOR
- `rebut(question: str, opponent_argument: str) -> Dict[str, Any]`: Rebut opponent's case

**Shared Memory Behavior**:
- Writes arguments: tags `["argument", "proponent", "round1"]`, segment `"debate"`, importance `0.9`
- Writes rebuttals: tags `["rebuttal", "proponent", "round2"]`, segment `"debate"`, importance `0.9`

### 2. OpponentAgent

**Role**: Argues AGAINST the decision

**Responsibilities**:
- Receive decision question
- Present compelling case AGAINST the decision
- Identify risks and concerns
- Read proponent's arguments from shared memory
- Rebut proponent's case with counter-arguments
- Maintain confidence scores throughout debate

**Signature**:
```python
class OpponentSignature(Signature):
    question: str = InputField(desc="Decision question")
    proponent_argument: str = InputField(desc="Proponent's argument (for rebuttal)", default="")

    argument: str = OutputField(desc="Argument opposing the decision")
    risks: str = OutputField(desc="Risks identified")
    confidence: str = OutputField(desc="Confidence score 0-1")
```

**Methods**:
- `argue(question: str) -> Dict[str, Any]`: Present initial case AGAINST
- `rebut(question: str, proponent_argument: str) -> Dict[str, Any]`: Rebut proponent's case

**Shared Memory Behavior**:
- Writes arguments: tags `["argument", "opponent", "round1"]`, segment `"debate"`, importance `0.9`
- Writes rebuttals: tags `["rebuttal", "opponent", "round2"]`, segment `"debate"`, importance `0.9`

### 3. JudgeAgent

**Role**: Evaluates all arguments and makes final decision

**Responsibilities**:
- Read all arguments from shared memory (both sides)
- Read all rebuttals from shared memory (both sides)
- Analyze strength of each position
- Evaluate evidence quality
- Determine which side presented better case
- Make final decision (approve/reject)
- Provide detailed reasoning
- Write decision to shared memory

**Decision Criteria**:
- Strength of arguments
- Quality of evidence
- Effectiveness of rebuttals
- Risk/benefit balance
- Overall persuasiveness

**Signature**:
```python
class JudgeSignature(Signature):
    arguments: str = InputField(desc="JSON list of all arguments and rebuttals")

    decision: str = OutputField(desc="Final decision: approve/reject")
    reasoning: str = OutputField(desc="Detailed reasoning")
    winner: str = OutputField(desc="Which side won: proponent/opponent/tie")
    confidence: str = OutputField(desc="Confidence in decision 0-1")
```

**Methods**:
- `evaluate(question: str) -> Dict[str, Any]`: Read all arguments, make decision

**Shared Memory Behavior**:
- Reads arguments: tags `["argument"]`, segments `["debate"]`, exclude_own `False`
- Reads rebuttals: tags `["rebuttal"]`, segments `["debate"]`, exclude_own `False`
- Writes decision: tags `["decision", "final"]`, segment `"decisions"`, importance `1.0`

## Workflow

The debate-decision workflow follows a three-round structure:

### Round 1: Initial Arguments

```python
# ProponentAgent presents case FOR
proponent_arg = proponent.argue(question)
# → Writes to SharedMemoryPool: ["argument", "proponent", "round1"]

# OpponentAgent presents case AGAINST
opponent_arg = opponent.argue(question)
# → Writes to SharedMemoryPool: ["argument", "opponent", "round1"]
```

**Outputs**:
- Proponent's initial argument with evidence and confidence
- Opponent's initial argument with risks and confidence

### Round 2: Rebuttals

```python
# ProponentAgent rebuts opponent's case
proponent_rebut = proponent.rebut(question, opponent_arg["argument"])
# → Writes to SharedMemoryPool: ["rebuttal", "proponent", "round2"]

# OpponentAgent rebuts proponent's case
opponent_rebut = opponent.rebut(question, proponent_arg["argument"])
# → Writes to SharedMemoryPool: ["rebuttal", "opponent", "round2"]
```

**Outputs**:
- Proponent's rebuttal addressing opponent's concerns
- Opponent's rebuttal addressing proponent's claims

### Round 3: Evaluation

```python
# JudgeAgent reads all arguments and rebuttals
decision = judge.evaluate(question)
# → Reads from SharedMemoryPool: tags ["argument", "rebuttal"]
# → Writes to SharedMemoryPool: ["decision", "final"]
```

**Outputs**:
- Final decision (approve/reject)
- Winner determination (proponent/opponent/tie)
- Detailed reasoning
- Confidence score

## Debate Rules

### Turn Order

1. **Round 1 - Opening Arguments**:
   - ProponentAgent argues FOR (no prior context)
   - OpponentAgent argues AGAINST (no prior context)
   - Both arguments written to shared memory

2. **Round 2 - Rebuttals**:
   - ProponentAgent reads opponent's argument and rebuts
   - OpponentAgent reads proponent's argument and rebuts
   - Both rebuttals written to shared memory

3. **Round 3 - Judgment**:
   - JudgeAgent reads ALL arguments and rebuttals
   - JudgeAgent evaluates strength of each position
   - JudgeAgent makes final decision and determines winner

### Rebuttal Requirements

**Proponent Rebuttal**:
- Must address specific points raised by opponent
- Provide additional evidence to counter opponent's risks
- Strengthen original argument with new perspective

**Opponent Rebuttal**:
- Must address specific claims made by proponent
- Identify flaws in proponent's evidence
- Raise additional risks not previously mentioned

### Judge Evaluation Criteria

1. **Argument Strength** (30%):
   - Clarity and coherence
   - Logical reasoning
   - Completeness of case

2. **Evidence Quality** (30%):
   - Credibility of sources
   - Relevance to decision
   - Specificity of examples

3. **Rebuttal Effectiveness** (20%):
   - Direct addressing of opposing points
   - Strength of counter-arguments
   - New insights introduced

4. **Risk/Benefit Balance** (20%):
   - Comprehensive risk identification
   - Realistic benefit assessment
   - Consideration of trade-offs

## Shared Memory Usage

### Tags Per Round

**Round 1 - Initial Arguments**:
- Proponent: `["argument", "proponent", "round1"]`
- Opponent: `["argument", "opponent", "round1"]`

**Round 2 - Rebuttals**:
- Proponent: `["rebuttal", "proponent", "round2"]`
- Opponent: `["rebuttal", "opponent", "round2"]`

**Round 3 - Decision**:
- Judge: `["decision", "final"]`

### Segments

**debate**: Contains all arguments and rebuttals from both sides
**decisions**: Contains final judge decision with reasoning

### Importance Levels

**Arguments/Rebuttals**: `0.9` - High importance for debate content
**Final Decision**: `1.0` - Maximum importance for final judgment

### Memory Flow

```python
# Write pattern
shared_memory.write_insight({
    "agent_id": agent_id,
    "content": json.dumps(argument_data),
    "tags": ["argument", "proponent", "round1"],
    "importance": 0.9,
    "segment": "debate",
    "metadata": {"question": question, "round": 1}
})

# Read pattern
arguments = shared_memory.read_relevant(
    agent_id=agent_id,
    tags=["argument"],
    segments=["debate"],
    exclude_own=False,
    limit=10
)
```

## Quick Start

### Basic Usage

```python
from workflow import debate_decision_workflow

# Run debate on a decision question
result = debate_decision_workflow(
    "Should we migrate our monolithic application to microservices architecture?"
)

# Access results
print(f"Decision: {result['decision']['decision']}")
print(f"Winner: {result['decision']['winner']}")
print(f"Reasoning: {result['decision']['reasoning']}")
```

### Custom Configuration

```python
from workflow import (
    ProponentAgent, OpponentAgent, JudgeAgent,
    DebateConfig, SharedMemoryPool
)

# Configure debate
config = DebateConfig(
    llm_provider="openai",
    model="gpt-4",
    rounds=2
)

# Create shared memory pool
shared_pool = SharedMemoryPool()

# Create agents
proponent = ProponentAgent(config, shared_pool, agent_id="proponent")
opponent = OpponentAgent(config, shared_pool, agent_id="opponent")
judge = JudgeAgent(config, shared_pool, agent_id="judge")

# Run debate manually
question = "Should we adopt GraphQL over REST?"

# Round 1
proponent_arg = proponent.argue(question)
opponent_arg = opponent.argue(question)

# Round 2
proponent_rebut = proponent.rebut(question, opponent_arg["argument"])
opponent_rebut = opponent.rebut(question, proponent_arg["argument"])

# Round 3
decision = judge.evaluate(question)
```

## Configuration

### DebateConfig Parameters

```python
@dataclass
class DebateConfig:
    llm_provider: str = "mock"     # LLM provider: "openai", "anthropic", "mock"
    model: str = "gpt-3.5-turbo"   # Model name
    rounds: int = 2                # Number of debate rounds (default: 2)
```

### Workflow Parameters

```python
def debate_decision_workflow(
    question: str,      # Decision question to debate
    rounds: int = 2     # Number of debate rounds
) -> Dict[str, Any]:
    ...
```

## Use Cases

### 1. Critical Business Decisions

**Scenario**: Deciding whether to enter a new market

```python
result = debate_decision_workflow(
    "Should we expand into the European market in Q1 2025?"
)

# Proponent argues: Growth potential, market timing, competitive advantage
# Opponent argues: Resource constraints, regulatory complexity, currency risk
# Judge evaluates: Risk/benefit balance, timing considerations, strategic alignment
```

### 2. Technology Adoption Decisions

**Scenario**: Evaluating new technology adoption

```python
result = debate_decision_workflow(
    "Should we adopt Kubernetes for container orchestration?"
)

# Proponent argues: Scalability, industry standard, ecosystem benefits
# Opponent argues: Complexity, learning curve, operational overhead
# Judge evaluates: Team readiness, use case fit, long-term viability
```

### 3. Architecture Decision Records (ADRs)

**Scenario**: Creating formal architecture decision with debate

```python
result = debate_decision_workflow(
    "Should we implement event sourcing for our order management system?"
)

# Document decision in ADR
adr_document = f"""
# ADR-042: Event Sourcing for Order Management

## Status: {result['decision']['decision']}

## Context
{result['question']}

## Arguments FOR
{result['proponent_argument']['argument']}
Evidence: {result['proponent_argument']['evidence']}

## Arguments AGAINST
{result['opponent_argument']['argument']}
Risks: {result['opponent_argument']['risks']}

## Decision
{result['decision']['reasoning']}
Winner: {result['decision']['winner']}
Confidence: {result['decision']['confidence']}
"""
```

## Related Examples

### Supervisor-Worker Pattern
**Path**: `examples/2-multi-agent/supervisor-worker/`

Centralized task delegation with parallel execution. Use when tasks are independent and need coordination.

**Comparison**:
- **Supervisor-Worker**: Hierarchical, task-based, parallel execution
- **Debate-Decision**: Adversarial, argument-based, sequential rounds

### Consensus-Building Pattern
**Path**: `examples/2-multi-agent/consensus-building/`

Democratic voting system with 2/3 consensus threshold. Use when multiple stakeholders need to agree.

**Comparison**:
- **Consensus-Building**: Democratic voting, multiple reviewers, consensus threshold
- **Debate-Decision**: Adversarial debate, single judge, winner determination

## Test Coverage

**Test File**: `tests/unit/examples/test_debate_decision.py`

**24 comprehensive tests covering**:
- Proponent arguments and rebuttals (3 tests)
- Opponent arguments and rebuttals (3 tests)
- Judge evaluation and decision-making (4 tests)
- Debate rounds structure (4 tests)
- Full workflow execution (4 tests)
- Debate quality and reasoning (4 tests)
- Shared memory usage patterns (2 tests)

Run tests:
```bash
pytest tests/unit/examples/test_debate_decision.py -v
```

## Implementation Notes

### Pattern Selection Guide

**Use Debate-Decision When**:
- Decision is critical and high-stakes
- Multiple perspectives are essential
- Risk assessment is paramount
- Objective evaluation is needed
- Devil's advocate thinking required

**Use Supervisor-Worker When**:
- Tasks are independent
- Parallel execution needed
- Centralized coordination required

**Use Consensus-Building When**:
- Multiple stakeholders involved
- Democratic decision-making preferred
- Consensus threshold important

## References

### Code Files
- **workflow.py**: Main implementation (670 lines)
- **test_debate_decision.py**: Comprehensive tests (660+ lines)
- **README.md**: This documentation (700+ lines)

### Academic References
- Dialectic Method: Socratic questioning and thesis-antithesis-synthesis
- Adversarial Collaboration: Structured disagreement for better decisions
- Red Team/Blue Team: Military strategy for testing plans through opposition

---

**Author**: Kaizen Framework Team
**Created**: 2025-10-02 (Phase 5, Task 5E.1, Example 3)
**Reference**: supervisor-worker, consensus-building examples
**Framework Version**: Kaizen v0.3.0+
