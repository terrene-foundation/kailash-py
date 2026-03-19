# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
External Agent Policy Engine (ABAC).

Implements Attribute-Based Access Control for external agents with support for:
- Time-based restrictions (business hours, maintenance windows)
- Location-based restrictions (IP allowlists, geo-restrictions)
- Environment-based restrictions (production, staging, development)
- Provider-based restrictions (Copilot Studio, custom REST, third-party)
- Tag-based restrictions (required tags, blocked tags)

Policy evaluation follows deny-by-default model with configurable conflict resolution.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PolicyEffect(str, Enum):
    """Policy decision effect."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class ConflictResolutionStrategy(str, Enum):
    """Policy conflict resolution strategies."""

    DENY_OVERRIDES = "deny_overrides"  # Any DENY wins
    ALLOW_OVERRIDES = "allow_overrides"  # Any ALLOW wins
    FIRST_APPLICABLE = "first_applicable"  # First matching policy wins


@dataclass
class ExternalAgentPrincipal:
    """
    External agent principal with attributes for policy evaluation.

    Attributes:
        external_agent_id: Unique agent identifier
        provider: Platform provider (copilot_studio, custom_rest_api, etc.)
        tags: Agent classification tags
        org_id: Organization identifier
        environment: Deployment environment (production, staging, development)
        location: Geographic location (country, region)
        ip_address: Request IP address for geo-location
    """

    external_agent_id: str
    provider: str
    tags: list[str] = field(default_factory=list)
    org_id: str | None = None
    environment: str = "development"
    location: dict[str, str] = field(default_factory=dict)  # {"country": "US", "region": "us-east-1"}
    ip_address: str | None = None


@dataclass
class ExternalAgentPolicyContext:
    """
    Context for policy evaluation.

    Attributes:
        principal: External agent principal
        action: Action being performed (invoke, configure, delete)
        resource: Resource identifier (external_agent_id)
        time: Request timestamp
        attributes: Additional context attributes for extensibility
    """

    principal: ExternalAgentPrincipal
    action: str  # "invoke", "configure", "delete"
    resource: str  # external_agent_id
    time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyEvaluationResult:
    """
    Result of policy evaluation.

    Attributes:
        effect: Final decision (ALLOW or DENY)
        reason: Human-readable reason for decision
        matched_policies: List of policy IDs that matched
        evaluation_time_ms: Time taken to evaluate (milliseconds)
        metadata: Additional evaluation context
    """

    effect: PolicyEffect
    reason: str
    matched_policies: list[str] = field(default_factory=list)
    evaluation_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class PolicyCondition(ABC):
    """
    Base class for policy conditions.

    All condition subclasses must implement evaluate() method.
    """

    @abstractmethod
    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate condition against context.

        Args:
            context: Policy evaluation context

        Returns:
            True if condition is satisfied, False otherwise
        """
        pass


