# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
PseudoAgent - Human facade for the EATP system.

PseudoAgents are the ONLY entities that can initiate trust chains.
They bridge human authentication to the agentic world.

EATP (Enterprise Agent Trust Protocol) requires that every action must
be traceable to a human. PseudoAgents are the root of all trust chains -
they represent authenticated humans in the agent system.

Key Properties:
- Cannot be delegated TO (only FROM)
- Always the root of trust chains
- Tied to a specific human identity
- Session-scoped (should be invalidated when human logs out)

Reference: docs/plans/eatp-integration/04-gap-analysis.md (G2: PseudoAgent)

Author: Kaizen Framework Team
Created: 2026-01-02
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from kailash.trust.execution_context import ExecutionContext, HumanOrigin

if TYPE_CHECKING:
    from kailash.trust.chain import DelegationRecord
    from kailash.trust.operations import TrustOperations


class AuthProvider(str, Enum):
    """
    Supported authentication providers.

    These represent the different authentication systems that can
    verify human identity before creating a PseudoAgent.
    """

    OKTA = "okta"
    AZURE_AD = "azure_ad"
    GOOGLE = "google"
    SAML = "saml"
    OIDC = "oidc"
    LDAP = "ldap"
    SESSION = "session"  # For testing/internal use
    CUSTOM = "custom"


@dataclass
class PseudoAgentConfig:
    """
    Configuration for PseudoAgent behavior.

    Attributes:
        default_constraints: Default constraints applied to all delegations
        session_timeout_minutes: How long before session expires (None = no timeout)
        require_mfa: Whether MFA is required for this pseudo-agent
        allowed_capabilities: Whitelist of capabilities that can be delegated
    """

    default_constraints: Dict[str, Any] = field(default_factory=dict)
    session_timeout_minutes: Optional[int] = None
    require_mfa: bool = False
    allowed_capabilities: Optional[List[str]] = None


