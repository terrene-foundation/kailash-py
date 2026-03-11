"""
Example 20: Handoff Pattern - Real-World Customer Support System

This example demonstrates a real-world use case: tiered customer support system
with automatic escalation based on issue complexity using the HandoffPattern.

Use Case:
A customer support team needs to route support tickets to appropriate expertise
levels (Tier 1 → Tier 2 → Tier 3) based on complexity, with full audit trail.

Learning Objectives:
- Real-world tier-based support system
- Automatic complexity-based routing
- Escalation tracking and reporting
- Performance metrics and analytics

Estimated time: 15 minutes
"""

import json
from datetime import datetime
from typing import Any, Dict, List

from kaizen.agents.coordination import create_handoff_pattern

# Sample support tickets
SUPPORT_TICKETS = [
    {
        "id": "T-001",
        "customer": "John Doe",
        "issue": "How do I reset my password?",
        "priority": "low",
        "category": "account",
    },
    {
        "id": "T-002",
        "customer": "Jane Smith",
        "issue": "Application crashes when exporting reports with more than 10,000 rows",
        "priority": "high",
        "category": "technical",
    },
    {
        "id": "T-003",
        "customer": "Bob Johnson",
        "issue": "Need to upgrade to Enterprise plan and configure SSO with SAML",
        "priority": "medium",
        "category": "billing",
    },
    {
        "id": "T-004",
        "customer": "Alice Williams",
        "issue": "Database performance degraded after schema migration, queries timing out",
        "priority": "critical",
        "category": "technical",
    },
    {
        "id": "T-005",
        "customer": "Charlie Brown",
        "issue": "Can you update my email address?",
        "priority": "low",
        "category": "account",
    },
]


