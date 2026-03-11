# Consensus-Building Multi-Agent Pattern

## Overview

The Consensus-Building pattern implements a democratic voting system where multiple agents collaborate to reach consensus on proposals. This pattern is ideal for scenarios requiring group decision-making, peer review, and multi-stakeholder approval processes.

**Key Features:**
- Democratic voting with 2/3 consensus threshold
- Multiple vote types (approve, reject, modify)
- Weighted voting (modify votes = 0.5 approval)
- Transparent decision rationale
- SharedMemoryPool integration for vote tracking

**Pattern Type:** Coordination and Decision-Making

**Complexity:** Intermediate

**Use Cases:**
- Code review decisions
- Architecture proposal voting
- Design review processes
- Quality assurance gates
- Multi-stakeholder decision-making

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Consensus-Building Workflow                  │
└─────────────────────────────────────────────────────────────────┘

                       Problem Statement
                              │
                              ▼
                    ┌──────────────────┐
                    │  ProposerAgent   │
                    │  - Analyzes      │
                    │  - Creates       │
                    │    proposal      │
                    └────────┬─────────┘
                             │
                             │ writes {"proposal", "reasoning"}
                             ▼
                    ┌──────────────────┐
                    │ SharedMemoryPool │
                    │ tags: ["proposal"│
                    │        "pending"] │
                    │ segment:          │
                    │   "proposals"     │
                    └────────┬─────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ ReviewerAgent│ │ ReviewerAgent│ │ ReviewerAgent│
    │      #1      │ │      #2      │ │      #3      │
    │              │ │              │ │              │
    │ - Reads      │ │ - Reads      │ │ - Reads      │
    │   proposal   │ │   proposal   │ │   proposal   │
    │ - Evaluates  │ │ - Evaluates  │ │ - Evaluates  │
    │ - Votes      │ │ - Votes      │ │ - Votes      │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
           │ writes vote    │ writes vote    │ writes vote
           └────────────────┼────────────────┘
                            ▼
                    ┌──────────────────┐
                    │ SharedMemoryPool │
                    │ tags: ["vote",   │
                    │   "reviewer_id", │
                    │   "proposal_id"] │
                    │ segment: "votes" │
                    └────────┬─────────┘
                             │
                             │ reads all votes
                             ▼
                    ┌──────────────────┐
                    │ FacilitatorAgent │
                    │ - Reads votes    │
                    │ - Calculates     │
                    │   consensus      │
                    │ - Applies rules  │
                    │ - Determines     │
                    │   decision       │
                    └────────┬─────────┘
                             │
                             │ writes decision
                             ▼
                    ┌──────────────────┐
                    │ SharedMemoryPool │
                    │ tags: ["decision"│
                    │        "final"]   │
                    │ segment:          │
                    │   "decisions"     │
                    └────────┬─────────┘
                             │
                             ▼
                      Final Decision
                    (ACCEPT/REJECT/
                    REQUEST_REVISION)
```

## Agents

### 1. ProposerAgent

**Role:** Creates solution proposals for problems

**Responsibilities:**
- Receives problem statement
- Analyzes problem and constraints
- Generates detailed solution proposal
- Provides reasoning behind proposal
- Writes proposal to SharedMemoryPool

**Signature:**
```python
class ProposalSignature(Signature):
    problem: str = InputField(desc="Problem to solve")
    proposal: str = OutputField(desc="Proposed solution")
    reasoning: str = OutputField(desc="Reasoning behind proposal")
```

**Shared Memory Behavior:**
- **Writes:** Proposals with tags `["proposal", "pending", proposal_id]`
- **Importance:** 0.9 (high priority for review)
- **Segment:** "proposals"

**Methods:**
- `propose(problem: str) -> Dict[str, Any]` - Create proposal

### 2. ReviewerAgent

**Role:** Reviews proposals and casts votes (3 instances)

**Responsibilities:**
- Reads proposals from SharedMemoryPool
- Analyzes proposal quality and feasibility
- Casts vote: approve/reject/modify
- Provides detailed feedback
- Assigns confidence score to vote
- Writes vote to SharedMemoryPool

**Signature:**
```python
class ReviewSignature(Signature):
    proposal: str = InputField(desc="Proposal to review")
    vote: str = OutputField(desc="Vote: approve/reject/modify")
    feedback: str = OutputField(desc="Feedback on proposal")
    confidence: str = OutputField(desc="Confidence score 0-1")