class PseudoAgent:
    """
    Human facade in the EATP system.

    PseudoAgents are the ONLY entities that can be the root_source
    of a delegation chain. They bridge human authentication to EATP.

    Key Properties:
    - Cannot be delegated TO (only FROM)
    - Always the root of trust chains
    - Tied to a specific human identity
    - Session-scoped (should be invalidated when human logs out)

    Example:
        >>> # Create from authenticated session
        >>> pseudo = PseudoAgent(
        ...     human_origin=HumanOrigin(
        ...         human_id="alice@corp.com",
        ...         display_name="Alice Chen",
        ...         auth_provider="okta",
        ...         session_id="sess-123",
        ...         authenticated_at=datetime.now(timezone.utc)
        ...     ),
        ...     trust_operations=trust_ops
        ... )
        >>>
        >>> # Delegate to an agent
        >>> delegation, ctx = await pseudo.delegate_to(
        ...     agent_id="invoice-processor",
        ...     task_id="november-invoices",
        ...     capabilities=["read_invoices", "process_invoices"],
        ...     constraints={"cost_limit": 1000}
        ... )
        >>>
        >>> # The agent can now execute with the context
        >>> await agent.execute_async(inputs, context=ctx)
    """

    def __init__(
        self,
        human_origin: HumanOrigin,
        trust_operations: "TrustOperations",
        config: Optional[PseudoAgentConfig] = None,
    ):
        """
        Initialize PseudoAgent.

        Args:
            human_origin: Verified human identity
            trust_operations: TrustOperations instance for delegation
            config: Optional configuration for pseudo-agent behavior
        """
        self._origin = human_origin
        self._trust_ops = trust_operations
        self._config = config or PseudoAgentConfig()

        # Generate pseudo-agent ID from human identity
        self._pseudo_id = f"pseudo:{human_origin.human_id}"

        # Track active delegations
        self._active_delegations: List[str] = []

    @property
    def agent_id(self) -> str:
        """
        The pseudo-agent's ID (used in delegation chains).

        Format: "pseudo:{human_id}"
        """
        return self._pseudo_id

    @property
    def human_origin(self) -> HumanOrigin:
        """The human identity this pseudo-agent represents."""
        return self._origin

    @property
    def session_id(self) -> str:
        """Get the session ID for this pseudo-agent."""
        return self._origin.session_id

    @property
    def is_session_valid(self) -> bool:
        """
        Check if the session is still valid.

        Returns:
            True if session is valid, False if expired
        """
        if self._config.session_timeout_minutes is None:
            return True

        elapsed = datetime.now(timezone.utc) - self._origin.authenticated_at
        return elapsed.total_seconds() < (self._config.session_timeout_minutes * 60)

    def create_execution_context(
        self,
        initial_constraints: Optional[Dict[str, Any]] = None,
    ) -> ExecutionContext:
        """
        Create an ExecutionContext rooted in this human.

        This is how ALL execution chains MUST start - from a PseudoAgent.

        Args:
            initial_constraints: Constraints for this execution

        Returns:
            ExecutionContext with this human as root_source

        Example:
            >>> ctx = pseudo_agent.create_execution_context(
            ...     initial_constraints={"cost_limit": 10000}
            ... )
            >>> # ctx.human_origin is the human who created this pseudo-agent
            >>> # ctx.delegation_chain is ["pseudo:alice@corp.com"]
        """
        constraints = {**self._config.default_constraints}
        if initial_constraints:
            constraints.update(initial_constraints)

        return ExecutionContext(
            human_origin=self._origin,
            delegation_chain=[self._pseudo_id],
            delegation_depth=0,
            constraints=constraints,
        )

    async def delegate_to(
        self,
        agent_id: str,
        task_id: str,
        capabilities: List[str],
        constraints: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> Tuple["DelegationRecord", ExecutionContext]:
        """
        Delegate trust from human to an agent.

        This is the ONLY way trust enters the agentic system.
        The returned ExecutionContext has this human as root_source.

        Args:
            agent_id: ID of the agent to delegate to
            task_id: ID of the task being delegated
            capabilities: Capabilities to grant
            constraints: Constraints to apply
            expires_at: When this delegation expires

        Returns:
            Tuple of (DelegationRecord, ExecutionContext for the agent)

        Raises:
            ValueError: If capability not in allowed list (when configured)
            SessionExpiredError: If session has expired

        Example:
            >>> delegation, ctx = await pseudo.delegate_to(
            ...     agent_id="data-analyzer",
            ...     task_id="quarterly-report",
            ...     capabilities=["read_sales_data", "generate_report"],
            ...     constraints={"data_scope": "Q4_2025"}
            ... )
        """
        # Check session validity
        if not self.is_session_valid:
            raise ValueError(f"Session expired for {self._origin.human_id}. User must re-authenticate.")

        # Check capability whitelist if configured
        if self._config.allowed_capabilities is not None:
            for cap in capabilities:
                if cap not in self._config.allowed_capabilities:
                    raise ValueError(f"Capability '{cap}' not in allowed capabilities list for {self._origin.human_id}")

        # Create initial context from this human
        ctx = self.create_execution_context(constraints)

        # Create delegation record via TrustOperations
        delegation = await self._trust_ops.delegate(
            delegator_id=self._pseudo_id,
            delegatee_id=agent_id,
            task_id=task_id,
            capabilities=capabilities,
            additional_constraints=list(constraints.keys()) if constraints else None,
            expires_at=expires_at,
            context=ctx,  # Pass context for EATP tracing
        )

        # Track active delegation
        self._active_delegations.append(delegation.id)

        # Create context for the delegated agent
        agent_ctx = ctx.with_delegation(agent_id, constraints)

        return delegation, agent_ctx

    async def revoke_delegation(self, delegation_id: str, agent_id: str) -> None:
        """
        Revoke a specific delegation.

        Args:
            delegation_id: ID of the delegation to revoke
            agent_id: ID of the agent whose delegation to revoke
        """
        await self._trust_ops.revoke_delegation(delegation_id, agent_id)

        # Remove from tracking
        if delegation_id in self._active_delegations:
            self._active_delegations.remove(delegation_id)

    async def revoke_all_delegations(self) -> List[str]:
        """
        Revoke all active delegations from this pseudo-agent.

        Use this when the human logs out or their access is revoked.
        Uses cascade revocation to invalidate all downstream delegations.

        Returns:
            List of successfully revoked delegation IDs

        Note:
            Revocation errors are logged but don't prevent other revocations.
            Check logs if fewer delegations are revoked than expected.
        """
        import logging

        logger = logging.getLogger(__name__)
        revoked = []
        failed = []

        for delegation_id in list(self._active_delegations):
            try:
                # Use cascade revocation to invalidate this delegation
                # and all downstream delegations
                await self._trust_ops.revoke_delegation(
                    delegation_id=delegation_id,
                    delegator_id=self.agent_id,
                    cascade=True,
                )
                revoked.append(delegation_id)
            except Exception as e:
                # Log the error but continue revoking others
                logger.warning(f"Failed to revoke delegation {delegation_id}: {e}. Continuing with other revocations.")
                failed.append((delegation_id, str(e)))

        # Clear tracking regardless of individual failures
        # (failed delegations may have been partially revoked)
        self._active_delegations.clear()

        if failed:
            logger.error(
                f"Failed to revoke {len(failed)} of {len(failed) + len(revoked)} "
                f"delegations from {self.agent_id}: {failed}"
            )

        return revoked

    def __str__(self) -> str:
        """Return human-readable representation."""
        return f"PseudoAgent({self._origin.human_id}, session={self._origin.session_id[:8]}...)"


class PseudoAgentFactory:
    """
    Factory for creating PseudoAgents from various auth sources.

    This is the single entry point for creating PseudoAgents.
    It handles validation and normalization of identity data.

    Example:
        >>> factory = PseudoAgentFactory(trust_ops)
        >>>
        >>> # From session data
        >>> pseudo = factory.from_session(
        ...     user_id="user-123",
        ...     email="alice@corp.com",
        ...     display_name="Alice Chen",
        ...     session_id="sess-456",
        ...     auth_provider="okta"
        ... )
        >>>
        >>> # From JWT claims
        >>> pseudo = factory.from_claims(
        ...     claims={"sub": "user-123", "email": "alice@corp.com", "name": "Alice"},
        ...     auth_provider="azure_ad"
        ... )
    """

    def __init__(
        self,
        trust_operations: "TrustOperations",
        default_config: Optional[PseudoAgentConfig] = None,
    ):
        """
        Initialize factory.

        Args:
            trust_operations: TrustOperations instance for delegation
            default_config: Default configuration for created pseudo-agents
        """
        self._trust_ops = trust_operations
        self._default_config = default_config

    def from_session(
        self,
        user_id: str,
        email: str,
        display_name: str,
        session_id: str,
        auth_provider: str = "session",
        config: Optional[PseudoAgentConfig] = None,
    ) -> PseudoAgent:
        """
        Create PseudoAgent from session data.

        Use this when you have already validated the user's identity
        and have session information.

        Args:
            user_id: Unique user identifier
            email: User's email (used as human_id)
            display_name: Human-readable name
            session_id: Current session ID
            auth_provider: How the user authenticated
            config: Optional configuration override

        Returns:
            PseudoAgent representing this human
        """
        origin = HumanOrigin(
            human_id=email,  # Use email as canonical ID
            display_name=display_name,
            auth_provider=auth_provider,
            session_id=session_id,
            authenticated_at=datetime.now(timezone.utc),
        )
        return PseudoAgent(
            origin,
            self._trust_ops,
            config or self._default_config,
        )

    def from_claims(
        self,
        claims: Dict[str, Any],
        auth_provider: str,
        config: Optional[PseudoAgentConfig] = None,
    ) -> PseudoAgent:
        """
        Create PseudoAgent from JWT claims or similar.

        Handles various claim formats from different identity providers.

        Args:
            claims: Dictionary of identity claims
            auth_provider: The auth provider (okta, azure_ad, etc.)
            config: Optional configuration override

        Returns:
            PseudoAgent representing this human

        Example:
            >>> # Standard OIDC claims
            >>> pseudo = factory.from_claims(
            ...     claims={"sub": "user-123", "email": "alice@corp.com", "name": "Alice"},
            ...     auth_provider="okta"
            ... )
            >>>
            >>> # Minimal claims
            >>> pseudo = factory.from_claims(
            ...     claims={"sub": "user-123"},
            ...     auth_provider="custom"
            ... )
        """
        # Extract human_id from various claim formats
        human_id = claims.get("email") or claims.get("sub") or claims.get("user_id")
        if not human_id:
            raise ValueError("Claims must contain 'email', 'sub', or 'user_id'")

        # Extract display name with fallbacks
        display_name = (
            claims.get("name")
            or claims.get("display_name")
            or claims.get("preferred_username")
            or claims.get("email")
            or claims.get("sub")
        )

        # Extract or generate session ID
        session_id = (
            claims.get("jti")  # JWT ID
            or claims.get("session_id")
            or claims.get("sid")  # Session ID claim
            or str(uuid.uuid4())
        )

        # Extract authentication time
        auth_time = claims.get("iat") or claims.get("auth_time")
        if auth_time:
            if isinstance(auth_time, (int, float)):
                authenticated_at = datetime.fromtimestamp(auth_time)
            else:
                authenticated_at = datetime.now(timezone.utc)
        else:
            authenticated_at = datetime.now(timezone.utc)

        origin = HumanOrigin(
            human_id=human_id,
            display_name=display_name,
            auth_provider=auth_provider,
            session_id=session_id,
            authenticated_at=authenticated_at,
        )
        return PseudoAgent(
            origin,
            self._trust_ops,
            config or self._default_config,
        )

    def from_http_request(
        self,
        headers: Dict[str, str],
        auth_provider: str = "oidc",
        user_header: str = "X-User-Id",
        email_header: str = "X-User-Email",
        name_header: str = "X-User-Name",
        session_header: str = "X-Session-Id",
        config: Optional[PseudoAgentConfig] = None,
    ) -> PseudoAgent:
        """
        Create PseudoAgent from HTTP request headers.

        Use this when identity is passed via headers (e.g., from API gateway).

        Args:
            headers: HTTP request headers
            auth_provider: Auth provider name
            user_header: Header containing user ID
            email_header: Header containing email
            name_header: Header containing display name
            session_header: Header containing session ID
            config: Optional configuration override

        Returns:
            PseudoAgent representing this human

        Raises:
            ValueError: If required headers are missing
        """
        email = headers.get(email_header)
        if not email:
            raise ValueError(f"Missing required header: {email_header}")

        user_id = headers.get(user_header, email)
        display_name = headers.get(name_header, email)
        session_id = headers.get(session_header, str(uuid.uuid4()))

        return self.from_session(
            user_id=user_id,
            email=email,
            display_name=display_name,
            session_id=session_id,
            auth_provider=auth_provider,
            config=config,
        )


# =============================================================================
# Helper Functions
# =============================================================================


def create_pseudo_agent_for_testing(
    human_id: str = "test@example.com",
    display_name: str = "Test User",
    trust_ops: Optional["TrustOperations"] = None,
) -> PseudoAgent:
    """
    Create a PseudoAgent for testing purposes.

    This is a convenience function for tests that need a PseudoAgent
    without setting up a full authentication flow.

    Args:
        human_id: Test user's email/ID
        display_name: Test user's display name
        trust_ops: TrustOperations instance (required)

    Returns:
        PseudoAgent for testing

    Example:
        >>> pseudo = create_pseudo_agent_for_testing(
        ...     "alice@test.com", "Alice Test", trust_ops
        ... )
    """
    if trust_ops is None:
        raise ValueError("trust_ops is required for PseudoAgent")

    origin = HumanOrigin(
        human_id=human_id,
        display_name=display_name,
        auth_provider="session",
        session_id=f"test-session-{uuid.uuid4()}",
        authenticated_at=datetime.now(timezone.utc),
    )
    return PseudoAgent(origin, trust_ops)
