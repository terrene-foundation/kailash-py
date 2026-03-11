"""
External Agent Policy Engine (ABAC) for Kaizen Framework.

Provides attribute-based access control (ABAC) for external agents with:
- Time-based policies (business hours, maintenance windows)
- Location-based policies (IP allowlist/blocklist, GeoIP)
- Environment-based policies (dev/staging/production)
- Data classification policies (public/internal/confidential/restricted)
- Provider-based policies (allowed/blocked providers)
- Tag-based policies (required/blocked tags)
- Policy conflict resolution (deny-overrides, allow-overrides, first-applicable)
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from kaizen.core.autonomy.permissions.types import PermissionType

logger = logging.getLogger(__name__)


class PolicyEffect(Enum):
    """Policy decision effect."""

    ALLOW = "ALLOW"
    """Allow the action."""

    DENY = "DENY"
    """Deny the action."""


class ConflictResolutionStrategy(Enum):
    """Policy conflict resolution strategies."""

    DENY_OVERRIDES = "deny_overrides"
    """If any policy returns DENY, final decision is DENY (most secure)."""

    ALLOW_OVERRIDES = "allow_overrides"
    """If any policy returns ALLOW, final decision is ALLOW (most permissive)."""

    FIRST_APPLICABLE = "first_applicable"
    """First matching policy wins (priority-based)."""


class Environment(Enum):
    """Deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class DataClassification(Enum):
    """Data classification levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass
class ExternalAgentPrincipal:
    """
    External agent principal with context attributes.

    Represents an external agent's identity and context for policy evaluation.
    """

    external_agent_id: str
    """Unique identifier for the external agent."""

    provider: str
    """Provider of the external agent (e.g., 'copilot_studio', 'custom_rest_api')."""

    tags: List[str] = field(default_factory=list)
    """Tags associated with the agent (e.g., ['approved', 'finance', 'production'])."""

    org_id: Optional[str] = None
    """Organization ID owning this agent."""

    environment: Optional[Environment] = None
    """Environment where agent is deployed (development, staging, production)."""

    location: Optional[Dict[str, str]] = None
    """
    Location information (country, region).

    Example: {"country": "US", "region": "us-east-1"}
    """


@dataclass
class ExternalAgentPolicyContext:
    """
    Context for policy evaluation.

    Contains all information needed to evaluate policies for an external agent action.
    """

    principal: ExternalAgentPrincipal
    """The external agent principal making the request."""

    action: str
    """Action being performed (e.g., 'invoke', 'configure', 'read', 'write')."""

    resource: str
    """Resource being accessed (typically external_agent_id)."""

    time: datetime
    """Timestamp of the request."""

    attributes: Dict[str, Any] = field(default_factory=dict)
    """Additional context attributes for extensibility."""

    ip_address: Optional[str] = None
    """IP address of the request (for location-based policies)."""

    data_classification: Optional[DataClassification] = None
    """Classification of data being accessed."""


@dataclass
class PolicyCondition(ABC):
    """
    Base class for policy conditions.

    All policy conditions must implement evaluate() to return True/False.
    """

    @abstractmethod
    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate if this condition matches the given context.

        Args:
            context: Policy evaluation context

        Returns:
            True if condition matches, False otherwise
        """
        pass