```

**Vote Types:**
- **approve:** Full approval (weight 1.0)
- **reject:** Full rejection (weight 0.0)
- **modify:** Partial approval with requested changes (weight 0.5)

**Shared Memory Behavior:**
- **Reads:** Proposals with tags `["proposal", "pending"]`
- **Writes:** Votes with tags `["vote", reviewer_id, proposal_id]`
- **Importance:** 0.8
- **Segment:** "votes"

**Methods:**
- `review(proposal: str, proposal_id: str) -> Dict[str, Any]` - Review and vote

### 3. FacilitatorAgent

**Role:** Counts votes and determines consensus

**Responsibilities:**
- Reads all votes from SharedMemoryPool
- Calculates vote tallies with weights
- Applies consensus rules (2/3 threshold)
- Determines final decision
- Provides transparent rationale
- Writes decision to SharedMemoryPool

**Signature:**
```python
class FacilitationSignature(Signature):
    votes: str = InputField(desc="JSON list of all votes")
    decision: str = OutputField(desc="Final decision")
    rationale: str = OutputField(desc="Decision rationale")
    consensus_level: str = OutputField(desc="Percentage agreement")
```

**Consensus Rules:**
- **Approval:** >= 2/3 approval → ACCEPT
- **Rejection:** >= 2/3 rejection → REJECT
- **Mixed:** No 2/3 majority → REQUEST_REVISION

**Vote Weights:**
- approve: 1.0
- reject: 0.0
- modify: 0.5 (counts as partial approval)

**Shared Memory Behavior:**
- **Reads:** Votes with tags `["vote", proposal_id]`
- **Writes:** Decisions with tags `["decision", "final", proposal_id]`
- **Importance:** 1.0 (highest priority)
- **Segment:** "decisions"

**Methods:**
- `get_votes(proposal_id: str) -> List[Dict]` - Retrieve all votes
- `calculate_consensus(votes: List[Dict]) -> tuple` - Calculate consensus
- `facilitate(proposal_id: str) -> Dict[str, Any]` - Facilitate decision

## Workflow

### Execution Flow

```python
def consensus_building_workflow(problem: str, num_reviewers: int = 3):
    """
    Step 1: ProposerAgent creates proposal
      ├─ Analyzes problem
      ├─ Generates solution
      └─ Writes to SharedMemoryPool (tags: ["proposal", "pending"])

    Step 2: ReviewerAgents vote on proposal (parallel)
      ├─ Reviewer 1 reads proposal, evaluates, casts vote
      ├─ Reviewer 2 reads proposal, evaluates, casts vote
      └─ Reviewer 3 reads proposal, evaluates, casts vote
      └─ All votes written to SharedMemoryPool (tags: ["vote"])

    Step 3: FacilitatorAgent determines consensus
      ├─ Reads all votes from SharedMemoryPool
      ├─ Calculates weighted vote tally
      ├─ Applies 2/3 consensus threshold
      ├─ Determines decision (ACCEPT/REJECT/REQUEST_REVISION)
      └─ Writes decision to SharedMemoryPool (tags: ["decision", "final"])

    Return: {
      "problem": <original problem>,
      "proposal": <proposed solution>,
      "votes": <list of all votes>,
      "decision": <final decision with rationale>,
      "stats": <shared memory statistics>
    }
    """
```

### Step-by-Step Execution

**Step 1: Proposal Creation**
```python
proposer = ProposerAgent(config, shared_pool, "proposer")
proposal_result = proposer.propose("How to improve code review process?")
# Output: {"proposal_id": "...", "proposal": "...", "reasoning": "..."}
```

**Step 2: Parallel Voting**
```python
reviewers = [
    ReviewerAgent(config, shared_pool, f"reviewer_{i}")
    for i in range(3)
]

votes = []
for reviewer in reviewers:
    vote = reviewer.review(proposal_result["proposal"], proposal_id)
    votes.append(vote)
# Output: [{"vote": "approve", ...}, {"vote": "modify", ...}, ...]
```

**Step 3: Consensus Determination**
```python
facilitator = FacilitatorAgent(config, shared_pool, "facilitator")
decision = facilitator.facilitate(proposal_id)
# Output: {
#   "decision": "ACCEPT",
#   "rationale": "Consensus reached with 83% approval...",
#   "consensus_level": "83.3%"
# }
```

## Consensus Rules

### Decision Matrix

| Approve | Reject | Modify | Approval % | Decision           |
|---------|--------|--------|------------|--------------------|
| 3       | 0      | 0      | 100%       | ACCEPT             |
| 2       | 1      | 0      | 67%        | ACCEPT (threshold) |
| 2       | 0      | 1      | 83%        | ACCEPT             |
| 1       | 2      | 0      | 33%        | REJECT             |
| 0       | 3      | 0      | 0%         | REJECT             |
| 1       | 1      | 1      | 50%        | REQUEST_REVISION   |
| 0       | 2      | 1      | 17%        | REJECT             |

### Calculation Formula

```
approval_weight = (approve_count × 1.0) + (modify_count × 0.5)
approval_ratio = approval_weight / total_votes

