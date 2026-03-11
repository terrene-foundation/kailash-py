"""
Tier 1 Unit Tests for External Agent Policy Engine.

Tests policy evaluation logic in isolation without external dependencies.

Intent:
- Verify policy condition evaluation (time, location, environment, provider, tags)
- Verify policy engine conflict resolution strategies
- Verify policy matching and evaluation logic
- All tests focus on INTENT not just technical assertions
"""

from datetime import datetime, time

import pytest
from kaizen.governance.policy_engine import (
    ConflictResolutionStrategy,
    DataClassification,
    DataClassificationCondition,
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


class TestTimeWindowCondition:
    """Test time-based policy conditions."""

    def test_business_hours_allow_within_hours(self):
        """
        Intent: Verify business hours logic allows requests within hours.

        Business logic: Requests during business hours (9am-5pm weekdays) should be allowed.
        """
        # Monday 10:00 AM (within business hours)
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime(2025, 12, 22, 10, 0, 0),  # Monday 10:00 AM
        )

        condition = TimeWindowCondition(
            business_hours={"mon-fri": "09:00-17:00", "timezone": "America/New_York"}
        )

        # Intent: Request during business hours should be allowed
        assert condition.evaluate(context) is True

    def test_business_hours_deny_outside_hours(self):
        """
        Intent: Verify business hours enforcement blocks requests outside hours.

        Business logic: Requests outside business hours (before 9am or after 5pm) should be denied.
        """
        # Monday 8:00 AM (before business hours)
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime(2025, 12, 22, 8, 0, 0),  # Monday 8:00 AM
        )

        condition = TimeWindowCondition(
            business_hours={"mon-fri": "09:00-17:00", "timezone": "America/New_York"}
        )

        # Intent: Request before business hours should be denied
        assert condition.evaluate(context) is False

    def test_business_hours_deny_weekend(self):
        """
        Intent: Verify business hours enforcement blocks weekend requests.

        Business logic: Requests on weekends should be denied when policy is mon-fri.
        """
        # Saturday 10:00 AM
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime(2025, 12, 20, 10, 0, 0),  # Saturday 10:00 AM
        )

        condition = TimeWindowCondition(
            business_hours={"mon-fri": "09:00-17:00", "timezone": "America/New_York"}
        )

        # Intent: Weekend requests should be denied
        assert condition.evaluate(context) is False

    def test_maintenance_window_deny(self):
        """
        Intent: Verify maintenance windows block requests during maintenance.

        Business logic: Requests during scheduled maintenance should be denied.
        """
        # During maintenance window
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime(2025, 12, 25, 12, 0, 0),  # Christmas Day 12:00 PM
        )

        condition = TimeWindowCondition(
            maintenance_windows=[
                {
                    "start": "2025-12-25T00:00:00+00:00",
                    "end": "2025-12-25T23:59:59+00:00",
                }
            ]
        )

        # Intent: Requests during maintenance should be denied
        assert condition.evaluate(context) is False

    def test_allowed_days_only_weekdays(self):
        """
        Intent: Verify allowed days restriction works correctly.

        Business logic: Only requests on specified days should be allowed.
        """
        # Monday (allowed)
        context_monday = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime(2025, 12, 22, 10, 0, 0),  # Monday
        )

        condition = TimeWindowCondition(
            allowed_days=["monday", "tuesday", "wednesday", "thursday", "friday"]
        )

        # Intent: Monday should be allowed
        assert condition.evaluate(context_monday) is True

        # Saturday (not allowed)
        context_saturday = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime(2025, 12, 20, 10, 0, 0),  # Saturday
        )

        # Intent: Saturday should be denied
        assert condition.evaluate(context_saturday) is False


class TestLocationCondition:
    """Test location-based policy conditions."""

    def test_allowed_countries_allow(self):
        """
        Intent: Verify location-based policies allow whitelisted countries.

        Business logic: Requests from allowed countries should be permitted.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                location={"country": "US", "region": "us-east-1"},
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = LocationCondition(allowed_countries=["US", "CA"])

        # Intent: US is in allowed list, should be allowed
        assert condition.evaluate(context) is True

    def test_allowed_countries_deny(self):
        """
        Intent: Verify location-based policies block non-whitelisted countries.

        Business logic: Requests from countries not in whitelist should be denied.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                location={"country": "RU", "region": "eu-west-1"},
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = LocationCondition(allowed_countries=["US", "CA"])

        # Intent: RU is not in allowed list, should be denied
        assert condition.evaluate(context) is False

    def test_blocked_countries_deny(self):
        """
        Intent: Verify location-based policies block blacklisted countries.

        Business logic: Requests from blocked countries should always be denied.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                location={"country": "CN", "region": "ap-east-1"},
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = LocationCondition(blocked_countries=["CN", "RU"])

        # Intent: CN is in blocked list, should be denied
        assert condition.evaluate(context) is False

    def test_allowed_regions_allow(self):
        """
        Intent: Verify region-based policies allow whitelisted regions.

        Business logic: Requests from allowed regions should be permitted.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                location={"country": "US", "region": "us-east-1"},
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = LocationCondition(allowed_regions=["us-east-1", "us-west-2"])

        # Intent: us-east-1 is in allowed list, should be allowed
        assert condition.evaluate(context) is True


