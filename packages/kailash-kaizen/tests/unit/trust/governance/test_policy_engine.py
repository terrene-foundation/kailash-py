"""
Tier 1 Unit Tests for External Agent Policy Engine.

Tests policy evaluation logic in isolation without external dependencies.
Verifies INTENT: Policy conditions and conflict resolution work correctly.
"""

from datetime import datetime, timezone

import pytest
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


class TestTimeWindowCondition:
    """Test time-based policy conditions."""

    def test_business_hours_within_window(self):
        """
        INTENT: Verify business hours logic allows access during working hours.
        """
        # Monday 10:00 AM EST (within business hours)
        test_time = datetime(2025, 12, 22, 15, 0, 0, tzinfo=timezone.utc)  # 10 AM EST

        condition = TimeWindowCondition(
            business_hours={
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "start_time": "09:00",
                "end_time": "17:00",
                "timezone": "America/New_York",
            }
        )

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(external_agent_id="test", provider="test"),
            action="invoke",
            resource="test",
            time=test_time,
        )

        result = condition.evaluate(context)
        assert result is True, "Should allow access during business hours"

    def test_business_hours_outside_window(self):
        """
        INTENT: Verify business hours logic blocks access outside working hours.
        """
        # Monday 8:00 PM EST (outside business hours)
        test_time = datetime(2025, 12, 23, 1, 0, 0, tzinfo=timezone.utc)  # 8 PM EST

        condition = TimeWindowCondition(
            business_hours={
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "start_time": "09:00",
                "end_time": "17:00",
                "timezone": "America/New_York",
            }
        )

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(external_agent_id="test", provider="test"),
            action="invoke",
            resource="test",
            time=test_time,
        )

        result = condition.evaluate(context)
        assert result is False, "Should block access outside business hours"

    def test_business_hours_weekend(self):
        """
        INTENT: Verify business hours logic blocks access on weekends.
        """
        # Saturday 10:00 AM EST (weekend)
        test_time = datetime(
            2025, 12, 20, 15, 0, 0, tzinfo=timezone.utc
        )  # Saturday 10 AM EST

        condition = TimeWindowCondition(
            business_hours={
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "start_time": "09:00",
                "end_time": "17:00",
                "timezone": "America/New_York",
            }
        )

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(external_agent_id="test", provider="test"),
            action="invoke",
            resource="test",
            time=test_time,
        )

        result = condition.evaluate(context)
        assert result is False, "Should block access on weekends"

    def test_maintenance_window_deny(self):
        """
        INTENT: Verify maintenance windows block access during scheduled maintenance.
        """
        # During maintenance window
        test_time = datetime(2025, 12, 25, 12, 0, 0, tzinfo=timezone.utc)

        condition = TimeWindowCondition(
            maintenance_windows=[
                {"start": "2025-12-25T00:00:00Z", "end": "2025-12-25T23:59:59Z"}
            ],
            deny_during_maintenance=True,
        )

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(external_agent_id="test", provider="test"),
            action="invoke",
            resource="test",
            time=test_time,
        )

        result = condition.evaluate(context)
        assert result is False, "Should deny access during maintenance window"

    def test_maintenance_window_allow(self):
        """
        INTENT: Verify access is allowed outside maintenance windows.
        """
        # Outside maintenance window
        test_time = datetime(2025, 12, 24, 12, 0, 0, tzinfo=timezone.utc)

        condition = TimeWindowCondition(
            maintenance_windows=[
                {"start": "2025-12-25T00:00:00Z", "end": "2025-12-25T23:59:59Z"}
            ],
            deny_during_maintenance=True,
        )

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(external_agent_id="test", provider="test"),
            action="invoke",
            resource="test",
            time=test_time,
        )

        result = condition.evaluate(context)
        assert result is True, "Should allow access outside maintenance window"

    def test_timezone_conversion_europe(self):
        """
        INTENT: Verify timezone conversion works correctly for European timezone.
        """
        # 14:00 UTC = 15:00 CET (within business hours)
        test_time = datetime(2025, 12, 22, 14, 0, 0, tzinfo=timezone.utc)

        condition = TimeWindowCondition(
            business_hours={
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "start_time": "09:00",
                "end_time": "17:00",
                "timezone": "Europe/Paris",
            }
        )

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(external_agent_id="test", provider="test"),
            action="invoke",
            resource="test",
            time=test_time,
        )

        result = condition.evaluate(context)
        assert result is True, "Should handle European timezone correctly"


