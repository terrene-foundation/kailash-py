"""
Example 8: Consensus Pattern - Real-World Architecture Review

This example demonstrates a real-world use case: architecture review board (ARB)
using the ConsensusPattern. Multiple expert reviewers evaluate architecture proposals
and reach consensus on technical decisions.

Use Case:
An engineering team needs to review and approve architecture proposals through a
formal Architecture Review Board (ARB) process with multiple expert perspectives.

Learning Objectives:
- Real-world multi-expert decision making
- Cross-functional perspective integration
- Architecture proposal evaluation
- Consensus-driven technical governance
- Decision documentation and traceability

Estimated time: 15 minutes
"""

import json
from datetime import datetime
from typing import Any, Dict, List

from kaizen.agents.coordination import create_consensus_pattern

# Sample architecture proposals
ARCHITECTURE_PROPOSALS = [
    {
        "title": "Migrate to Microservices Architecture",
        "description": """
        Proposal: Break monolithic application into microservices

        Current State:
        - Single monolithic Django application
        - 200K lines of code
        - 15 developers working on same codebase
        - Deployment takes 2 hours
        - Scaling issues during peak traffic

        Proposed Solution:
        - Decompose into 8 microservices
        - Each service owns its data
        - API Gateway for routing
        - Independent deployment pipelines
        - Containerized with Kubernetes

        Benefits:
        - Independent scaling
        - Faster deployments (15 min per service)
        - Team autonomy
        - Technology diversity

        Risks:
        - Distributed system complexity
        - Network latency
        - Data consistency challenges
        - Learning curve for team
        """,
        "impact": "high",
        "timeline": "6 months",
    },
    {
        "title": "Implement Event-Driven Architecture for Order Processing",
        "description": """
        Proposal: Replace synchronous order processing with event-driven architecture

        Current State:
        - Synchronous order processing
        - Tight coupling between services
        - Cascading failures
        - Poor resilience

        Proposed Solution:
        - Event bus (Apache Kafka)
        - Asynchronous event processing
        - Event sourcing for orders
        - CQRS pattern for reads/writes

        Benefits:
        - Better resilience
        - Loose coupling
        - Scalable event processing
        - Audit trail via event log

        Risks:
        - Eventual consistency
        - Debugging complexity
        - Infrastructure overhead
        """,
        "impact": "medium",
        "timeline": "3 months",
    },
    {
        "title": "Adopt GraphQL API Gateway",
        "description": """
        Proposal: Replace REST APIs with GraphQL gateway

        Current State:
        - 50+ REST endpoints
        - Over-fetching and under-fetching
        - Multiple API calls for single view
        - API versioning challenges

        Proposed Solution:
        - Single GraphQL gateway
        - Schema-driven development
        - Client-specific data fetching
        - Real-time subscriptions

        Benefits:
        - Reduced network calls
        - Better mobile experience
        - Type safety
        - Better developer experience

        Risks:
        - Team learning curve
        - Query complexity
        - Caching challenges
        """,
        "impact": "medium",
        "timeline": "2 months",
    },
]


def format_arb_report(
    proposal: Dict[str, Any],
    votes: List[Dict[str, Any]],
    consensus: Dict[str, Any],
    perspectives: List[str],
) -> Dict[str, Any]:
    """Format Architecture Review Board report."""

    # Count votes
    approvals = sum(1 for v in votes if v["vote"] == "approve")
    rejections = sum(1 for v in votes if v["vote"] == "reject")
    abstentions = sum(1 for v in votes if v["vote"] == "abstain")

    # Calculate confidence
    avg_confidence = sum(v["confidence"] for v in votes) / len(votes) if votes else 0

    # Build perspective breakdown
    perspective_votes = {}
    for vote in votes:
        # Find which voter (perspective) cast this vote
        perspective = next((p for p in perspectives if p in str(vote)), "unknown")
        perspective_votes[perspective] = {
            "vote": vote["vote"],
            "confidence": vote["confidence"],
            "reasoning": (
                vote["reasoning"][:100] + "..."
                if len(vote["reasoning"]) > 100
                else vote["reasoning"]
            ),
        }

    return {
        "timestamp": datetime.now().isoformat(),
        "proposal": proposal.get("title", "N/A"),
        "impact": proposal.get("impact", "N/A"),
        "timeline": proposal.get("timeline", "N/A"),
        "review_outcome": {
            "consensus_reached": consensus["consensus_reached"] == "yes",
            "final_decision": consensus["final_decision"],
            "vote_summary": consensus["vote_summary"],
        },
        "vote_breakdown": {
            "approve": approvals,
            "reject": rejections,
            "abstain": abstentions,
            "total": len(votes),
            "approval_rate": f"{(approvals/len(votes)*100):.1f}%" if votes else "0%",
        },
        "confidence_metrics": {
            "average": round(avg_confidence, 2),
            "status": (
                "high"
                if avg_confidence > 0.7
                else ("moderate" if avg_confidence > 0.5 else "low")
            ),
        },
        "perspective_breakdown": perspective_votes,
        "recommendation": (
            "APPROVED" if consensus["consensus_reached"] == "yes" else "REJECTED"
        ),
    }