class TestEnvironmentCondition:
    """Test environment-based policy conditions."""

    def test_environment_match_allow(self):
        """
        Intent: Verify environment-based policies work correctly.

        Business logic: Requests matching allowed environment should be permitted.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                environment=Environment.PRODUCTION,
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = EnvironmentCondition(allowed_environments=[Environment.PRODUCTION])

        # Intent: Production environment is allowed
        assert condition.evaluate(context) is True

    def test_environment_mismatch_deny(self):
        """
        Intent: Verify environment-based policies deny wrong environments.

        Business logic: Requests from non-allowed environments should be denied.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                environment=Environment.DEVELOPMENT,
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = EnvironmentCondition(allowed_environments=[Environment.PRODUCTION])

        # Intent: Development environment is not allowed
        assert condition.evaluate(context) is False

    def test_blocked_environment_matches(self):
        """
        Intent: Verify blocked environment condition matches when environment is blocked.

        Business logic: Condition should return True when environment matches blocked list
        (indicating the policy should be applied).
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                environment=Environment.PRODUCTION,
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = EnvironmentCondition(blocked_environments=[Environment.PRODUCTION])

        # Intent: Production is in blocked list, condition matches (returns True)
        # This would then be used with a DENY policy to deny the request
        assert condition.evaluate(context) is True


class TestProviderCondition:
    """Test provider-based policy conditions."""

    def test_allowed_provider_allow(self):
        """
        Intent: Verify provider whitelisting works.

        Business logic: Requests from allowed providers should be permitted.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = ProviderCondition(
            allowed_providers=["copilot_studio", "custom_rest_api"]
        )

        # Intent: copilot_studio is in allowed list
        assert condition.evaluate(context) is True

    def test_allowed_provider_deny(self):
        """
        Intent: Verify provider whitelisting denies non-allowed providers.

        Business logic: Requests from non-whitelisted providers should be denied.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="third_party_agent",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = ProviderCondition(
            allowed_providers=["copilot_studio", "custom_rest_api"]
        )

        # Intent: third_party_agent is not in allowed list
        assert condition.evaluate(context) is False

    def test_blocked_provider_matches(self):
        """
        Intent: Verify provider blacklist condition matches when provider is blocked.

        Business logic: Condition should return True when provider matches blocked list
        (indicating the policy should be applied).
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="untrusted_provider",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = ProviderCondition(blocked_providers=["untrusted_provider"])

        # Intent: untrusted_provider is in blocked list, condition matches (returns True)
        # This would then be used with a DENY policy to deny the request
        assert condition.evaluate(context) is True


