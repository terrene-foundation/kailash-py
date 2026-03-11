"""
Quick Start Example: External Agent Policy Engine (ABAC)

This example demonstrates how to use the External Agent Policy Engine for
attribute-based access control of external agents.

Run with:
    python examples/governance/policy_engine_quick_start.py
"""

from datetime import datetime

from kaizen.governance import (
    ConflictResolutionStrategy,
    Environment,
    EnvironmentCondition,
    ExternalAgentPolicy,
    ExternalAgentPolicyContext,
    ExternalAgentPolicyEngine,
    ExternalAgentPrincipal,
    LocationCondition,
    PolicyEffect,
    ProviderCondition,
    TagCondition,
    TimeWindowCondition,
)


def example_1_business_hours():
    """Example 1: Business hours policy."""
    print("\n=== Example 1: Business Hours Policy ===")

    # Create policy: Allow only during business hours
    policy = ExternalAgentPolicy(
        policy_id="policy-business-hours",
        name="Allow only during business hours",
        effect=PolicyEffect.ALLOW,
        conditions=[
            TimeWindowCondition(
                business_hours={
                    "mon-fri": "09:00-17:00",
                    "timezone": "America/New_York",
                }
            )
        ],
        priority=10,
    )

    # Create policy engine
    engine = ExternalAgentPolicyEngine(
        policies=[policy],
        conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES,
    )

    # Test: Monday 10:00 AM (within business hours)
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="agent-001", provider="copilot_studio"
        ),
        action="invoke",
        resource="agent-001",
        time=datetime(2025, 12, 22, 10, 0, 0),  # Monday 10:00 AM
    )

    decision = engine.evaluate_policies(context)
    print(f"Decision: {decision.effect.value}")
    print(f"Reason: {decision.reason}")
    print(f"Evaluation time: {decision.evaluation_time_ms:.2f}ms")


def example_2_production_location():
    """Example 2: Production environment + location restriction."""
    print("\n=== Example 2: Production + Location Policy ===")

    # Policy: Allow production only from US/CA
    policy = ExternalAgentPolicy(
        policy_id="policy-prod-location",
        name="Production restricted to US/CA",
        effect=PolicyEffect.ALLOW,
        conditions=[
            EnvironmentCondition(allowed_environments=[Environment.PRODUCTION]),
            LocationCondition(allowed_countries=["US", "CA"]),
        ],
        priority=20,
    )

    engine = ExternalAgentPolicyEngine(
        policies=[policy], conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES
    )

    # Test: Production from US
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="agent-prod-001",
            provider="copilot_studio",
            environment=Environment.PRODUCTION,
            location={"country": "US", "region": "us-east-1"},
        ),
        action="invoke",
        resource="agent-prod-001",
        time=datetime.now(),
    )

    decision = engine.evaluate_policies(context)
    print(f"Decision: {decision.effect.value}")
    print(f"Reason: {decision.reason}")


def example_3_tag_based():
    """Example 3: Tag-based approval."""
    print("\n=== Example 3: Tag-Based Approval ===")

    # Policy: Require "approved" and "finance" tags
    policy = ExternalAgentPolicy(
        policy_id="policy-finance-approved",
        name="Require finance approval tags",
        effect=PolicyEffect.ALLOW,
        conditions=[TagCondition(required_tags={"approved", "finance"})],
        priority=30,
    )

    engine = ExternalAgentPolicyEngine(
        policies=[policy], conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES
    )

    # Test with required tags
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="agent-finance-001",
            provider="custom_rest_api",
            tags=["approved", "finance", "production"],
        ),
        action="invoke",
        resource="agent-finance-001",
        time=datetime.now(),
    )

    decision = engine.evaluate_policies(context)
    print(f"Decision: {decision.effect.value}")
    print(f"Reason: {decision.reason}")


def example_4_conflict_resolution():
    """Example 4: Conflict resolution - deny overrides."""
    print("\n=== Example 4: Conflict Resolution ===")

    # Policy 1: ALLOW copilot_studio
    allow_policy = ExternalAgentPolicy(
        policy_id="policy-allow",
        name="Allow Copilot Studio",
        effect=PolicyEffect.ALLOW,
        conditions=[ProviderCondition(allowed_providers=["copilot_studio"])],
        priority=10,
    )

    # Policy 2: DENY production
    deny_policy = ExternalAgentPolicy(
        policy_id="policy-deny",
        name="Deny production",
        effect=PolicyEffect.DENY,
        conditions=[
            EnvironmentCondition(blocked_environments=[Environment.PRODUCTION])
        ],
        priority=20,
    )

    # Engine with DENY_OVERRIDES
    engine = ExternalAgentPolicyEngine(
        policies=[allow_policy, deny_policy],
        conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES,
    )

    # Context matching BOTH policies
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="agent-001",
            provider="copilot_studio",  # Matches allow_policy
            environment=Environment.PRODUCTION,  # Matches deny_policy
        ),
        action="invoke",
        resource="agent-001",
        time=datetime.now(),
    )

    decision = engine.evaluate_policies(context)
    print(f"Decision: {decision.effect.value}")
    print(f"Reason: {decision.reason}")
    print(f"Matched policies: {decision.matched_policies}")


def example_5_no_policies():
    """Example 5: Default deny when no policies match."""
    print("\n=== Example 5: Default Deny ===")

    # Empty engine (no policies)
    engine = ExternalAgentPolicyEngine(
        policies=[], conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES
    )

    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="agent-001", provider="unknown_provider"
        ),
        action="invoke",
        resource="agent-001",
        time=datetime.now(),
    )

    decision = engine.evaluate_policies(context)
    print(f"Decision: {decision.effect.value}")
    print(f"Reason: {decision.reason}")


if __name__ == "__main__":
    print("External Agent Policy Engine - Quick Start Examples")
    print("=" * 60)

    example_1_business_hours()
    example_2_production_location()
    example_3_tag_based()
    example_4_conflict_resolution()
    example_5_no_policies()

    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("\nFor more information, see:")
    print("- docs/governance/external-agent-abac-policies.md")
    print("- POLICY_ENGINE_IMPLEMENTATION_SUMMARY.md")
