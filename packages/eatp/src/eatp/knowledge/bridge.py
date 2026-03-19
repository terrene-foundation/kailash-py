# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
CARE-038: Trust-Chain-to-Knowledge Bridge for Trust Knowledge Ledger.

Bridges trust operations with knowledge management, enabling:
- Knowledge creation with trust chain verification
- Trust-aware knowledge querying
- Knowledge trust verification
- Untrusted knowledge flagging

The bridge provides graceful degradation when TrustOperations is not
configured, allowing basic knowledge management without full trust
infrastructure.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from eatp.knowledge.entry import KnowledgeEntry, KnowledgeType
from eatp.knowledge.provenance import (
    InMemoryProvenanceStore,
    ProvenanceRecord,
    ProvRelation,
)

from eatp.reasoning import ReasoningTrace

if TYPE_CHECKING:
    from eatp.operations import TrustOperations


class InMemoryKnowledgeStore:
    """
    In-memory store for knowledge entries.

    Provides storage and querying for KnowledgeEntry objects with
    support for filtering by content type and source agent.

    Example:
        >>> store = InMemoryKnowledgeStore()
        >>> entry = KnowledgeEntry.create(
        ...     content="API rate limit is 1000 requests per minute",
        ...     content_type=KnowledgeType.FACTUAL,
        ...     source_agent_id="agent-001",
        ...     trust_chain_ref="chain-abc123",
        ... )
        >>> await store.store(entry)
        >>> retrieved = await store.get(entry.entry_id)
    """

    def __init__(self) -> None:
        """Initialize empty knowledge store."""
        self._entries: Dict[str, KnowledgeEntry] = {}

    async def store(self, entry: KnowledgeEntry) -> None:
        """
        Store a knowledge entry.

        Args:
            entry: KnowledgeEntry to store
        """
        self._entries[entry.entry_id] = entry

    async def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        """
        Get a knowledge entry by ID.

        Args:
            entry_id: ID of the entry to retrieve

        Returns:
            KnowledgeEntry if found, None otherwise
        """
        return self._entries.get(entry_id)

    async def update(self, entry: KnowledgeEntry) -> None:
        """
        Update an existing knowledge entry.

        Args:
            entry: KnowledgeEntry with updated data

        Note:
            If entry doesn't exist, it will be created.
        """
        self._entries[entry.entry_id] = entry

    async def query(
        self,
        content_type: Optional[str] = None,
        source_agent_id: Optional[str] = None,
    ) -> List[KnowledgeEntry]:
        """
        Query knowledge entries with optional filters.

        Args:
            content_type: Filter by content type value (e.g., "factual")
            source_agent_id: Filter by source agent ID

        Returns:
            List of matching KnowledgeEntry objects
        """
        results: List[KnowledgeEntry] = []

        for entry in self._entries.values():
            # Apply content_type filter
            if content_type is not None:
                if entry.content_type.value != content_type:
                    continue

            # Apply source_agent_id filter
            if source_agent_id is not None:
                if entry.source_agent_id != source_agent_id:
                    continue

            results.append(entry)

        return results

    async def get_all(self) -> List[KnowledgeEntry]:
        """
        Get all knowledge entries.

        Returns:
            List of all KnowledgeEntry objects
        """
        return list(self._entries.values())


