"""
Example 19: Handoff Pattern - Advanced Usage

This example demonstrates advanced features of the HandoffPattern,
including complex escalation scenarios, handoff analytics, and optimization strategies.

Learning Objectives:
- Complex escalation scenarios
- Handoff analytics and metrics
- Performance optimization
- Error handling and edge cases

Estimated time: 10 minutes
"""

from typing import Any, Dict, List

from kaizen.agents.coordination import create_handoff_pattern


def analyze_handoff_metrics(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze handoff metrics from history."""
    if not history:
        return {"error": "No history available"}

    metrics = {
        "total_decisions": len(history),
        "tiers_involved": list(set(d["tier_level"] for d in history)),
        "escalations": sum(1 for d in history if d["can_handle"] == "no"),
        "avg_complexity": sum(d["complexity_score"] for d in history) / len(history),
        "final_tier": history[-1]["tier_level"],
        "decision_trail": [f"T{d['tier_level']}" for d in history],
    }

    return metrics


def main():
    print("=" * 70)
    print("Handoff Pattern - Advanced Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # SCENARIO 1: Multi-Tier Escalation Analysis
    # ==================================================================
    print("Scenario 1: Multi-Tier Escalation Analysis")
    print("-" * 70)

    handoff1 = create_handoff_pattern(num_tiers=5)

    tasks = [
        ("Simple calculation", "What is 15% of 200?"),
        (
            "Moderate analysis",
            "Analyze the pros and cons of microservices architecture",
        ),
        (
            "Complex problem",
            "Design a fault-tolerant distributed cache with consistency guarantees",
        ),
        (
            "Expert level",
            "Optimize query performance for 1B+ row database with sub-second latency requirements",
        ),
    ]

    print(f"Testing {len(tasks)} tasks with 5-tier system:")
    print()

    for idx, (category, task) in enumerate(tasks, 1):
        result = handoff1.execute_with_handoff(task, max_tier=5)
        print(f"{idx}. {category}")
        print(
            f"   Tier: {result['final_tier']}, Escalations: {result['escalation_count']}"
        )

    print()

    # ==================================================================
    # SCENARIO 2: Handoff Analytics
    # ==================================================================
    print("Scenario 2: Handoff Analytics and Metrics")
    print("-" * 70)

    handoff2 = create_handoff_pattern(num_tiers=3)

    complex_task = "Implement distributed transaction processing with ACID guarantees across microservices"
    result2 = handoff2.execute_with_handoff(
        complex_task, context="System design", max_tier=3
    )

    history = handoff2.get_handoff_history(result2["execution_id"])
    metrics = analyze_handoff_metrics(history)

    print("Handoff Metrics:")
    print(f"  - Total decisions: {metrics['total_decisions']}")
    print(f"  - Tiers involved: {metrics['tiers_involved']}")
    print(f"  - Escalations: {metrics['escalations']}")
    print(f"  - Avg complexity: {metrics['avg_complexity']:.2f}")
    print(f"  - Decision trail: {' → '.join(metrics['decision_trail'])}")
    print(f"  - Final tier: {metrics['final_tier']}")
    print()

    # ==================================================================
    # SCENARIO 3: Performance Optimization
    # ==================================================================
    print("Scenario 3: Performance Optimization Strategies")
    print("-" * 70)

    # Strategy 1: Minimal tiers for simple tasks
    fast_handoff = create_handoff_pattern(
        num_tiers=2,
        tier_configs={
            1: {"model": "gpt-3.5-turbo", "temperature": 0.3, "max_tokens": 500},
            2: {"model": "gpt-4", "temperature": 0.5, "max_tokens": 1000},
        },
    )

    # Strategy 2: More tiers for complex tasks
    deep_handoff = create_handoff_pattern(
        num_tiers=4,
        tier_configs={
            1: {"model": "gpt-3.5-turbo", "temperature": 0.3},
            2: {"model": "gpt-4", "temperature": 0.5},
            3: {"model": "gpt-4", "temperature": 0.7},
            4: {"model": "gpt-4-turbo", "temperature": 0.8},
        },
    )

    print("Strategy 1 - Fast Handoff (2 tiers):")
    print("  ✓ Lower latency (fewer evaluations)")
    print("  ✓ Lower cost (fewer tier checks)")
    print("  ✓ Best for: Simple to moderate tasks")
    print()

    print("Strategy 2 - Deep Handoff (4 tiers):")
    print("  ✓ Better specialization")
    print("  ✓ More granular routing")
    print("  ✓ Best for: Complex, varied workloads")
    print()

    # ==================================================================
    # SCENARIO 4: Edge Cases and Error Handling
    # ==================================================================
    print("Scenario 4: Edge Cases and Error Handling")
    print("-" * 70)

    handoff4 = create_handoff_pattern(num_tiers=3)

    # Test 1: Max tier limit enforcement
    result4a = handoff4.execute_with_handoff(
        "Extremely complex quantum computing algorithm optimization",
        max_tier=2,  # Limit to tier 2
    )

    print("Test 1 - Max Tier Enforcement:")
    print("  Task requires tier 3+, limited to tier 2")
    print(f"  Result: Handled at tier {result4a['final_tier']} (capped)")
    print()

    # Test 2: Simple task (no escalation)
    result4b = handoff4.execute_with_handoff("Convert 100 USD to EUR", max_tier=3)

    print("Test 2 - No Escalation Needed:")
    print(f"  Simple task handled at tier {result4b['final_tier']}")
    print(f"  Escalations: {result4b['escalation_count']}")
    print()

    # ==================================================================
    # SCENARIO 5: Handoff History Analysis
    # ==================================================================
    print("Scenario 5: Detailed Handoff History Analysis")
    print("-" * 70)

    handoff5 = create_handoff_pattern(num_tiers=3)

    result5 = handoff5.execute_with_handoff(
        "Design a real-time fraud detection system with ML pipeline",
        context="Enterprise system architecture",
        max_tier=3,
    )

    history5 = handoff5.get_handoff_history(result5["execution_id"])

    print("Detailed Escalation Analysis:")
    for idx, decision in enumerate(history5, 1):
        print(f"\n  Step {idx} - Tier {decision['tier_level']}:")
        print(f"    Agent: {decision['agent_id']}")
        print(f"    Can handle: {decision['can_handle']}")
        print(f"    Complexity: {decision['complexity_score']:.2f}")
        print(f"    Reasoning: {decision['reasoning'][:80]}...")
        print(f"    Action: {decision['handoff_decision']}")
        if decision["can_handle"] == "no":
            print(f"    Next tier: {decision['requires_tier']}")

    print()

    # ==================================================================
    # SCENARIO 6: Workload-Specific Optimization
    # ==================================================================
    print("Scenario 6: Workload-Specific Optimization")
    print("-" * 70)

    # Different handoff patterns for different workloads

    # Customer Support (favor quick resolution)
    support_handoff = create_handoff_pattern(
        num_tiers=3,
        tier_configs={
            1: {"temperature": 0.3},  # Deterministic responses
            2: {"temperature": 0.5},
            3: {"temperature": 0.7},
        },
    )

    # Research & Analysis (favor thoroughness)
    research_handoff = create_handoff_pattern(
        num_tiers=5,
        tier_configs={
            1: {"temperature": 0.5},
            2: {"temperature": 0.6},
            3: {"temperature": 0.7},
            4: {"temperature": 0.8},
            5: {"model": "gpt-4-turbo", "temperature": 0.9},
        },
    )

    print("Support Workload (3 tiers, lower temp):")
    print("  → Fast, deterministic responses")
    print("  → Cost-effective for high volume")
    print()

    print("Research Workload (5 tiers, higher temp):")
    print("  → Deep, creative analysis")
    print("  → Quality over speed")
    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Advanced Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to analyze multi-tier escalation patterns")
    print("  ✓ How to extract handoff metrics and analytics")
    print("  ✓ How to optimize performance (tier count, config)")
    print("  ✓ How to handle edge cases (max tier, simple tasks)")
    print("  ✓ How to analyze detailed handoff history")
    print("  ✓ How to optimize for specific workloads")
    print()
    print("Optimization Strategies:")
    print("  → Fewer tiers (2-3) for simple, high-volume workloads")
    print("  → More tiers (4-5) for complex, varied workloads")
    print("  → Lower temperature for deterministic tasks")
    print("  → Higher temperature for creative/research tasks")
    print("  → Fast models (gpt-3.5) for lower tiers")
    print("  → Powerful models (gpt-4-turbo) for top tiers")
    print()
    print("Monitoring Recommendations:")
    print("  → Track escalation rates by task type")
    print("  → Monitor tier utilization")
    print("  → Analyze avg complexity scores")
    print("  → Review handoff decision trails")
    print("  → Optimize tier configs based on metrics")
    print()


if __name__ == "__main__":
    main()