class TestLocationCondition:
    """Test location-based policy conditions."""

    def test_allowed_countries_match(self):
        """
        INTENT: Verify location-based policies allow whitelisted countries.
        """
        condition = LocationCondition(allowed_countries=["US", "CA"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test",
                provider="test",
                location={"country": "US"},
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is True, "Should allow access from whitelisted country"

    def test_allowed_countries_no_match(self):
        """
        INTENT: Verify location-based policies block non-whitelisted countries.
        """
        condition = LocationCondition(allowed_countries=["US", "CA"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test",
                provider="test",
                location={"country": "CN"},
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is False, "Should block access from non-whitelisted country"

    def test_blocked_countries(self):
        """
        INTENT: Verify location-based policies can match blocked countries (for use with DENY policy).
        """
        condition = LocationCondition(countries=["CN", "RU", "KP"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test",
                provider="test",
                location={"country": "RU"},
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert (
            result is True
        ), "Should match blocked country (use with DENY policy to block)"

    def test_ip_allowlist_match(self):
        """
        INTENT: Verify IP allowlist allows whitelisted IPs.
        """
        condition = LocationCondition(allowed_ips=["192.168.1.1", "10.0.0.1"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test",
                provider="test",
                ip_address="192.168.1.1",
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is True, "Should allow access from whitelisted IP"

    def test_ip_blocklist_match(self):
        """
        INTENT: Verify IP condition can match blocked IPs (for use with DENY policy).
        """
        condition = LocationCondition(ips=["192.168.1.100"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test",
                provider="test",
                ip_address="192.168.1.100",
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is True, "Should match blocked IP (use with DENY policy to block)"


class TestEnvironmentCondition:
    """Test environment-based policy conditions."""

    def test_allowed_environments_match(self):
        """
        INTENT: Verify environment-based policies allow matching environment.
        """
        condition = EnvironmentCondition(allowed_environments=["production"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="test", environment="production"
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is True, "Should allow access in allowed environment"

    def test_allowed_environments_no_match(self):
        """
        INTENT: Verify environment-based policies block non-matching environment.
        """
        condition = EnvironmentCondition(allowed_environments=["production"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="test", environment="development"
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is False, "Should block access in non-allowed environment"

    def test_blocked_environments(self):
        """
        INTENT: Verify environment-based policies can match blocked environments (for use with DENY policy).
        """
        condition = EnvironmentCondition(environments=["development"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="test", environment="development"
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert (
            result is True
        ), "Should match blocked environment (use with DENY policy to block)"


class TestProviderCondition:
    """Test provider-based policy conditions."""

    def test_allowed_providers_match(self):
        """
        INTENT: Verify provider whitelisting allows approved providers.
        """
        condition = ProviderCondition(allowed_providers=["copilot_studio"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="copilot_studio"
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is True, "Should allow access from whitelisted provider"

    def test_allowed_providers_no_match(self):
        """
        INTENT: Verify provider whitelisting blocks non-approved providers.
        """
        condition = ProviderCondition(allowed_providers=["copilot_studio"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="third_party_agent"
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is False, "Should block access from non-whitelisted provider"

    def test_blocked_providers(self):
        """
        INTENT: Verify provider condition can match blocked providers (for use with DENY policy).
        """
        condition = ProviderCondition(providers=["third_party_agent"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="third_party_agent"
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert (
            result is True
        ), "Should match blocked provider (use with DENY policy to block)"


class TestTagCondition:
    """Test tag-based policy conditions."""

    def test_required_tags_present(self):
        """
        INTENT: Verify tag-based policies allow agents with required tags.
        """
        condition = TagCondition(required_tags=["approved"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test",
                provider="test",
                tags=["approved", "production"],
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is True, "Should allow access when required tags present"

    def test_required_tags_missing(self):
        """
        INTENT: Verify tag-based policies block agents missing required tags.
        """
        condition = TagCondition(required_tags=["approved"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="test", tags=["experimental"]
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is False, "Should block access when required tags missing"

    def test_blocked_tags_present(self):
        """
        INTENT: Verify tag-based policies block agents with blocked tags.
        """
        condition = TagCondition(blocked_tags=["experimental"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="test", tags=["experimental"]
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is False, "Should block access when blocked tags present"

    def test_blocked_tags_absent(self):
        """
        INTENT: Verify tag-based policies allow agents without blocked tags.
        """
        condition = TagCondition(blocked_tags=["experimental"])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="test", tags=["approved"]
            ),
            action="invoke",
            resource="test",
        )

        result = condition.evaluate(context)
        assert result is True, "Should allow access when blocked tags absent"


@pytest.mark.asyncio
class TestPolicyEngine:
    """Test policy engine evaluation and conflict resolution."""

    async def test_single_allow_policy(self):
        """
        INTENT: Verify single ALLOW policy grants access.
        """
        engine = ExternalAgentPolicyEngine()

        policy = ExternalAgentPolicy(
            policy_id="allow_copilot",
            name="Allow Copilot",
            effect=PolicyEffect.ALLOW,
            conditions=[ProviderCondition(allowed_providers=["copilot_studio"])],
        )
        engine.add_policy(policy)

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="copilot_studio"
            ),
            action="invoke",
            resource="test",
        )

        result = await engine.evaluate_policies(context)
        assert result.effect == PolicyEffect.ALLOW
        assert "allow_copilot" in result.matched_policies

    async def test_single_deny_policy(self):
        """
        INTENT: Verify single DENY policy blocks access.
        """
        engine = ExternalAgentPolicyEngine()

        policy = ExternalAgentPolicy(
            policy_id="deny_third_party",
            name="Deny Third Party",
            effect=PolicyEffect.DENY,
            conditions=[ProviderCondition(blocked_providers=["third_party_agent"])],
        )
        engine.add_policy(policy)

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="third_party_agent"
            ),
            action="invoke",
            resource="test",
        )

        result = await engine.evaluate_policies(context)
        assert result.effect == PolicyEffect.DENY
        assert "deny_third_party" in result.matched_policies

    async def test_deny_overrides_conflict_resolution(self):
        """
        INTENT: Verify deny_overrides strategy: DENY wins over ALLOW.
        """
        engine = ExternalAgentPolicyEngine(
            conflict_resolution_strategy=ConflictResolutionStrategy.DENY_OVERRIDES
        )

        # Add ALLOW policy
        allow_policy = ExternalAgentPolicy(
            policy_id="allow_copilot",
            name="Allow Copilot",
            effect=PolicyEffect.ALLOW,
            conditions=[ProviderCondition(allowed_providers=["copilot_studio"])],
            priority=2,
        )
        engine.add_policy(allow_policy)

        # Add DENY policy (higher priority)
        deny_policy = ExternalAgentPolicy(
            policy_id="deny_production",
            name="Deny Production",
            effect=PolicyEffect.DENY,
            conditions=[EnvironmentCondition(blocked_environments=["production"])],
            priority=1,
        )
        engine.add_policy(deny_policy)

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test",
                provider="copilot_studio",
                environment="production",
            ),
            action="invoke",
            resource="test",
        )

        result = await engine.evaluate_policies(context)
        assert result.effect == PolicyEffect.DENY, "DENY should override ALLOW"
        assert "deny_production" in result.matched_policies
        assert "allow_copilot" in result.matched_policies

    async def test_allow_overrides_conflict_resolution(self):
        """
        INTENT: Verify allow_overrides strategy: ALLOW wins over DENY.
        """
        engine = ExternalAgentPolicyEngine(
            conflict_resolution_strategy=ConflictResolutionStrategy.ALLOW_OVERRIDES
        )

        # Add DENY policy
        deny_policy = ExternalAgentPolicy(
            policy_id="deny_development",
            name="Deny Development",
            effect=PolicyEffect.DENY,
            conditions=[EnvironmentCondition(blocked_environments=["development"])],
            priority=2,
        )
        engine.add_policy(deny_policy)

        # Add ALLOW policy (higher priority)
        allow_policy = ExternalAgentPolicy(
            policy_id="allow_approved",
            name="Allow Approved",
            effect=PolicyEffect.ALLOW,
            conditions=[TagCondition(required_tags=["approved"])],
            priority=1,
        )
        engine.add_policy(allow_policy)

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test",
                provider="test",
                environment="development",
                tags=["approved"],
            ),
            action="invoke",
            resource="test",
        )

        result = await engine.evaluate_policies(context)
        assert result.effect == PolicyEffect.ALLOW, "ALLOW should override DENY"
        assert "allow_approved" in result.matched_policies

    async def test_first_applicable_conflict_resolution(self):
        """
        INTENT: Verify first_applicable strategy: first matching policy wins.
        """
        engine = ExternalAgentPolicyEngine(
            conflict_resolution_strategy=ConflictResolutionStrategy.FIRST_APPLICABLE
        )

        # Add DENY policy (priority 1, evaluated first)
        deny_policy = ExternalAgentPolicy(
            policy_id="deny_first",
            name="Deny First",
            effect=PolicyEffect.DENY,
            conditions=[ProviderCondition(allowed_providers=["copilot_studio"])],
            priority=1,
        )
        engine.add_policy(deny_policy)

        # Add ALLOW policy (priority 2, evaluated second)
        allow_policy = ExternalAgentPolicy(
            policy_id="allow_second",
            name="Allow Second",
            effect=PolicyEffect.ALLOW,
            conditions=[ProviderCondition(allowed_providers=["copilot_studio"])],
            priority=2,
        )
        engine.add_policy(allow_policy)

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="copilot_studio"
            ),
            action="invoke",
            resource="test",
        )

        result = await engine.evaluate_policies(context)
        assert result.effect == PolicyEffect.DENY, "First matching policy should win"
        assert "deny_first" in result.matched_policies
        assert "allow_second" not in result.matched_policies

    async def test_no_matching_policies_deny_by_default(self):
        """
        INTENT: Verify deny-by-default when no policies match.
        """
        engine = ExternalAgentPolicyEngine()

        # Add policy that won't match
        policy = ExternalAgentPolicy(
            policy_id="allow_copilot",
            name="Allow Copilot",
            effect=PolicyEffect.ALLOW,
            conditions=[ProviderCondition(allowed_providers=["copilot_studio"])],
        )
        engine.add_policy(policy)

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="third_party_agent"
            ),
            action="invoke",
            resource="test",
        )

        result = await engine.evaluate_policies(context)
        assert result.effect == PolicyEffect.DENY, "Should deny by default"
        assert "deny-by-default" in result.reason.lower()

    async def test_policy_evaluation_performance(self):
        """
        INTENT: Verify policy evaluation completes within performance target (<5ms).
        """
        engine = ExternalAgentPolicyEngine()

        # Add multiple policies
        for i in range(10):
            policy = ExternalAgentPolicy(
                policy_id=f"policy_{i}",
                name=f"Policy {i}",
                effect=PolicyEffect.ALLOW if i % 2 == 0 else PolicyEffect.DENY,
                conditions=[
                    ProviderCondition(allowed_providers=["copilot_studio"]),
                    EnvironmentCondition(allowed_environments=["production"]),
                ],
                priority=i,
            )
            engine.add_policy(policy)

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test",
                provider="copilot_studio",
                environment="production",
            ),
            action="invoke",
            resource="test",
        )

        result = await engine.evaluate_policies(context)
        assert (
            result.evaluation_time_ms < 5.0
        ), f"Evaluation took {result.evaluation_time_ms}ms (should be <5ms)"

    async def test_disabled_policy_not_evaluated(self):
        """
        INTENT: Verify disabled policies are not evaluated.
        """
        engine = ExternalAgentPolicyEngine()

        # Add disabled policy
        policy = ExternalAgentPolicy(
            policy_id="disabled_policy",
            name="Disabled Policy",
            effect=PolicyEffect.ALLOW,
            conditions=[ProviderCondition(allowed_providers=["copilot_studio"])],
            enabled=False,
        )
        engine.add_policy(policy)

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="test", provider="copilot_studio"
            ),
            action="invoke",
            resource="test",
        )

        result = await engine.evaluate_policies(context)
        assert (
            result.effect == PolicyEffect.DENY
        ), "Disabled policy should not allow access"
        assert "disabled_policy" not in result.matched_policies
