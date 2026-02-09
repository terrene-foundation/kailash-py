"""TrustVerifier for bridging Core SDK runtime to Kaizen TrustOperations (CARE-016).

This module provides the TrustVerifier class that enables trust-based verification
of workflow, node, and resource access in the Kailash runtime. It bridges to
Kaizen's TrustOperations when available, with graceful fallback behavior.

Design Principles:
    - Optional Kaizen integration (works standalone with fallback behavior)
    - Caching for performance (configurable TTL)
    - Three verification modes: DISABLED, PERMISSIVE, ENFORCING
    - High-risk node awareness for elevated verification
    - Audit trail for denied operations

Usage:
    from kailash.runtime.trust import TrustVerifier, TrustVerifierConfig

    # Basic usage with defaults (disabled mode)
    verifier = TrustVerifier()

    # With Kaizen backend
    from kaizen.trust.operations import TrustOperations
    verifier = TrustVerifier(
        kaizen_backend=TrustOperations(...),
        config=TrustVerifierConfig(mode="enforcing"),
    )

    # Verify access
    result = await verifier.verify_workflow_access(
        workflow_id="my-workflow",
        agent_id="agent-123",
        trust_context=RuntimeTrustContext(...),
    )
    if result.allowed:
        # Execute workflow
        pass

Version:
    Added in: v0.11.0
    Part of: CARE trust implementation (Phase 2)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from kailash.runtime.trust.context import RuntimeTrustContext, TrustVerificationMode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of a trust verification check.

    Represents the outcome of verifying whether an agent has permission
    to execute a workflow, node, or access a resource.

    Attributes:
        allowed: Whether the operation is allowed
        reason: Human-readable reason for the decision
        constraints: Any constraints that apply to the allowed operation
        capability_used: The capability that granted access (if any)
        trace_id: Trace ID for audit trail

    Example:
        >>> result = VerificationResult(allowed=True, reason="Access granted")
        >>> if result:  # Uses __bool__
        ...     print("Allowed!")
        Allowed!
    """

    allowed: bool
    reason: Optional[str] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    capability_used: Optional[str] = None
    trace_id: Optional[str] = None

    def __bool__(self) -> bool:
        """Allow using result directly in boolean context.

        Returns:
            True if allowed, False otherwise
        """
        return self.allowed

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary.

        Returns:
            Dictionary representation of the result
        """
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "constraints": self.constraints,
            "capability_used": self.capability_used,
            "trace_id": self.trace_id,
        }


@dataclass
class TrustVerifierConfig:
    """Configuration for TrustVerifier.

    Attributes:
        mode: Verification mode - "disabled", "permissive", or "enforcing"
        cache_enabled: Whether to cache verification results
        cache_ttl_seconds: Time-to-live for cached results in seconds
        fallback_allow: Whether to allow operations when verifier unavailable
        audit_denials: Whether to log denied operations
        high_risk_nodes: List of node types that require elevated verification

    Example:
        >>> config = TrustVerifierConfig(
        ...     mode="enforcing",
        ...     cache_ttl_seconds=120,
        ...     high_risk_nodes=["BashCommand", "FileWrite"],
        ... )
    """

    mode: str = "disabled"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 60
    fallback_allow: Optional[bool] = None  # None = mode-aware default (CARE-042)
    audit_denials: bool = True
    high_risk_nodes: List[str] = field(
        default_factory=lambda: [
            "BashCommand",
            "HttpRequest",
            "DatabaseQuery",
            "FileWrite",
            "CodeExecution",
            "PythonCode",
        ]
    )


class TrustVerifier:
    """Bridge between Core SDK runtime and Kaizen TrustOperations for verification.

    TrustVerifier provides a verification layer that can optionally integrate
    with Kaizen's TrustOperations to enforce trust policies on workflow,
    node, and resource access.

    Modes:
        - DISABLED: No verification, all operations allowed (default)
        - PERMISSIVE: Verify and log, but allow even if denied
        - ENFORCING: Block operations that fail verification

    Caching:
        Results are cached to avoid repeated backend calls. Cache entries
        expire after the configured TTL.

    Example:
        >>> verifier = TrustVerifier(
        ...     config=TrustVerifierConfig(mode="enforcing"),
        ... )
        >>> result = await verifier.verify_workflow_access(
        ...     workflow_id="my-workflow",
        ...     agent_id="agent-123",
        ... )
        >>> if result.allowed:
        ...     print("Access granted")
    """

    def __init__(
        self,
        kaizen_backend: Optional[Any] = None,
        config: Optional[TrustVerifierConfig] = None,
    ) -> None:
        """Initialize the TrustVerifier.

        Args:
            kaizen_backend: Optional Kaizen TrustOperations instance for verification
            config: Optional configuration (defaults to TrustVerifierConfig())
        """
        self._backend = kaizen_backend
        self._config = config or TrustVerifierConfig()
        self._cache: Dict[str, Tuple[VerificationResult, float]] = {}
        # ROUND6-001: Thread-safe access to _cache dict
        self._cache_lock = threading.Lock()
        self._mode = TrustVerificationMode(self._config.mode)

        # CARE-042: Mode-aware fallback default
        # In ENFORCING mode, fallback MUST deny (fail-closed) unless explicitly overridden
        if self._config.fallback_allow is None:
            self._effective_fallback_allow = (
                self._mode != TrustVerificationMode.ENFORCING
            )
        else:
            self._effective_fallback_allow = self._config.fallback_allow

    @property
    def is_enabled(self) -> bool:
        """Check if verification is enabled.

        Returns:
            True if mode is not DISABLED
        """
        return self._mode != TrustVerificationMode.DISABLED

    @property
    def is_enforcing(self) -> bool:
        """Check if verification is in enforcing mode.

        Returns:
            True if mode is ENFORCING
        """
        return self._mode == TrustVerificationMode.ENFORCING

    def clear_cache(self) -> None:
        """Clear all cached verification results."""
        # ROUND6-001: Thread-safe cache clear
        with self._cache_lock:
            self._cache.clear()

    def invalidate_agent(self, agent_id: str) -> int:
        """Invalidate all cached results for a specific agent (CARE-043).

        Call this when an agent is revoked to ensure revocation takes
        immediate effect without waiting for cache TTL expiry.

        Args:
            agent_id: The agent whose cache entries should be invalidated

        Returns:
            Number of cache entries removed
        """
        # ROUND6-001: Thread-safe cache invalidation
        with self._cache_lock:
            # CARE-058: Use null byte separator pattern matching
            keys_to_remove = [
                key for key in self._cache if key.endswith(f"\x00{agent_id}")
            ]
            for key in keys_to_remove:
                del self._cache[key]
        if keys_to_remove:
            logger.info(
                "Invalidated %d cache entries for revoked agent %s",
                len(keys_to_remove),
                agent_id,
            )
        return len(keys_to_remove)

    def invalidate_node(self, node_type: str) -> int:
        """Invalidate all cached results for a specific node type (CARE-043).

        Args:
            node_type: The node type whose cache entries should be invalidated

        Returns:
            Number of cache entries removed
        """
        # ROUND6-001: Thread-safe cache invalidation
        with self._cache_lock:
            # CARE-058: Use null byte separator pattern matching
            keys_to_remove = [
                key
                for key in self._cache
                if key.startswith("node\x00") and f"\x00{node_type}\x00" in key
            ]
            for key in keys_to_remove:
                del self._cache[key]
        return len(keys_to_remove)

    def _get_cached(self, cache_key: str) -> Optional[VerificationResult]:
        """Get a cached verification result.

        Args:
            cache_key: The cache key to look up

        Returns:
            Cached VerificationResult if found and not expired, None otherwise
        """
        if not self._config.cache_enabled:
            return None

        # ROUND6-001: Thread-safe cache read and expiry cleanup
        with self._cache_lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None

            result, expiry = entry
            if time.time() > expiry:
                del self._cache[cache_key]
                return None

        return result

    def _set_cache(self, cache_key: str, result: VerificationResult) -> None:
        """Cache a verification result.

        Args:
            cache_key: The cache key to store under
            result: The VerificationResult to cache
        """
        if self._config.cache_enabled:
            expiry = time.time() + self._config.cache_ttl_seconds
            # ROUND6-001: Thread-safe cache write
            with self._cache_lock:
                self._cache[cache_key] = (result, expiry)

    def _handle_denial(
        self,
        result: VerificationResult,
        context: str,
    ) -> VerificationResult:
        """Handle a denied verification result.

        Logs the denial if audit is enabled, and converts to allowed
        if in PERMISSIVE mode.

        Args:
            result: The denied VerificationResult
            context: Context string for logging (e.g., "workflow=xyz agent=abc")

        Returns:
            The original result in ENFORCING mode, or allowed result in PERMISSIVE mode
        """
        if self._config.audit_denials:
            logger.warning(
                "Trust verification DENIED: %s reason=%s",
                context,
                result.reason,
            )

        if self._mode == TrustVerificationMode.PERMISSIVE:
            logger.warning(
                "PERMISSIVE mode: allowing denied operation %s",
                context,
            )
            return VerificationResult(
                allowed=True,
                reason=f"PERMISSIVE: {result.reason}",
                constraints=result.constraints,
                capability_used=result.capability_used,
                trace_id=result.trace_id,
            )

        return result

    async def verify_workflow_access(
        self,
        workflow_id: str,
        agent_id: str,
        trust_context: Optional[RuntimeTrustContext] = None,
    ) -> VerificationResult:
        """Verify if an agent can execute a workflow.

        Args:
            workflow_id: The workflow to verify access to
            agent_id: The agent requesting access
            trust_context: Optional RuntimeTrustContext for additional context

        Returns:
            VerificationResult indicating whether access is allowed
        """
        if not self.is_enabled:
            return VerificationResult(allowed=True, reason="Verification disabled")

        # CARE-058: Use null byte separator to prevent cache key collision attacks.
        # Colon separator is vulnerable when IDs contain colons (e.g., "a:b" + "c" vs "a" + "b:c").
        # Null byte cannot appear in legitimate string IDs, making it collision-resistant.
        cache_key = f"wf\x00{workflow_id}\x00{agent_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Call Kaizen backend if available
        if self._backend is not None:
            try:
                # Try to import VerificationLevel from Kaizen
                try:
                    from kaizen.trust.chain import VerificationLevel

                    level = VerificationLevel.STANDARD
                except ImportError:
                    level = None

                kaizen_result = await self._backend.verify(
                    agent_id=agent_id,
                    action=f"execute_workflow:{workflow_id}",
                    level=level,
                    context=trust_context.to_dict() if trust_context else None,
                )
                result = VerificationResult(
                    allowed=kaizen_result.valid,
                    reason=kaizen_result.reason,
                    constraints=(
                        {c: True for c in kaizen_result.effective_constraints}
                        if kaizen_result.effective_constraints
                        else {}
                    ),
                    capability_used=kaizen_result.capability_used,
                    trace_id=trust_context.trace_id if trust_context else None,
                )
            except Exception as e:
                if self.is_enforcing:
                    logger.critical(
                        "SECURITY: Verification backend unavailable for workflow %s "
                        "in ENFORCING mode (fallback_allow=%s): %s",
                        workflow_id,
                        self._effective_fallback_allow,
                        e,
                    )
                else:
                    logger.error(
                        "Verification failed for workflow %s: %s", workflow_id, e
                    )
                result = VerificationResult(
                    allowed=self._effective_fallback_allow,
                    reason=f"Verification unavailable: {e}",
                    trace_id=trust_context.trace_id if trust_context else None,
                )
        else:
            # No backend - use fallback
            result = VerificationResult(
                allowed=self._effective_fallback_allow,
                reason="No verification backend configured",
                trace_id=trust_context.trace_id if trust_context else None,
            )

        self._set_cache(cache_key, result)

        # Handle denial if not allowed
        if not result.allowed:
            result = self._handle_denial(
                result,
                f"workflow={workflow_id} agent={agent_id}",
            )

        return result

    async def verify_node_access(
        self,
        node_id: str,
        node_type: str,
        agent_id: str,
        trust_context: Optional[RuntimeTrustContext] = None,
    ) -> VerificationResult:
        """Verify if an agent can execute a specific node.

        High-risk nodes (configured in TrustVerifierConfig) receive elevated
        verification when a backend is available.

        Args:
            node_id: The node instance ID
            node_type: The node type (e.g., "BashCommand", "HttpRequest")
            agent_id: The agent requesting access
            trust_context: Optional RuntimeTrustContext for additional context

        Returns:
            VerificationResult indicating whether access is allowed
        """
        if not self.is_enabled:
            return VerificationResult(allowed=True, reason="Verification disabled")

        # CARE-058: Use null byte separator to prevent cache key collision attacks.
        # Colon separator is vulnerable when IDs contain colons.
        # Null byte cannot appear in legitimate string IDs, making it collision-resistant.
        cache_key = f"node\x00{node_id}\x00{node_type}\x00{agent_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        is_high_risk = node_type in self._config.high_risk_nodes

        if self._backend is not None:
            try:
                # Try to import VerificationLevel from Kaizen
                try:
                    from kaizen.trust.chain import VerificationLevel

                    level = (
                        VerificationLevel.FULL
                        if is_high_risk
                        else VerificationLevel.QUICK
                    )
                except ImportError:
                    level = None

                kaizen_result = await self._backend.verify(
                    agent_id=agent_id,
                    action=f"execute_node:{node_type}:{node_id}",
                    level=level,
                    context=trust_context.to_dict() if trust_context else None,
                )
                result = VerificationResult(
                    allowed=kaizen_result.valid,
                    reason=kaizen_result.reason,
                    constraints=(
                        {c: True for c in kaizen_result.effective_constraints}
                        if kaizen_result.effective_constraints
                        else {}
                    ),
                    capability_used=kaizen_result.capability_used,
                    trace_id=trust_context.trace_id if trust_context else None,
                )
            except Exception as e:
                if self.is_enforcing:
                    logger.critical(
                        "SECURITY: Verification backend unavailable for node %s "
                        "in ENFORCING mode (fallback_allow=%s): %s",
                        node_id,
                        self._effective_fallback_allow,
                        e,
                    )
                else:
                    logger.error("Verification failed for node %s: %s", node_id, e)
                result = VerificationResult(
                    allowed=self._effective_fallback_allow,
                    reason=f"Verification unavailable: {e}",
                    trace_id=trust_context.trace_id if trust_context else None,
                )
        else:
            result = VerificationResult(
                allowed=self._effective_fallback_allow,
                reason="No verification backend configured",
                trace_id=trust_context.trace_id if trust_context else None,
            )

        self._set_cache(cache_key, result)

        # Handle denial if not allowed
        if not result.allowed:
            result = self._handle_denial(
                result,
                f"node={node_id} type={node_type} agent={agent_id}",
            )

        return result

    async def verify_resource_access(
        self,
        resource: str,
        action: str,
        agent_id: str,
        trust_context: Optional[RuntimeTrustContext] = None,
    ) -> VerificationResult:
        """Verify if an agent can access a resource.

        Args:
            resource: The resource path or identifier
            action: The action to perform (e.g., "read", "write")
            agent_id: The agent requesting access
            trust_context: Optional RuntimeTrustContext for additional context

        Returns:
            VerificationResult indicating whether access is allowed
        """
        if not self.is_enabled:
            return VerificationResult(allowed=True, reason="Verification disabled")

        # CARE-058: Use null byte separator to prevent cache key collision attacks.
        # Colon separator is vulnerable when IDs contain colons.
        # Null byte cannot appear in legitimate string IDs, making it collision-resistant.
        cache_key = f"res\x00{resource}\x00{action}\x00{agent_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if self._backend is not None:
            try:
                kaizen_result = await self._backend.verify(
                    agent_id=agent_id,
                    action=action,
                    resource=resource,
                    context=trust_context.to_dict() if trust_context else None,
                )
                result = VerificationResult(
                    allowed=kaizen_result.valid,
                    reason=kaizen_result.reason,
                    constraints=(
                        {c: True for c in kaizen_result.effective_constraints}
                        if kaizen_result.effective_constraints
                        else {}
                    ),
                    capability_used=kaizen_result.capability_used,
                    trace_id=trust_context.trace_id if trust_context else None,
                )
            except Exception as e:
                if self.is_enforcing:
                    logger.critical(
                        "SECURITY: Verification backend unavailable for resource %s "
                        "in ENFORCING mode (fallback_allow=%s): %s",
                        resource,
                        self._effective_fallback_allow,
                        e,
                    )
                else:
                    logger.error("Verification failed for resource %s: %s", resource, e)
                result = VerificationResult(
                    allowed=self._effective_fallback_allow,
                    reason=f"Verification unavailable: {e}",
                    trace_id=trust_context.trace_id if trust_context else None,
                )
        else:
            result = VerificationResult(
                allowed=self._effective_fallback_allow,
                reason="No verification backend configured",
                trace_id=trust_context.trace_id if trust_context else None,
            )

        self._set_cache(cache_key, result)

        # Handle denial if not allowed
        if not result.allowed:
            result = self._handle_denial(
                result,
                f"resource={resource} action={action} agent={agent_id}",
            )

        return result


class MockTrustVerifier(TrustVerifier):
    """Mock verifier for testing without Kaizen backend.

    Provides configurable allow/deny behavior for testing trust verification
    without requiring an actual Kaizen TrustOperations backend.

    Example:
        >>> verifier = MockTrustVerifier(
        ...     default_allow=True,
        ...     denied_agents=["blocked-agent"],
        ...     denied_nodes=["BashCommand"],
        ... )
        >>> result = await verifier.verify_workflow_access(
        ...     workflow_id="test-wf",
        ...     agent_id="good-agent",
        ... )
        >>> result.allowed
        True
    """

    def __init__(
        self,
        default_allow: bool = True,
        denied_agents: Optional[List[str]] = None,
        denied_nodes: Optional[List[str]] = None,
        config: Optional[TrustVerifierConfig] = None,
    ) -> None:
        """Initialize the MockTrustVerifier.

        Args:
            default_allow: Default behavior when not explicitly denied
            denied_agents: List of agent IDs that should be denied
            denied_nodes: List of node types that should be denied
            config: Optional configuration (defaults to enforcing mode)
        """
        super().__init__(
            kaizen_backend=None,
            config=config or TrustVerifierConfig(mode="enforcing"),
        )
        self._default_allow = default_allow
        self._denied_agents = set(denied_agents or [])
        self._denied_nodes = set(denied_nodes or [])

    async def verify_workflow_access(
        self,
        workflow_id: str,
        agent_id: str,
        trust_context: Optional[RuntimeTrustContext] = None,
    ) -> VerificationResult:
        """Verify workflow access using mock rules.

        Args:
            workflow_id: The workflow to verify access to
            agent_id: The agent requesting access
            trust_context: Optional RuntimeTrustContext for additional context

        Returns:
            VerificationResult based on mock rules
        """
        if not self.is_enabled:
            return VerificationResult(allowed=True, reason="Verification disabled")

        # CARE-058: Use null byte separator to prevent cache key collision attacks.
        cache_key = f"wf\x00{workflow_id}\x00{agent_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        trace_id = trust_context.trace_id if trust_context else None

        if agent_id in self._denied_agents:
            allowed = False
            reason = f"Agent {agent_id} is denied"
        else:
            allowed = self._default_allow
            reason = "Mock: allowed" if allowed else "Mock: denied by default"

        result = VerificationResult(allowed=allowed, reason=reason, trace_id=trace_id)

        self._set_cache(cache_key, result)

        if not result.allowed and self._mode == TrustVerificationMode.PERMISSIVE:
            result = VerificationResult(
                allowed=True,
                reason=f"PERMISSIVE: {result.reason}",
                trace_id=trace_id,
            )

        return result

    async def verify_node_access(
        self,
        node_id: str,
        node_type: str,
        agent_id: str,
        trust_context: Optional[RuntimeTrustContext] = None,
    ) -> VerificationResult:
        """Verify node access using mock rules.

        Args:
            node_id: The node instance ID
            node_type: The node type
            agent_id: The agent requesting access
            trust_context: Optional RuntimeTrustContext for additional context

        Returns:
            VerificationResult based on mock rules
        """
        if not self.is_enabled:
            return VerificationResult(allowed=True, reason="Verification disabled")

        # CARE-058: Use null byte separator to prevent cache key collision attacks.
        cache_key = f"node\x00{node_id}\x00{node_type}\x00{agent_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        trace_id = trust_context.trace_id if trust_context else None

        if agent_id in self._denied_agents:
            allowed = False
            reason = f"Agent {agent_id} is denied"
        elif node_type in self._denied_nodes:
            allowed = False
            reason = f"Node {node_type} is denied"
        else:
            allowed = self._default_allow
            reason = "Mock: allowed" if allowed else "Mock: denied by default"

        result = VerificationResult(allowed=allowed, reason=reason, trace_id=trace_id)

        self._set_cache(cache_key, result)

        if not result.allowed and self._mode == TrustVerificationMode.PERMISSIVE:
            result = VerificationResult(
                allowed=True,
                reason=f"PERMISSIVE: {result.reason}",
                trace_id=trace_id,
            )

        return result

    async def verify_resource_access(
        self,
        resource: str,
        action: str,
        agent_id: str,
        trust_context: Optional[RuntimeTrustContext] = None,
    ) -> VerificationResult:
        """Verify resource access using mock rules.

        Args:
            resource: The resource path or identifier
            action: The action to perform
            agent_id: The agent requesting access
            trust_context: Optional RuntimeTrustContext for additional context

        Returns:
            VerificationResult based on mock rules
        """
        if not self.is_enabled:
            return VerificationResult(allowed=True, reason="Verification disabled")

        # CARE-058: Use null byte separator to prevent cache key collision attacks.
        cache_key = f"res\x00{resource}\x00{action}\x00{agent_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        trace_id = trust_context.trace_id if trust_context else None

        if agent_id in self._denied_agents:
            allowed = False
            reason = f"Agent {agent_id} is denied"
        else:
            allowed = self._default_allow
            reason = "Mock: allowed" if allowed else "Mock: denied by default"

        result = VerificationResult(allowed=allowed, reason=reason, trace_id=trace_id)

        self._set_cache(cache_key, result)

        if not result.allowed and self._mode == TrustVerificationMode.PERMISSIVE:
            result = VerificationResult(
                allowed=True,
                reason=f"PERMISSIVE: {result.reason}",
                trace_id=trace_id,
            )

        return result
