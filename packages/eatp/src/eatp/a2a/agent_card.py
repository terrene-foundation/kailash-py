# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Agent Card Generator.

Generates A2A Agent Cards with EATP trust extensions from trust chains.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from eatp.a2a.exceptions import AgentCardError
from eatp.a2a.models import AgentCapability, AgentCard, TrustExtensions
from eatp.chain import CapabilityAttestation, TrustLineageChain
from eatp.operations import TrustOperations

logger = logging.getLogger(__name__)


class AgentCardGenerator:
    """
    Generate A2A Agent Cards from trust chains.

    The generator creates Agent Cards with EATP trust extensions,
    allowing other agents to discover and verify this agent's capabilities.

    Example:
        >>> generator = AgentCardGenerator(
        ...     trust_operations=trust_ops,
        ...     base_url="https://agent.example.com",
        ... )
        >>> card = await generator.generate(
        ...     agent_id="agent-001",
        ...     name="Data Analyzer",
        ...     version="1.0.0",
        ... )
        >>> print(card.to_dict())
    """

    def __init__(
        self,
        trust_operations: TrustOperations,
        base_url: Optional[str] = None,
    ):
        """
        Initialize the Agent Card generator.

        Args:
            trust_operations: TrustOperations for retrieving trust chains.
            base_url: Base URL for the agent's A2A endpoints.
        """
        self._trust_ops = trust_operations
        self._base_url = base_url

    async def generate(
        self,
        agent_id: str,
        name: str,
        version: str,
        description: Optional[str] = None,
        additional_capabilities: Optional[List[AgentCapability]] = None,
        include_trust: bool = True,
    ) -> AgentCard:
        """
        Generate an Agent Card for the specified agent.

        Args:
            agent_id: The agent's unique identifier.
            name: Human-readable name for the agent.
            version: Agent version string.
            description: Optional description of the agent.
            additional_capabilities: Additional capabilities not in trust chain.
            include_trust: Whether to include EATP trust extensions.

        Returns:
            AgentCard with all information populated.

        Raises:
            AgentCardError: If the trust chain cannot be retrieved.
        """
        trust_extensions = None
        capabilities: List[AgentCapability] = []

        if include_trust:
            try:
                chain = await self._trust_ops.get_chain(agent_id)
                if chain:
                    trust_extensions = self._build_trust_extensions(chain)
                    capabilities = self._extract_capabilities(chain)
            except Exception as e:
                logger.warning(f"Could not retrieve trust chain for {agent_id}: {e}")
                # Continue without trust extensions

        # Add any additional capabilities
        if additional_capabilities:
            capabilities.extend(additional_capabilities)

        # Build the agent card
        now = datetime.now(timezone.utc)
        card = AgentCard(
            agent_id=agent_id,
            name=name,
            version=version,
            description=description,
            capabilities=capabilities,
            protocols=["a2a/1.0", "eatp/1.0"],
            endpoint=f"{self._base_url}/a2a/jsonrpc" if self._base_url else None,
            trust=trust_extensions,
            created_at=now,
            updated_at=now,
        )

        return card

    def _build_trust_extensions(self, chain: TrustLineageChain) -> TrustExtensions:
        """Build EATP trust extensions from trust chain."""
        genesis = chain.genesis

        # Extract attested capabilities (TrustLineageChain uses 'capabilities')
        attested_caps = (
            [cap.capability for cap in chain.capabilities] if chain.capabilities else []
        )

        # Extract constraints from envelope (uses active_constraints attribute)
        constraints = None
        if chain.constraint_envelope and chain.constraint_envelope.active_constraints:
            constraints = {
                c.constraint_type.value: c.value
                for c in chain.constraint_envelope.active_constraints
            }

        return TrustExtensions(
            trust_chain_hash=chain.hash(),
            genesis_authority_id=genesis.authority_id,
            genesis_authority_type=genesis.authority_type.value,
            verification_endpoint=(
                f"{self._base_url}/a2a/jsonrpc" if self._base_url else None
            ),
            delegation_endpoint=(
                f"{self._base_url}/a2a/jsonrpc" if self._base_url else None
            ),
            capabilities_attested=attested_caps if attested_caps else None,
            constraints=constraints,
        )

    def _extract_capabilities(self, chain: TrustLineageChain) -> List[AgentCapability]:
        """Extract capabilities from trust chain attestations."""
        capabilities = []

        for attestation in chain.capabilities:
            # Extract constraints for this capability
            cap_constraints = None
            if attestation.constraints:
                cap_constraints = attestation.constraints

            capability = AgentCapability(
                name=attestation.capability,
                description=f"Attested capability: {attestation.capability_type.value}",
                constraints=cap_constraints,
            )
            capabilities.append(capability)

        return capabilities

    async def generate_from_chain(
        self,
        chain: TrustLineageChain,
        name: str,
        version: str,
        description: Optional[str] = None,
    ) -> AgentCard:
        """
        Generate an Agent Card directly from a trust chain.

        Args:
            chain: The agent's trust chain.
            name: Human-readable name for the agent.
            version: Agent version string.
            description: Optional description of the agent.

        Returns:
            AgentCard with trust extensions.
        """
        trust_extensions = self._build_trust_extensions(chain)
        capabilities = self._extract_capabilities(chain)

        now = datetime.now(timezone.utc)
        return AgentCard(
            agent_id=chain.genesis.agent_id,
            name=name,
            version=version,
            description=description,
            capabilities=capabilities,
            protocols=["a2a/1.0", "eatp/1.0"],
            endpoint=f"{self._base_url}/a2a/jsonrpc" if self._base_url else None,
            trust=trust_extensions,
            created_at=now,
            updated_at=now,
        )


class AgentCardCache:
    """
    In-memory cache for Agent Cards with TTL support.

    Caches generated Agent Cards to reduce trust chain lookups
    and improve response times for /.well-known/agent.json.
    """

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize the cache.

        Args:
            ttl_seconds: Time-to-live for cached cards (default: 5 minutes).
        """
        self._cache: Dict[str, tuple[AgentCard, datetime]] = {}
        self._ttl_seconds = ttl_seconds

    def get(self, agent_id: str) -> Optional[AgentCard]:
        """
        Get cached Agent Card if not expired.

        Args:
            agent_id: The agent's identifier.

        Returns:
            Cached AgentCard or None if not found/expired.
        """
        if agent_id not in self._cache:
            return None

        card, cached_at = self._cache[agent_id]
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()

        if age > self._ttl_seconds:
            del self._cache[agent_id]
            return None

        return card

    def set(self, agent_id: str, card: AgentCard) -> None:
        """
        Cache an Agent Card.

        Args:
            agent_id: The agent's identifier.
            card: The Agent Card to cache.
        """
        self._cache[agent_id] = (card, datetime.now(timezone.utc))

    def invalidate(self, agent_id: str) -> None:
        """
        Invalidate cached Agent Card.

        Args:
            agent_id: The agent's identifier.
        """
        if agent_id in self._cache:
            del self._cache[agent_id]

    def clear(self) -> None:
        """Clear all cached cards."""
        self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "ttl_seconds": self._ttl_seconds,
        }
