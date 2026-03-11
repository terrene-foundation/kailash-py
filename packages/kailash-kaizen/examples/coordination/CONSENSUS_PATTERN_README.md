# ConsensusPattern Documentation

**Status**: ✅ Production Ready
**Test Coverage**: 89/89 tests passing (100%)
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
9. [Voting Strategies](#voting-strategies)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The **ConsensusPattern** is a multi-agent coordination pattern that enables democratic decision-making through voting. A proposer agent creates proposals, multiple voter agents evaluate and cast votes, and an aggregator determines consensus.

### Key Features

- ✅ **Zero-Config**: Works out-of-the-box with sensible defaults
- ✅ **Progressive Configuration**: Override only what you need
- ✅ **Democratic Voting**: Multiple perspectives reach consensus
- ✅ **Shared Memory Coordination**: Tag-based message routing
- ✅ **Confidence Tracking**: Vote confidence levels (0.0-1.0)
- ✅ **Voter Perspectives**: Role-based evaluation (technical, business, etc.)
- ✅ **Production Ready**: Comprehensive test coverage and validation

### When to Use

**Ideal For**:
- Architecture review boards
- Multi-expert decision making
- Technical RFC approval
- Design review committees
- Feature prioritization
- Risk assessment panels

**Not Ideal For**:
- Single-person decisions (use single agent instead)
- Time-critical decisions (voting takes time)
- Simple yes/no questions (overhead not worth it)

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                      ConsensusPattern                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐                                           │
│  │   Proposer   │  ← Creates proposals for voting           │
│  └──────┬───────┘                                           │
│         │                                                     │
│         ↓                                                     │
│  ┌─────────────────────────────────────┐                    │
│  │      SharedMemoryPool               │                    │
│  │  ┌───────────┐  ┌─────────┐        │                    │
│  │  │ Proposals │  │  Votes  │        │                    │
│  │  └───────────┘  └─────────┘        │                    │
│  └─────────────────────────────────────┘                    │
│         ↓           ↑           ↑                            │
│  ┌──────┴───────────┴───────────┴──────────┐               │
│  │                                           │               │
│  │  Voter 1   Voter 2   Voter 3  ...  Voter N                │
│  │    ↓         ↓         ↓            ↓   │               │
│  │   Vote     Vote      Vote         Vote  │               │
│  │  (perspective-based evaluation)         │               │
│  └─────────────────────────────────────────┘               │
│                        ↓                                      │
│                 ┌──────────────┐                            │
│                 │  Aggregator  │  ← Determines consensus     │
│                 └──────────────┘                            │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Coordination Flow

1. **Proposal Creation** → Proposer creates proposal on topic
2. **Shared Memory** → Proposal written with tags: `["proposal", request_id]`
3. **Voter Evaluation** → Each voter reads proposal, evaluates from their perspective
4. **Vote Casting** → Voters cast votes (approve/reject/abstain) with confidence
5. **Vote Storage** → Votes written with tags: `["vote", proposal_id, voter_id]`
6. **Consensus Determination** → Aggregator tallies votes, determines consensus (>50% approve)
7. **Final Decision** → Consensus result returned to user

### Agents

#### ProposerAgent
- **Role**: Create proposals for voting
- **Responsibilities**:
  - Generate detailed proposals on topics
  - Provide context and rationale
  - Write proposals to shared memory

#### VoterAgent
- **Role**: Evaluate and vote on proposals
- **Responsibilities**:
  - Read proposals from shared memory
  - Evaluate from specific perspective (e.g., security, cost)
  - Cast vote (approve/reject/abstain) with reasoning
  - Provide confidence level (0.0-1.0)
  - Write votes to shared memory

#### AggregatorAgent
- **Role**: Determine consensus from votes
- **Responsibilities**:
  - Read all votes for proposal
  - Tally votes (approve, reject, abstain)
  - Determine consensus (>50% approve)
  - Generate vote summary and final decision

---

## Quick Start

### Installation

```bash
# Install Kaizen (includes all dependencies)
pip install kailash-kaizen
```

### Minimal Example (Zero-Config)

```python
from kaizen.agents.coordination import create_consensus_pattern

# Create pattern with defaults (3 voters, gpt-3.5-turbo)
pattern = create_consensus_pattern()

# Create proposal
proposal = pattern.create_proposal(
    topic="Should we adopt AI code review?",
    context="Pros: faster reviews. Cons: cost."
)

# Voters evaluate and vote
for voter in pattern.voters:
    vote = voter.vote(proposal)
    print(f"{voter.agent_id}: {vote['vote']}")

# Determine consensus
result = pattern.determine_consensus(proposal['proposal_id'])
print(f"Consensus: {result['consensus_reached']}")
print(f"Decision: {result['final_decision']}")
```

### 30-Second Setup

```python
# 1. Create pattern (one line)
pattern = create_consensus_pattern(num_voters=5)

# 2. Create proposal (one line)
proposal = pattern.create_proposal("Adopt microservices?")

# 3. Vote (3 lines)
for voter in pattern.voters:
    voter.vote(proposal)

# 4. Get consensus (one line)
result = pattern.determine_consensus(proposal["proposal_id"])
```

---

## Usage Examples

We provide 4 comprehensive examples demonstrating different aspects of the pattern:

### 1. Basic Usage (`05_consensus_pattern_basic.py`)
**What it covers**:
- Zero-config pattern creation
- Proposal creation
- Democratic voting process
- Consensus determination
- Result interpretation

**Run it**:
```bash
python examples/coordination/05_consensus_pattern_basic.py
```

### 2. Progressive Configuration (`06_consensus_pattern_configuration.py`)
**What it covers**:
- Custom number of voters
- Custom models and parameters
- Voter perspectives for role-based evaluation
- Separate configs per agent type
- Environment variable usage

**Run it**:
```bash
python examples/coordination/06_consensus_pattern_configuration.py
```

### 3. Advanced Usage (`07_consensus_pattern_advanced.py`)
**What it covers**:
- Tie scenarios and resolution
- Confidence-weighted analysis
- Abstention handling and quorum
- Multi-round consensus building
- Supermajority requirements

**Run it**:
```bash
python examples/coordination/07_consensus_pattern_advanced.py
```

### 4. Real-World Architecture Review (`08_consensus_pattern_architecture_review.py`)
**What it covers**:
- Architecture Review Board (ARB) implementation
- Multi-expert panel with diverse perspectives
- Complex technical proposal evaluation
- Decision documentation and traceability
- Governance and audit reporting

**Run it**:
```bash
python examples/coordination/08_consensus_pattern_architecture_review.py
```

---

## API Reference

### Factory Function

#### `create_consensus_pattern()`

Creates a complete ConsensusPattern with all agents initialized.

**Signature**:
```python
def create_consensus_pattern(
    num_voters: int = 3,
    voter_perspectives: Optional[List[str]] = None,
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    shared_memory: Optional[SharedMemoryPool] = None,
    proposer_config: Optional[Dict[str, Any]] = None,
    voter_config: Optional[Dict[str, Any]] = None,
    aggregator_config: Optional[Dict[str, Any]] = None
) -> ConsensusPattern
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `num_voters` | `int` | `3` | Number of voter agents to create |
| `voter_perspectives` | `Optional[List[str]]` | `None` | Perspectives for voters (e.g., ["technical", "business", "security"]) |
| `llm_provider` | `Optional[str]` | `None` | LLM provider (uses `KAIZEN_LLM_PROVIDER` env var if not set) |
| `model` | `Optional[str]` | `None` | Model name (uses `KAIZEN_MODEL` env var if not set) |
| `temperature` | `Optional[float]` | `None` | Temperature (uses `KAIZEN_TEMPERATURE` env var if not set) |
| `max_tokens` | `Optional[int]` | `None` | Max tokens (uses `KAIZEN_MAX_TOKENS` env var if not set) |
| `shared_memory` | `Optional[SharedMemoryPool]` | `None` | Custom shared memory (creates new if not provided) |
| `proposer_config` | `Optional[Dict]` | `None` | Config dict for proposer (overrides basic params) |
| `voter_config` | `Optional[Dict]` | `None` | Config dict for voters (overrides basic params) |
| `aggregator_config` | `Optional[Dict]` | `None` | Config dict for aggregator (overrides basic params) |

**Returns**: `ConsensusPattern` instance

**Environment Variables** (used if parameters not provided):
- `KAIZEN_LLM_PROVIDER` - Default LLM provider
- `KAIZEN_MODEL` - Default model
- `KAIZEN_TEMPERATURE` - Default temperature
- `KAIZEN_MAX_TOKENS` - Default max tokens

### Pattern Class

#### `ConsensusPattern`

Main pattern class extending `BaseMultiAgentPattern`.

**Attributes**:
```python
@dataclass
class ConsensusPattern(BaseMultiAgentPattern):
    proposer: ProposerAgent
    voters: List[VoterAgent]
    aggregator: AggregatorAgent
    shared_memory: SharedMemoryPool
```

**Methods**:

##### `create_proposal(topic: str, context: str = "") -> Dict[str, Any]`
Create proposal for voting.

**Parameters**:
- `topic` (str): Topic for proposal
- `context` (str): Additional context (optional)

**Returns**: Dictionary with proposal_id, request_id, topic, proposal, rationale

**Example**:
```python
proposal = pattern.create_proposal(
    "Should we adopt microservices?",
    "Current monolith has scaling issues"
)
```

##### `collect_votes(proposal_id: str) -> List[Dict[str, Any]]`
Collect all votes for a proposal.

**Parameters**:
- `proposal_id` (str): Proposal ID

**Returns**: List of vote dictionaries

**Example**:
```python
votes = pattern.collect_votes(proposal_id)
print(f"Total votes: {len(votes)}")
```

##### `determine_consensus(proposal_id: str) -> Dict[str, Any]`
Determine consensus from votes.

**Parameters**:
- `proposal_id` (str): Proposal ID

**Returns**: Dictionary with consensus_reached, final_decision, vote_summary

**Example**:
```python
result = pattern.determine_consensus(proposal_id)
if result['consensus_reached'] == 'yes':
    print("Consensus achieved!")
```

##### `get_agents() -> List[BaseAgent]`
Get all agents in pattern.

**Returns**: List containing [proposer] + voters + [aggregator]

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
pattern.clear_shared_memory()  # Reset for next proposal
```

### Agent APIs

#### ProposerAgent

```python
class ProposerAgent(BaseAgent):
    def create_proposal(
        self,
        topic: str,
        context: str = ""
    ) -> Dict[str, Any]:
        """Create proposal for voting."""
```

**Returns**:
```python
{
    "proposal_id": "unique_id",
    "request_id": "unique_request_id",
    "topic": "proposal topic",
    "proposal": "detailed proposal text",
    "rationale": "reasoning for proposal"
}
```

#### VoterAgent

```python
class VoterAgent(BaseAgent):
    perspective: str  # e.g., "security", "cost", "technical"

    def get_proposals(self) -> List[Dict[str, Any]]:
        """Read proposals from shared memory."""

    def vote(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate proposal and cast vote."""
```

**Vote Returns**:
```python
{
    "proposal_id": "proposal_id",
    "voter_id": "voter_id",
    "vote": "approve" | "reject" | "abstain",
    "reasoning": "vote reasoning text",
    "confidence": 0.0-1.0  # confidence level
}
```

#### AggregatorAgent

```python
class AggregatorAgent(BaseAgent):
    def aggregate_votes(self, proposal_id: str) -> Dict[str, Any]:
        """Tally votes and determine consensus."""

    def check_consensus_reached(self, proposal_id: str) -> bool:
        """Check if consensus achieved (>50% approve)."""
```

**Consensus Returns**:
```python
{
    "consensus_reached": "yes" | "no",
    "final_decision": "decision summary",
    "vote_summary": "detailed vote breakdown"
}
```

---

## Configuration

### Configuration Levels

The pattern supports 5 levels of configuration, from simplest to most control:

#### Level 1: Zero-Config
```python
# Uses all defaults and environment variables
pattern = create_consensus_pattern()
```

#### Level 2: Custom Voters
```python
# Override number of voters
pattern = create_consensus_pattern(num_voters=5)
```

#### Level 3: Voter Perspectives
```python
# Assign specific perspectives/roles
pattern = create_consensus_pattern(
    num_voters=3,
    voter_perspectives=["security", "performance", "cost"]
)
```

#### Level 4: Model Configuration
```python
# Override model and parameters
pattern = create_consensus_pattern(
    num_voters=3,
    model="gpt-4",
    temperature=0.7
)
```

#### Level 5: Separate Agent Configs
```python
# Different configs for different agent types
pattern = create_consensus_pattern(
    num_voters=3,
    voter_perspectives=["technical", "business", "legal"],
    proposer_config={
        'model': 'gpt-4',
        'temperature': 0.5
    },
    voter_config={
        'model': 'gpt-4',
        'temperature': 0.7
    },
    aggregator_config={
        'model': 'gpt-3.5-turbo',
        'temperature': 0.2
    }
)
```

### Recommended Configurations

#### Cost-Optimized
```python
pattern = create_consensus_pattern(
    num_voters=3,
    proposer_config={'model': 'gpt-3.5-turbo'},
    voter_config={'model': 'gpt-3.5-turbo'},
    aggregator_config={'model': 'gpt-3.5-turbo'}
)
```

#### Performance-Optimized
```python
pattern = create_consensus_pattern(
    num_voters=5,
    proposer_config={'model': 'gpt-4', 'temperature': 0.5},
    voter_config={'model': 'gpt-4', 'temperature': 0.7},
    aggregator_config={'model': 'gpt-3.5-turbo', 'temperature': 0.2}
)
```

#### Multi-Expert Panel
```python
pattern = create_consensus_pattern(
    num_voters=7,
    voter_perspectives=[
        "security",
        "performance",
        "scalability",
        "cost",
        "compliance",
        "ux",
        "developer_experience"
    ],
    model="gpt-4"
)
```

---

## Best Practices

### 1. Voter Count and Perspectives

**Guideline**: Use odd number of voters to avoid ties

```python
# Good: Odd number avoids ties
pattern = create_consensus_pattern(
    num_voters=5,
    voter_perspectives=["security", "performance", "cost", "ux", "compliance"]
)

# Problematic: Even number can tie (2-2)
pattern = create_consensus_pattern(num_voters=4)  # Can tie
```

**Recommended Voter Counts**:
- **3 voters**: Small, quick decisions
- **5 voters**: Balanced panels
- **7+ voters**: Complex, high-impact decisions

### 2. Voter Perspective Assignment

**Guideline**: Assign specific, non-overlapping perspectives

```python
# Good: Clear, distinct perspectives
voter_perspectives = [
    "security",          # Security implications
    "performance",       # Performance impact
    "cost",             # Financial considerations
    "developer_experience",  # Dev UX
    "compliance"        # Regulatory compliance
]

# Problematic: Overlapping/vague perspectives
voter_perspectives = ["general", "general", "general"]  # No diversity
```

**Common Perspective Categories**:
- **Technical**: security, performance, scalability, maintainability
- **Business**: cost, roi, market_impact, competitive_advantage
- **User**: ux, accessibility, user_value
- **Operations**: operations, devops, reliability, monitoring

### 3. Consensus Threshold Tuning

**Guideline**: Adjust consensus threshold based on decision impact

```python
# Standard majority (>50%)
if approvals > len(votes) / 2:
    consensus = True

# Supermajority for critical decisions (>67%)
if approvals > len(votes) * 0.67:
    consensus = True

# Unanimous for high-risk changes (100%)
if approvals == len(votes):
    consensus = True
```

### 4. Confidence Analysis

**Guideline**: Analyze vote confidence for decision quality

```python
# Calculate average confidence
avg_confidence = sum(v['confidence'] for v in votes) / len(votes)

# Interpret confidence
if avg_confidence > 0.7:
    print("High confidence - strong consensus")
elif avg_confidence > 0.5:
    print("Moderate confidence - acceptable")
else:
    print("Low confidence - may need more info or re-vote")
```

### 5. Abstention and Quorum

**Guideline**: Set quorum requirements to ensure valid votes

```python
# Count non-abstain votes
active_votes = [v for v in votes if v['vote'] != 'abstain']

# Check quorum (e.g., 50% active participation)
quorum_required = len(pattern.voters) * 0.5

if len(active_votes) >= quorum_required:
    # Proceed with consensus determination
    result = pattern.determine_consensus(proposal_id)
else:
    print(f"Quorum not met: {len(active_votes)}/{quorum_required}")
```

### 6. Multi-Round Voting

**Guideline**: Allow proposal revision and re-voting

```python
# Round 1
proposal_r1 = pattern.create_proposal(topic, context_v1)
for voter in pattern.voters:
    voter.vote(proposal_r1)

result_r1 = pattern.determine_consensus(proposal_r1['proposal_id'])

if result_r1['consensus_reached'] == 'no':
    # Clear memory for round 2
    pattern.clear_shared_memory()

    # Revised proposal with more context
    proposal_r2 = pattern.create_proposal(topic, context_v2_improved)
    for voter in pattern.voters:
        voter.vote(proposal_r2)

    result_r2 = pattern.determine_consensus(proposal_r2['proposal_id'])
```

---

## Use Cases

### 1. Architecture Review Board (ARB)

**Scenario**: Formal architecture proposal review and approval

```python
arb_pattern = create_consensus_pattern(
    num_voters=5,
    voter_perspectives=["security", "performance", "scalability", "cost", "compliance"]
)

# Create architecture proposal
proposal = arb_pattern.create_proposal(
    topic="Migrate to microservices architecture",
    context="Current monolith has scaling issues..."
)

# ARB members review and vote
for voter in arb_pattern.voters:
    vote = voter.vote(proposal)

# Determine consensus
decision = arb_pattern.determine_consensus(proposal['proposal_id'])
```

### 2. Technical RFC Approval

**Scenario**: RFC review and approval process

```python
rfc_pattern = create_consensus_pattern(
    num_voters=3,
    voter_perspectives=["technical_lead", "architect", "domain_expert"]
)

# Submit RFC for review
rfc = rfc_pattern.create_proposal(
    topic="RFC-123: New API Authentication Scheme",
    context="Proposal to replace basic auth with OAuth2..."
)
```

### 3. Feature Prioritization

**Scenario**: Product team votes on feature priorities

```python
product_pattern = create_consensus_pattern(
    num_voters=4,
    voter_perspectives=["product", "engineering", "design", "customer_success"]
)

# Propose feature
feature = product_pattern.create_proposal(
    topic="Add dark mode support",
    context="Highly requested by users, moderate effort..."
)
```

### 4. Code Review Consensus

**Scenario**: Multiple reviewers must approve code changes

```python
review_pattern = create_consensus_pattern(
    num_voters=3,
    voter_perspectives=["senior_dev_1", "senior_dev_2", "security_reviewer"]
)

# Review code change
review = review_pattern.create_proposal(
    topic="PR #456: Refactor authentication module",
    context="Changes: ..."
)
```

---

## Voting Strategies

### Simple Majority (Default)

**Rule**: >50% approve

```python
approvals = sum(1 for v in votes if v['vote'] == 'approve')
consensus = approvals > len(votes) / 2
```

**Use For**: Standard decisions, low-to-medium impact changes

### Supermajority

**Rule**: ≥67% approve

```python
approvals = sum(1 for v in votes if v['vote'] == 'approve')
consensus = approvals >= len(votes) * 0.67
```

**Use For**: High-impact decisions, architecture changes, breaking changes

### Unanimous

**Rule**: 100% approve

```python
approvals = sum(1 for v in votes if v['vote'] == 'approve')
consensus = approvals == len(votes)
```

**Use For**: Critical decisions, irreversible changes, security policies

### Confidence-Weighted

**Rule**: Weight votes by confidence level

```python
weighted_approvals = sum(
    v['confidence'] for v in votes if v['vote'] == 'approve'
)
total_confidence = sum(v['confidence'] for v in votes)
consensus = weighted_approvals > total_confidence / 2
```

**Use For**: Expert panels where confidence matters

### Quorum-Based

**Rule**: Minimum participation required

```python
active_votes = [v for v in votes if v['vote'] != 'abstain']
quorum_met = len(active_votes) >= len(votes) * 0.5

if quorum_met:
    approvals = sum(1 for v in active_votes if v['vote'] == 'approve')
    consensus = approvals > len(active_votes) / 2
```

**Use For**: Ensuring sufficient participation

---

## Troubleshooting

### Common Issues

#### Issue 1: Tie in voting (even number of voters)

**Symptom**: 2-2 split, no clear consensus

**Cause**: Even number of voters

**Solution**:
```python
# Option 1: Use odd number of voters
pattern = create_consensus_pattern(num_voters=5)  # Instead of 4

# Option 2: Add tiebreaker voter
if approvals == rejections:
    # Add specialized tiebreaker voter
    tiebreaker = VoterAgent(..., perspective="tiebreaker")
    tiebreaker_vote = tiebreaker.vote(proposal)
```

#### Issue 2: Low vote confidence

**Symptom**: Average confidence <0.5

**Cause**: Voters lack information or expertise

**Solution**:
```python
# Check confidence
avg_conf = sum(v['confidence'] for v in votes) / len(votes)

if avg_conf < 0.5:
    # Provide more context and re-propose
    pattern.clear_shared_memory()
    enhanced_proposal = pattern.create_proposal(
        topic=topic,
        context=context + "\n\nAdditional details: ..."
    )
```

#### Issue 3: High abstention rate

**Symptom**: >50% voters abstain

**Cause**: Topic too technical or outside voter expertise

**Solution**:
```python
# Check abstentions
abstentions = sum(1 for v in votes if v['vote'] == 'abstain')

if abstentions > len(votes) * 0.5:
    # Adjust voter perspectives to match topic
    pattern = create_consensus_pattern(
        num_voters=3,
        voter_perspectives=["domain_expert_1", "domain_expert_2", "domain_expert_3"]
    )
```

#### Issue 4: No consensus after multiple rounds

**Symptom**: Still no consensus after 2-3 rounds

**Cause**: Fundamental disagreement

**Solution**:
```python
# After 3 rounds with no consensus
if round_count >= 3 and consensus_reached == 'no':
    # Escalation options:
    # 1. Require only supermajority instead of unanimity
    # 2. Escalate to higher authority
    # 3. Table the decision
    # 4. Compromise on modified proposal
```

#### Issue 5: Votes not being collected

**Symptom**: `collect_votes()` returns empty list

**Cause**: Voters haven't voted or wrong proposal_id

**Solution**:
```python
# Ensure all voters voted
for voter in pattern.voters:
    voter.vote(proposal)

# Verify votes in memory
votes_in_memory = pattern.get_shared_insights(tags=["vote", proposal['proposal_id']])
print(f"Votes in memory: {len(votes_in_memory)}")

# Use correct proposal_id
votes = pattern.collect_votes(proposal['proposal_id'])  # Correct ID
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
pattern = create_consensus_pattern(num_voters=3)
proposal = pattern.create_proposal("Test topic")
```

### Validation Checklist

Before deploying to production, verify:

- [ ] Pattern validates: `pattern.validate_pattern() == True`
- [ ] Correct number of voters: `len(pattern.voters) == expected`
- [ ] Voter perspectives assigned: All voters have `perspective` attribute
- [ ] Shared memory configured: `pattern.shared_memory is not None`
- [ ] Proposal creation works: `create_proposal()` returns valid dict
- [ ] Voters can vote: All voters have `vote()` method working
- [ ] Consensus determination works: `determine_consensus()` returns valid result
- [ ] Memory clears properly: `clear_shared_memory()` works

---

## Advanced Topics

### Custom Voting Logic

Extend AggregatorAgent for custom consensus logic:

```python
from kaizen.agents.coordination import AggregatorAgent

class SupermajorityAggregator(AggregatorAgent):
    def aggregate_votes(self, proposal_id: str) -> Dict[str, Any]:
        votes = self.get_votes(proposal_id)

        # Custom supermajority logic (67%)
        approvals = sum(1 for v in votes if v['vote'] == 'approve')
        total = len(votes)

        consensus = "yes" if approvals >= total * 0.67 else "no"

        return {
            "consensus_reached": consensus,
            "final_decision": f"{approvals}/{total} approve (67% required)",
            "vote_summary": f"Supermajority: {consensus}"
        }
```

### Weighted Voting

Implement weighted voting by expertise:

```python
# Assign weights to voters
voter_weights = {
    "security": 2.0,      # Security votes count double
    "performance": 1.5,
    "cost": 1.0,
    "ux": 1.0
}

# Calculate weighted consensus
weighted_approvals = sum(
    voter_weights[v['voter_id']] for v in votes if v['vote'] == 'approve'
)
total_weight = sum(voter_weights.values())

consensus = weighted_approvals > total_weight / 2
```

### Integration with Other Patterns

Combine with SupervisorWorkerPattern for complex workflows:

```python
# Use ConsensusPattern for decision
consensus_pattern = create_consensus_pattern(num_voters=3)
proposal = consensus_pattern.create_proposal("Adopt new tech?")
# ... voting ...
decision = consensus_pattern.determine_consensus(proposal_id)

# If approved, use SupervisorWorkerPattern for execution
if decision['consensus_reached'] == 'yes':
    from kaizen.agents.coordination import create_supervisor_worker_pattern

    worker_pattern = create_supervisor_worker_pattern(num_workers=5)
    tasks = worker_pattern.delegate("Implement approved change")
    # ... execution ...
```

---

## Further Reading

- **Implementation Details**: See `PHASE3_CONSENSUS_PATTERN_COMPLETE.md`
- **Test Suite**: See `tests/unit/agents/coordination/test_consensus_pattern.py`
- **Validation Report**: See `CONSENSUS_PATTERN_VALIDATION_REPORT.md`
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
- **Examples**: `examples/coordination/` directory (examples 05-08)
- **Tests**: `tests/unit/agents/coordination/` for usage patterns
- **Community**: [Link to community forum/chat]

---

**Last Updated**: 2025-10-04
**Pattern Version**: 1.0.0
**Status**: ✅ Production Ready