def format_support_report(
    ticket: Dict[str, Any], result: Dict[str, Any], history: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Format support ticket resolution report."""
    return {
        "timestamp": datetime.now().isoformat(),
        "ticket_id": ticket["id"],
        "customer": ticket["customer"],
        "priority": ticket["priority"],
        "category": ticket["category"],
        "resolution": {
            "tier_handled": result["final_tier"],
            "escalations": result["escalation_count"],
            "confidence": result["confidence"],
            "response": result["result"][:200] + "...",
        },
        "escalation_trail": [
            {
                "tier": d["tier_level"],
                "decision": d["handoff_decision"],
                "complexity": d["complexity_score"],
            }
            for d in history
        ],
    }


def main():
    print("=" * 70)
    print("Real-World Customer Support System - Tiered Escalation")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Configure Support Tiers
    # ==================================================================
    print("Step 1: Configuring tiered support system...")
    print("-" * 70)

    print("Support Tier Configuration:")
    print("  - Tier 1 (General Support): Basic account/billing issues")
    print("  - Tier 2 (Technical Support): Application and integration issues")
    print("  - Tier 3 (Engineering): Complex technical problems, performance issues")
    print()

    # ==================================================================
    # STEP 2: Create Handoff Pattern
    # ==================================================================
    print("Step 2: Creating handoff pattern...")
    print("-" * 70)

    # Optimize tier configs for support workload
    support_handoff = create_handoff_pattern(
        tier_configs={
            1: {
                "model": "gpt-3.5-turbo",
                "temperature": 0.3,  # Deterministic for FAQ responses
                "max_tokens": 800,
            },
            2: {
                "model": "gpt-4",
                "temperature": 0.5,  # Balanced for technical help
                "max_tokens": 1200,
            },
            3: {
                "model": "gpt-4-turbo",
                "temperature": 0.7,  # Creative problem-solving
                "max_tokens": 1800,
            },
        }
    )

    print("✓ Support system created successfully!")
    print(f"  - Tiers: {sorted(support_handoff.tiers.keys())}")
    print("  - Routing: Automatic complexity-based")
    print()

    # ==================================================================
    # STEP 3: Process Support Tickets
    # ==================================================================
    print("Step 3: Processing support tickets...")
    print("-" * 70)
    print()

    support_reports = []

    for idx, ticket in enumerate(SUPPORT_TICKETS, 1):
        print(f"{'='*70}")
        print(f"TICKET {idx}/{len(SUPPORT_TICKETS)}: {ticket['id']}")
        print(f"{'='*70}")
        print()

        print(f"Customer: {ticket['customer']}")
        print(f"Priority: {ticket['priority'].upper()}")
        print(f"Category: {ticket['category'].capitalize()}")
        print(f"Issue: {ticket['issue']}")
        print()

        # Process ticket with handoff
        print("Processing...")
        print("-" * 70)

        result = support_handoff.execute_with_handoff(
            task=ticket["issue"],
            context=f"Support ticket - Priority: {ticket['priority']}, Category: {ticket['category']}",
            max_tier=3,
        )

        print("✓ Ticket resolved")
        print()

        # Display resolution info
        print("Resolution:")
        print(f"  - Handled by: Tier {result['final_tier']}")
        print(f"  - Escalations: {result['escalation_count']}")
        print(f"  - Confidence: {result['confidence']:.2f}")
        print()

        # Get escalation trail
        history = support_handoff.get_handoff_history(result["execution_id"])

        print("Escalation Trail:")
        for decision in history:
            tier_name = ["General", "Technical", "Engineering"][
                decision["tier_level"] - 1
            ]
            action_icon = "✓" if decision["can_handle"] == "yes" else "→"
            action_text = (
                "Handled"
                if decision["can_handle"] == "yes"
                else f"Escalate (complexity: {decision['complexity_score']:.2f})"
            )
            print(
                f"  {action_icon} Tier {decision['tier_level']} ({tier_name}): {action_text}"
            )

        print()

        # Display response preview
        print("Response Preview:")
        print(f"  {result['result'][:150]}...")
        print()

        # Generate report
        report = format_support_report(ticket, result, history)
        support_reports.append(report)

        # Clear memory for next ticket
        support_handoff.clear_shared_memory()

        print()

    # ==================================================================
    # STEP 4: Support Session Analytics
    # ==================================================================
    print("=" * 70)
    print("SUPPORT SESSION ANALYTICS")
    print("=" * 70)
    print()

    print(f"Session Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Tickets Processed: {len(support_reports)}")
    print()

    # Tier utilization
    tier_distribution = {}
    for report in support_reports:
        tier = report["resolution"]["tier_handled"]
        tier_distribution[tier] = tier_distribution.get(tier, 0) + 1

    print("Tier Utilization:")
    print("-" * 70)
    for tier in sorted(tier_distribution.keys()):
        count = tier_distribution[tier]
        percentage = (count / len(support_reports)) * 100
        tier_name = ["General Support", "Technical Support", "Engineering"][tier - 1]
        print(f"  Tier {tier} ({tier_name}): {count} tickets ({percentage:.1f}%)")
    print()

    # Escalation metrics
    total_escalations = sum(r["resolution"]["escalations"] for r in support_reports)
    avg_escalations = total_escalations / len(support_reports)

    print("Escalation Metrics:")
    print(f"  - Total escalations: {total_escalations}")
    print(f"  - Average per ticket: {avg_escalations:.2f}")
    print(
        f"  - Tickets resolved at Tier 1: {tier_distribution.get(1, 0)}/{len(support_reports)}"
    )
    print()

    # Priority analysis
    print("Resolution by Priority:")
    print("-" * 70)
    priority_tiers = {}
    for report in support_reports:
        priority = report["priority"]
        tier = report["resolution"]["tier_handled"]
        if priority not in priority_tiers:
            priority_tiers[priority] = []
        priority_tiers[priority].append(tier)

    for priority in ["critical", "high", "medium", "low"]:
        if priority in priority_tiers:
            avg_tier = sum(priority_tiers[priority]) / len(priority_tiers[priority])
            print(f"  {priority.capitalize()}: Avg Tier {avg_tier:.1f}")
    print()

    # ==================================================================
    # STEP 5: Recommendations
    # ==================================================================
    print("Step 5: System recommendations...")
    print("-" * 70)

    tier1_usage = tier_distribution.get(1, 0) / len(support_reports) * 100

    print("Performance Analysis:")
    if tier1_usage > 60:
        print(f"  ✓ Excellent - {tier1_usage:.0f}% resolved at Tier 1")
        print("  → Cost-efficient support operation")
    elif tier1_usage > 40:
        print(f"  → Good - {tier1_usage:.0f}% resolved at Tier 1")
        print("  → Consider expanding Tier 1 capabilities")
    else:
        print(f"  ⚠️  {tier1_usage:.0f}% resolved at Tier 1 (target: >40%)")
        print("  → Review Tier 1 training and documentation")

    print()

    print("Optimization Opportunities:")
    print("  → Add self-service FAQ for common Tier 1 issues")
    print("  → Train Tier 1 on most frequent escalation patterns")
    print("  → Consider adding Tier 1.5 for borderline cases")
    print("  → Monitor critical/high priority ticket routing")
    print()

    # ==================================================================
    # STEP 6: Export Reports
    # ==================================================================
    print("Step 6: Exporting support reports...")
    print("-" * 70)

    print(f"✓ {len(support_reports)} support reports generated")
    print()

    # Show sample report
    print("Sample Support Report (JSON):")
    print("-" * 70)
    sample = support_reports[0]
    print(json.dumps(sample, indent=2)[:500] + "...")
    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Customer Support Session Complete!")
    print("=" * 70)
    print()

    print("What you learned:")
    print("  ✓ How to build tiered customer support systems")
    print("  ✓ How to configure tier-specific models and params")
    print("  ✓ How to track escalation trails for audit")
    print("  ✓ How to analyze support session metrics")
    print("  ✓ How to optimize tier utilization")
    print("  ✓ How to generate support reports")
    print()

    print("Production Considerations:")
    print("  → Store escalation history in database")
    print("  → Track resolution time per tier")
    print("  → Implement SLA monitoring")
    print("  → Add customer satisfaction scoring")
    print("  → Create escalation alerts for high-priority tickets")
    print("  → Implement knowledge base integration")
    print("  → Add automatic ticket categorization")
    print()

    print("Best Practices:")
    print("  → Optimize for Tier 1 resolution (target: >60%)")
    print("  → Use fast models for Tier 1 (cost-efficient)")
    print("  → Reserve powerful models for complex tiers")
    print("  → Track escalation patterns to improve routing")
    print("  → Monitor confidence scores for quality assurance")
    print("  → Regular analysis of tier utilization metrics")
    print()

    print("Use Cases for Handoff Pattern:")
    print("  → Customer support (tier-based escalation)")
    print("  → IT helpdesk (L1 → L2 → L3 support)")
    print("  → Medical diagnosis (general → specialist → expert)")
    print("  → Financial advisory (basic → advanced → expert)")
    print("  → Content moderation (automated → human → expert review)")
    print("  → Bug triage (developer → senior → architect)")
    print()


if __name__ == "__main__":
    main()