class TrustKnowledgeBridge:
    """
    Bridge between trust operations and knowledge management.

    Enables creation of knowledge entries with trust chain verification,
    trust-aware querying, and knowledge trust verification.

    Supports graceful degradation when TrustOperations is not configured,
    allowing basic knowledge management without full trust infrastructure.

    Example:
        >>> # With trust operations
        >>> bridge = TrustKnowledgeBridge(
        ...     trust_operations=trust_ops,
        ...     knowledge_store=InMemoryKnowledgeStore(),
        ...     provenance_store=InMemoryProvenanceStore(),
        ... )
        >>>
        >>> # Create knowledge with trust verification
        >>> entry = await bridge.create_knowledge_with_trust(
        ...     content="API supports 10,000 concurrent connections",
        ...     content_type="factual",
        ...     agent_id="agent-001",
        ...     confidence_score=0.95,
        ... )
        >>>
        >>> # Without trust operations (graceful degradation)
        >>> bridge = TrustKnowledgeBridge(
        ...     trust_operations=None,
        ...     knowledge_store=InMemoryKnowledgeStore(),
        ...     provenance_store=InMemoryProvenanceStore(),
        ... )
        >>> entry = await bridge.create_knowledge_with_trust(...)  # Still works
    """

    def __init__(
        self,
        trust_operations: Optional["TrustOperations"],
        knowledge_store: InMemoryKnowledgeStore,
        provenance_store: InMemoryProvenanceStore,
    ) -> None:
        """
        Initialize TrustKnowledgeBridge.

        Args:
            trust_operations: TrustOperations instance for trust verification.
                             Can be None for basic operation without trust verification.
            knowledge_store: Store for knowledge entries
            provenance_store: Store for provenance records
        """
        self._trust_operations = trust_operations
        self._knowledge_store = knowledge_store
        self._provenance_store = provenance_store

    async def create_knowledge_with_trust(
        self,
        content: str,
        content_type: str,
        agent_id: str,
        confidence_score: float = 0.8,
        derived_from: Optional[List[str]] = None,
        **metadata: Any,
    ) -> KnowledgeEntry:
        """
        Create a knowledge entry with trust chain verification.

        If TrustOperations is configured, verifies the agent has a valid
        trust chain and attaches trust chain reference and constraint
        envelope reference to the entry.

        If TrustOperations is None, creates entry with agent_id as
        trust_chain_ref (graceful degradation).

        Args:
            content: The knowledge content
            content_type: Type of knowledge (must match KnowledgeType values:
                         "factual", "procedural", "tacit_trace", "insight",
                         "decision_rationale")
            agent_id: ID of the agent contributing the knowledge
            confidence_score: Confidence level (0.0 to 1.0, default 0.8)
            derived_from: Optional list of entry IDs this knowledge is derived from
            **metadata: Additional metadata key-value pairs

        Returns:
            The created KnowledgeEntry

        Raises:
            ValueError: If content_type is not a valid KnowledgeType value
        """
        # Parse content type
        try:
            knowledge_type = KnowledgeType(content_type)
        except ValueError as e:
            valid_types = [kt.value for kt in KnowledgeType]
            raise ValueError(f"Invalid content_type '{content_type}'. Must be one of: {valid_types}") from e

        # Determine trust chain reference and constraint envelope reference
        trust_chain_ref: str
        constraint_envelope_ref: Optional[str] = None
        constraint_scope: Optional[str] = None

        if self._trust_operations is not None:
            # Try to get trust chain for the agent
            try:
                chain = await self._trust_operations.trust_store.get_chain(agent_id)
                trust_chain_ref = chain.hash()
                if chain.constraint_envelope:
                    constraint_envelope_ref = chain.constraint_envelope.id
                    # Extract constraint scope from envelope
                    if chain.constraint_envelope.active_constraints:
                        scope_parts = []
                        for constraint in chain.constraint_envelope.active_constraints:
                            scope_parts.append(str(constraint.value))
                        if scope_parts:
                            constraint_scope = ";".join(scope_parts)
            except Exception:
                # If chain not found, use agent_id as fallback
                trust_chain_ref = agent_id
        else:
            # Graceful degradation: use agent_id as trust chain reference
            trust_chain_ref = agent_id

        # Build metadata dict
        entry_metadata: Dict[str, Any] = dict(metadata)
        if constraint_scope:
            entry_metadata["constraint_scope"] = constraint_scope

        # Create knowledge entry
        entry = KnowledgeEntry.create(
            content=content,
            content_type=knowledge_type,
            source_agent_id=agent_id,
            trust_chain_ref=trust_chain_ref,
            constraint_envelope_ref=constraint_envelope_ref,
            confidence_score=confidence_score,
            metadata=entry_metadata,
        )

        # Store knowledge entry
        await self._knowledge_store.store(entry)

        # Create provenance record
        activity = "derivation" if derived_from else "creation"
        prov_record = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity=activity,
            agent_id=agent_id,
            derived_from=derived_from,
        )

        # Store provenance record
        await self._provenance_store.store(prov_record)

        return entry

    async def query_by_trust_level(
        self,
        min_confidence: float = 0.8,
        min_verifiers: int = 0,
        content_type: Optional[str] = None,
    ) -> List[KnowledgeEntry]:
        """
        Query knowledge entries by trust level.

        Filters entries by confidence score and number of verifiers.

        Args:
            min_confidence: Minimum confidence score (0.0 to 1.0, default 0.8)
            min_verifiers: Minimum number of verifiers (default 0)
            content_type: Optional content type filter

        Returns:
            List of matching KnowledgeEntry objects
        """
        # Get all entries, optionally filtered by content type
        entries = await self._knowledge_store.query(content_type=content_type)

        # Filter by confidence score and verifiers
        results: List[KnowledgeEntry] = []
        for entry in entries:
            if entry.confidence_score >= min_confidence:
                if len(entry.verified_by) >= min_verifiers:
                    results.append(entry)

        return results

    async def query_by_agent(
        self,
        agent_id: str,
        include_derived: bool = False,
    ) -> List[KnowledgeEntry]:
        """
        Query knowledge entries by agent.

        Args:
            agent_id: Agent ID to query for
            include_derived: If True, also include knowledge derived from
                           this agent's entries

        Returns:
            List of matching KnowledgeEntry objects
        """
        # Get entries directly created by agent
        direct_entries = await self._knowledge_store.query(source_agent_id=agent_id)

        if not include_derived:
            return direct_entries

        # Find entries derived from this agent's knowledge
        result_ids = {entry.entry_id for entry in direct_entries}
        results = list(direct_entries)

        # Get entry IDs from direct entries
        source_ids = {entry.entry_id for entry in direct_entries}

        # Query provenance for entries derived from these sources
        # We need to check all provenance records
        all_prov = await self._provenance_store.query()

        for prov_record in all_prov:
            # Skip if already in results
            if prov_record.entity_id in result_ids:
                continue

            # Check if derived from any of the agent's entries
            derived_from = prov_record.relations.get(ProvRelation.WAS_DERIVED_FROM.value, [])
            for source_id in derived_from:
                if source_id in source_ids:
                    # Get the knowledge entry
                    entry = await self._knowledge_store.get(prov_record.entity_id)
                    if entry is not None:
                        results.append(entry)
                        result_ids.add(entry.entry_id)
                    break

        return results

    async def query_by_constraint_scope(
        self,
        constraint_scope: str,
    ) -> List[KnowledgeEntry]:
        """
        Query knowledge entries by constraint scope.

        Matches entries where metadata["constraint_scope"] contains the
        specified constraint scope.

        Args:
            constraint_scope: Constraint scope to search for

        Returns:
            List of matching KnowledgeEntry objects
        """
        all_entries = await self._knowledge_store.get_all()

        results: List[KnowledgeEntry] = []
        for entry in all_entries:
            entry_scope = entry.metadata.get("constraint_scope", "")
            if constraint_scope in entry_scope:
                results.append(entry)

        return results

    async def verify_knowledge_trust(
        self,
        entry_id: str,
    ) -> Dict[str, Any]:
        """
        Verify the trust chain for a knowledge entry.

        Args:
            entry_id: ID of the knowledge entry to verify

        Returns:
            Dictionary with verification results:
            - valid: True if trust verification passed
            - reason: Explanation of result
            - entry_id: The entry ID verified
            - agent_id: Source agent ID (if entry found)
            - trust_chain_ref: Trust chain reference (if entry found)
            - has_trust_operations: Whether TrustOperations is configured
        """
        # Get entry from store
        entry = await self._knowledge_store.get(entry_id)
        if entry is None:
            return {
                "valid": False,
                "reason": "Knowledge entry not found",
                "entry_id": entry_id,
            }

        result: Dict[str, Any] = {
            "entry_id": entry_id,
            "agent_id": entry.source_agent_id,
            "trust_chain_ref": entry.trust_chain_ref,
            "constraint_envelope_ref": entry.constraint_envelope_ref,
            "has_trust_operations": self._trust_operations is not None,
        }

        if self._trust_operations is None:
            # Without trust operations, we can only do basic validation
            result["valid"] = True
            result["reason"] = "Basic validation passed (no TrustOperations configured)"
            return result

        # Verify source agent has valid trust chain
        try:
            chain = await self._trust_operations.trust_store.get_chain(entry.source_agent_id)

            # Check chain exists and is not expired
            if chain.is_expired():
                result["valid"] = False
                result["reason"] = "Agent trust chain is expired"
                return result

            # Verify trust chain reference matches
            current_hash = chain.hash()
            if entry.trust_chain_ref != current_hash:
                result["valid"] = False
                result["reason"] = (
                    f"Trust chain reference mismatch: entry has "
                    f"'{entry.trust_chain_ref}', current chain hash is '{current_hash}'"
                )
                return result

            result["valid"] = True
            result["reason"] = "Trust chain verification passed"
            result["chain_hash"] = current_hash
            result["capabilities"] = [cap.capability for cap in chain.capabilities]

        except Exception as e:
            result["valid"] = False
            result["reason"] = f"Trust chain verification failed: {str(e)}"

        return result

    async def flag_untrusted_knowledge(
        self,
        entry_id: str,
        reason: str,
    ) -> None:
        """
        Flag a knowledge entry as untrusted.

        Updates the entry's metadata to mark it as untrusted with a reason
        and timestamp.

        Args:
            entry_id: ID of the knowledge entry to flag
            reason: Reason for flagging as untrusted

        Note:
            Does nothing if entry not found (no error raised).
        """
        entry = await self._knowledge_store.get(entry_id)
        if entry is None:
            return

        # Update metadata
        entry.metadata["untrusted"] = True
        entry.metadata["untrusted_reason"] = reason
        entry.metadata["flagged_at"] = datetime.now(timezone.utc).isoformat()

        # Update entry in store
        await self._knowledge_store.update(entry)

    async def reasoning_trace_to_knowledge(
        self,
        trace: ReasoningTrace,
        agent_id: str,
        derived_from: Optional[List[str]] = None,
    ) -> KnowledgeEntry:
        """
        Convert a ReasoningTrace into a KnowledgeEntry with provenance.

        Creates a DECISION_RATIONALE knowledge entry from a reasoning trace,
        preserving the decision, rationale, methodology, evidence, and
        alternatives as structured metadata. The entry is stored in the
        knowledge store with a provenance record linking it to the agent.

        Args:
            trace: The ReasoningTrace to convert
            agent_id: ID of the agent that produced the reasoning
            derived_from: Optional list of entry IDs this reasoning is derived from

        Returns:
            The created KnowledgeEntry with DECISION_RATIONALE type
        """
        # Build content from decision and rationale
        content = f"Decision: {trace.decision}\nRationale: {trace.rationale}"

        # Build metadata from trace fields
        entry_metadata: Dict[str, Any] = {
            "confidentiality": trace.confidentiality.value,
            "reasoning_timestamp": trace.timestamp.isoformat(),
        }

        if trace.methodology is not None:
            entry_metadata["methodology"] = trace.methodology

        if trace.alternatives_considered:
            entry_metadata["alternatives_considered"] = trace.alternatives_considered

        if trace.evidence:
            entry_metadata["evidence"] = trace.evidence

        # Use trace confidence if available, otherwise default to 0.8
        confidence_score = trace.confidence if trace.confidence is not None else 0.8

        # Determine trust chain reference
        trust_chain_ref: str
        if self._trust_operations is not None:
            try:
                chain = await self._trust_operations.trust_store.get_chain(agent_id)
                trust_chain_ref = chain.hash()
            except Exception:
                trust_chain_ref = agent_id
        else:
            trust_chain_ref = agent_id

        # Create knowledge entry
        entry = KnowledgeEntry.create(
            content=content,
            content_type=KnowledgeType.DECISION_RATIONALE,
            source_agent_id=agent_id,
            trust_chain_ref=trust_chain_ref,
            confidence_score=confidence_score,
            metadata=entry_metadata,
        )

        # Store knowledge entry
        await self._knowledge_store.store(entry)

        # Create provenance record
        activity = "derivation" if derived_from else "creation"
        prov_record = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity=activity,
            agent_id=agent_id,
            derived_from=derived_from,
        )

        # Store provenance record
        await self._provenance_store.store(prov_record)

        return entry
