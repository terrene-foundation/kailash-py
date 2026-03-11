"""
External Agent Policy Engine Usage Examples.

Demonstrates ABAC (Attribute-Based Access Control) for external agents
with time, location, environment, provider, and tag-based policies.
"""

import asyncio
from datetime import datetime, timezone

from kaizen.trust.governance import (
    ConflictResolutionStrategy,
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


async def example_1_simple_allow_policy():
    """
    Example 1: Simple ALLOW policy for Copilot Studio in production.

    INTENT: Only allow Microsoft Copilot Studio agents in production environment.
    """
    print("\n" + "=" * 80)
    print("Example 1: Simple ALLOW Policy")
    print("=" * 80)

    # Create engine
    engine = ExternalAgentPolicyEngine()

    # Create policy
    policy = ExternalAgentPolicy(
        policy_id="allow_copilot_prod",
        name="Allow Copilot in Production",
        effect=PolicyEffect.ALLOW,
        conditions=[
            ProviderCondition(providers=["copilot_studio"]),
            EnvironmentCondition(environments=["production"]),
        ],
        priority=1,
    )
    engine.add_policy(policy)

    # Test 1: Matching context (should ALLOW)
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="copilot_hr",
            provider="copilot_studio",
            environment="production",
        ),
        action="invoke",
        resource="copilot_hr",
    )

    result = await engine.evaluate_policies(context)
    print("\n✅ Test 1 - Copilot in Production:")
    print(f"   Decision: {result.effect.value}")
    print(f"   Reason: {result.reason}")
    print(f"   Evaluation: {result.evaluation_time_ms:.2f}ms")

    # Test 2: Non-matching context (should DENY)
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="custom_agent",
            provider="third_party_agent",
            environment="production",
        ),
        action="invoke",
        resource="custom_agent",
    )

    result = await engine.evaluate_policies(context)
    print("\n❌ Test 2 - Third-Party Agent:")
    print(f"   Decision: {result.effect.value}")
    print(f"   Reason: {result.reason}")


async def example_2_deny_policy():
    """
    Example 2: DENY policy to block third-party agents.

    INTENT: Block all third-party agents regardless of environment.
    """
    print("\n" + "=" * 80)
    print("Example 2: DENY Policy for Third-Party Agents")
    print("=" * 80)

    engine = ExternalAgentPolicyEngine()

    # Create DENY policy
    deny_policy = ExternalAgentPolicy(
        policy_id="deny_third_party",
        name="Block Third-Party Agents",
        effect=PolicyEffect.DENY,
        conditions=[ProviderCondition(providers=["third_party_agent"])],
        priority=1,
    )
    engine.add_policy(deny_policy)

    # Test: Third-party agent should be blocked
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="custom_agent",
            provider="third_party_agent",
            environment="production",
        ),
        action="invoke",
        resource="custom_agent",
    )

    result = await engine.evaluate_policies(context)
    print("\n❌ Third-Party Agent Blocked:")
    print(f"   Decision: {result.effect.value}")
    print(f"   Reason: {result.reason}")
    print(f"   Matched Policies: {result.matched_policies}")


async def example_3_business_hours_policy():
    """
    Example 3: Time-based policy with business hours restriction.

    INTENT: Only allow agent invocations during business hours (Mon-Fri 9am-5pm EST).
    """
    print("\n" + "=" * 80)
    print("Example 3: Business Hours Policy")
    print("=" * 80)

    engine = ExternalAgentPolicyEngine()

    # Create business hours policy
    policy = ExternalAgentPolicy(
        policy_id="business_hours_only",
        name="Allow Only During Business Hours",
        effect=PolicyEffect.ALLOW,
        conditions=[
            TimeWindowCondition(
                business_hours={
                    "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "timezone": "America/New_York",
                }
            )
        ],
        priority=1,
    )
    engine.add_policy(policy)

    # Test 1: Monday 10:00 EST (within hours)
    monday_morning = datetime(2025, 12, 22, 15, 0, 0, tzinfo=timezone.utc)  # 10 AM EST

    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="test", provider="copilot_studio"
        ),
        action="invoke",
        resource="test",
        time=monday_morning,
    )

    result = await engine.evaluate_policies(context)
    print("\n✅ Monday 10:00 AM EST:")
    print(f"   Decision: {result.effect.value}")
    print(f"   Reason: {result.reason}")

    # Test 2: Monday 20:00 EST (outside hours)
    monday_evening = datetime(2025, 12, 23, 1, 0, 0, tzinfo=timezone.utc)  # 8 PM EST

    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="test", provider="copilot_studio"
        ),
        action="invoke",
        resource="test",
        time=monday_evening,
    )

    result = await engine.evaluate_policies(context)
    print("\n❌ Monday 8:00 PM EST:")
    print(f"   Decision: {result.effect.value}")
    print(f"   Reason: {result.reason}")