class TimeWindowCondition(PolicyCondition):
    """
    Time-based policy condition.

    Supports:
    - Business hours (weekday + time range + timezone)
    - Maintenance windows (start/end datetime ranges)
    - Blackout periods (deny during specific times)

    Examples:
        >>> # Business hours: Mon-Fri 9am-5pm EST
        >>> condition = TimeWindowCondition(
        ...     business_hours={
        ...         "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        ...         "start_time": "09:00",
        ...         "end_time": "17:00",
        ...         "timezone": "America/New_York"
        ...     }
        ... )
        >>>
        >>> # Maintenance window
        >>> condition = TimeWindowCondition(
        ...     maintenance_windows=[
        ...         {"start": "2025-12-25T00:00:00Z", "end": "2025-12-25T23:59:59Z"}
        ...     ],
        ...     deny_during_maintenance=True
        ... )
    """

    def __init__(
        self,
        business_hours: dict[str, Any] | None = None,
        maintenance_windows: list[dict[str, str]] | None = None,
        deny_during_maintenance: bool = True,
    ):
        """
        Initialize time window condition.

        Args:
            business_hours: Business hours configuration
                - days: List of allowed weekdays (lowercase)
                - start_time: Start time (HH:MM format)
                - end_time: End time (HH:MM format)
                - timezone: Timezone name (e.g., America/New_York)
            maintenance_windows: List of maintenance windows
                - start: ISO 8601 datetime string
                - end: ISO 8601 datetime string
            deny_during_maintenance: Whether to deny during maintenance windows
        """
        self.business_hours = business_hours
        self.maintenance_windows = maintenance_windows or []
        self.deny_during_maintenance = deny_during_maintenance

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate time window condition.

        Args:
            context: Policy evaluation context

        Returns:
            True if current time satisfies condition, False otherwise
        """
        current_time = context.time

        # Check maintenance windows
        if self.maintenance_windows:
            for window in self.maintenance_windows:
                start = datetime.fromisoformat(window["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(window["end"].replace("Z", "+00:00"))

                # Make current_time timezone-aware if needed
                if current_time.tzinfo is None:
                    from datetime import timezone

                    current_time = current_time.replace(tzinfo=timezone.utc)

                if start <= current_time <= end:
                    # During maintenance window
                    return not self.deny_during_maintenance

        # Check business hours
        if self.business_hours:
            from datetime import timezone

            import pytz

            # Get timezone
            tz_name = self.business_hours.get("timezone", "UTC")
            tz = pytz.timezone(tz_name)

            # Convert current time to target timezone
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)
            current_time_local = current_time.astimezone(tz)

            # Check day of week
            weekday = current_time_local.strftime("%A").lower()
            allowed_days = [day.lower() for day in self.business_hours.get("days", [])]
            if allowed_days and weekday not in allowed_days:
                return False

            # Check time range
            start_time_str = self.business_hours.get("start_time")
            end_time_str = self.business_hours.get("end_time")

            if start_time_str and end_time_str:
                start_time = time.fromisoformat(start_time_str)
                end_time = time.fromisoformat(end_time_str)
                current_time_only = current_time_local.time()

                if not (start_time <= current_time_only <= end_time):
                    return False

        return True


class LocationCondition(PolicyCondition):
    """
    Location-based policy condition.

    Supports:
    - Country matching (ISO 3166-1 alpha-2 codes)
    - IP matching

    Note: Use with ALLOW policies for allowlisting, DENY policies for blocklisting.

    Examples:
        >>> # ALLOW policy: only US and Canada
        >>> policy = ExternalAgentPolicy(
        ...     effect=PolicyEffect.ALLOW,
        ...     conditions=[LocationCondition(countries=["US", "CA"])]
        ... )
        >>>
        >>> # DENY policy: block specific countries
        >>> policy = ExternalAgentPolicy(
        ...     effect=PolicyEffect.DENY,
        ...     conditions=[LocationCondition(countries=["CN", "RU"])]
        ... )
    """

    def __init__(
        self,
        countries: list[str] | None = None,
        ips: list[str] | None = None,
        allowed_countries: list[str] | None = None,  # Deprecated
        blocked_countries: list[str] | None = None,  # Deprecated
        allowed_ips: list[str] | None = None,  # Deprecated
        blocked_ips: list[str] | None = None,  # Deprecated
    ):
        """
        Initialize location condition.

        Args:
            countries: List of country codes to match (ISO 3166-1 alpha-2)
            ips: List of IP addresses/ranges to match
            allowed_countries: (Deprecated) Use countries with ALLOW policy
            blocked_countries: (Deprecated) Use countries with DENY policy
            allowed_ips: (Deprecated) Use ips with ALLOW policy
            blocked_ips: (Deprecated) Use ips with DENY policy
        """
        # Handle deprecated parameters
        if allowed_countries is not None:
            self.countries = allowed_countries
        elif blocked_countries is not None:
            self.countries = blocked_countries
        else:
            self.countries = countries or []

        if allowed_ips is not None:
            self.ips = allowed_ips
        elif blocked_ips is not None:
            self.ips = blocked_ips
        else:
            self.ips = ips or []

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate location condition.

        Args:
            context: Policy evaluation context

        Returns:
            True if location matches, False otherwise
        """
        # If both filters are empty, match all
        if not self.countries and not self.ips:
            return True

        # Check IP match
        ip_address = context.principal.ip_address
        if self.ips and ip_address:
            if ip_address in self.ips:
                return True
            # If IPs specified but no match, fail
            if self.countries:
                # Continue to country check
                pass
            else:
                return False

        # Check country match
        country = context.principal.location.get("country")
        if self.countries and country:
            return country in self.countries

        # No match
        return False