if approval_ratio >= 0.67:
    decision = "ACCEPT"
elif rejection_ratio >= 0.67:
    decision = "REJECT"
else:
    decision = "REQUEST_REVISION"
```

### Threshold Configuration

The consensus threshold can be configured:

```python
config = ConsensusConfig(
    consensus_threshold=0.67  # 2/3 = 67%
)
# Other options:
# - 0.75 for 3/4 supermajority
# - 0.51 for simple majority
# - 1.0 for unanimous decision
```

## Shared Memory Usage

### Memory Segments

| Segment    | Content          | Tags                              | Importance |
|------------|------------------|-----------------------------------|------------|
| proposals  | Proposal data    | ["proposal", "pending", id]       | 0.9        |
| votes      | Vote data        | ["vote", reviewer_id, id]         | 0.8        |
| decisions  | Decision data    | ["decision", "final", id]         | 1.0        |

### Tag Strategy

**Proposal Tags:**
- `proposal` - Identifies as proposal
- `pending` - Status indicator
- `<proposal_id>` - Unique identifier

**Vote Tags:**
- `vote` - Identifies as vote
- `<reviewer_id>` - Reviewer identifier
- `<proposal_id>` - Links to proposal

**Decision Tags:**
- `decision` - Identifies as decision
- `final` - Status indicator
- `<proposal_id>` - Links to proposal

### Insight Structure

**Proposal Insight:**
```python
{
    "agent_id": "proposer",
    "content": json.dumps({
        "proposal": "...",
        "reasoning": "...",
        "problem": "..."
    }),
    "tags": ["proposal", "pending", "proposal_abc123"],
    "importance": 0.9,
    "segment": "proposals",
    "metadata": {
        "proposal_id": "proposal_abc123",
        "problem": "..."
    }
}
```

**Vote Insight:**
```python
{
    "agent_id": "reviewer_1",
    "content": json.dumps({
        "vote": "approve",
        "feedback": "...",
        "confidence": "0.9"
    }),
    "tags": ["vote", "reviewer_1", "proposal_abc123"],
    "importance": 0.8,
    "segment": "votes",
    "metadata": {
        "proposal_id": "proposal_abc123",
        "reviewer_id": "reviewer_1"
    }
}
```

## Quick Start

### Basic Usage

```python
from workflow import consensus_building_workflow

# Run consensus workflow
result = consensus_building_workflow(
    "Should we migrate to microservices architecture?"
)

# Access results
print(f"Problem: {result['problem']}")
print(f"Proposal: {result['proposal']['proposal']}")
print(f"Decision: {result['decision']['decision']}")
print(f"Consensus: {result['decision']['consensus_level']}")
print(f"Rationale: {result['decision']['rationale']}")

# Vote breakdown
for vote in result['votes']:
    print(f"  {vote['reviewer_id']}: {vote['vote']}")
```

### Custom Configuration

```python
from workflow import (
    consensus_building_workflow,
    ConsensusConfig
)

# Custom configuration
config = ConsensusConfig(
    llm_provider="openai",
    model="gpt-4",
    num_reviewers=5,  # More reviewers
    consensus_threshold=0.80  # Higher threshold (4/5)
)

# Run with custom config
result = consensus_building_workflow(
    "Should we rewrite in Rust?",
    num_reviewers=5
)
```

### Direct Agent Usage

```python
from workflow import (
    ProposerAgent,
    ReviewerAgent,
    FacilitatorAgent,
    ConsensusConfig
)
from kaizen.memory.shared_memory import SharedMemoryPool

# Setup
pool = SharedMemoryPool()
config = ConsensusConfig()

# Create agents
proposer = ProposerAgent(config, pool, "proposer")
reviewer1 = ReviewerAgent(config, pool, "reviewer_1")
reviewer2 = ReviewerAgent(config, pool, "reviewer_2")
reviewer3 = ReviewerAgent(config, pool, "reviewer_3")
facilitator = FacilitatorAgent(config, pool, "facilitator")

# Execute manually
proposal = proposer.propose("What's the best database?")
vote1 = reviewer1.review(proposal["proposal"], proposal["proposal_id"])
vote2 = reviewer2.review(proposal["proposal"], proposal["proposal_id"])
vote3 = reviewer3.review(proposal["proposal"], proposal["proposal_id"])
decision = facilitator.facilitate(proposal["proposal_id"])

