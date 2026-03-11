"""
Example 7: Consensus Pattern - Advanced Usage

This example demonstrates advanced features of the ConsensusPattern,
including tie handling, confidence analysis, multi-round voting, and consensus strategies.

Learning Objectives:
- Tie scenarios and resolution
- Confidence-weighted voting
- Multi-round consensus building
- Abstention handling
- Quorum requirements
- Consensus threshold tuning

Estimated time: 10 minutes
"""

from typing import Any, Dict, List

from kaizen.agents.coordination import create_consensus_pattern


def analyze_vote_confidence(votes: List[Dict[str, Any]]):
    """Analyze confidence levels across votes."""
    if not votes:
        return {
            "avg_confidence": 0.0,
            "min_confidence": 0.0,
            "max_confidence": 0.0,
            "high_confidence_votes": 0,
        }

    confidences = [v["confidence"] for v in votes]

    return {
        "avg_confidence": sum(confidences) / len(confidences),
        "min_confidence": min(confidences),
        "max_confidence": max(confidences),
        "high_confidence_votes": sum(1 for c in confidences if c > 0.7),
    }


def check_quorum(
    votes: List[Dict[str, Any]], total_voters: int, quorum_pct: float = 0.5
) -> bool:
    """Check if voting quorum is met."""
    non_abstain_votes = [v for v in votes if v["vote"] != "abstain"]
    quorum_required = int(total_voters * quorum_pct)
    return len(non_abstain_votes) >= quorum_required


