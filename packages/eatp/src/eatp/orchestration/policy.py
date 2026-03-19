# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Trust Policy Engine - Evaluate trust policies during orchestration.

The TrustPolicyEngine evaluates policies before agent actions in
orchestrated workflows, ensuring compliance with trust requirements.

Policy Types:
- REQUIRE_GENESIS: Agent must have established trust chain
- REQUIRE_CAPABILITY: Agent must have specific capability
- ENFORCE_CONSTRAINT: Agent must satisfy constraint
- REQUIRE_DELEGATION: Agent must have valid delegation from parent
- VERIFY_CHAIN_INTEGRITY: Trust chain must be cryptographically valid

Example:
    from eatp.orchestration.policy import (
        TrustPolicy,
        PolicyType,
        TrustPolicyEngine,
    )

    # Create policies
    require_genesis = TrustPolicy.require_genesis()
    require_analyze = TrustPolicy.require_capability("analyze_data")

    # Combine policies
    combined = require_genesis.and_(require_analyze)

    # Create engine
    engine = TrustPolicyEngine(trust_operations=trust_ops)
    engine.register_policy(combined)

    # Evaluate before action
    result = await engine.evaluate_for_agent("agent-001", context)
    if not result.allowed:
        raise PolicyViolationError(result.policy_name, "agent-001", result.reason)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from eatp.orchestration.exceptions import PolicyViolationError
from eatp.orchestration.execution_context import TrustExecutionContext

logger = logging.getLogger(__name__)


class PolicyType(str, Enum):
    """Types of trust policies."""

    REQUIRE_GENESIS = "require_genesis"
    REQUIRE_CAPABILITY = "require_capability"
    ENFORCE_CONSTRAINT = "enforce_constraint"
    REQUIRE_DELEGATION = "require_delegation"
    VERIFY_CHAIN_INTEGRITY = "verify_chain_integrity"
    CUSTOM = "custom"


@dataclass
class PolicyResult:
    """Result of policy evaluation."""

    allowed: bool
    policy_name: str
    reason: str = ""
    evaluation_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(cls, policy_name: str, reason: str = "Policy passed") -> "PolicyResult":
        """Create an allow result."""
        return cls(allowed=True, policy_name=policy_name, reason=reason)

    @classmethod
    def deny(cls, policy_name: str, reason: str) -> "PolicyResult":
        """Create a deny result."""
        return cls(allowed=False, policy_name=policy_name, reason=reason)


# Type alias for policy evaluator function
PolicyEvaluator = Callable[
    [str, Optional[TrustExecutionContext], Any],
    Coroutine[Any, Any, PolicyResult],
]