print(f"Decision: {decision['decision']}")
print(f"Consensus: {decision['consensus_level']}")
```

## Configuration

### ConsensusConfig

```python
@dataclass
class ConsensusConfig:
    llm_provider: str = "mock"         # LLM provider
    model: str = "gpt-3.5-turbo"       # LLM model
    num_reviewers: int = 3              # Number of reviewers
    consensus_threshold: float = 0.67   # 2/3 threshold
```

**Parameters:**

- **llm_provider** (str): LLM provider ("openai", "anthropic", "mock")
- **model** (str): Model identifier
- **num_reviewers** (int): Number of reviewer agents (default: 3)
- **consensus_threshold** (float): Approval threshold 0-1 (default: 0.67)

**Threshold Options:**
- `0.51` - Simple majority (>50%)
- `0.67` - Two-thirds supermajority (2/3)
- `0.75` - Three-quarters supermajority (3/4)
- `1.0` - Unanimous decision (100%)

## Use Cases

### 1. Code Review Decisions

**Scenario:** Automated code review approval/rejection

```python
result = consensus_building_workflow(
    "Should PR #123 be merged? Changes: Added caching layer, refactored database queries."
)
# Decision: ACCEPT if 2+ reviewers approve
# Output: Merge approved/rejected/needs changes
```

**Benefits:**
- Democratic review process
- Prevents single point of failure
- Captures diverse perspectives

### 2. Architecture Proposal Voting

**Scenario:** Team votes on architectural changes

```python
result = consensus_building_workflow(
    "Proposal: Adopt event-driven architecture with Kafka for order processing."
)
# Decision: ACCEPT/REJECT/REQUEST_REVISION
# Rationale: Consensus with detailed feedback
```

**Benefits:**
- Ensures team alignment
- Documents decision rationale
- Reduces bikeshedding

### 3. Design Review Process

**Scenario:** UI/UX design approval

```python
result = consensus_building_workflow(
    "New checkout flow design: 3-step process vs current 5-step."
)
# Decision: Based on designer + PM + engineer votes
```

**Benefits:**
- Multi-stakeholder input
- Balanced perspective
- Transparent decision trail

### 4. Quality Assurance Gates

**Scenario:** Release approval decision

```python
result = consensus_building_workflow(
    "Release v2.0: 98% test coverage, 2 known low-priority bugs."
)
# Decision: QA + Security + DevOps vote
# Threshold: Must have 100% approval to release
```

**Benefits:**
- Multi-domain validation
- Risk assessment
- Audit trail

### 5. Multi-Stakeholder Decision-Making

**Scenario:** Feature prioritization

```python
result = consensus_building_workflow(
    "Feature request: Add dark mode. Effort: 2 weeks, User requests: 1,234"
)
# Decision: Product + Eng + Design vote
```

**Benefits:**
- Balanced priorities
- Resource allocation
- Stakeholder buy-in

## Related Examples

### Similar Patterns

1. **[supervisor-worker](../supervisor-worker/)** - Centralized delegation with task distribution
   - **Similarity:** Both use SharedMemoryPool for coordination
   - **Difference:** Supervisor-worker is hierarchical, consensus is democratic

2. **[debate-decision](../debate-decision/)** - Two agents debate to reach decision
   - **Similarity:** Both involve decision-making processes
   - **Difference:** Debate is adversarial, consensus is collaborative

3. **[domain-specialists](../domain-specialists/)** - Multiple experts provide specialized input
   - **Similarity:** Both aggregate multiple agent perspectives
   - **Difference:** Specialists provide expertise, consensus provides votes

### When to Use Each

| Pattern              | Use When                                    |
|----------------------|---------------------------------------------|
| **Consensus**        | Democratic voting, approval gates           |
| **Supervisor-Worker**| Clear hierarchy, task delegation            |
| **Debate-Decision**  | Need adversarial perspectives               |
| **Domain-Specialist**| Need specialized domain knowledge           |

## Performance Characteristics

### Complexity

- **Time Complexity:** O(n) where n = number of reviewers
- **Memory:** O(n) for storing n votes
- **Parallelization:** Reviewer voting can be parallelized

### Scalability

**Tested Configurations:**
- 3 reviewers (default) - ~4 seconds
- 5 reviewers - ~6 seconds
- 10 reviewers - ~12 seconds

**Limits:**
- Practical maximum: ~20 reviewers
- Beyond 20: Consider sampling or delegation

### Optimization Tips

1. **Parallel Voting:** Use threading/async for reviewer execution
2. **Early Termination:** Stop when threshold reached (3/3 approve = done)
3. **Weighted Voting:** Senior reviewers = higher weight
4. **Caching:** Cache proposal analysis for multiple votes

## Testing

### Running Tests

```bash
# Run all consensus tests
pytest tests/unit/examples/test_consensus_building.py -v