async def example_4_conflict_resolution():
    """
    Example 4: Conflict resolution with multiple policies.

    INTENT: Demonstrate deny_overrides strategy where DENY wins over ALLOW.
    """
    print("\n" + "=" * 80)
    print("Example 4: Conflict Resolution (Deny-Overrides)")
    print("=" * 80)

    # Use deny_overrides strategy
    engine = ExternalAgentPolicyEngine(
        conflict_resolution_strategy=ConflictResolutionStrategy.DENY_OVERRIDES
    )

    # Policy 1: ALLOW Copilot
    allow_policy = ExternalAgentPolicy(
        policy_id="allow_copilot",
        name="Allow Copilot",
        effect=PolicyEffect.ALLOW,
        conditions=[ProviderCondition(providers=["copilot_studio"])],
        priority=2,
    )
    engine.add_policy(allow_policy)

    # Policy 2: DENY production environment
    deny_policy = ExternalAgentPolicy(
        policy_id="deny_production",
        name="Deny Production",
        effect=PolicyEffect.DENY,
        conditions=[EnvironmentCondition(environments=["production"])],
        priority=1,
    )
    engine.add_policy(deny_policy)

    # Test: Copilot in production (both policies match)
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="copilot_hr",
            provider="copilot_studio",
            environment="production",
        ),
        action="invoke",
        resource="copilot_hr",
    )

    result = await engine.evaluate_policies(context)
    print("\n❌ Copilot in Production (DENY wins):")
    print(f"   Decision: {result.effect.value}")
    print(f"   Reason: {result.reason}")
    print(f"   Matched Policies: {result.matched_policies}")
    print(f"   Strategy: {result.metadata['strategy']}")


async def example_5_tag_based_policy():
    """
    Example 5: Tag-based policy requiring approval tag.

    INTENT: Only allow agents with "approved" tag.
    """
    print("\n" + "=" * 80)
    print("Example 5: Tag-Based Policy")
    print("=" * 80)

    engine = ExternalAgentPolicyEngine()

    # Create tag-based policy
    policy = ExternalAgentPolicy(
        policy_id="require_approved_tag",
        name="Require Approved Tag",
        effect=PolicyEffect.ALLOW,
        conditions=[TagCondition(required_tags=["approved"])],
        priority=1,
    )
    engine.add_policy(policy)

    # Test 1: Agent with approved tag
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="test",
            provider="copilot_studio",
            tags=["approved", "production"],
        ),
        action="invoke",
        resource="test",
    )

    result = await engine.evaluate_policies(context)
    print("\n✅ Agent with 'approved' tag:")
    print(f"   Decision: {result.effect.value}")
    print(f"   Tags: {context.principal.tags}")

    # Test 2: Agent without approved tag
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="test", provider="copilot_studio", tags=["experimental"]
        ),
        action="invoke",
        resource="test",
    )

    result = await engine.evaluate_policies(context)
    print("\n❌ Agent without 'approved' tag:")
    print(f"   Decision: {result.effect.value}")
    print(f"   Reason: {result.reason}")
    print(f"   Tags: {context.principal.tags}")


async def example_6_location_based_policy():
    """
    Example 6: Location-based policy restricting by country.

    INTENT: Only allow agents from US and Canada.
    """
    print("\n" + "=" * 80)
    print("Example 6: Location-Based Policy")
    print("=" * 80)

    engine = ExternalAgentPolicyEngine()

    # Create location-based policy
    policy = ExternalAgentPolicy(
        policy_id="allow_us_ca_only",
        name="Allow US and Canada Only",
        effect=PolicyEffect.ALLOW,
        conditions=[LocationCondition(countries=["US", "CA"])],
        priority=1,
    )
    engine.add_policy(policy)

    # Test 1: Request from US
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="test",
            provider="copilot_studio",
            location={"country": "US"},
        ),
        action="invoke",
        resource="test",
    )

    result = await engine.evaluate_policies(context)
    print("\n✅ Request from US:")
    print(f"   Decision: {result.effect.value}")
    print(f"   Location: {context.principal.location}")

    # Test 2: Request from non-allowed country
    context = ExternalAgentPolicyContext(
        principal=ExternalAgentPrincipal(
            external_agent_id="test",
            provider="copilot_studio",
            location={"country": "RU"},
        ),
        action="invoke",
        resource="test",
    )

    result = await engine.evaluate_policies(context)
    print("\n❌ Request from Russia:")
    print(f"   Decision: {result.effect.value}")
    print(f"   Reason: {result.reason}")
    print(f"   Location: {context.principal.location}")


async def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("EXTERNAL AGENT POLICY ENGINE - USAGE EXAMPLES")
    print("=" * 80)

    await example_1_simple_allow_policy()
    await example_2_deny_policy()
    await example_3_business_hours_policy()
    await example_4_conflict_resolution()
    await example_5_tag_based_policy()
    await example_6_location_based_policy()

    print("\n" + "=" * 80)
    print("ALL EXAMPLES COMPLETED SUCCESSFULLY")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