@dataclass
class TrustPolicy:
    """
    Trust policy definition.

    Policies can be combined using AND, OR, NOT operations to create
    complex policy compositions.

    Attributes:
        policy_type: Type of policy
        policy_name: Human-readable policy name
        policy_config: Configuration for the policy
        evaluator: Async function that evaluates the policy
        required: If True, policy must pass for execution
    """

    policy_type: PolicyType
    policy_name: str
    policy_config: Dict[str, Any] = field(default_factory=dict)
    evaluator: Optional[PolicyEvaluator] = None
    required: bool = True
    _composed_policies: List["TrustPolicy"] = field(default_factory=list)
    _composition_type: Optional[str] = None  # "and", "or", "not"

    @classmethod
    def require_genesis(cls, policy_name: str = "require_genesis") -> "TrustPolicy":
        """Create policy requiring agent to have established trust chain."""
        return cls(
            policy_type=PolicyType.REQUIRE_GENESIS,
            policy_name=policy_name,
            policy_config={},
        )

    @classmethod
    def require_capability(
        cls,
        capability: str,
        policy_name: Optional[str] = None,
    ) -> "TrustPolicy":
        """Create policy requiring agent to have specific capability."""
        return cls(
            policy_type=PolicyType.REQUIRE_CAPABILITY,
            policy_name=policy_name or f"require_capability_{capability}",
            policy_config={"capability": capability},
        )

    @classmethod
    def enforce_constraint(
        cls,
        constraint_type: str,
        constraint_value: Any,
        policy_name: Optional[str] = None,
    ) -> "TrustPolicy":
        """Create policy enforcing a constraint."""
        return cls(
            policy_type=PolicyType.ENFORCE_CONSTRAINT,
            policy_name=policy_name or f"enforce_{constraint_type}",
            policy_config={
                "constraint_type": constraint_type,
                "constraint_value": constraint_value,
            },
        )

    @classmethod
    def require_delegation(
        cls,
        from_agent_id: str,
        policy_name: Optional[str] = None,
    ) -> "TrustPolicy":
        """Create policy requiring delegation from specific agent."""
        return cls(
            policy_type=PolicyType.REQUIRE_DELEGATION,
            policy_name=policy_name or f"require_delegation_from_{from_agent_id}",
            policy_config={"from_agent_id": from_agent_id},
        )

    @classmethod
    def verify_chain_integrity(
        cls,
        policy_name: str = "verify_chain_integrity",
    ) -> "TrustPolicy":
        """Create policy verifying trust chain cryptographic integrity."""
        return cls(
            policy_type=PolicyType.VERIFY_CHAIN_INTEGRITY,
            policy_name=policy_name,
            policy_config={},
        )

    @classmethod
    def custom(
        cls,
        policy_name: str,
        evaluator: PolicyEvaluator,
        config: Optional[Dict[str, Any]] = None,
    ) -> "TrustPolicy":
        """Create custom policy with user-defined evaluator."""
        return cls(
            policy_type=PolicyType.CUSTOM,
            policy_name=policy_name,
            policy_config=config or {},
            evaluator=evaluator,
        )

    def and_(self, other: "TrustPolicy") -> "TrustPolicy":
        """Combine with another policy using AND."""
        return TrustPolicy(
            policy_type=PolicyType.CUSTOM,
            policy_name=f"({self.policy_name} AND {other.policy_name})",
            _composed_policies=[self, other],
            _composition_type="and",
        )

    def or_(self, other: "TrustPolicy") -> "TrustPolicy":
        """Combine with another policy using OR."""
        return TrustPolicy(
            policy_type=PolicyType.CUSTOM,
            policy_name=f"({self.policy_name} OR {other.policy_name})",
            _composed_policies=[self, other],
            _composition_type="or",
        )

    def not_(self) -> "TrustPolicy":
        """Negate this policy."""
        return TrustPolicy(
            policy_type=PolicyType.CUSTOM,
            policy_name=f"NOT({self.policy_name})",
            _composed_policies=[self],
            _composition_type="not",
        )

    def is_composed(self) -> bool:
        """Check if this is a composed policy."""
        return len(self._composed_policies) > 0


@dataclass
class CacheEntry:
    """Cache entry for policy evaluation results."""

    result: PolicyResult
    expires_at: datetime