# Run specific test class
pytest tests/unit/examples/test_consensus_building.py::TestProposalCreation -v

# Run with coverage
pytest tests/unit/examples/test_consensus_building.py --cov=workflow
```

### Test Coverage

**20 comprehensive tests covering:**

1. **Proposal Creation (3 tests)**
   - Proposal generation
   - Shared memory storage
   - Reasoning documentation

2. **Reviewer Voting (5 tests)**
   - Approve votes
   - Reject votes
   - Modify votes
   - Multiple reviewers
   - Vote storage

3. **Facilitator Consensus (5 tests)**
   - Vote reading
   - All approve scenario
   - Split vote scenario
   - All reject scenario
   - Modify vote weighting

4. **Full Workflow (4 tests)**
   - Complete workflow
   - Approval path
   - Rejection path
   - Revision request path

5. **Consensus Rules (2 tests)**
   - Threshold met
   - Threshold not met

6. **Integration (1 test)**
   - Shared memory statistics

## Example Output

```
============================================================
Consensus-Building Pattern: Should we migrate to microservices?
============================================================

Step 1: Proposer creating solution...
  - Proposal ID: proposal_a1b2c3d4
  - Proposal: Adopt microservices architecture with API gateway...
  - Reasoning: Current monolith faces scaling challenges...

Step 2: Reviewers voting on proposal...
  - reviewer_1: approve (confidence: 0.9)
  - reviewer_2: modify (confidence: 0.7)
  - reviewer_3: approve (confidence: 0.85)

Step 3: Facilitator calculating consensus...
  - Decision: ACCEPT
  - Consensus Level: 83.3%
  - Rationale: Consensus reached with 83.3% approval (2 approve, 1 modify, 0 reject)

============================================================
Shared Memory Statistics:
============================================================
  - Total insights: 5
  - Agents involved: 5
  - Tag distribution: {'proposal': 1, 'pending': 1, 'vote': 3, 'decision': 1}
  - Segment distribution: {'proposals': 1, 'votes': 3, 'decisions': 1}
============================================================

Workflow Complete!
Problem: Should we migrate to microservices?
Proposal: Adopt microservices architecture with API gateway...
Votes: 3 reviewers
Decision: ACCEPT
Consensus: 83.3%
```

## Implementation Notes

### Design Decisions

1. **2/3 Threshold:** Balances consensus with decisiveness
2. **Modify Weight 0.5:** Partial approval for nuanced feedback
3. **SharedMemoryPool:** Enables transparent vote tracking
4. **Three Reviewers:** Minimum for meaningful consensus

### Extension Points

**Custom Vote Types:**
```python
# Add "abstain" vote type
# Weight: 0.25 (minimal approval)
if vote_type == "abstain":
    approve_weight += 0.25
```

**Weighted Reviewers:**
```python
# Senior reviewers have higher weight
reviewer_weights = {
    "senior_reviewer": 2.0,
    "junior_reviewer": 1.0
}
approve_weight += reviewer_weights.get(reviewer_id, 1.0)
```

**Dynamic Threshold:**
```python
# Adjust threshold based on proposal importance
if proposal_metadata.get("critical"):
    threshold = 1.0  # Unanimous for critical decisions
else:
    threshold = 0.67  # 2/3 for normal decisions
```

### Known Limitations

1. **Sequential Facilitation:** Facilitator must wait for all votes
2. **No Vote Revision:** Reviewers can't change votes after submission
3. **Fixed Threshold:** Threshold is static (not adaptive)
4. **No Quorum:** No minimum participation requirement

### Future Enhancements

- **Async Voting:** Non-blocking reviewer execution
- **Vote Revision:** Allow reviewers to update votes
- **Adaptive Threshold:** Adjust based on vote distribution
- **Quorum Requirements:** Minimum participation threshold
- **Delegated Voting:** Reviewers can delegate to others
- **Weighted Expertise:** Domain expert votes weighted higher

---

**Author:** Kaizen Framework Team
**Created:** 2025-10-02 (Phase 5, Task 5E.1, Example 2)
**Reference:** supervisor-worker example, Phase 4 shared-insights
**Pattern:** Coordination and Decision-Making
