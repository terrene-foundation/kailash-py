"""
Example 12: Debate Pattern - Real-World Technical Decision Making

This example demonstrates a real-world use case: technical design debates for
product features using the DebatePattern. Technical advocates debate pros/cons
and a technical lead makes the final decision.

Use Case:
An engineering team needs to make critical technical decisions through structured
debate between advocates for different approaches.

Learning Objectives:
- Real-world technical decision making
- Multi-round technical debates
- Evidence-based argumentation
- Decision documentation and traceability

Estimated time: 15 minutes
"""

import json
from datetime import datetime
from typing import Any, Dict

from kaizen.agents.coordination import create_debate_pattern

# Sample technical decisions
TECHNICAL_DECISIONS = [
    {
        "title": "Database Choice: PostgreSQL vs MongoDB",
        "context": """
        Project: New e-commerce platform

        Requirements:
        - High transaction volume (100k+ daily)
        - Complex relational data (users, orders, products, inventory)
        - Real-time analytics needed
        - Team has SQL experience but limited NoSQL experience

        PostgreSQL Pros:
        - ACID compliance
        - Strong relational model
        - Team expertise
        - Mature ecosystem

        MongoDB Pros:
        - Flexible schema
        - Horizontal scaling
        - JSON-native
        - Fast reads for analytics
        """,
        "rounds": 2,
    },
    {
        "title": "API Design: REST vs GraphQL",
        "context": """
        Project: Mobile + Web application backend

        Requirements:
        - Multiple client types (iOS, Android, Web)
        - Complex nested data relationships
        - Bandwidth efficiency important (mobile)
        - Real-time updates needed

        REST Pros:
        - Simple, well-understood
        - Good caching support
        - Smaller learning curve
        - Wide tooling support

        GraphQL Pros:
        - Single endpoint
        - Client-specific queries
        - Reduced over-fetching
        - Strong typing
        """,
        "rounds": 3,
    },
    {
        "title": "Deployment Strategy: Kubernetes vs Serverless",
        "context": """
        Project: SaaS application deployment

        Requirements:
        - Variable traffic (10x spikes)
        - Cost optimization important
        - Fast deployment needed
        - Team size: 3 DevOps engineers

        Kubernetes Pros:
        - Full control
        - Consistent environment
        - No vendor lock-in
        - Better for stateful apps

        Serverless Pros:
        - Auto-scaling
        - Pay-per-use
        - Zero infrastructure management
        - Faster development
        """,
        "rounds": 2,
    },
]


def format_decision_report(
    decision: Dict[str, Any], result: Dict[str, Any], judgment: Dict[str, Any]
) -> Dict[str, Any]:
    """Format technical decision report."""

    return {
        "timestamp": datetime.now().isoformat(),
        "decision_title": decision["title"],
        "debate_id": result["debate_id"],
        "rounds_completed": result["rounds"],
        "final_decision": {
            "winner": judgment["winner"],
            "decision": judgment["decision"],
            "confidence": judgment["confidence"],
            "reasoning": judgment["reasoning"],
        },
        "arguments": {
            "proponent": result.get("proponent_argument", "N/A")[:200] + "...",
            "opponent": result.get("opponent_argument", "N/A")[:200] + "...",
        },
        "recommendation": (
            "ADOPT FOR" if judgment["decision"] == "for" else "ADOPT AGAINST"
        ),
        "confidence_level": (
            "high"
            if judgment["confidence"] > 0.7
            else ("moderate" if judgment["confidence"] > 0.5 else "low")
        ),
    }


