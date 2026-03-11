# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Agent Registry - Central registry for agent discovery and management.

This module provides the main AgentRegistry class that orchestrates
agent registration, discovery, and status management with trust verification.

Key Components:
- AgentRegistry: Main registry class with trust-aware operations
- DiscoveryQuery: Query builder for complex agent discovery
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from eatp.chain import VerificationLevel
from eatp.exceptions import TrustChainNotFoundError
from eatp.operations import TrustOperations
from eatp.registry.exceptions import (
    AgentNotFoundError,
    TrustVerificationError,
    ValidationError,
)
from eatp.registry.models import AgentMetadata, AgentStatus, RegistrationRequest
from eatp.registry.store import AgentRegistryStore

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryQuery:
    """
    Query builder for complex agent discovery.

    This dataclass allows specifying multiple criteria for finding
    agents in the registry. Results are filtered and ranked based
    on the criteria.

    Attributes:
        capabilities: List of capabilities to search for. Agents must
            have these capabilities to be included in results.

        match_all: If True, agents must have ALL listed capabilities.
            If False, agents must have ANY of the capabilities.
            Default is True for stricter matching.

        agent_type: Optional filter for agent type. Only agents with
            this exact type will be included.

        status: Filter by agent status. Default is ACTIVE to only
            return available agents.

        exclude_constraints: Optional list of constraints to exclude.
            Agents with ANY of these constraints will be filtered out.
            Useful for avoiding agents with restrictions.

        min_last_seen: Optional minimum last_seen timestamp. Agents
            not seen since this time will be excluded. Useful for
            ensuring agents are recently active.

    Example:
        >>> query = DiscoveryQuery(
        ...     capabilities=["analyze_data", "generate_report"],
        ...     match_all=True,
        ...     agent_type="worker",
        ...     status=AgentStatus.ACTIVE,
        ...     exclude_constraints=["network_access"],
        ...     min_last_seen=datetime.now(timezone.utc) - timedelta(minutes=5)
        ... )
        >>> results = await registry.discover(query)
    """

    capabilities: List[str] = field(default_factory=list)
    match_all: bool = True
    agent_type: Optional[str] = None
    status: AgentStatus = AgentStatus.ACTIVE
    exclude_constraints: List[str] = field(default_factory=list)
    min_last_seen: Optional[datetime] = None