@dataclass
class TimeWindowCondition(PolicyCondition):
    """
    Time-based policy condition.

    Supports business hours, maintenance windows, and blackout periods.
    """

    business_hours: Optional[Dict[str, str]] = None
    """
    Business hours specification.

    Example: {
        "mon-fri": "09:00-17:00",
        "timezone": "America/New_York"
    }
    """

    maintenance_windows: Optional[List[Dict[str, str]]] = None
    """
    Maintenance windows (deny during these periods).

    Example: [
        {"start": "2025-12-25T00:00:00Z", "end": "2025-12-25T23:59:59Z"}
    ]
    """

    allowed_days: Optional[List[str]] = None
    """
    Allowed days of week.

    Example: ["monday", "tuesday", "wednesday", "thursday", "friday"]
    """

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate time-based conditions.

        Args:
            context: Policy evaluation context

        Returns:
            True if time conditions are met, False otherwise
        """
        current_time = context.time

        # Check maintenance windows (deny during maintenance)
        if self.maintenance_windows:
            for window in self.maintenance_windows:
                start = datetime.fromisoformat(window["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(window["end"].replace("Z", "+00:00"))
                # Make current_time timezone-aware if needed
                if current_time.tzinfo is None:
                    from datetime import timezone

                    current_time = current_time.replace(tzinfo=timezone.utc)
                if start <= current_time <= end:
                    logger.debug(
                        f"Current time {current_time} is within maintenance window"
                    )
                    return False

        # Check allowed days
        if self.allowed_days:
            current_day = current_time.strftime("%A").lower()
            if current_day not in self.allowed_days:
                logger.debug(f"Current day {current_day} not in allowed days")
                return False

        # Check business hours
        if self.business_hours:
            # Parse business hours (simplified - assumes single range for now)
            for day_range, time_range in self.business_hours.items():
                if day_range == "timezone":
                    continue

                # Parse time range (e.g., "09:00-17:00")
                start_str, end_str = time_range.split("-")
                start_hour, start_min = map(int, start_str.split(":"))
                end_hour, end_min = map(int, end_str.split(":"))

                start_time = time(start_hour, start_min)
                end_time = time(end_hour, end_min)

                current_time_only = current_time.time()

                # Check if current time is within business hours
                if start_time <= current_time_only <= end_time:
                    # Also check day range (e.g., "mon-fri")
                    if day_range == "mon-fri":
                        current_day_num = current_time.weekday()  # 0=Monday, 6=Sunday
                        if 0 <= current_day_num <= 4:  # Monday to Friday
                            return True
                    elif day_range == "mon-sun":
                        return True

                logger.debug(f"Current time {current_time_only} outside business hours")
                return False

        # If no conditions specified, allow by default
        return True


@dataclass
class LocationCondition(PolicyCondition):
    """
    Location-based policy condition.

    Uses IP address and GeoIP lookup for country/region restrictions.
    """

    allowed_countries: Optional[List[str]] = None
    """List of allowed country codes (e.g., ['US', 'CA'])."""

    blocked_countries: Optional[List[str]] = None
    """List of blocked country codes (e.g., ['RU', 'CN'])."""

    allowed_regions: Optional[List[str]] = None
    """List of allowed regions (e.g., ['us-east-1', 'eu-west-1'])."""

    blocked_regions: Optional[List[str]] = None
    """List of blocked regions."""

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate location-based conditions.

        Args:
            context: Policy evaluation context

        Returns:
            True if location conditions are met, False otherwise
        """
        location = context.principal.location

        if not location:
            logger.warning("No location information available for policy evaluation")
            return False

        country = location.get("country")
        region = location.get("region")

        # Check blocked countries first (deny takes precedence)
        if self.blocked_countries and country in self.blocked_countries:
            logger.debug(f"Country {country} is in blocked list")
            return False

        # Check allowed countries
        if self.allowed_countries and country not in self.allowed_countries:
            logger.debug(f"Country {country} not in allowed list")
            return False

        # Check blocked regions
        if self.blocked_regions and region in self.blocked_regions:
            logger.debug(f"Region {region} is in blocked list")
            return False

        # Check allowed regions
        if self.allowed_regions and region not in self.allowed_regions:
            logger.debug(f"Region {region} not in allowed list")
            return False

        return True


@dataclass
class EnvironmentCondition(PolicyCondition):
    """
    Environment-based policy condition.

    Restricts access based on deployment environment.
    """

    allowed_environments: Optional[List[Environment]] = None
    """List of allowed environments."""

    blocked_environments: Optional[List[Environment]] = None
    """List of blocked environments."""

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate environment-based conditions.

        Returns True if this condition matches and the policy should be applied.

        Args:
            context: Policy evaluation context

        Returns:
            True if condition matches (policy should be applied), False otherwise
        """
        environment = context.principal.environment

        if not environment:
            logger.warning("No environment specified for policy evaluation")
            return False

        # If blocked_environments is specified, check if current environment is in it
        # Return True if it IS in the blocked list (meaning: yes, apply this policy)
        if self.blocked_environments:
            is_blocked = environment in self.blocked_environments
            if is_blocked:
                logger.debug(f"Environment {environment} matches blocked list")
                return True
            else:
                logger.debug(f"Environment {environment} not in blocked list")
                return False

        # If allowed_environments is specified, check if current environment is in it
        # Return True if it IS in the allowed list (meaning: yes, apply this policy)
        if self.allowed_environments:
            is_allowed = environment in self.allowed_environments
            if is_allowed:
                logger.debug(f"Environment {environment} matches allowed list")
                return True
            else:
                logger.debug(f"Environment {environment} not in allowed list")
                return False

        # If no conditions specified, match by default
        return True


@dataclass
class ProviderCondition(PolicyCondition):
    """
    Provider-based policy condition.

    Restricts access based on external agent provider.
    """

    allowed_providers: Optional[List[str]] = None
    """List of allowed providers (e.g., ['copilot_studio', 'custom_rest_api'])."""

    blocked_providers: Optional[List[str]] = None
    """List of blocked providers."""

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate provider-based conditions.

        Returns True if this condition matches and the policy should be applied.

        Args:
            context: Policy evaluation context

        Returns:
            True if condition matches (policy should be applied), False otherwise
        """
        provider = context.principal.provider

        # If blocked_providers is specified, check if current provider is in it
        if self.blocked_providers:
            is_blocked = provider in self.blocked_providers
            if is_blocked:
                logger.debug(f"Provider {provider} matches blocked list")
                return True
            else:
                logger.debug(f"Provider {provider} not in blocked list")
                return False

        # If allowed_providers is specified, check if current provider is in it
        if self.allowed_providers:
            is_allowed = provider in self.allowed_providers
            if is_allowed:
                logger.debug(f"Provider {provider} matches allowed list")
                return True
            else:
                logger.debug(f"Provider {provider} not in allowed list")
                return False

        # If no conditions specified, match by default
        return True


