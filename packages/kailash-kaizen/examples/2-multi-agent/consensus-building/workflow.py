"""
Consensus-Building Multi-Agent Pattern.

This example demonstrates voting-based decision-making using SharedMemoryPool
from Phase 2 (Week 3). Multiple agents vote on proposals to reach consensus.

Agents:
1. ProposerAgent - Creates solution proposals
2. ReviewerAgent - Reviews and votes on proposals (3 instances)
3. FacilitatorAgent - Counts votes, determines consensus, handles ties

Key Features:
- Democratic voting system
- 2/3 consensus threshold
- Multiple vote types (approve/reject/modify)
- Weighted voting (modify = 0.5)
- Transparent decision rationale

Architecture:
    Problem Statement
         |
         v
    ProposerAgent (creates proposal)
         |
         v (writes to SharedMemoryPool)
    SharedMemoryPool ["proposal", "pending"]
         |
         v (reviewers read proposal)
    ReviewerAgent(s) (3 instances vote)
         |
         v (write votes to SharedMemoryPool)
    SharedMemoryPool ["vote"]
         |
         v (facilitator reads votes)
    FacilitatorAgent (calculates consensus)
         |
         v (writes decision to SharedMemoryPool)
    Final Decision

Consensus Rules:
- Approval: >= 2/3 reviewers vote "approve" → ACCEPT
- Rejection: >= 2/3 reviewers vote "reject" → REJECT
- Mixed: No 2/3 majority → REQUEST_REVISION
- Modify votes: Counted as partial approval (weight 0.5)

Use Cases:
- Code review decisions
- Architecture proposal voting
- Multi-stakeholder decision-making
- Quality assurance gates

Author: Kaizen Framework Team
Created: 2025-10-02 (Phase 5, Task 5E.1, Example 2)
Reference: supervisor-worker example, Phase 4 shared-insights
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# Signature definitions


class ProposalSignature(Signature):
    """Signature for proposal creation."""

    problem: str = InputField(desc="Problem to solve")

    proposal: str = OutputField(desc="Proposed solution")
    reasoning: str = OutputField(desc="Reasoning behind proposal")


class ReviewSignature(Signature):
    """Signature for proposal review and voting."""

    proposal: str = InputField(desc="Proposal to review")

    vote: str = OutputField(desc="Vote: approve/reject/modify", default="approve")
    feedback: str = OutputField(desc="Feedback on proposal", default="")
    confidence: str = OutputField(desc="Confidence score 0-1", default="0.8")


class FacilitationSignature(Signature):
    """Signature for vote facilitation and consensus."""

    votes: str = InputField(desc="JSON list of all votes")

    decision: str = OutputField(desc="Final decision: ACCEPT/REJECT/REQUEST_REVISION")
    rationale: str = OutputField(desc="Decision rationale")
    consensus_level: str = OutputField(desc="Percentage agreement", default="0.0")


# Configuration


@dataclass
class ConsensusConfig:
    """Configuration for consensus-building workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    num_reviewers: int = 3
    consensus_threshold: float = 0.67  # 2/3 threshold


# Agent implementations


class ProposerAgent(BaseAgent):
    """
    ProposerAgent: Creates solution proposals.

    Responsibilities:
    - Receive problem statement
    - Analyze problem and constraints
    - Generate solution proposal
    - Provide reasoning for proposal
    - Write proposal to shared memory

    Shared Memory Behavior:
    - Writes proposals with tags: ["proposal", "pending", proposal_id]
    - Importance: 0.9 (high priority for review)
    - Segment: "proposals"
    """

    def __init__(
        self, config: ConsensusConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize ProposerAgent.

        Args:
            config: Consensus workflow configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=ProposalSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config

    def propose(self, problem: str) -> Dict[str, Any]:
        """
        Create proposal for problem.

        Args:
            problem: Problem statement to solve

        Returns:
            Dictionary containing proposal and reasoning
        """
        # Generate proposal ID
        proposal_id = f"proposal_{uuid.uuid4().hex[:8]}"

        # Execute proposal generation via base agent
        result = self.run(problem=problem, session_id=f"propose_{proposal_id}")

        # Extract proposal and reasoning
        proposal = result.get("proposal", "")
        reasoning = result.get("reasoning", "")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content=json.dumps(
                {"proposal": proposal, "reasoning": reasoning, "problem": problem}
            ),
            tags=["proposal", "pending", proposal_id],
            importance=0.9,
            segment="proposals",
        )

        return {
            "proposal_id": proposal_id,
            "proposal": proposal,
            "reasoning": reasoning,
        }