class TrustPolicyEngine:
    """
    Engine for evaluating trust policies.

    Features:
    - Policy registration and management
    - Result caching with configurable TTL
    - Batch policy evaluation
    - Built-in evaluators for standard policy types

    Example:
        engine = TrustPolicyEngine(trust_operations=trust_ops)
        engine.register_policy(TrustPolicy.require_genesis())

        result = await engine.evaluate_for_agent("agent-001", context)
        if not result.allowed:
            # Handle policy violation
            pass
    """

    def __init__(
        self,
        trust_operations: Any,
        cache_ttl_seconds: float = 300.0,  # 5 minutes
        enable_cache: bool = True,
    ):
        """
        Initialize the policy engine.

        Args:
            trust_operations: TrustOperations instance for verification
            cache_ttl_seconds: Cache TTL in seconds
            enable_cache: Whether to enable result caching
        """
        self._trust_ops = trust_operations
        self._cache_ttl = cache_ttl_seconds
        self._enable_cache = enable_cache
        self._policies: Dict[str, TrustPolicy] = {}
        self._cache: Dict[str, CacheEntry] = {}
        self._evaluation_count = 0
        self._cache_hits = 0

    def register_policy(self, policy: TrustPolicy) -> None:
        """Register a policy with the engine."""
        self._policies[policy.policy_name] = policy
        logger.debug(f"Registered policy: {policy.policy_name}")

    def unregister_policy(self, policy_name: str) -> bool:
        """Unregister a policy by name."""
        if policy_name in self._policies:
            del self._policies[policy_name]
            logger.debug(f"Unregistered policy: {policy_name}")
            return True
        return False

    def get_policy(self, policy_name: str) -> Optional[TrustPolicy]:
        """Get a registered policy by name."""
        return self._policies.get(policy_name)

    def list_policies(self) -> List[str]:
        """List all registered policy names."""
        return list(self._policies.keys())

    def clear_cache(self) -> int:
        """Clear the evaluation cache. Returns number of entries cleared."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "total_evaluations": self._evaluation_count,
            "cache_hits": self._cache_hits,
            "cache_entries": len(self._cache),
            "hit_rate": (self._cache_hits / self._evaluation_count if self._evaluation_count > 0 else 0.0),
        }

    async def evaluate_policy(
        self,
        policy: TrustPolicy,
        agent_id: str,
        context: Optional[TrustExecutionContext] = None,
    ) -> PolicyResult:
        """
        Evaluate a single policy for an agent.

        Args:
            policy: Policy to evaluate
            agent_id: Agent being evaluated
            context: Optional execution context

        Returns:
            PolicyResult with evaluation outcome
        """
        start_time = time.perf_counter()
        self._evaluation_count += 1

        # Check cache
        cache_key = f"{policy.policy_name}:{agent_id}:{context.context_id if context else 'none'}"
        if self._enable_cache:
            cached = self._cache.get(cache_key)
            if cached and cached.expires_at > datetime.now(timezone.utc):
                self._cache_hits += 1
                return cached.result

        # Evaluate policy
        if policy.is_composed():
            result = await self._evaluate_composed(policy, agent_id, context)
        elif policy.evaluator:
            result = await policy.evaluator(agent_id, context, self._trust_ops)
        else:
            result = await self._evaluate_builtin(policy, agent_id, context)

        # Record evaluation time
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        result.evaluation_time_ms = elapsed_ms

        # Cache result
        if self._enable_cache:
            self._cache[cache_key] = CacheEntry(
                result=result,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=self._cache_ttl),
            )

        return result

    async def evaluate_for_agent(
        self,
        agent_id: str,
        context: Optional[TrustExecutionContext] = None,
        policies: Optional[List[str]] = None,
    ) -> PolicyResult:
        """
        Evaluate all registered policies for an agent.

        Args:
            agent_id: Agent being evaluated
            context: Optional execution context
            policies: Specific policies to evaluate (None = all)

        Returns:
            Combined PolicyResult (all must pass)
        """
        start_time = time.perf_counter()

        policy_names = policies or list(self._policies.keys())
        if not policy_names:
            return PolicyResult.allow("no_policies", "No policies to evaluate")

        results = []
        for name in policy_names:
            policy = self._policies.get(name)
            if policy:
                result = await self.evaluate_policy(policy, agent_id, context)
                results.append(result)

                # Fail fast on required policy violation
                if not result.allowed and policy.required:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    return PolicyResult(
                        allowed=False,
                        policy_name=name,
                        reason=result.reason,
                        evaluation_time_ms=elapsed_ms,
                        metadata={"failed_policy": name},
                    )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return PolicyResult(
            allowed=True,
            policy_name="all_policies",
            reason=f"All {len(results)} policies passed",
            evaluation_time_ms=elapsed_ms,
            metadata={"evaluated_policies": policy_names},
        )

    async def _evaluate_composed(
        self,
        policy: TrustPolicy,
        agent_id: str,
        context: Optional[TrustExecutionContext],
    ) -> PolicyResult:
        """Evaluate a composed (AND/OR/NOT) policy."""
        if policy._composition_type == "and":
            for p in policy._composed_policies:
                result = await self.evaluate_policy(p, agent_id, context)
                if not result.allowed:
                    return PolicyResult.deny(
                        policy.policy_name,
                        f"AND composition failed: {result.reason}",
                    )
            return PolicyResult.allow(policy.policy_name, "All AND conditions passed")

        elif policy._composition_type == "or":
            reasons = []
            for p in policy._composed_policies:
                result = await self.evaluate_policy(p, agent_id, context)
                if result.allowed:
                    return PolicyResult.allow(
                        policy.policy_name,
                        f"OR condition passed: {p.policy_name}",
                    )
                reasons.append(result.reason)
            return PolicyResult.deny(
                policy.policy_name,
                f"No OR conditions passed: {'; '.join(reasons)}",
            )

        elif policy._composition_type == "not":
            result = await self.evaluate_policy(policy._composed_policies[0], agent_id, context)
            if result.allowed:
                return PolicyResult.deny(
                    policy.policy_name,
                    f"NOT condition failed: {result.reason}",
                )
            return PolicyResult.allow(policy.policy_name, "NOT condition passed")

        return PolicyResult.deny(
            policy.policy_name,
            f"Unknown composition type: {policy._composition_type}",
        )

    async def _evaluate_builtin(
        self,
        policy: TrustPolicy,
        agent_id: str,
        context: Optional[TrustExecutionContext],
    ) -> PolicyResult:
        """Evaluate a built-in policy type."""
        if policy.policy_type == PolicyType.REQUIRE_GENESIS:
            return await self._eval_require_genesis(policy, agent_id)

        elif policy.policy_type == PolicyType.REQUIRE_CAPABILITY:
            return await self._eval_require_capability(policy, agent_id, context)

        elif policy.policy_type == PolicyType.ENFORCE_CONSTRAINT:
            return await self._eval_enforce_constraint(policy, agent_id, context)

        elif policy.policy_type == PolicyType.REQUIRE_DELEGATION:
            return await self._eval_require_delegation(policy, agent_id, context)

        elif policy.policy_type == PolicyType.VERIFY_CHAIN_INTEGRITY:
            return await self._eval_verify_chain_integrity(policy, agent_id)

        return PolicyResult.deny(
            policy.policy_name,
            f"Unknown policy type: {policy.policy_type}",
        )

    async def _eval_require_genesis(
        self,
        policy: TrustPolicy,
        agent_id: str,
    ) -> PolicyResult:
        """Evaluate REQUIRE_GENESIS policy."""
        try:
            chain = await self._trust_ops.get_chain(agent_id)
            if chain is None:
                return PolicyResult.deny(
                    policy.policy_name,
                    f"Agent '{agent_id}' has no established trust chain",
                )
            return PolicyResult.allow(
                policy.policy_name,
                f"Agent '{agent_id}' has valid genesis",
            )
        except Exception as e:
            return PolicyResult.deny(
                policy.policy_name,
                f"Failed to verify genesis: {e}",
            )

    async def _eval_require_capability(
        self,
        policy: TrustPolicy,
        agent_id: str,
        context: Optional[TrustExecutionContext],
    ) -> PolicyResult:
        """Evaluate REQUIRE_CAPABILITY policy."""
        required_cap = policy.policy_config.get("capability")
        if not required_cap:
            return PolicyResult.deny(
                policy.policy_name,
                "No capability specified in policy config",
            )

        # Check context first (delegated capabilities)
        if context and context.has_capability(required_cap):
            return PolicyResult.allow(
                policy.policy_name,
                f"Capability '{required_cap}' found in execution context",
            )

        # Check trust chain
        try:
            chain = await self._trust_ops.get_chain(agent_id)
            if chain:
                for attestation in chain.capability_attestations:
                    if attestation.capability == required_cap:
                        # Check expiration
                        if attestation.expires_at and attestation.expires_at < datetime.now(timezone.utc):
                            continue
                        return PolicyResult.allow(
                            policy.policy_name,
                            f"Capability '{required_cap}' found in trust chain",
                        )
        except Exception as e:
            return PolicyResult.deny(
                policy.policy_name,
                f"Failed to check capabilities: {e}",
            )

        return PolicyResult.deny(
            policy.policy_name,
            f"Agent '{agent_id}' lacks capability '{required_cap}'",
        )

    async def _eval_enforce_constraint(
        self,
        policy: TrustPolicy,
        agent_id: str,
        context: Optional[TrustExecutionContext],
    ) -> PolicyResult:
        """Evaluate ENFORCE_CONSTRAINT policy."""
        constraint_type = policy.policy_config.get("constraint_type")
        required_value = policy.policy_config.get("constraint_value")

        if not constraint_type:
            return PolicyResult.deny(
                policy.policy_name,
                "No constraint_type specified in policy config",
            )

        if context is None:
            return PolicyResult.deny(
                policy.policy_name,
                "No execution context provided for constraint evaluation",
            )

        actual_value = context.get_constraint(constraint_type)
        if actual_value is None:
            return PolicyResult.deny(
                policy.policy_name,
                f"Constraint '{constraint_type}' not found in context",
            )

        # Compare constraint values
        if isinstance(required_value, (int, float)) and isinstance(actual_value, (int, float)):
            if actual_value > required_value:
                return PolicyResult.deny(
                    policy.policy_name,
                    f"Constraint '{constraint_type}' value {actual_value} exceeds limit {required_value}",
                )
        elif isinstance(required_value, (list, set)) and isinstance(actual_value, (list, set)):
            if not set(actual_value).issubset(set(required_value)):
                return PolicyResult.deny(
                    policy.policy_name,
                    f"Constraint '{constraint_type}' has values outside allowed set",
                )

        return PolicyResult.allow(
            policy.policy_name,
            f"Constraint '{constraint_type}' satisfied",
        )

    async def _eval_require_delegation(
        self,
        policy: TrustPolicy,
        agent_id: str,
        context: Optional[TrustExecutionContext],
    ) -> PolicyResult:
        """Evaluate REQUIRE_DELEGATION policy."""
        from_agent = policy.policy_config.get("from_agent_id")
        if not from_agent:
            return PolicyResult.deny(
                policy.policy_name,
                "No from_agent_id specified in policy config",
            )

        if context is None:
            return PolicyResult.deny(
                policy.policy_name,
                "No execution context provided for delegation check",
            )

        # Check delegation chain
        delegation_path = context.get_delegation_path()
        if from_agent in delegation_path:
            return PolicyResult.allow(
                policy.policy_name,
                f"Valid delegation from '{from_agent}' found in chain",
            )

        return PolicyResult.deny(
            policy.policy_name,
            f"No delegation from '{from_agent}' found in chain",
        )

    async def _eval_verify_chain_integrity(
        self,
        policy: TrustPolicy,
        agent_id: str,
    ) -> PolicyResult:
        """Evaluate VERIFY_CHAIN_INTEGRITY policy."""
        try:
            result = await self._trust_ops.verify(agent_id=agent_id)
            if result.valid:
                return PolicyResult.allow(
                    policy.policy_name,
                    "Trust chain integrity verified",
                )
            return PolicyResult.deny(
                policy.policy_name,
                f"Trust chain integrity check failed: {result.reason}",
            )
        except Exception as e:
            return PolicyResult.deny(
                policy.policy_name,
                f"Failed to verify chain integrity: {e}",
            )