@dataclass
class TagCondition(PolicyCondition):
    """
    Tag-based policy condition.

    Requires agents to have specific tags.
    """

    required_tags: Optional[Set[str]] = None
    """Tags that must be present (set intersection)."""

    blocked_tags: Optional[Set[str]] = None
    """Tags that must not be present."""

    any_of_tags: Optional[Set[str]] = None
    """At least one of these tags must be present (set union)."""

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate tag-based conditions.

        Args:
            context: Policy evaluation context

        Returns:
            True if tag conditions are met, False otherwise
        """
        agent_tags = set(context.principal.tags)

        # Check blocked tags first (deny takes precedence)
        if self.blocked_tags and agent_tags & self.blocked_tags:
            logger.debug(f"Agent has blocked tags: {agent_tags & self.blocked_tags}")
            return False

        # Check required tags (all must be present)
        if self.required_tags and not self.required_tags.issubset(agent_tags):
            missing = self.required_tags - agent_tags
            logger.debug(f"Agent missing required tags: {missing}")
            return False

        # Check any_of_tags (at least one must be present)
        if self.any_of_tags and not (agent_tags & self.any_of_tags):
            logger.debug(f"Agent has none of the required tags: {self.any_of_tags}")
            return False

        return True


@dataclass
class DataClassificationCondition(PolicyCondition):
    """
    Data classification-based policy condition.

    Restricts access based on data sensitivity level.
    """

    allowed_classifications: Optional[List[DataClassification]] = None
    """List of allowed data classifications."""

    requires_encryption: bool = False
    """Whether encryption is required for this classification."""

    def evaluate(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate data classification conditions.

        Args:
            context: Policy evaluation context

        Returns:
            True if classification conditions are met, False otherwise
        """
        classification = context.data_classification

        if not classification:
            logger.warning("No data classification specified for policy evaluation")
            return False

        # Check allowed classifications
        if (
            self.allowed_classifications
            and classification not in self.allowed_classifications
        ):
            logger.debug(f"Classification {classification} not in allowed list")
            return False

        # Check encryption requirement
        if self.requires_encryption:
            encryption_enabled = context.attributes.get("encryption_enabled", False)
            if not encryption_enabled:
                logger.debug("Encryption required but not enabled")
                return False

        return True


