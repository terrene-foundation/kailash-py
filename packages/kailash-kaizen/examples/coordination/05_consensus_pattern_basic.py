"""
Example 5: Consensus Pattern - Basic Usage

This example demonstrates the basic usage of the ConsensusPattern with zero-configuration.
Multiple voter agents evaluate proposals and reach consensus through democratic voting.

Learning Objectives:
- Zero-config pattern creation
- Proposal creation
- Democratic voting process
- Consensus determination
- Result interpretation

Estimated time: 5 minutes
"""

from kaizen.agents.coordination import create_consensus_pattern


def main():
    print("=" * 70)
    print("Consensus Pattern - Basic Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Create Pattern (Zero-Config!)
    # ==================================================================
    print("Step 1: Creating consensus pattern...")
    print("-" * 70)

    # Create pattern with default settings
    # - 3 voters (default)
    # - Uses gpt-3.5-turbo (default model)
    # - Uses environment variables if set (KAIZEN_MODEL, etc.)
    pattern = create_consensus_pattern()

    print("✓ Pattern created successfully!")
    print(f"  - Proposer: {pattern.proposer.agent_id}")
    print(f"  - Voters: {[v.agent_id for v in pattern.voters]}")
    print(f"  - Aggregator: {pattern.aggregator.agent_id}")
    print(f"  - Shared Memory: {pattern.shared_memory is not None}")
    print()

    # ==================================================================
    # STEP 2: Validate Pattern
    # ==================================================================
    print("Step 2: Validating pattern initialization...")
    print("-" * 70)

    if pattern.validate_pattern():
        print("✓ Pattern validation passed!")
        print(f"  - All agents initialized: {len(pattern.get_agents())} agents")
        print(f"  - Unique agent IDs: {pattern.get_agent_ids()}")
        print("  - Shared memory configured: YES")
    else:
        print("✗ Pattern validation failed!")
        return

    print()

    # ==================================================================
    # STEP 3: Create Proposal
    # ==================================================================
    print("Step 3: Creating proposal for voting...")
    print("-" * 70)

    # Proposer creates a proposal on a topic
    topic = "Should we adopt AI-powered code review in our development workflow?"
    context = """
    We're considering integrating AI code review to:
    - Catch bugs early
    - Enforce coding standards
    - Reduce review time

    Concerns include:
    - Cost of AI service
    - Accuracy of AI suggestions
    - Developer trust in AI
    """

    proposal = pattern.create_proposal(topic, context)

    print("✓ Proposal created!")
    print(f"  - Proposal ID: {proposal['proposal_id']}")
    print(f"  - Topic: {proposal['topic']}")
    print(f"  - Proposal: {proposal['proposal'][:100]}...")
    print(f"  - Rationale: {proposal['rationale'][:100]}...")
    print()

    # ==================================================================
    # STEP 4: Voters Evaluate and Vote
    # ==================================================================
    print("Step 4: Voters evaluating proposal...")
    print("-" * 70)

    # Each voter independently evaluates the proposal
    votes = []
    for voter in pattern.voters:
        print(f"\n{voter.agent_id} evaluating proposal...")

        # Voter casts their vote
        vote_result = voter.vote(proposal)

        votes.append(vote_result)

        print(f"  ✓ Vote cast: {vote_result['vote'].upper()}")
        print(f"    Reasoning: {vote_result['reasoning'][:80]}...")
        print(f"    Confidence: {vote_result['confidence']:.2f}")

    print()
    print(f"✓ All {len(votes)} voters have cast their votes!")
    print()

    # ==================================================================
    # STEP 5: Determine Consensus
    # ==================================================================
    print("Step 5: Determining consensus...")
    print("-" * 70)

    # Aggregator tallies votes and determines consensus
    consensus_result = pattern.determine_consensus(proposal["proposal_id"])

    print("Consensus Result:")
    print(f"  - Consensus Reached: {consensus_result['consensus_reached'].upper()}")
    print(f"  - Final Decision: {consensus_result['final_decision']}")
    print()
    print("Vote Summary:")
    print(f"  {consensus_result['vote_summary']}")
    print()

    # ==================================================================
    # STEP 6: Interpret Results
    # ==================================================================
    print("Step 6: Interpreting vote results...")
    print("-" * 70)

    # Count votes
    approvals = sum(1 for v in votes if v["vote"] == "approve")
    rejections = sum(1 for v in votes if v["vote"] == "reject")
    abstentions = sum(1 for v in votes if v["vote"] == "abstain")

    print("Vote Distribution:")
    print(f"  - Approve: {approvals}/{len(votes)} ({approvals/len(votes)*100:.1f}%)")
    print(f"  - Reject: {rejections}/{len(votes)} ({rejections/len(votes)*100:.1f}%)")
    print(
        f"  - Abstain: {abstentions}/{len(votes)} ({abstentions/len(votes)*100:.1f}%)"
    )
    print()

    # Consensus threshold (>50% approve)
    consensus_threshold = len(votes) / 2
    if approvals > consensus_threshold:
        print(f"✓ CONSENSUS ACHIEVED (>{consensus_threshold:.0f} approvals needed)")
    else:
        print(
            f"✗ NO CONSENSUS ({approvals} approvals, >{consensus_threshold:.0f} needed)"
        )

    print()

    # Average confidence
    avg_confidence = sum(v["confidence"] for v in votes) / len(votes)
    print(f"Average Voter Confidence: {avg_confidence:.2f}/1.00")

    if avg_confidence > 0.7:
        print("  → High confidence in votes")
    elif avg_confidence > 0.5:
        print("  → Moderate confidence in votes")
    else:
        print("  → Low confidence in votes")

    print()

    # ==================================================================
    # STEP 7: Cleanup (Optional)
    # ==================================================================
    print("Step 7: Cleanup (optional)...")
    print("-" * 70)

    # Clear shared memory if you want to reuse the pattern
    pattern.clear_shared_memory()
    print("✓ Shared memory cleared (pattern ready for next proposal)")
    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to create a consensus pattern (zero-config)")
    print("  ✓ How to create proposals for voting")
    print("  ✓ How voters evaluate and cast votes")
    print("  ✓ How to determine consensus from votes")
    print("  ✓ How to interpret vote results and confidence")
    print("  ✓ How to cleanup shared memory for reuse")
    print()
    print("Next steps:")
    print("  → Try example 6: Progressive configuration")
    print("  → Try example 7: Advanced voting with perspectives")
    print("  → Try example 8: Real-world multi-expert decision making")
    print()


if __name__ == "__main__":
    main()