def main():
    print("=" * 70)
    print("Real-World Technical Decision Making")
    print("Debate Pattern Implementation")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Configure Technical Debate Pattern
    # ==================================================================
    print("Step 1: Configuring technical debate pattern")
    print("-" * 70)

    print("Debate Configuration:")
    print("  - Proponent: Argues FOR the first option")
    print("  - Opponent: Argues AGAINST (supports alternative)")
    print("  - Judge: Technical lead making final decision")
    print()

    # ==================================================================
    # STEP 2: Create Debate Pattern
    # ==================================================================
    print("Step 2: Creating debate pattern...")
    print("-" * 70)

    # Create pattern optimized for technical debates
    # - Use GPT-4 for better technical reasoning
    # - Higher token limit for detailed arguments
    debate_pattern = create_debate_pattern(
        proponent_config={
            "model": "gpt-4",
            "temperature": 0.6,  # Balanced creativity
            "max_tokens": 2000,
        },
        opponent_config={
            "model": "gpt-4",
            "temperature": 0.6,  # Balanced creativity
            "max_tokens": 2000,
        },
        judge_config={
            "model": "gpt-4",
            "temperature": 0.3,  # More deterministic judgment
            "max_tokens": 1500,
        },
    )

    print("✓ Debate pattern created successfully!")
    print(f"  - Proponent: {debate_pattern.proponent.agent_id} (GPT-4)")
    print(f"  - Opponent: {debate_pattern.opponent.agent_id} (GPT-4)")
    print(f"  - Judge: {debate_pattern.judge.agent_id} (GPT-4)")
    print()

    # ==================================================================
    # STEP 3: Conduct Technical Debates
    # ==================================================================
    print("Step 3: Conducting technical debates...")
    print("-" * 70)
    print()

    decision_reports = []

    for idx, decision in enumerate(TECHNICAL_DECISIONS, 1):
        print(f"{'='*70}")
        print(
            f"TECHNICAL DECISION {idx}/{len(TECHNICAL_DECISIONS)}: {decision['title']}"
        )
        print(f"{'='*70}")
        print()

        print("Context:")
        print(f"{decision['context']}")
        print()

        print("Debate Configuration:")
        print(f"  - Rounds: {decision['rounds']}")
        print(
            f"  - Format: {'Initial arguments + rebuttals' if decision['rounds'] > 1 else 'Initial arguments only'}"
        )
        print()

        # Run debate
        print("Debate in Progress...")
        print("-" * 70)

        result = debate_pattern.debate(
            topic=decision["title"],
            context=decision["context"],
            rounds=decision["rounds"],
        )

        print(f"✓ Debate completed ({decision['rounds']} rounds)")
        print()

        # Display arguments
        print("Proponent Argument (FOR first option):")
        print(f"  {result['proponent_argument'][:150]}...")
        print()

        print("Opponent Argument (AGAINST / for alternative):")
        print(f"  {result['opponent_argument'][:150]}...")
        print()

        # Get judgment
        judgment = debate_pattern.get_judgment(result["debate_id"])

        print("Technical Lead Decision:")
        print(f"  Winner: {judgment['winner'].upper()}")
        print(f"  Confidence: {judgment['confidence']:.2f}")
        print()
        print("Reasoning:")
        print(f"  {judgment['reasoning'][:250]}...")
        print()

        # Generate report
        report = format_decision_report(decision, result, judgment)
        decision_reports.append(report)

        # Clear memory for next debate
        debate_pattern.clear_shared_memory()

        print()

    # ==================================================================
    # STEP 4: Decision Summary Report
    # ==================================================================
    print("=" * 70)
    print("TECHNICAL DECISION SESSION SUMMARY")
    print("=" * 70)
    print()

    print(f"Session Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Decisions Made: {len(decision_reports)}")
    print()

    # Summary table
    print("Decision Outcomes:")
    print("-" * 70)
    print(f"{'Decision':<45} {'Winner':<15} {'Confidence':<12}")
    print("-" * 70)

    for report in decision_reports:
        decision_short = (
            report["decision_title"][:42] + "..."
            if len(report["decision_title"]) > 45
            else report["decision_title"]
        )
        print(
            f"{decision_short:<45} {report['final_decision']['winner'].upper():<15} {report['final_decision']['confidence']:<.2f}"
        )

    print()

    # Confidence analysis
    avg_confidence = sum(
        r["final_decision"]["confidence"] for r in decision_reports
    ) / len(decision_reports)
    high_confidence = sum(
        1 for r in decision_reports if r["confidence_level"] == "high"
    )

    print("Decision Confidence Analysis:")
    print(f"  - Average confidence: {avg_confidence:.2f}")
    print(f"  - High confidence decisions: {high_confidence}/{len(decision_reports)}")
    print()

    if avg_confidence > 0.7:
        print("  → Strong consensus across decisions")
    elif avg_confidence > 0.5:
        print("  → Moderate confidence - some uncertainty")
    else:
        print("  → Low confidence - decisions were close calls")

    print()

    # ==================================================================
    # STEP 5: Export Decision Reports
    # ==================================================================
    print("Step 5: Exporting decision reports...")
    print("-" * 70)

    # In real scenario, would save to database or file system
    print(f"✓ {len(decision_reports)} decision reports generated")
    print()

    # Show sample report (first decision)
    print("Sample Decision Report (JSON format):")
    print("-" * 70)
    sample_report = decision_reports[0]
    print(json.dumps(sample_report, indent=2)[:600] + "...")
    print()

    # ==================================================================
    # STEP 6: Action Items
    # ==================================================================
    print("Step 6: Generating action items...")
    print("-" * 70)

    print("Recommended Actions:")
    for i, report in enumerate(decision_reports, 1):
        print(f"\n{i}. {report['decision_title']}")

        if report["final_decision"]["decision"] == "for":
            action = "PROCEED with first option"
        else:
            action = "ADOPT alternative approach"

        print(f"   Action: {action}")
        print(f"   Confidence: {report['confidence_level']}")

        if report["confidence_level"] == "low":
            print("   ⚠️  Low confidence - Consider additional research or prototype")
        elif report["confidence_level"] == "moderate":
            print("   → Moderate confidence - Proceed with monitoring")
        else:
            print("   ✓ High confidence - Safe to proceed")

    print()

    # ==================================================================
    # Summary and Next Steps
    # ==================================================================
    print("=" * 70)
    print("Technical Decision Session Complete!")
    print("=" * 70)
    print()

    print("What you learned:")
    print("  ✓ How to structure technical debates for product decisions")
    print("  ✓ How to configure debates for technical reasoning")
    print("  ✓ How to conduct multi-round technical debates")
    print("  ✓ How to generate decision reports and action items")
    print("  ✓ How to analyze confidence levels for decision quality")
    print()

    print("Production Considerations:")
    print("  → Store debate arguments in knowledge base for future reference")
    print("  → Track decision outcomes and validate predictions")
    print("  → Implement appeal process for low-confidence decisions")
    print("  → Integrate with architecture decision records (ADRs)")
    print("  → Add evidence links and benchmarks to arguments")
    print("  → Set up automated debate triggers for specific decisions")
    print("  → Create decision templates for common patterns")
    print()

    print("Debate Best Practices:")
    print("  → Use 1-2 rounds for tactical decisions")
    print("  → Use 2-3 rounds for strategic decisions")
    print("  → Use 3+ rounds for critical, irreversible decisions")
    print("  → Set confidence thresholds (e.g., >0.7 for auto-approval)")
    print("  → Document dissenting arguments for transparency")
    print("  → Review decisions periodically to validate predictions")
    print()

    print("Use Cases for Debate Pattern:")
    print("  → Technical design decisions (databases, APIs, architectures)")
    print("  → Build vs buy evaluations")
    print("  → Technology stack selections")
    print("  → Scaling strategy debates")
    print("  → Security policy decisions")
    print("  → Performance optimization trade-offs")
    print("  → Technical debt prioritization")
    print()


if __name__ == "__main__":
    main()