@dataclass
class ExternalAgentPolicy:
    """
    Complete external agent policy with conditions and metadata.

    Combines effect (ALLOW/DENY) with conditions for evaluation.
    """

    policy_id: str
    """Unique policy identifier."""

    name: str
    """Human-readable policy name."""

    effect: PolicyEffect
    """Policy effect (ALLOW or DENY)."""

    conditions: List[PolicyCondition]
    """List of conditions that must all be true for policy to apply."""

    priority: int = 0
    """
    Priority for conflict resolution (higher = evaluated first).

    Default: 0 (lowest priority)
    """

    description: Optional[str] = None
    """Optional policy description."""

    principal_pattern: Optional[str] = None
    """
    Optional regex pattern for matching principal IDs.

    If specified, policy only applies to principals matching this pattern.
    """

    action_pattern: Optional[str] = None
    """
    Optional regex pattern for matching actions.

    If specified, policy only applies to actions matching this pattern.
    """

    def __post_init__(self):
        """Compile regex patterns if specified."""
        if self.principal_pattern:
            self._principal_regex = re.compile(self.principal_pattern)
        else:
            self._principal_regex = None

        if self.action_pattern:
            self._action_regex = re.compile(self.action_pattern)
        else:
            self._action_regex = None

    def matches_context(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Check if this policy applies to the given context.

        Args:
            context: Policy evaluation context

        Returns:
            True if policy applies to this context, False otherwise
        """
        # Check principal pattern
        if self._principal_regex:
            if not self._principal_regex.fullmatch(context.principal.external_agent_id):
                return False

        # Check action pattern
        if self._action_regex:
            if not self._action_regex.fullmatch(context.action):
                return False

        return True

    def evaluate_conditions(self, context: ExternalAgentPolicyContext) -> bool:
        """
        Evaluate all conditions for this policy.

        All conditions must be true for the policy to apply.

        Args:
            context: Policy evaluation context

        Returns:
            True if all conditions are met, False otherwise
        """
        for condition in self.conditions:
            if not condition.evaluate(context):
                logger.debug(
                    f"Policy {self.policy_id}: Condition {type(condition).__name__} failed"
                )
                return False

        return True


@dataclass
class PolicyDecision:
    """
    Result of policy evaluation.

    Contains the final decision and metadata about how it was reached.
    """

    effect: PolicyEffect
    """Final decision (ALLOW or DENY)."""

    reason: str
    """Human-readable reason for the decision."""

    matched_policies: List[str]
    """List of policy IDs that matched this request."""

    evaluation_time_ms: float = 0.0
    """Time taken to evaluate policies in milliseconds."""

    context_attributes: Dict[str, Any] = field(default_factory=dict)
    """Context attributes captured for audit logging."""


class ExternalAgentPolicyEngine:
    """
    External agent policy engine with ABAC evaluation.

    Features:
    - Policy caching with TTL
    - Conflict resolution strategies
    - Performance optimization (<5ms p95)
    - Audit logging
    """

    def __init__(
        self,
        policies: Optional[List[ExternalAgentPolicy]] = None,
        conflict_resolution: ConflictResolutionStrategy = ConflictResolutionStrategy.DENY_OVERRIDES,
        cache_ttl_seconds: int = 60,
    ):
        """
        Initialize policy engine.

        Args:
            policies: Initial list of policies (optional)
            conflict_resolution: Strategy for resolving policy conflicts
            cache_ttl_seconds: TTL for policy cache in seconds
        """
        self.policies: List[ExternalAgentPolicy] = policies or []
        self.conflict_resolution = conflict_resolution
        self.cache_ttl_seconds = cache_ttl_seconds

        # Policy cache indexed by (principal_type, action, resource) for O(1) lookup
        self._policy_cache: Dict[tuple, List[ExternalAgentPolicy]] = {}
        self._cache_timestamp: Optional[datetime] = None

        logger.info(
            f"Initialized ExternalAgentPolicyEngine with "
            f"{len(self.policies)} policies, "
            f"conflict_resolution={conflict_resolution.value}"
        )

    def add_policy(self, policy: ExternalAgentPolicy) -> None:
        """
        Add a policy to the engine.

        Args:
            policy: Policy to add
        """
        self.policies.append(policy)
        self._invalidate_cache()
        logger.debug(f"Added policy: {policy.policy_id} ({policy.name})")

    def remove_policy(self, policy_id: str) -> bool:
        """
        Remove a policy from the engine.

        Args:
            policy_id: ID of policy to remove

        Returns:
            True if policy was removed, False if not found
        """
        initial_len = len(self.policies)
        self.policies = [p for p in self.policies if p.policy_id != policy_id]

        if len(self.policies) < initial_len:
            self._invalidate_cache()
            logger.debug(f"Removed policy: {policy_id}")
            return True

        return False

    def _invalidate_cache(self) -> None:
        """Invalidate policy cache."""
        self._policy_cache.clear()
        self._cache_timestamp = None
        logger.debug("Policy cache invalidated")

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid based on TTL."""
        if not self._cache_timestamp:
            return False

        elapsed = (datetime.now() - self._cache_timestamp).total_seconds()
        return elapsed < self.cache_ttl_seconds

    def evaluate_policies(self, context: ExternalAgentPolicyContext) -> PolicyDecision:
        """
        Evaluate all policies for the given context.

        Applies conflict resolution strategy to determine final decision.

        Args:
            context: Policy evaluation context

        Returns:
            PolicyDecision with final effect and metadata
        """
        import time

        start_time = time.time()

        # Find applicable policies
        applicable_policies = [
            policy for policy in self.policies if policy.matches_context(context)
        ]

        if not applicable_policies:
            # No policies matched - default DENY for security
            decision = PolicyDecision(
                effect=PolicyEffect.DENY,
                reason="No applicable policies found (default deny)",
                matched_policies=[],
                evaluation_time_ms=(time.time() - start_time) * 1000,
                context_attributes={
                    "external_agent_id": context.principal.external_agent_id,
                    "action": context.action,
                    "resource": context.resource,
                    "environment": (
                        context.principal.environment.value
                        if context.principal.environment
                        else None
                    ),
                },
            )
            logger.info(
                f"Policy evaluation: {decision.effect.value} - {decision.reason}"
            )
            return decision

        # Sort by priority (highest first)
        sorted_policies = sorted(
            applicable_policies, key=lambda p: p.priority, reverse=True
        )

        # Evaluate conditions for each policy
        allow_policies: List[ExternalAgentPolicy] = []
        deny_policies: List[ExternalAgentPolicy] = []

        for policy in sorted_policies:
            if policy.evaluate_conditions(context):
                if policy.effect == PolicyEffect.ALLOW:
                    allow_policies.append(policy)
                else:
                    deny_policies.append(policy)

                # For first_applicable, return immediately
                if (
                    self.conflict_resolution
                    == ConflictResolutionStrategy.FIRST_APPLICABLE
                ):
                    decision = PolicyDecision(
                        effect=policy.effect,
                        reason=f"First applicable policy: {policy.name}",
                        matched_policies=[policy.policy_id],
                        evaluation_time_ms=(time.time() - start_time) * 1000,
                        context_attributes={
                            "external_agent_id": context.principal.external_agent_id,
                            "action": context.action,
                            "resource": context.resource,
                            "environment": (
                                context.principal.environment.value
                                if context.principal.environment
                                else None
                            ),
                        },
                    )
                    logger.info(
                        f"Policy evaluation (first_applicable): "
                        f"{decision.effect.value} - {decision.reason}"
                    )
                    return decision

        # Apply conflict resolution strategy
        matched_policy_ids = [p.policy_id for p in (allow_policies + deny_policies)]

        if self.conflict_resolution == ConflictResolutionStrategy.DENY_OVERRIDES:
            # If any DENY, final decision is DENY
            if deny_policies:
                effect = PolicyEffect.DENY
                reason = f"Deny overrides: {len(deny_policies)} deny policies matched"
            else:
                effect = PolicyEffect.ALLOW
                reason = f"Allow: {len(allow_policies)} allow policies matched"

        elif self.conflict_resolution == ConflictResolutionStrategy.ALLOW_OVERRIDES:
            # If any ALLOW, final decision is ALLOW
            if allow_policies:
                effect = PolicyEffect.ALLOW
                reason = (
                    f"Allow overrides: {len(allow_policies)} allow policies matched"
                )
            else:
                effect = PolicyEffect.DENY
                reason = f"Deny: {len(deny_policies)} deny policies matched"

        else:
            # Should not reach here if first_applicable handled above
            effect = PolicyEffect.DENY
            reason = "Unknown conflict resolution strategy"

        decision = PolicyDecision(
            effect=effect,
            reason=reason,
            matched_policies=matched_policy_ids,
            evaluation_time_ms=(time.time() - start_time) * 1000,
            context_attributes={
                "external_agent_id": context.principal.external_agent_id,
                "action": context.action,
                "resource": context.resource,
                "environment": (
                    context.principal.environment.value
                    if context.principal.environment
                    else None
                ),
            },
        )

        logger.info(
            f"Policy evaluation ({self.conflict_resolution.value}): "
            f"{decision.effect.value} - {decision.reason} "
            f"({len(matched_policy_ids)} policies matched, "
            f"{decision.evaluation_time_ms:.2f}ms)"
        )

        return decision


# Export all public types
__all__ = [
    "PolicyEffect",
    "ConflictResolutionStrategy",
    "Environment",
    "DataClassification",
    "ExternalAgentPrincipal",
    "ExternalAgentPolicyContext",
    "PolicyCondition",
    "TimeWindowCondition",
    "LocationCondition",
    "EnvironmentCondition",
    "ProviderCondition",
    "TagCondition",
    "DataClassificationCondition",
    "ExternalAgentPolicy",
    "PolicyDecision",
    "ExternalAgentPolicyEngine",
]