class EnvironmentCondition(PolicyCondition):
    """
    Environment-based policy condition.

    Supports:
    - Environment matching (environment in specified list)

    Note: Use with ALLOW policies for allowlisting, DENY policies for blocklisting.

    Examples:
        >>> # ALLOW policy: production only
        >>> policy = ExternalAgentPolicy(
        ...     effect=PolicyEffect.ALLOW,
        ...     conditions=[EnvironmentCondition(environments=["production"])]
        ... )
        >>>
        >>> # DENY policy: block development
        >>> policy = ExternalAgentPolicy(
        ...     effect=PolicyEffect.DENY,
        ...     conditions=[EnvironmentCondition(environments=["development"])]
        ... )
    """

    def __init__(
        self,
        environments: list[str] | None = None,
        allowed_environments: list[str] | None = None,  # Deprecated
        blocked_environments: list[str] | None = None,  # Deprecated
    ):
        """
        Initialize environment condition.

        Args:
            environments: List of environments to match
            allowed_environments: (Deprecated) Use environments with ALLOW policy
            blocked_environments: (Deprecated) Use environments with DENY policy
        """
        # Handle deprecated parameters
        if allowed_environments is not None:
            self.environments = allowed_environments
        elif blocked_environments is not None:
            self.environments = blocked_environments
        else:
            self.environments = environments or []

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate environment condition.

        Args:
            context: Policy evaluation context

        Returns:
            True if environment matches, False otherwise
        """
        environment = context.principal.environment

        if not self.environments:
            # No environment filter = matches all
            return True

        # Condition is satisfied if environment is in the list
        return environment in self.environments


class ProviderCondition(PolicyCondition):
    """
    Provider-based policy condition.

    Supports:
    - Provider matching (provider in specified list)

    Note: Use with ALLOW policies for allowlisting, DENY policies for blocklisting.

    Examples:
        >>> # ALLOW policy: only allow Copilot Studio
        >>> policy = ExternalAgentPolicy(
        ...     effect=PolicyEffect.ALLOW,
        ...     conditions=[ProviderCondition(providers=["copilot_studio"])]
        ... )
        >>>
        >>> # DENY policy: block third-party agents
        >>> policy = ExternalAgentPolicy(
        ...     effect=PolicyEffect.DENY,
        ...     conditions=[ProviderCondition(providers=["third_party_agent"])]
        ... )
    """

    def __init__(
        self,
        providers: list[str] | None = None,
        allowed_providers: list[str] | None = None,  # Deprecated, use providers
        blocked_providers: (list[str] | None) = None,  # Deprecated, use providers with DENY policy
    ):
        """
        Initialize provider condition.

        Args:
            providers: List of provider types to match
            allowed_providers: (Deprecated) Use providers with ALLOW policy
            blocked_providers: (Deprecated) Use providers with DENY policy
        """
        # Handle deprecated parameters
        if allowed_providers is not None:
            self.providers = allowed_providers
        elif blocked_providers is not None:
            self.providers = blocked_providers
        else:
            self.providers = providers or []

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate provider condition.

        Args:
            context: Policy evaluation context

        Returns:
            True if provider matches, False otherwise
        """
        provider = context.principal.provider

        if not self.providers:
            # No provider filter = matches all
            return True

        # Condition is satisfied if provider is in the list
        return provider in self.providers