class AgentRegistry:
    """
    Central registry for agent discovery and registration.

    The AgentRegistry provides trust-aware agent registration and
    discovery. It integrates with the trust system to verify that
    agents have valid trust chains before registration.

    Features:
    - Trust-verified registration
    - Capability-based discovery
    - Complex query support
    - Heartbeat and status tracking
    - Stale agent detection

    Example:
        >>> registry = AgentRegistry(
        ...     store=postgres_store,
        ...     trust_operations=trust_ops,
        ...     verify_on_registration=True
        ... )
        >>>
        >>> # Register an agent
        >>> request = RegistrationRequest(
        ...     agent_id="agent-001",
        ...     agent_type="worker",
        ...     capabilities=["analyze_data"],
        ...     trust_chain_hash=chain.compute_hash()
        ... )
        >>> metadata = await registry.register(request)
        >>>
        >>> # Discover agents
        >>> agents = await registry.find_by_capability("analyze_data")
    """

    def __init__(
        self,
        store: AgentRegistryStore,
        trust_operations: Optional[TrustOperations] = None,
        verify_on_registration: bool = True,
        auto_update_last_seen: bool = True,
        heartbeat_interval: int = 60,
    ):
        """
        Initialize the AgentRegistry.

        Args:
            store: Storage backend for agent metadata.

            trust_operations: TrustOperations instance for trust verification.
                Required if verify_on_registration is True.

            verify_on_registration: Whether to verify agent's trust chain
                before allowing registration. Default True for security.
                Set to False only in trusted environments.

            auto_update_last_seen: Whether to update last_seen timestamp
                when agents are accessed via get(). Default True.

            heartbeat_interval: Expected interval (seconds) between agent
                heartbeats. Used for stale agent detection.
        """
        self._store = store
        self._trust_ops = trust_operations
        self._verify_on_registration = verify_on_registration
        self._auto_update_last_seen = auto_update_last_seen
        self._heartbeat_interval = heartbeat_interval

        if verify_on_registration and not trust_operations:
            raise ValueError(
                "trust_operations is required when verify_on_registration is True"
            )

    async def register(self, request: RegistrationRequest) -> AgentMetadata:
        """
        Register a new agent in the registry.

        Registration includes:
        1. Request validation
        2. Trust chain verification (if enabled)
        3. Capability verification against trust chain
        4. Metadata creation and storage

        Args:
            request: Registration request with agent details.

        Returns:
            AgentMetadata for the registered agent.

        Raises:
            ValidationError: If request validation fails.
            TrustChainNotFoundError: If agent has no trust chain.
            TrustVerificationError: If trust verification fails.
            AgentAlreadyRegisteredError: If agent already registered.

        Example:
            >>> request = RegistrationRequest(
            ...     agent_id="agent-001",
            ...     agent_type="worker",
            ...     capabilities=["analyze_data"],
            ...     trust_chain_hash=chain.compute_hash()
            ... )
            >>> metadata = await registry.register(request)
            >>> assert metadata.status == AgentStatus.ACTIVE
        """
        # Step 1: Validate request
        errors = request.validate()
        if errors:
            logger.warning(
                f"Registration validation failed for {request.agent_id}: {errors}"
            )
            raise ValidationError(errors)

        # Step 2: Verify trust (if enabled)
        if self._verify_on_registration and request.verify_trust:
            await self._verify_registration_trust(request)

        # Step 3: Create metadata
        now = datetime.now(timezone.utc)
        metadata = AgentMetadata(
            agent_id=request.agent_id,
            agent_type=request.agent_type,
            capabilities=request.capabilities,
            constraints=request.constraints,
            status=AgentStatus.ACTIVE,
            trust_chain_hash=request.trust_chain_hash,
            registered_at=now,
            last_seen=now,
            metadata=request.metadata,
            endpoint=request.endpoint,
            public_key=request.public_key,
        )

        # Step 4: Store metadata
        await self._store.register_agent(metadata)

        logger.info(
            f"Registered agent {request.agent_id} with capabilities: {request.capabilities}"
        )

        return metadata

    async def unregister(self, agent_id: str) -> None:
        """
        Remove an agent from the registry.

        Note: This does NOT revoke the agent's trust chain. Trust
        and registration are managed separately. Use TrustOperations
        to revoke trust.

        Args:
            agent_id: ID of the agent to unregister.

        Raises:
            AgentNotFoundError: If agent not found.
        """
        await self._store.delete_agent(agent_id)
        logger.info(f"Unregistered agent: {agent_id}")

    async def get(self, agent_id: str) -> Optional[AgentMetadata]:
        """
        Retrieve an agent's metadata.

        If auto_update_last_seen is enabled, this also updates the
        agent's last_seen timestamp (useful for tracking activity).

        Args:
            agent_id: ID of the agent to retrieve.

        Returns:
            AgentMetadata if found, None otherwise.
        """
        metadata = await self._store.get_agent(agent_id)

        if metadata and self._auto_update_last_seen:
            try:
                await self._store.update_last_seen(agent_id, datetime.now(timezone.utc))
            except Exception as e:
                logger.warning(f"Failed to update last_seen for {agent_id}: {e}")

        return metadata

    async def update_status(
        self,
        agent_id: str,
        status: AgentStatus,
        reason: Optional[str] = None,
    ) -> None:
        """
        Update an agent's status.

        Args:
            agent_id: ID of the agent to update.
            status: New status value.
            reason: Optional reason for the status change (logged).

        Raises:
            AgentNotFoundError: If agent not found.
        """
        await self._store.update_status(agent_id, status)

        log_msg = f"Updated status for {agent_id}: {status.value}"
        if reason:
            log_msg += f" (reason: {reason})"
        logger.info(log_msg)

    async def find_by_capability(
        self,
        capability: str,
        active_only: bool = True,
    ) -> List[AgentMetadata]:
        """
        Find agents with a specific capability.

        Args:
            capability: The capability to search for.
            active_only: If True, only return ACTIVE agents.

        Returns:
            List of matching agents, sorted by last_seen (recent first).
        """
        agents = await self._store.find_by_capability(capability)

        if active_only:
            agents = [a for a in agents if a.status == AgentStatus.ACTIVE]

        return agents

    async def find_by_capabilities(
        self,
        capabilities: List[str],
        match_all: bool = True,
        active_only: bool = True,
    ) -> List[AgentMetadata]:
        """
        Find agents with multiple capabilities.

        Args:
            capabilities: List of capabilities to search for.
            match_all: If True, agent must have ALL capabilities.
                      If False, agent must have ANY capability.
            active_only: If True, only return ACTIVE agents.

        Returns:
            List of matching agents, sorted by match quality.
        """
        if not capabilities:
            return []

        # Check if store has the method
        if hasattr(self._store, "find_by_capabilities"):
            agents = await self._store.find_by_capabilities(capabilities, match_all)
        else:
            # Fallback: use find_by_capability for each and combine
            if match_all:
                # Start with first capability, then filter
                agents = await self._store.find_by_capability(capabilities[0])
                for cap in capabilities[1:]:
                    agents = [a for a in agents if cap in a.capabilities]
            else:
                # Union of all results
                seen = set()
                agents = []
                for cap in capabilities:
                    for agent in await self._store.find_by_capability(cap):
                        if agent.agent_id not in seen:
                            seen.add(agent.agent_id)
                            agents.append(agent)

        if active_only:
            agents = [a for a in agents if a.status == AgentStatus.ACTIVE]

        # Sort by capability match count (best match first)
        def match_count(agent: AgentMetadata) -> int:
            return sum(1 for cap in capabilities if cap in agent.capabilities)

        return sorted(agents, key=match_count, reverse=True)

    async def discover(self, query: DiscoveryQuery) -> List[AgentMetadata]:
        """
        Discover agents matching a complex query.

        This method supports filtering by multiple criteria and
        returns results ranked by relevance.

        Args:
            query: DiscoveryQuery with search criteria.

        Returns:
            List of matching agents, ranked by:
            1. Capability match count
            2. Recency (last_seen)
            3. Type match

        Example:
            >>> query = DiscoveryQuery(
            ...     capabilities=["analyze_data"],
            ...     agent_type="worker",
            ...     exclude_constraints=["network_access"]
            ... )
            >>> results = await registry.discover(query)
        """
        # Start with capability search
        if query.capabilities:
            agents = await self.find_by_capabilities(
                query.capabilities,
                match_all=query.match_all,
                active_only=False,  # We'll filter by status below
            )
        else:
            agents = await self._store.list_all()

        # Filter by status
        agents = [a for a in agents if a.status == query.status]

        # Filter by agent type
        if query.agent_type:
            agents = [a for a in agents if a.agent_type == query.agent_type]

        # Filter by excluded constraints
        if query.exclude_constraints:
            agents = [
                a
                for a in agents
                if not any(c in a.constraints for c in query.exclude_constraints)
            ]

        # Filter by min_last_seen
        if query.min_last_seen:
            agents = [a for a in agents if a.last_seen >= query.min_last_seen]

        # Rank results
        agents = self._rank_discovery_results(agents, query)

        return agents

    async def heartbeat(self, agent_id: str) -> None:
        """
        Update an agent's last_seen timestamp.

        This is a lightweight operation for agents to signal
        they are still active. Should be called periodically.

        Args:
            agent_id: ID of the agent sending heartbeat.

        Raises:
            AgentNotFoundError: If agent not found.
        """
        await self._store.update_last_seen(agent_id, datetime.now(timezone.utc))
        logger.debug(f"Heartbeat received from {agent_id}")

    async def get_stale_agents(
        self, timeout: Optional[int] = None
    ) -> List[AgentMetadata]:
        """
        Find agents that haven't sent heartbeats recently.

        Args:
            timeout: Seconds without heartbeat to consider stale.
                    Defaults to 5x heartbeat_interval.

        Returns:
            List of stale agents.
        """
        if timeout is None:
            timeout = self._heartbeat_interval * 5

        if hasattr(self._store, "find_stale_agents"):
            return await self._store.find_stale_agents(timeout)
        else:
            # Fallback: filter in memory
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout)
            all_agents = await self._store.list_all()
            return [
                a
                for a in all_agents
                if a.status == AgentStatus.ACTIVE and a.last_seen < cutoff
            ]

    async def list_all(self, active_only: bool = False) -> List[AgentMetadata]:
        """
        List all registered agents.

        Args:
            active_only: If True, only return ACTIVE agents.

        Returns:
            List of all agents.
        """
        agents = await self._store.list_all()

        if active_only:
            agents = [a for a in agents if a.status == AgentStatus.ACTIVE]

        return agents

    async def validate_agent_trust(self, agent_id: str) -> bool:
        """
        Validate an agent's current trust status.

        Checks that the agent's trust chain exists and is valid.
        Updates agent status to REVOKED if trust has been revoked.

        Args:
            agent_id: ID of the agent to validate.

        Returns:
            True if trust is valid, False otherwise.
        """
        if not self._trust_ops:
            logger.warning("Cannot validate trust: trust_operations not configured")
            return True  # Assume valid if trust checking disabled

        try:
            # Verify trust
            result = await self._trust_ops.verify(
                agent_id=agent_id,
                action="registry_validation",
                level=VerificationLevel.STANDARD,
            )

            if not result.valid:
                # Update status to REVOKED
                try:
                    await self.update_status(
                        agent_id,
                        AgentStatus.REVOKED,
                        reason=f"Trust verification failed: {result.reason}",
                    )
                except AgentNotFoundError:
                    pass  # Agent not in registry

                return False

            return True

        except TrustChainNotFoundError:
            # No trust chain - revoke
            try:
                await self.update_status(
                    agent_id,
                    AgentStatus.REVOKED,
                    reason="Trust chain not found",
                )
            except AgentNotFoundError:
                pass

            return False

        except Exception as e:
            logger.error(f"Error validating trust for {agent_id}: {e}")
            return False

    async def _verify_registration_trust(self, request: RegistrationRequest) -> None:
        """
        Verify an agent's trust chain before registration.

        Checks:
        1. Trust chain exists
        2. Chain hash matches request
        3. Agent has all requested capabilities in trust chain

        Raises:
            TrustChainNotFoundError: If no trust chain exists.
            TrustVerificationError: If verification fails.
        """
        if not self._trust_ops:
            raise ValueError("trust_operations required for trust verification")

        try:
            # Verify trust chain exists and is valid
            result = await self._trust_ops.verify(
                agent_id=request.agent_id,
                action="registration",
                level=VerificationLevel.STANDARD,
            )

            if not result.valid:
                raise TrustVerificationError(
                    request.agent_id,
                    reason=result.reason or "Trust verification failed",
                )

            # Get the trust chain to verify capabilities
            chain = await self._trust_ops.get_chain(request.agent_id)

            if not chain:
                raise TrustChainNotFoundError(agent_id=request.agent_id)

            # Verify hash matches (prevents registration with stale chain)
            chain_hash = chain.compute_hash()
            if request.trust_chain_hash and chain_hash != request.trust_chain_hash:
                raise TrustVerificationError(
                    request.agent_id,
                    reason=(
                        f"Trust chain hash mismatch: "
                        f"expected {request.trust_chain_hash}, got {chain_hash}"
                    ),
                )

            # Verify requested capabilities are in trust chain
            chain_capabilities = set()
            for attestation in chain.capability_attestations:
                chain_capabilities.add(attestation.capability)

            missing = set(request.capabilities) - chain_capabilities
            if missing:
                raise TrustVerificationError(
                    request.agent_id,
                    reason=f"Capabilities not in trust chain: {missing}",
                )

            logger.debug(f"Trust verification passed for {request.agent_id}")

        except TrustChainNotFoundError:
            raise
        except TrustVerificationError:
            raise
        except Exception as e:
            logger.error(f"Trust verification error for {request.agent_id}: {e}")
            raise TrustVerificationError(
                request.agent_id,
                reason=f"Trust verification error: {e}",
            )

    def _rank_discovery_results(
        self,
        agents: List[AgentMetadata],
        query: DiscoveryQuery,
    ) -> List[AgentMetadata]:
        """
        Rank discovery results by relevance.

        Ranking factors:
        1. Capability match count (higher is better)
        2. Recency (more recent last_seen is better)
        3. Type match (exact match is better)
        """

        def score(agent: AgentMetadata) -> float:
            # Capability score (0-100)
            if query.capabilities:
                cap_matches = sum(
                    1 for c in query.capabilities if c in agent.capabilities
                )
                cap_score = (cap_matches / len(query.capabilities)) * 100
            else:
                cap_score = 100  # No capability filter

            # Recency score (0-100, decays over time)
            minutes_ago = (
                datetime.now(timezone.utc) - agent.last_seen
            ).total_seconds() / 60
            recency_score = max(0, 100 - minutes_ago)

            # Type score (0-50)
            if query.agent_type:
                type_score = 50 if agent.agent_type == query.agent_type else 0
            else:
                type_score = 25  # Partial score when not filtering

            # Total weighted score
            return (cap_score * 0.5) + (recency_score * 0.3) + (type_score * 0.2)

        return sorted(agents, key=score, reverse=True)