def main():
    print("=" * 70)
    print("Consensus Pattern - Advanced Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # SCENARIO 1: Tie Resolution
    # ==================================================================
    print("Scenario 1: Tie Resolution")
    print("-" * 70)

    # Create pattern with even number of voters
    pattern = create_consensus_pattern(
        num_voters=4, voter_perspectives=["technical", "business", "legal", "product"]
    )

    # Create controversial proposal
    proposal = pattern.create_proposal(
        topic="Should we prioritize speed over code quality for this sprint?",
        context="Tight deadline but tech debt is accumulating",
    )

    print(f"Proposal: {proposal['topic']}")
    print()

    # Simulate tie (2-2 split)
    print("Voting results:")
    votes = []
    for i, voter in enumerate(pattern.voters):
        vote = voter.vote(proposal)
        votes.append(vote)

        # Show vote
        print(
            f"  {voter.perspective:12} → {vote['vote']:8} (confidence: {vote['confidence']:.2f})"
        )

    print()

    # Check consensus
    result = pattern.determine_consensus(proposal["proposal_id"])

    # Analyze tie
    approvals = sum(1 for v in votes if v["vote"] == "approve")
    rejections = sum(1 for v in votes if v["vote"] == "reject")

    if approvals == rejections:
        print(f"⚖️  TIE DETECTED: {approvals}-{rejections} split")
        print(f"   Consensus: {result['consensus_reached']}")
        print(f"   Resolution: {result['final_decision'][:80]}...")
        print()
        print("   Tie Resolution Options:")
        print("   → Add tiebreaker voter (odd number of voters)")
        print("   → Use confidence-weighted voting")
        print("   → Require supermajority (>60%)")
        print("   → Escalate to higher authority")
    else:
        print(f"✓ Clear decision: {approvals} approve, {rejections} reject")

    print()

    # ==================================================================
    # SCENARIO 2: Confidence-Weighted Analysis
    # ==================================================================
    print("Scenario 2: Confidence-Weighted Analysis")
    print("-" * 70)

    # Create pattern with diverse perspectives
    pattern2 = create_consensus_pattern(
        num_voters=5,
        voter_perspectives=["security", "performance", "ux", "cost", "compliance"],
    )

    # New proposal
    proposal2 = pattern2.create_proposal(
        topic="Should we adopt a new database technology?",
        context="Current DB works but new tech promises better performance",
    )

    print(f"Proposal: {proposal2['topic']}")
    print()

    # Collect votes
    votes2 = []
    print("Voting with confidence levels:")
    for voter in pattern2.voters:
        vote = voter.vote(proposal2)
        votes2.append(vote)
        print(
            f"  {voter.perspective:12} → {vote['vote']:8} (conf: {vote['confidence']:.2f})"
        )

    print()

    # Analyze confidence
    conf_analysis = analyze_vote_confidence(votes2)

    print("Confidence Analysis:")
    print(f"  - Average: {conf_analysis['avg_confidence']:.2f}")
    print(
        f"  - Range: {conf_analysis['min_confidence']:.2f} - {conf_analysis['max_confidence']:.2f}"
    )
    print(
        f"  - High confidence votes (>0.7): {conf_analysis['high_confidence_votes']}/{len(votes2)}"
    )
    print()

    if conf_analysis["avg_confidence"] < 0.5:
        print("  ⚠️  Low average confidence → May need more information")
    elif conf_analysis["avg_confidence"] > 0.7:
        print("  ✓ High average confidence → Strong consensus")
    else:
        print("  → Moderate confidence → Acceptable consensus")

    print()

    # ==================================================================
    # SCENARIO 3: Abstention Handling
    # ==================================================================
    print("Scenario 3: Abstention Handling")
    print("-" * 70)

    # Create pattern
    pattern3 = create_consensus_pattern(
        num_voters=5,
        voter_perspectives=["expert1", "expert2", "expert3", "novice1", "novice2"],
    )

    # Technical proposal (novices likely to abstain)
    proposal3 = pattern3.create_proposal(
        topic="Should we implement a custom garbage collector?",
        context="Highly technical decision requiring deep expertise",
    )

    print(f"Proposal: {proposal3['topic']}")
    print()

    # Vote
    votes3 = []
    print("Voting results (technical topic):")
    for voter in pattern3.voters:
        vote = voter.vote(proposal3)
        votes3.append(vote)
        print(
            f"  {voter.perspective:12} → {vote['vote']:8} (conf: {vote['confidence']:.2f})"
        )

    print()

    # Analyze abstentions
    abstentions = sum(1 for v in votes3 if v["vote"] == "abstain")
    active_votes = len(votes3) - abstentions

    print("Abstention Analysis:")
    print(
        f"  - Abstentions: {abstentions}/{len(votes3)} ({abstentions/len(votes3)*100:.1f}%)"
    )
    print(f"  - Active votes: {active_votes}/{len(votes3)}")
    print()

    # Check quorum
    quorum_met = check_quorum(votes3, len(pattern3.voters), quorum_pct=0.5)

    if quorum_met:
        print("  ✓ Quorum met (≥50% active votes)")
    else:
        print("  ✗ Quorum NOT met (<50% active votes)")
        print("    → Need more voters or re-proposal with more context")

    print()

    # ==================================================================
    # SCENARIO 4: Multi-Round Consensus
    # ==================================================================
    print("Scenario 4: Multi-Round Consensus")
    print("-" * 70)

    # Create pattern
    pattern4 = create_consensus_pattern(
        num_voters=3, voter_perspectives=["proposer", "reviewer1", "reviewer2"]
    )

    # Initial proposal
    topic = "Should we refactor the authentication module?"
    context_round1 = "Current auth code is hard to maintain"

    print("Round 1: Initial Proposal")
    print(f"  Topic: {topic}")
    print(f"  Context: {context_round1}")
    print()

    proposal_r1 = pattern4.create_proposal(topic, context_round1)

    # Round 1 votes
    votes_r1 = []
    for voter in pattern4.voters:
        vote = voter.vote(proposal_r1)
        votes_r1.append(vote)
        print(f"  {voter.perspective:12} → {vote['vote']:8}")

    result_r1 = pattern4.determine_consensus(proposal_r1["proposal_id"])
    print(f"\nRound 1 Result: {result_r1['consensus_reached']}")
    print()

    # If no consensus, revise proposal
    if result_r1["consensus_reached"] == "no":
        print("Round 2: Revised Proposal (with more details)")

        # Clear memory for new proposal
        pattern4.clear_shared_memory()

        # Revised proposal with more context
        context_round2 = """
        Current auth code is hard to maintain.
        Proposed refactor includes:
        - Better test coverage
        - Modular design
        - Security improvements
        Timeline: 2 weeks, minimal risk
        """

        proposal_r2 = pattern4.create_proposal(topic, context_round2.strip())

        print("  Additional context provided")
        print()

        # Round 2 votes
        votes_r2 = []
        for voter in pattern4.voters:
            vote = voter.vote(proposal_r2)
            votes_r2.append(vote)
            print(f"  {voter.perspective:12} → {vote['vote']:8}")

        result_r2 = pattern4.determine_consensus(proposal_r2["proposal_id"])
        print(f"\nRound 2 Result: {result_r2['consensus_reached']}")
        print()

        if result_r2["consensus_reached"] == "yes":
            print("  ✓ Consensus achieved after revision")
        else:
            print("  → Still no consensus - may need compromise or escalation")

    print()

    # ==================================================================
    # SCENARIO 5: Supermajority Requirement
    # ==================================================================
    print("Scenario 5: Supermajority Requirement")
    print("-" * 70)

    # Create pattern with more voters
    pattern5 = create_consensus_pattern(
        num_voters=7, voter_perspectives=["voter" + str(i) for i in range(1, 8)]
    )

    # Critical decision requiring supermajority
    proposal5 = pattern5.create_proposal(
        topic="Should we sunset a major product feature?",
        context="Feature used by 5% of users but costs 30% of maintenance",
    )

    print(f"Proposal: {proposal5['topic']}")
    print("Requirement: 67% supermajority (≥5 out of 7)")
    print()

    # Vote
    votes5 = []
    for voter in pattern5.voters:
        vote = voter.vote(proposal5)
        votes5.append(vote)

    # Count votes
    approvals = sum(1 for v in votes5 if v["vote"] == "approve")
    total = len(votes5)
    approval_pct = (approvals / total) * 100

    print("Vote Results:")
    print(f"  - Approve: {approvals}/{total} ({approval_pct:.1f}%)")
    print()

    # Check supermajority (67%)
    supermajority_threshold = total * 0.67
    if approvals >= supermajority_threshold:
        print(f"  ✓ Supermajority achieved (≥{supermajority_threshold:.0f} votes)")
        print("    → Decision approved")
    else:
        print(f"  ✗ Supermajority NOT achieved (<{supermajority_threshold:.0f} votes)")
        print("    → Decision rejected")

    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Advanced Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to handle tie scenarios")
    print("  ✓ How to analyze vote confidence levels")
    print("  ✓ How to handle abstentions and check quorum")
    print("  ✓ How to implement multi-round consensus building")
    print("  ✓ How to require supermajority for critical decisions")
    print()
    print("Advanced Patterns:")
    print("  → Weighted voting (by expertise or stake)")
    print("  → Veto power for specific voters")
    print("  → Ranked-choice voting")
    print("  → Delegation (voter assigns vote to expert)")
    print("  → Time-boxed voting windows")
    print()
    print("Best Practices:")
    print("  → Use odd number of voters to avoid ties")
    print("  → Set quorum requirements (e.g., 50% active votes)")
    print("  → Analyze confidence for decision quality")
    print("  → Allow multi-round voting for complex decisions")
    print("  → Use supermajority (67%) for critical changes")
    print()


if __name__ == "__main__":
    main()