class ReviewerAgent(BaseAgent):
    """
    ReviewerAgent: Reviews and votes on proposals.

    Responsibilities:
    - Read proposals from shared memory
    - Analyze proposal quality
    - Vote: approve/reject/modify
    - Provide feedback and confidence score
    - Write vote to shared memory

    Shared Memory Behavior:
    - Reads proposals with tags: ["proposal", "pending"]
    - Writes votes with tags: ["vote", reviewer_id, proposal_id]
    - Importance: 0.8 for votes
    - Segment: "votes"
    """

    def __init__(
        self, config: ConsensusConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize ReviewerAgent.

        Args:
            config: Consensus workflow configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=ReviewSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config

    def review(
        self, proposal: str, proposal_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Review proposal and vote.

        Args:
            proposal: Proposal text to review
            proposal_id: Optional proposal identifier

        Returns:
            Dictionary containing vote, feedback, and confidence
        """
        if proposal_id is None:
            proposal_id = f"proposal_{uuid.uuid4().hex[:8]}"

        # Execute review via base agent
        result = self.run(
            proposal=proposal, session_id=f"review_{self.agent_id}_{proposal_id}"
        )

        # Extract vote information with proper defaults for mock provider
        # Mock provider may return generic results, so provide valid defaults
        vote = result.get("vote", "approve")
        # Validate vote is one of the allowed values
        if vote not in ["approve", "reject", "modify"]:
            vote = "approve"  # Default to approve if invalid

        feedback = result.get("feedback", "Proposal reviewed")
        confidence = result.get("confidence", "0.8")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content=json.dumps(
                {"vote": vote, "feedback": feedback, "confidence": confidence}
            ),
            tags=["vote", self.agent_id, proposal_id],
            importance=0.8,
            segment="votes",
        )

        return {
            "vote": vote,
            "feedback": feedback,
            "confidence": confidence,
            "reviewer_id": self.agent_id,
        }


class FacilitatorAgent(BaseAgent):
    """
    FacilitatorAgent: Counts votes and determines consensus.

    Responsibilities:
    - Read all votes from shared memory
    - Calculate vote tallies
    - Apply consensus rules (2/3 threshold)
    - Determine final decision
    - Provide decision rationale
    - Write decision to shared memory

    Consensus Rules:
    - approve votes: weight 1.0
    - reject votes: weight 0.0
    - modify votes: weight 0.5 (partial approval)
    - >= 2/3 approval: ACCEPT
    - >= 2/3 rejection: REJECT
    - No 2/3 majority: REQUEST_REVISION

    Shared Memory Behavior:
    - Reads votes with tags: ["vote", proposal_id]
    - Writes decisions with tags: ["decision", "final", proposal_id]
    - Importance: 1.0 for decisions
    - Segment: "decisions"
    """

    def __init__(
        self, config: ConsensusConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize FacilitatorAgent.

        Args:
            config: Consensus workflow configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=FacilitationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config

    def get_votes(self, proposal_id: str) -> List[Dict[str, Any]]:
        """
        Get all votes for a proposal.

        Args:
            proposal_id: Proposal identifier

        Returns:
            List of vote dictionaries
        """
        if not self.shared_memory:
            return []

        # Read votes from shared memory
        vote_insights = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["vote", proposal_id],
            exclude_own=True,
            limit=50,
        )

        # Parse votes
        votes = []
        for insight in vote_insights:
            content = insight.get("content", "{}")
            if isinstance(content, str):
                try:
                    vote_data = json.loads(content)
                    vote_data["reviewer_id"] = insight.get("agent_id")
                    votes.append(vote_data)
                except json.JSONDecodeError:
                    continue

        return votes

    def calculate_consensus(
        self, votes: List[Dict[str, Any]]
    ) -> tuple[str, float, str]:
        """
        Calculate consensus based on votes.

        Args:
            votes: List of vote dictionaries

        Returns:
            Tuple of (decision, consensus_level, rationale)
        """
        if not votes:
            return "REQUEST_REVISION", 0.0, "No votes received"

        # Count votes with weights
        total_votes = len(votes)
        approve_weight = 0.0
        reject_weight = 0.0

        vote_counts = {"approve": 0, "reject": 0, "modify": 0}

        for vote in votes:
            vote_type = vote.get("vote", "").lower()
            vote_counts[vote_type] = vote_counts.get(vote_type, 0) + 1

            if vote_type == "approve":
                approve_weight += 1.0
            elif vote_type == "reject":
                reject_weight += 1.0
            elif vote_type == "modify":
                approve_weight += 0.5  # Partial approval

        # Calculate percentages
        approval_ratio = approve_weight / total_votes if total_votes > 0 else 0.0
        rejection_ratio = reject_weight / total_votes if total_votes > 0 else 0.0

        # Apply consensus rules
        if approval_ratio >= self.config.consensus_threshold:
            decision = "ACCEPT"
            rationale = f"Consensus reached with {approval_ratio:.1%} approval ({vote_counts['approve']} approve, {vote_counts['modify']} modify, {vote_counts['reject']} reject)"
        elif rejection_ratio >= self.config.consensus_threshold:
            decision = "REJECT"
            rationale = f"Rejected with {rejection_ratio:.1%} rejection ({vote_counts['reject']} reject, {vote_counts['approve']} approve, {vote_counts['modify']} modify)"
        else:
            decision = "REQUEST_REVISION"
            rationale = f"No consensus reached - {approval_ratio:.1%} approval, {rejection_ratio:.1%} rejection ({vote_counts['approve']} approve, {vote_counts['reject']} reject, {vote_counts['modify']} modify)"

        return decision, approval_ratio, rationale

    def facilitate(self, proposal_id: str) -> Dict[str, Any]:
        """
        Facilitate consensus for proposal.

        Args:
            proposal_id: Proposal identifier

        Returns:
            Dictionary containing decision, rationale, and consensus level
        """
        # Get votes
        votes = self.get_votes(proposal_id)

        # Calculate consensus
        decision, consensus_level, rationale = self.calculate_consensus(votes)

        # Execute facilitation via base agent (for enhanced rationale)
        result = self.run(
            votes=json.dumps(votes), session_id=f"facilitate_{proposal_id}"
        )

        # Use calculated decision but allow agent to enhance rationale
        agent_rationale = result.get("rationale", rationale)

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content=json.dumps(
                {
                    "decision": decision,
                    "rationale": agent_rationale or rationale,
                    "consensus_level": consensus_level,
                    "votes": votes,
                }
            ),
            tags=["decision", "final", proposal_id],
            importance=1.0,
            segment="decisions",
        )

        return {
            "decision": decision,
            "rationale": agent_rationale or rationale,
            "consensus_level": f"{consensus_level:.1%}",
            "votes": votes,
        }


# Workflow function


def consensus_building_workflow(problem: str, num_reviewers: int = 3) -> Dict[str, Any]:
    """
    Run consensus-building multi-agent workflow.

    This workflow demonstrates voting-based decision-making:
    1. ProposerAgent creates proposal for problem
    2. Proposal written to SharedMemoryPool
    3. ReviewerAgents (3) read and vote on proposal
    4. Votes written to SharedMemoryPool
    5. FacilitatorAgent reads votes and determines consensus
    6. Final decision returned with rationale

    Args:
        problem: Problem statement to solve
        num_reviewers: Number of reviewer agents (default: 3)

    Returns:
        Dictionary containing:
        - problem: Original problem statement
        - proposal: Proposed solution
        - votes: Individual reviewer votes
        - decision: Final consensus decision
        - stats: Shared memory statistics
    """
    # Setup shared memory pool
    shared_pool = SharedMemoryPool()
    config = ConsensusConfig(num_reviewers=num_reviewers)

    # Create agents
    proposer = ProposerAgent(config, shared_pool, agent_id="proposer")

    reviewers = []
    for i in range(num_reviewers):
        reviewer = ReviewerAgent(config, shared_pool, agent_id=f"reviewer_{i+1}")
        reviewers.append(reviewer)

    facilitator = FacilitatorAgent(config, shared_pool, agent_id="facilitator")

    print(f"\n{'='*60}")
    print(f"Consensus-Building Pattern: {problem}")
    print(f"{'='*60}\n")

    # Step 1: Proposer creates proposal
    print("Step 1: Proposer creating solution...")
    proposal_result = proposer.propose(problem)
    proposal_id = proposal_result["proposal_id"]
    print(f"  - Proposal ID: {proposal_id}")
    print(f"  - Proposal: {proposal_result['proposal'][:100]}...")
    print(f"  - Reasoning: {proposal_result['reasoning'][:100]}...")

    # Step 2: Reviewers vote on proposal
    print("\nStep 2: Reviewers voting on proposal...")
    votes = []
    for reviewer in reviewers:
        vote_result = reviewer.review(
            proposal_result["proposal"], proposal_id=proposal_id
        )
        votes.append(vote_result)
        print(
            f"  - {vote_result['reviewer_id']}: {vote_result['vote']} (confidence: {vote_result['confidence']})"
        )

    # Step 3: Facilitator determines consensus
    print("\nStep 3: Facilitator calculating consensus...")
    decision_result = facilitator.facilitate(proposal_id)
    print(f"  - Decision: {decision_result['decision']}")
    print(f"  - Consensus Level: {decision_result['consensus_level']}")
    print(f"  - Rationale: {decision_result['rationale']}")

    # Show shared memory stats
    stats = shared_pool.get_stats()
    print(f"\n{'='*60}")
    print("Shared Memory Statistics:")
    print(f"{'='*60}")
    print(f"  - Total insights: {stats['insight_count']}")
    print(f"  - Agents involved: {stats['agent_count']}")
    print(f"  - Tag distribution: {stats['tag_distribution']}")
    print(f"  - Segment distribution: {stats['segment_distribution']}")
    print(f"{'='*60}\n")

    return {
        "problem": problem,
        "proposal": proposal_result,
        "votes": votes,
        "decision": decision_result,
        "stats": stats,
    }


# Main execution
if __name__ == "__main__":
    # Run example workflow
    result = consensus_building_workflow(
        "Should we migrate our monolithic application to microservices architecture?"
    )

    print("\nWorkflow Complete!")
    print(f"Problem: {result['problem']}")
    print(f"Proposal: {result['proposal']['proposal']}")
    print(f"Votes: {len(result['votes'])} reviewers")
    print(f"Decision: {result['decision']['decision']}")
    print(f"Consensus: {result['decision']['consensus_level']}")