def main():
    print("=" * 70)
    print("Real-World Architecture Review Board (ARB)")
    print("Consensus Pattern Implementation")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Configure Architecture Review Board
    # ==================================================================
    print("Step 1: Configuring Architecture Review Board")
    print("-" * 70)

    # Define ARB members with their perspectives
    arb_perspectives = [
        "security",  # Security architect
        "performance",  # Performance engineer
        "scalability",  # Infrastructure architect
        "cost",  # FinOps/Cost engineer
        "developer_experience",  # Developer advocate
    ]

    print(f"ARB Composition ({len(arb_perspectives)} reviewers):")
    for perspective in arb_perspectives:
        print(f"  - {perspective.replace('_', ' ').title()} Expert")
    print()

    # ==================================================================
    # STEP 2: Create ARB Pattern
    # ==================================================================
    print("Step 2: Creating ARB pattern...")
    print("-" * 70)

    # Create pattern optimized for architecture review
    # - Use GPT-4 for proposer (better architectural thinking)
    # - Use GPT-4 for voters (need expert-level evaluation)
    # - Use GPT-3.5 for aggregator (simple vote tallying)
    arb_pattern = create_consensus_pattern(
        num_voters=len(arb_perspectives),
        voter_perspectives=arb_perspectives,
        proposer_config={
            "model": "gpt-4",
            "temperature": 0.5,  # Balanced for proposals
            "max_tokens": 2000,
        },
        voter_config={
            "model": "gpt-4",
            "temperature": 0.6,  # Thoughtful evaluation
            "max_tokens": 1500,
        },
        aggregator_config={
            "model": "gpt-3.5-turbo",
            "temperature": 0.2,  # Precise aggregation
        },
    )

    print("✓ ARB pattern created successfully!")
    print(f"  - Proposer: {arb_pattern.proposer.agent_id}")
    print(f"  - Reviewers: {len(arb_pattern.voters)}")
    print(f"  - Aggregator: {arb_pattern.aggregator.agent_id}")
    print()

    # ==================================================================
    # STEP 3: Review Architecture Proposals
    # ==================================================================
    print("Step 3: Reviewing architecture proposals...")
    print("-" * 70)
    print()

    arb_reports = []

    for idx, arch_proposal in enumerate(ARCHITECTURE_PROPOSALS, 1):
        print(f"{'='*70}")
        print(f"PROPOSAL {idx}/{len(ARCHITECTURE_PROPOSALS)}: {arch_proposal['title']}")
        print(f"{'='*70}")
        print()

        # Create formal proposal
        proposal = arb_pattern.create_proposal(
            topic=arch_proposal["title"], context=arch_proposal["description"]
        )

        print(f"Impact: {arch_proposal['impact'].upper()}")
        print(f"Timeline: {arch_proposal['timeline']}")
        print(f"Proposal ID: {proposal['proposal_id']}")
        print()

        # ARB members review and vote
        print("ARB Review in Progress...")
        print("-" * 70)

        votes = []
        for voter in arb_pattern.voters:
            vote = voter.vote(proposal)
            votes.append(vote)

            # Display vote
            perspective = voter.perspective.replace("_", " ").title()
            print(
                f"{perspective:25} → {vote['vote'].upper():8} (confidence: {vote['confidence']:.2f})"
            )
            print(f"  Reasoning: {vote['reasoning'][:80]}...")
            print()

        # Determine consensus
        consensus = arb_pattern.determine_consensus(proposal["proposal_id"])

        print("ARB Decision:")
        print(f"  Consensus: {consensus['consensus_reached'].upper()}")
        print(f"  Decision: {consensus['final_decision']}")
        print()
        print("Vote Summary:")
        print(f"  {consensus['vote_summary']}")
        print()

        # Generate ARB report
        report = format_arb_report(arch_proposal, votes, consensus, arb_perspectives)
        arb_reports.append(report)

        # Clear memory for next proposal
        arb_pattern.clear_shared_memory()

        print()

    # ==================================================================
    # STEP 4: ARB Summary Report
    # ==================================================================
    print("=" * 70)
    print("ARB SESSION SUMMARY")
    print("=" * 70)
    print()

    print(f"Session Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Proposals Reviewed: {len(arb_reports)}")
    print()

    # Summary table
    print("Proposal Outcomes:")
    print("-" * 70)
    print(f"{'Proposal':<45} {'Impact':<8} {'Decision':<12} {'Approval %':<12}")
    print("-" * 70)

    for report in arb_reports:
        proposal_short = (
            report["proposal"][:42] + "..."
            if len(report["proposal"]) > 45
            else report["proposal"]
        )
        print(
            f"{proposal_short:<45} {report['impact'].upper():<8} {report['recommendation']:<12} {report['vote_breakdown']['approval_rate']:<12}"
        )

    print()

    # Statistics
    approved = sum(1 for r in arb_reports if r["recommendation"] == "APPROVED")
    rejected = sum(1 for r in arb_reports if r["recommendation"] == "REJECTED")

    print("Session Statistics:")
    print(
        f"  - Approved: {approved}/{len(arb_reports)} ({approved/len(arb_reports)*100:.1f}%)"
    )
    print(
        f"  - Rejected: {rejected}/{len(arb_reports)} ({rejected/len(arb_reports)*100:.1f}%)"
    )
    print()

    # Confidence analysis
    avg_session_confidence = sum(
        r["confidence_metrics"]["average"] for r in arb_reports
    ) / len(arb_reports)
    print(f"Average Decision Confidence: {avg_session_confidence:.2f}")

    if avg_session_confidence > 0.7:
        print("  → High confidence across all decisions")
    elif avg_session_confidence > 0.5:
        print("  → Moderate confidence - some uncertainty remains")
    else:
        print("  → Low confidence - decisions may need reconsideration")

    print()

    # ==================================================================
    # STEP 5: Export ARB Reports
    # ==================================================================
    print("Step 5: Exporting ARB reports...")
    print("-" * 70)

    # In real scenario, would save to database or file system
    print(f"✓ {len(arb_reports)} ARB reports generated")
    print()

    # Show sample report (first proposal)
    print("Sample ARB Report (JSON format):")
    print("-" * 70)
    sample_report = arb_reports[0]
    print(json.dumps(sample_report, indent=2)[:500] + "...")
    print()

    # ==================================================================
    # Summary and Next Steps
    # ==================================================================
    print("=" * 70)
    print("Architecture Review Board Session Complete!")
    print("=" * 70)
    print()

    print("What you learned:")
    print("  ✓ How to implement formal Architecture Review Board process")
    print("  ✓ How to configure multi-expert panels with diverse perspectives")
    print("  ✓ How to evaluate complex technical proposals")
    print("  ✓ How to reach consensus across functional areas")
    print("  ✓ How to generate audit reports for governance")
    print()

    print("Production Considerations:")
    print("  → Store proposals and votes in database for audit trail")
    print("  → Implement proposal templates for consistency")
    print("  → Add automated compliance checks (security, cost, etc.)")
    print("  → Integrate with architecture decision records (ADRs)")
    print("  → Send notifications to stakeholders")
    print("  → Track proposal lifecycle (draft → review → approved/rejected)")
    print("  → Implement appeal/revision process for rejected proposals")
    print()

    print("ARB Best Practices:")
    print("  → Include cross-functional perspectives (5-7 reviewers)")
    print("  → Set clear decision criteria upfront")
    print("  → Require supermajority (67%) for high-impact changes")
    print("  → Document dissenting opinions for transparency")
    print("  → Review periodically (weekly/biweekly ARB meetings)")
    print("  → Maintain proposal backlog and prioritization")
    print()

    print("Use Cases for Consensus Pattern:")
    print("  → Architecture review boards")
    print("  → Technical RFC approval process")
    print("  → Code review consensus (multiple reviewers)")
    print("  → Feature prioritization voting")
    print("  → Design review committees")
    print("  → Risk assessment panels")
    print("  → Investment decision committees")
    print()


if __name__ == "__main__":
    main()