class TagCondition(PolicyCondition):
    """
    Tag-based policy condition.

    Supports:
    - Required tags (agent must have all specified tags)
    - Blocked tags (agent must not have any specified tags)

    Examples:
        >>> # Require "approved" tag
        >>> condition = TagCondition(required_tags=["approved"])
        >>>
        >>> # Block "experimental" tag
        >>> condition = TagCondition(blocked_tags=["experimental"])
    """

    def __init__(
        self,
        required_tags: list[str] | None = None,
        blocked_tags: list[str] | None = None,
    ):
        """
        Initialize tag condition.

        Args:
            required_tags: List of tags that must be present
            blocked_tags: List of tags that must not be present
        """
        self.required_tags = required_tags or []
        self.blocked_tags = blocked_tags or []

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate tag condition.

        Args:
            context: Policy evaluation context

        Returns:
            True if tags satisfy condition, False otherwise
        """
        agent_tags = set(context.principal.tags)

        # Check blocked tags (any blocked tag present = fail)
        if self.blocked_tags:
            if any(tag in agent_tags for tag in self.blocked_tags):
                return False

        # Check required tags (all required tags must be present)
        if self.required_tags:
            if not all(tag in agent_tags for tag in self.required_tags):
                return False

        return True


@dataclass
class ExternalAgentPolicy:
    """
    External agent policy definition.

    Attributes:
        policy_id: Unique policy identifier
        name: Human-readable policy name
        effect: Policy effect (ALLOW or DENY)
        conditions: List of conditions that must ALL be satisfied
        priority: Priority for conflict resolution (lower = higher priority)
        description: Optional policy description
        enabled: Whether policy is active
    """

    policy_id: str
    name: str
    effect: PolicyEffect
    conditions: list[PolicyCondition] = field(default_factory=list)
    priority: int = 100
    description: str | None = None
    enabled: bool = True


class ExternalAgentPolicyEngine:
    """
    Policy engine for external agent access control.

    Evaluates policies using Attribute-Based Access Control (ABAC) model.
    Supports multiple conflict resolution strategies.

    Examples:
        >>> engine = ExternalAgentPolicyEngine()
        >>>
        >>> # Create policy
        >>> policy = ExternalAgentPolicy(
        ...     policy_id="allow_copilot_prod",
        ...     name="Allow Copilot in Production",
        ...     effect=PolicyEffect.ALLOW,
        ...     conditions=[
        ...         ProviderCondition(allowed_providers=["copilot_studio"]),
        ...         EnvironmentCondition(allowed_environments=["production"])
        ...     ],
        ...     priority=1
        ... )
        >>> engine.add_policy(policy)
        >>>
        >>> # Evaluate policy
        >>> context = ExternalAgentPolicyContext(
        ...     principal=ExternalAgentPrincipal(
        ...         external_agent_id="copilot_hr",
        ...         provider="copilot_studio",
        ...         environment="production"
        ...     ),
        ...     action="invoke",
        ...     resource="copilot_hr"
        ... )
        >>> result = await engine.evaluate_policies(context)
        >>> result.effect
        PolicyEffect.ALLOW
    """

    def __init__(
        self,
        runtime: Any | None = None,
        db: Any | None = None,
        conflict_resolution_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.DENY_OVERRIDES,
        cache_ttl_seconds: int = 60,
    ):
        """
        Initialize policy engine.

        Args:
            runtime: AsyncLocalRuntime for workflow execution
            db: Optional DataFlow instance for persistence
            conflict_resolution_strategy: Strategy for resolving conflicting policies
            cache_ttl_seconds: Policy cache TTL in seconds
        """
        self.runtime = runtime
        self.db = db
        self.conflict_resolution_strategy = conflict_resolution_strategy
        self.cache_ttl_seconds = cache_ttl_seconds

        # In-memory policy cache
        self.policies: dict[str, ExternalAgentPolicy] = {}
        self._cache_timestamp: datetime | None = None

    def add_policy(self, policy: ExternalAgentPolicy) -> None:
        """
        Add policy to engine.

        Args:
            policy: Policy to add
        """
        self.policies[policy.policy_id] = policy
        logger.info(f"Policy added: {policy.policy_id} ({policy.name})")

    def remove_policy(self, policy_id: str) -> None:
        """
        Remove policy from engine.

        Args:
            policy_id: Policy identifier to remove
        """
        if policy_id in self.policies:
            del self.policies[policy_id]
            logger.info(f"Policy removed: {policy_id}")

    async def evaluate_policies(self, context: ExternalAgentPolicyContext) -> PolicyEvaluationResult:
        """
        Evaluate all applicable policies against context.

        Args:
            context: Policy evaluation context

        Returns:
            PolicyEvaluationResult with final decision

        Examples:
            >>> context = ExternalAgentPolicyContext(
            ...     principal=ExternalAgentPrincipal(
            ...         external_agent_id="test",
            ...         provider="copilot_studio"
            ...     ),
            ...     action="invoke",
            ...     resource="test"
            ... )
            >>> result = await engine.evaluate_policies(context)
        """
        import time

        start_time = time.time()

        # Filter enabled policies
        enabled_policies = [p for p in self.policies.values() if p.enabled]

        # Sort by priority (lower number = higher priority)
        enabled_policies.sort(key=lambda p: p.priority)

        matched_allow_policies = []
        matched_deny_policies = []

        # Evaluate each policy
        for policy in enabled_policies:
            if self._evaluate_policy(policy, context):
                if policy.effect == PolicyEffect.ALLOW:
                    matched_allow_policies.append(policy.policy_id)
                else:
                    matched_deny_policies.append(policy.policy_id)

                # Short-circuit for first_applicable strategy
                if self.conflict_resolution_strategy == ConflictResolutionStrategy.FIRST_APPLICABLE:
                    effect = policy.effect
                    reason = f"First applicable policy: {policy.name}"
                    matched_policies = [policy.policy_id]
                    break
        else:
            # Apply conflict resolution strategy
            effect, reason, matched_policies = self._resolve_conflicts(matched_allow_policies, matched_deny_policies)

        # Calculate evaluation time
        evaluation_time_ms = (time.time() - start_time) * 1000

        result = PolicyEvaluationResult(
            effect=effect,
            reason=reason,
            matched_policies=matched_policies,
            evaluation_time_ms=evaluation_time_ms,
            metadata={
                "strategy": self.conflict_resolution_strategy.value,
                "total_policies": len(enabled_policies),
                "allow_policies": len(matched_allow_policies),
                "deny_policies": len(matched_deny_policies),
            },
        )

        # Log evaluation
        logger.info(
            f"Policy evaluation: {effect.value} - {reason} "
            f"(matched: {len(matched_policies)}, time: {evaluation_time_ms:.2f}ms)"
        )

        return result

    def _evaluate_policy(self, policy: ExternalAgentPolicy, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate single policy against context.

        Args:
            policy: Policy to evaluate
            context: Evaluation context

        Returns:
            True if all conditions are satisfied, False otherwise
        """
        if not policy.conditions:
            # Policy with no conditions always matches
            return True

        # All conditions must be satisfied (AND logic)
        for condition in policy.conditions:
            try:
                if not condition.evaluate(context):
                    return False
            except Exception as e:
                logger.error(f"Error evaluating condition for policy {policy.policy_id}: {e}")
                return False

        return True

    def _resolve_conflicts(
        self, allow_policies: list[str], deny_policies: list[str]
    ) -> tuple[PolicyEffect, str, list[str]]:
        """
        Resolve conflicts between ALLOW and DENY policies.

        Args:
            allow_policies: List of policy IDs that returned ALLOW
            deny_policies: List of policy IDs that returned DENY

        Returns:
            Tuple of (effect, reason, matched_policies)
        """
        # Deny-by-default if no policies matched
        if not allow_policies and not deny_policies:
            return (
                PolicyEffect.DENY,
                "No matching policies (deny-by-default)",
                [],
            )

        # Apply conflict resolution strategy
        if self.conflict_resolution_strategy == ConflictResolutionStrategy.DENY_OVERRIDES:
            if deny_policies:
                return (
                    PolicyEffect.DENY,
                    f"Denied by policy (deny-overrides): {', '.join(deny_policies)}",
                    deny_policies + allow_policies,
                )
            else:
                return (
                    PolicyEffect.ALLOW,
                    f"Allowed by policy: {', '.join(allow_policies)}",
                    allow_policies,
                )

        elif self.conflict_resolution_strategy == ConflictResolutionStrategy.ALLOW_OVERRIDES:
            if allow_policies:
                return (
                    PolicyEffect.ALLOW,
                    f"Allowed by policy (allow-overrides): {', '.join(allow_policies)}",
                    allow_policies + deny_policies,
                )
            else:
                return (
                    PolicyEffect.DENY,
                    f"Denied by policy: {', '.join(deny_policies)}",
                    deny_policies,
                )

        else:
            # FIRST_APPLICABLE (should not reach here)
            return (
                PolicyEffect.DENY,
                "Invalid conflict resolution state",
                [],
            )


# Export all public types
__all__ = [
    "PolicyEffect",
    "ConflictResolutionStrategy",
    "ExternalAgentPrincipal",
    "ExternalAgentPolicyContext",
    "PolicyEvaluationResult",
    "PolicyCondition",
    "TimeWindowCondition",
    "LocationCondition",
    "EnvironmentCondition",
    "ProviderCondition",
    "TagCondition",
    "ExternalAgentPolicy",
    "ExternalAgentPolicyEngine",
]