class TestTagCondition:
    """Test tag-based policy conditions."""

    def test_required_tags_present_allow(self):
        """
        Intent: Verify tag-based policies enforce required tags.

        Business logic: Agents with all required tags should be allowed.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                tags=["approved", "finance", "production"],
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = TagCondition(required_tags={"approved", "production"})

        # Intent: Agent has all required tags
        assert condition.evaluate(context) is True

    def test_required_tags_missing_deny(self):
        """
        Intent: Verify tag-based policies deny when required tags are missing.

        Business logic: Agents missing required tags should be denied.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                tags=["approved"],  # Missing "production" tag
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = TagCondition(required_tags={"approved", "production"})

        # Intent: Agent missing "production" tag
        assert condition.evaluate(context) is False

    def test_blocked_tags_deny(self):
        """
        Intent: Verify tag-based policies block agents with forbidden tags.

        Business logic: Agents with blocked tags should be denied.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                tags=["experimental", "beta"],
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = TagCondition(blocked_tags={"experimental"})

        # Intent: Agent has blocked tag "experimental"
        assert condition.evaluate(context) is False

    def test_any_of_tags_allow(self):
        """
        Intent: Verify any_of_tags logic allows if at least one tag matches.

        Business logic: Agents with at least one of the specified tags should be allowed.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                tags=["finance"],  # Has one of the required tags
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = TagCondition(any_of_tags={"finance", "hr", "legal"})

        # Intent: Agent has "finance" tag (one of the required)
        assert condition.evaluate(context) is True

    def test_any_of_tags_deny(self):
        """
        Intent: Verify any_of_tags logic denies if no tags match.

        Business logic: Agents with none of the specified tags should be denied.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                tags=["engineering"],  # Doesn't have any required tags
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        condition = TagCondition(any_of_tags={"finance", "hr", "legal"})

        # Intent: Agent has none of the required tags
        assert condition.evaluate(context) is False


class TestDataClassificationCondition:
    """Test data classification-based policy conditions."""

    def test_allowed_classification_allow(self):
        """
        Intent: Verify classification policies allow permitted classifications.

        Business logic: Requests with allowed data classifications should be permitted.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
            data_classification=DataClassification.PUBLIC,
        )

        condition = DataClassificationCondition(
            allowed_classifications=[
                DataClassification.PUBLIC,
                DataClassification.INTERNAL,
            ]
        )

        # Intent: PUBLIC classification is allowed
        assert condition.evaluate(context) is True

    def test_encryption_required_with_encryption_allow(self):
        """
        Intent: Verify encryption requirement allows when encryption enabled.

        Business logic: Confidential data with encryption should be allowed when encryption required.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
            data_classification=DataClassification.CONFIDENTIAL,
            attributes={"encryption_enabled": True},
        )

        condition = DataClassificationCondition(
            allowed_classifications=[DataClassification.CONFIDENTIAL],
            requires_encryption=True,
        )

        # Intent: Confidential data with encryption should be allowed
        assert condition.evaluate(context) is True

    def test_encryption_required_without_encryption_deny(self):
        """
        Intent: Verify encryption requirement denies when encryption not enabled.

        Business logic: Confidential data without encryption should be denied when encryption required.
        """
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
            data_classification=DataClassification.CONFIDENTIAL,
            attributes={"encryption_enabled": False},
        )

        condition = DataClassificationCondition(
            allowed_classifications=[DataClassification.CONFIDENTIAL],
            requires_encryption=True,
        )

        # Intent: Confidential data without encryption should be denied
        assert condition.evaluate(context) is False


class TestExternalAgentPolicyEngine:
    """Test policy engine with conflict resolution strategies."""

    def test_deny_overrides_strategy(self):
        """
        Intent: Verify deny_overrides strategy - DENY wins over ALLOW.

        Business logic: When multiple policies match, any DENY should result in final DENY.
        """
        # Create policies
        allow_policy = ExternalAgentPolicy(
            policy_id="policy-allow",
            name="Allow copilot_studio",
            effect=PolicyEffect.ALLOW,
            conditions=[ProviderCondition(allowed_providers=["copilot_studio"])],
            priority=1,
        )

        deny_policy = ExternalAgentPolicy(
            policy_id="policy-deny",
            name="Deny production",
            effect=PolicyEffect.DENY,
            conditions=[
                EnvironmentCondition(blocked_environments=[Environment.PRODUCTION])
            ],
            priority=2,
        )

        # Create engine with deny_overrides strategy
        engine = ExternalAgentPolicyEngine(
            policies=[allow_policy, deny_policy],
            conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES,
        )

        # Create context matching both policies
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                environment=Environment.PRODUCTION,
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        # Intent: DENY should win over ALLOW
        decision = engine.evaluate_policies(context)
        assert decision.effect == PolicyEffect.DENY
        assert "policy-deny" in decision.matched_policies
        assert "policy-allow" in decision.matched_policies

    def test_allow_overrides_strategy(self):
        """
        Intent: Verify allow_overrides strategy - ALLOW wins over DENY.

        Business logic: When multiple policies match, any ALLOW should result in final ALLOW.
        """
        # Create policies
        allow_policy = ExternalAgentPolicy(
            policy_id="policy-allow",
            name="Allow approved tag",
            effect=PolicyEffect.ALLOW,
            conditions=[TagCondition(required_tags={"approved"})],
            priority=1,
        )

        deny_policy = ExternalAgentPolicy(
            policy_id="policy-deny",
            name="Deny production",
            effect=PolicyEffect.DENY,
            conditions=[
                EnvironmentCondition(blocked_environments=[Environment.PRODUCTION])
            ],
            priority=2,
        )

        # Create engine with allow_overrides strategy
        engine = ExternalAgentPolicyEngine(
            policies=[allow_policy, deny_policy],
            conflict_resolution=ConflictResolutionStrategy.ALLOW_OVERRIDES,
        )

        # Create context matching both policies
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                environment=Environment.PRODUCTION,
                tags=["approved"],
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        # Intent: ALLOW should win over DENY
        decision = engine.evaluate_policies(context)
        assert decision.effect == PolicyEffect.ALLOW
        assert "policy-allow" in decision.matched_policies
        assert "policy-deny" in decision.matched_policies

    def test_first_applicable_strategy(self):
        """
        Intent: Verify first_applicable strategy - first matching policy wins.

        Business logic: The first policy that matches (by priority) determines the result.
        """
        # Create policies with different priorities
        high_priority_deny = ExternalAgentPolicy(
            policy_id="policy-high",
            name="High priority deny",
            effect=PolicyEffect.DENY,
            conditions=[
                EnvironmentCondition(blocked_environments=[Environment.PRODUCTION])
            ],
            priority=100,  # Highest priority
        )

        low_priority_allow = ExternalAgentPolicy(
            policy_id="policy-low",
            name="Low priority allow",
            effect=PolicyEffect.ALLOW,
            conditions=[ProviderCondition(allowed_providers=["copilot_studio"])],
            priority=1,  # Lower priority
        )

        # Create engine with first_applicable strategy
        engine = ExternalAgentPolicyEngine(
            policies=[low_priority_allow, high_priority_deny],
            conflict_resolution=ConflictResolutionStrategy.FIRST_APPLICABLE,
        )

        # Create context matching both policies
        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
                environment=Environment.PRODUCTION,
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        # Intent: First matching policy (highest priority) wins
        decision = engine.evaluate_policies(context)
        assert decision.effect == PolicyEffect.DENY
        assert decision.matched_policies == ["policy-high"]

    def test_no_policies_default_deny(self):
        """
        Intent: Verify default deny when no policies match.

        Business logic: For security, requests with no matching policies should be denied.
        """
        engine = ExternalAgentPolicyEngine(policies=[])

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        # Intent: No policies should result in default DENY
        decision = engine.evaluate_policies(context)
        assert decision.effect == PolicyEffect.DENY
        assert "No applicable policies" in decision.reason

    def test_policy_pattern_matching(self):
        """
        Intent: Verify policy pattern matching for principals and actions.

        Business logic: Policies should only apply to matching principals/actions.
        """
        # Policy that only applies to specific agent pattern
        policy = ExternalAgentPolicy(
            policy_id="policy-pattern",
            name="Allow specific agents",
            effect=PolicyEffect.ALLOW,
            conditions=[],
            priority=1,
            principal_pattern=r"agent-prod-.*",  # Only matches agent-prod-* agents
            action_pattern=r"invoke",  # Only matches "invoke" action
        )

        engine = ExternalAgentPolicyEngine(policies=[policy])

        # Matching context
        matching_context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-prod-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-prod-001",
            time=datetime.now(),
        )

        # Intent: Matching pattern should apply policy
        decision_match = engine.evaluate_policies(matching_context)
        assert decision_match.effect == PolicyEffect.ALLOW

        # Non-matching context (different agent ID pattern)
        non_matching_context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-dev-001",  # Doesn't match pattern
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-dev-001",
            time=datetime.now(),
        )

        # Intent: Non-matching pattern should not apply policy (default deny)
        decision_no_match = engine.evaluate_policies(non_matching_context)
        assert decision_no_match.effect == PolicyEffect.DENY

    def test_performance_under_5ms(self):
        """
        Intent: Verify policy evaluation is performant (<5ms p95).

        Business logic: Policy evaluation must not bottleneck invocations.
        """
        # Create 100 policies
        policies = []
        for i in range(100):
            policies.append(
                ExternalAgentPolicy(
                    policy_id=f"policy-{i}",
                    name=f"Policy {i}",
                    effect=PolicyEffect.ALLOW if i % 2 == 0 else PolicyEffect.DENY,
                    conditions=[
                        ProviderCondition(allowed_providers=["copilot_studio"])
                    ],
                    priority=i,
                )
            )

        engine = ExternalAgentPolicyEngine(
            policies=policies,
            conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES,
        )

        context = ExternalAgentPolicyContext(
            principal=ExternalAgentPrincipal(
                external_agent_id="agent-001",
                provider="copilot_studio",
            ),
            action="invoke",
            resource="agent-001",
            time=datetime.now(),
        )

        # Evaluate and check performance
        decision = engine.evaluate_policies(context)

        # Intent: Evaluation should be fast (<5ms)
        assert decision.evaluation_time_ms < 5.0
