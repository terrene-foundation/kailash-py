# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Trust Operations.

Implements the four core EATP operations:
- ESTABLISH: Create initial trust for an agent
- DELEGATE: Transfer trust from one agent to another
- VERIFY: Validate trust for an action
- AUDIT: Record agent actions

Phase 1 (Week 2) implements ESTABLISH and VERIFY.
Phase 1 (Week 3) implements DELEGATE and AUDIT.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from kailash.trust.authority import (
    AuthorityPermission,
    AuthorityRegistryProtocol,
    OrganizationalAuthority,
)
from kailash.trust.chain import (
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
    VerificationResult,
)
from kailash.trust.constraint_validator import ConstraintValidator
from kailash.trust.signing.crypto import (
    hash_chain,
    serialize_for_signing,
    sign,
    verify_signature,
)
from kailash.trust.exceptions import (
    AgentAlreadyEstablishedError,
    AuthorityInactiveError,
    AuthorityNotFoundError,
    CapabilityNotFoundError,
    ConstraintViolationError,
    DelegationError,
    InvalidSignatureError,
    InvalidTrustChainError,
    TrustChainNotFoundError,
    TrustError,
    VerificationFailedError,
)
from kailash.trust.execution_context import (
    ExecutionContext,
    HumanOrigin,
    get_current_context,
)
from kailash.trust.chain_store import TrustStore

# Logger for trust operations
logger = logging.getLogger(__name__)

# Maximum allowed delegation depth from human origin (CARE-004)
# This prevents DoS attacks through deep delegation chains and
# ensures traceability can be maintained back to human origin.
MAX_DELEGATION_DEPTH = 10


@dataclass
class CapabilityRequest:
    """
    Request for a capability during ESTABLISH.

    Attributes:
        capability: Name of the capability (e.g., "analyze_data")
        capability_type: Type of capability (ACCESS, ACTION, etc.)
        constraints: Specific constraints for this capability
        scope: Optional scope restrictions (e.g., {"databases": ["finance_db"]})
    """

    capability: str
    capability_type: CapabilityType
    constraints: List[str] = field(default_factory=list)
    scope: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstraintEvaluationResult:
    """Result of constraint evaluation."""

    permitted: bool
    violations: List[Dict[str, Any]] = field(default_factory=list)


class TrustKeyManager:
    """
    Manages cryptographic keys for trust operations.

    This is a simple in-memory implementation for Phase 1.
    Production would use HSM or secure key management service.
    """

    def __init__(self):
        """Initialize key manager."""
        self._keys: Dict[str, str] = {}  # key_id -> private_key

    def register_key(self, key_id: str, private_key: str) -> None:
        """
        Register a private key.

        Args:
            key_id: Identifier for the key
            private_key: Base64-encoded private key
        """
        self._keys[key_id] = private_key

    def get_key(self, key_id: str) -> Optional[str]:
        """
        Get a private key by ID.

        Args:
            key_id: Identifier for the key

        Returns:
            The private key or None if not found
        """
        return self._keys.get(key_id)

    async def sign(self, payload: str, key_id: str) -> str:
        """
        Sign a payload with a specific key.

        Args:
            payload: Data to sign
            key_id: Key to use for signing

        Returns:
            Base64-encoded signature

        Raises:
            ValueError: If key not found
        """
        private_key = self._keys.get(key_id)
        if not private_key:
            raise ValueError(f"Key not found: {key_id}")
        return sign(payload, private_key)

    async def verify(self, payload: str, signature: str, public_key: str) -> bool:
        """
        Verify a signature.

        Args:
            payload: Original data
            signature: Signature to verify
            public_key: Public key for verification

        Returns:
            True if signature is valid
        """
        return verify_signature(payload, signature, public_key)


class TrustOperations:
    """
    Core EATP trust operations.

    Implements the four operations that manipulate and verify Trust Lineage Chains:
    - ESTABLISH: Create initial trust
    - DELEGATE: Transfer trust (Week 3)
    - VERIFY: Validate trust
    - AUDIT: Record actions (Week 3)

    Example:
        >>> # Initialize components
        >>> from kailash.trust.chain_store.memory import InMemoryTrustStore
        >>> store = InMemoryTrustStore()
        >>> key_manager = TrustKeyManager()
        >>>
        >>> # Create operations instance
        >>> trust_ops = TrustOperations(registry, key_manager, store)
        >>> await trust_ops.initialize()
        >>>
        >>> # Establish trust for an agent
        >>> chain = await trust_ops.establish(
        ...     agent_id="agent-001",
        ...     authority_id="org-acme",
        ...     capabilities=[
        ...         CapabilityRequest(
        ...             capability="analyze_data",
        ...             capability_type=CapabilityType.ACCESS,
        ...         )
        ...     ],
        ... )
        >>>
        >>> # Verify trust for an action
        >>> result = await trust_ops.verify(
        ...     agent_id="agent-001",
        ...     action="analyze_data",
        ... )
    """

    def __init__(
        self,
        authority_registry: AuthorityRegistryProtocol,
        key_manager: TrustKeyManager,
        trust_store: TrustStore,
        max_delegation_depth: int = MAX_DELEGATION_DEPTH,
    ):
        """
        Initialize TrustOperations.

        Args:
            authority_registry: Registry for organizational authorities
            key_manager: Manager for cryptographic keys
            trust_store: Storage for trust chains
            max_delegation_depth: Maximum allowed delegation depth from human origin
                                  (CARE-004). Defaults to MAX_DELEGATION_DEPTH (10).
        """
        self.authority_registry = authority_registry
        self.key_manager = key_manager
        self.trust_store = trust_store
        self.max_delegation_depth = max_delegation_depth
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize trust operations and dependencies."""
        if self._initialized:
            return
        await self.authority_registry.initialize()
        await self.trust_store.initialize()
        self._initialized = True

    # =========================================================================
    # ESTABLISH Operation
    # =========================================================================

    async def establish(
        self,
        agent_id: str,
        authority_id: str,
        capabilities: List[CapabilityRequest],
        constraints: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> TrustLineageChain:
        """
        ESTABLISH: Create initial trust for an agent.

        This operation creates a new Trust Lineage Chain for an agent,
        establishing the genesis of trust from an organizational authority.

        Args:
            agent_id: Unique identifier for the agent
            authority_id: Authority granting trust
            capabilities: Requested capabilities
            constraints: Initial constraints (applied to all capabilities)
            metadata: Additional context
            expires_at: Optional expiration datetime

        Returns:
            TrustLineageChain: Complete trust chain for agent

        Raises:
            AuthorityNotFoundError: If authority doesn't exist
            AuthorityInactiveError: If authority is not active
            AgentAlreadyEstablishedError: If agent already has trust
            TrustStoreDatabaseError: If storage fails
        """
        constraints = constraints or []
        metadata = metadata or {}

        # 1. Validate authority exists and is active
        authority = await self._validate_authority(authority_id)

        # 2. Check authority has permission to create agents
        if not authority.has_permission(AuthorityPermission.CREATE_AGENTS):
            raise TrustError(f"Authority {authority_id} does not have permission to create agents")

        # 3. Check agent doesn't already have a trust chain
        try:
            existing = await self.trust_store.get_chain(agent_id)
            if existing:
                raise AgentAlreadyEstablishedError(agent_id)
        except TrustChainNotFoundError:
            pass  # Expected - agent should not exist

        # 4. Create Genesis Record
        genesis = GenesisRecord(
            id=f"gen-{uuid4()}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=authority.authority_type,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            signature="",  # Will be signed below
            signature_algorithm="Ed25519",
            metadata=metadata,
        )

        # 5. Sign genesis record
        genesis_payload = serialize_for_signing(genesis.to_signing_payload())
        genesis.signature = await self.key_manager.sign(genesis_payload, authority.signing_key_id)

        # 6. Create Capability Attestations
        capability_attestations = []
        for cap_request in capabilities:
            attestation = await self._create_capability_attestation(
                cap_request=cap_request,
                authority=authority,
                global_constraints=constraints,
                expires_at=expires_at,
            )
            capability_attestations.append(attestation)

        # 7. Create initial Constraint Envelope
        constraint_envelope = self._compute_constraint_envelope(
            agent_id=agent_id,
            genesis=genesis,
            capabilities=capability_attestations,
            delegations=[],
        )

        # 8. Create Trust Lineage Chain
        chain = TrustLineageChain(
            genesis=genesis,
            capabilities=capability_attestations,
            delegations=[],
            constraint_envelope=constraint_envelope,
            audit_anchors=[],
        )

        # 9. Store chain
        await self.trust_store.store_chain(chain, expires_at)

        return chain

    async def _validate_authority(
        self,
        authority_id: str,
    ) -> OrganizationalAuthority:
        """
        Validate that an authority exists and is active.

        Args:
            authority_id: Authority to validate

        Returns:
            The OrganizationalAuthority

        Raises:
            AuthorityNotFoundError: If not found
            AuthorityInactiveError: If inactive
        """
        return await self.authority_registry.get_authority(authority_id)

    async def _create_capability_attestation(
        self,
        cap_request: CapabilityRequest,
        authority: OrganizationalAuthority,
        global_constraints: List[str],
        expires_at: Optional[datetime],
    ) -> CapabilityAttestation:
        """
        Create and sign a capability attestation.

        Args:
            cap_request: The capability request
            authority: The attesting authority
            global_constraints: Constraints applied to all capabilities
            expires_at: Optional expiration

        Returns:
            Signed CapabilityAttestation
        """
        # Combine capability-specific and global constraints (deduplicated, order-preserved)
        seen = set()
        all_constraints = []
        for c in cap_request.constraints + global_constraints:
            if c not in seen:
                seen.add(c)
                all_constraints.append(c)

        attestation = CapabilityAttestation(
            id=f"cap-{uuid4()}",
            capability=cap_request.capability,
            capability_type=cap_request.capability_type,
            constraints=all_constraints,
            attester_id=authority.id,
            attested_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            signature="",
            scope=cap_request.scope,
        )

        # Sign attestation
        payload = serialize_for_signing(attestation.to_signing_payload())
        attestation.signature = await self.key_manager.sign(payload, authority.signing_key_id)

        return attestation

    def _compute_constraint_envelope(
        self,
        agent_id: str,
        genesis: GenesisRecord,
        capabilities: List[CapabilityAttestation],
        delegations: List[DelegationRecord],
    ) -> ConstraintEnvelope:
        """
        Compute the effective constraint envelope for an agent.

        The constraint envelope aggregates all constraints from:
        - Genesis record
        - Capability attestations
        - Delegation records (constraint tightening)

        Args:
            agent_id: The agent ID
            genesis: Genesis record
            capabilities: Capability attestations
            delegations: Delegation records

        Returns:
            ConstraintEnvelope with all effective constraints
        """
        constraints = []

        # Add genesis-level constraints
        for name in genesis.metadata.get("constraints", []):
            constraints.append(
                Constraint(
                    id=f"con-{uuid4()}",
                    constraint_type=ConstraintType.FINANCIAL,  # Default type
                    value=name,
                    source="genesis",
                )
            )

        # Add capability-level constraints
        for cap in capabilities:
            for name in cap.constraints:
                constraints.append(
                    Constraint(
                        id=f"con-{uuid4()}",
                        constraint_type=ConstraintType.OPERATIONAL,
                        value=name,
                        source=f"capability:{cap.id}",
                    )
                )

        # Add delegation constraints (constraint tightening)
        for delegation in delegations:
            for name in delegation.constraint_subset:
                constraints.append(
                    Constraint(
                        id=f"con-{uuid4()}",
                        constraint_type=ConstraintType.DATA_ACCESS,
                        value=name,
                        source=f"delegation:{delegation.id}",
                    )
                )

        # Create envelope
        envelope = ConstraintEnvelope(
            id=f"env-{uuid4()}",
            agent_id=agent_id,
            active_constraints=constraints,
            computed_at=datetime.now(timezone.utc),
            valid_until=genesis.expires_at,
            constraint_hash="",  # Will be computed by __post_init__
        )

        return envelope

    # =========================================================================
    # VERIFY Operation
    # =========================================================================

    async def verify(
        self,
        agent_id: str,
        action: str,
        resource: Optional[str] = None,
        level: VerificationLevel = VerificationLevel.STANDARD,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        VERIFY: Check if agent has trust to perform action.

        This is the primary trust verification operation, called before
        every agent action to ensure trust requirements are met.

        Verification Levels:
        - QUICK (~1ms): Hash and expiration check only
        - STANDARD (~5ms): + Capability and constraint validation
        - FULL (~50ms): + Cryptographic signature verification

        Args:
            agent_id: Agent requesting to act
            action: Action to perform
            resource: Optional resource being accessed
            level: Verification thoroughness
            context: Additional context for constraint evaluation

        Returns:
            VerificationResult: Whether action is permitted

        Note:
            This operation is designed for high performance as it's
            called before every agent action.
        """
        context = context or {}

        # 1. Get agent's trust chain
        try:
            chain = await self.trust_store.get_chain(agent_id)
        except TrustChainNotFoundError:
            return VerificationResult(
                valid=False,
                reason="No trust chain found",
                level=level,
            )

        # QUICK level: Just check hash and expiration
        if level == VerificationLevel.QUICK:
            return await self._verify_quick(chain, level)

        # STANDARD level: Check capabilities and constraints
        capability = self._match_capability(chain, action)
        if not capability:
            return VerificationResult(
                valid=False,
                reason=f"No capability found for action '{action}'",
                level=level,
            )

        # Evaluate constraints
        constraint_result = self._evaluate_constraints(
            chain.constraint_envelope,
            action,
            resource,
            context,
        )

        if not constraint_result.permitted:
            return VerificationResult(
                valid=False,
                reason="Constraint violation",
                violations=constraint_result.violations,
                level=level,
            )

        # Reasoning trace verification (implemented in Phase 4)
        # Check if REASONING_REQUIRED constraint is active
        reasoning_required = any(
            c.constraint_type == ConstraintType.REASONING_REQUIRED for c in chain.constraint_envelope.active_constraints
        )

        reasoning_present: Optional[bool] = None
        reasoning_verified: Optional[bool] = None
        reasoning_violations: List[Dict[str, str]] = []

        if reasoning_required:
            reasoning_present = self._check_reasoning_presence(chain)

            # Bug fix: record non-blocking violation when reasoning is required
            # but missing (spec says "recorded in the violations list as a
            # non-blocking finding")
            if reasoning_present is False:
                reasoning_violations.append(
                    {
                        "constraint_type": "reasoning_required",
                        "severity": "warning",
                        "reason": (
                            "REASONING_REQUIRED constraint active but no "
                            "reasoning trace found on delegation/audit records"
                        ),
                    }
                )

        # FULL level: Also verify all signatures
        if level == VerificationLevel.FULL:
            # At FULL level, REASONING_REQUIRED is a hard constraint:
            # if active and no reasoning trace present, verification MUST fail.
            if reasoning_required and reasoning_present is False:
                return VerificationResult(
                    valid=False,
                    reason=(
                        "REASONING_REQUIRED constraint active but no reasoning "
                        "trace present (hard failure at FULL verification level)"
                    ),
                    violations=reasoning_violations,
                    level=level,
                    reasoning_present=False,
                    reasoning_verified=False,
                )

            # Verify reasoning hash + signature BEFORE delegation signatures
            # (reasoning integrity is a separate, cheaper check).
            # Always verify crypto integrity when traces are present, regardless
            # of REASONING_REQUIRED constraint. The constraint controls whether
            # ABSENCE is a violation; forged traces should always be caught.
            has_any_reasoning = self._check_reasoning_presence(chain)
            if has_any_reasoning:
                reasoning_check = await self._verify_reasoning_traces(chain)
                reasoning_verified = reasoning_check.valid
                if not reasoning_check.valid:
                    return VerificationResult(
                        valid=False,
                        reason=reasoning_check.reason,
                        violations=reasoning_violations,
                        level=level,
                        reasoning_present=reasoning_present,
                        reasoning_verified=False,
                    )

            signature_result = await self._verify_signatures(chain)
            if not signature_result.valid:
                return signature_result

        return VerificationResult(
            valid=True,
            level=level,
            capability_used=capability.id,
            effective_constraints=chain.get_effective_constraints(capability.capability),
            violations=reasoning_violations,
            reasoning_present=reasoning_present,
            reasoning_verified=reasoning_verified,
        )

    async def _verify_quick(
        self,
        chain: TrustLineageChain,
        level: VerificationLevel,
    ) -> VerificationResult:
        """
        Perform quick verification (expiration check only).

        Args:
            chain: Trust chain to verify
            level: Verification level

        Returns:
            VerificationResult
        """
        if chain.is_expired():
            return VerificationResult(
                valid=False,
                reason="Trust chain expired",
                level=level,
            )

        return VerificationResult(
            valid=True,
            level=level,
        )

    def _check_reasoning_presence(
        self,
        chain: TrustLineageChain,
    ) -> Optional[bool]:
        """
        Check if reasoning traces are present on delegation records and audit anchors.

        Returns None if there are no delegations or audit anchors to check,
        True if all records have reasoning traces, False if any record is missing one.

        Args:
            chain: Trust chain to check

        Returns:
            None if no records to check, True if all present, False if any missing
        """
        records_to_check = []
        records_to_check.extend(chain.delegations)
        records_to_check.extend(chain.audit_anchors)

        if not records_to_check:
            return None

        for record in records_to_check:
            if record.reasoning_trace is None:
                return False

        return True

    async def _verify_reasoning_traces(
        self,
        chain: TrustLineageChain,
    ) -> VerificationResult:
        """
        Verify reasoning trace hashes and signatures on all records in a chain.

        For each delegation and audit anchor that has a reasoning trace:
        1. Verify reasoning_trace_hash matches hash_reasoning_trace(reasoning_trace)
        2. Verify reasoning_signature is present
        3. Verify reasoning_signature cryptographically against the authority's
           public key (Ed25519)

        Args:
            chain: Trust chain to verify

        Returns:
            VerificationResult with reasoning verification status
        """
        from kailash.trust.signing.crypto import hash_reasoning_trace

        # Resolve the authority's public key for cryptographic verification.
        # Same pattern used in _verify_signatures().
        authority = await self.authority_registry.get_authority(
            chain.genesis.authority_id,
            include_inactive=True,
        )

        # Check delegations
        for delegation in chain.delegations:
            if delegation.reasoning_trace is not None:
                # Verify hash
                expected_hash = hash_reasoning_trace(delegation.reasoning_trace)
                if delegation.reasoning_trace_hash != expected_hash:
                    return VerificationResult(
                        valid=False,
                        reason=(f"Reasoning trace hash mismatch on delegation {delegation.id}"),
                        level=VerificationLevel.FULL,
                        reasoning_verified=False,
                    )

                # Verify signature presence
                if delegation.reasoning_signature is None:
                    return VerificationResult(
                        valid=False,
                        reason=(f"Reasoning signature missing on delegation {delegation.id}"),
                        level=VerificationLevel.FULL,
                        reasoning_verified=False,
                    )

                # Cryptographically verify reasoning signature against
                # authority's public key, bound to the delegation record ID
                try:
                    reasoning_payload = serialize_for_signing(
                        {
                            "parent_record_id": delegation.id,
                            "reasoning": delegation.reasoning_trace.to_signing_payload(),
                        }
                    )
                    sig_valid = verify_signature(
                        reasoning_payload,
                        delegation.reasoning_signature,
                        authority.public_key,
                    )
                except InvalidSignatureError:
                    sig_valid = False

                if not sig_valid:
                    return VerificationResult(
                        valid=False,
                        reason=(f"Reasoning signature cryptographic verification failed on delegation {delegation.id}"),
                        level=VerificationLevel.FULL,
                        reasoning_verified=False,
                    )

        # Check audit anchors
        for anchor in chain.audit_anchors:
            if anchor.reasoning_trace is not None:
                # Verify hash
                expected_hash = hash_reasoning_trace(anchor.reasoning_trace)
                if anchor.reasoning_trace_hash != expected_hash:
                    return VerificationResult(
                        valid=False,
                        reason=(f"Reasoning trace hash mismatch on audit anchor {anchor.id}"),
                        level=VerificationLevel.FULL,
                        reasoning_verified=False,
                    )

                # Verify signature presence
                if anchor.reasoning_signature is None:
                    return VerificationResult(
                        valid=False,
                        reason=(f"Reasoning signature missing on audit anchor {anchor.id}"),
                        level=VerificationLevel.FULL,
                        reasoning_verified=False,
                    )

                # Cryptographically verify reasoning signature against
                # authority's public key, bound to the audit anchor ID
                try:
                    reasoning_payload = serialize_for_signing(
                        {
                            "parent_record_id": anchor.id,
                            "reasoning": anchor.reasoning_trace.to_signing_payload(),
                        }
                    )
                    sig_valid = verify_signature(
                        reasoning_payload,
                        anchor.reasoning_signature,
                        authority.public_key,
                    )
                except InvalidSignatureError:
                    sig_valid = False

                if not sig_valid:
                    return VerificationResult(
                        valid=False,
                        reason=(f"Reasoning signature cryptographic verification failed on audit anchor {anchor.id}"),
                        level=VerificationLevel.FULL,
                        reasoning_verified=False,
                    )

        return VerificationResult(
            valid=True,
            level=VerificationLevel.FULL,
            reasoning_verified=True,
        )

    def _match_capability(
        self,
        chain: TrustLineageChain,
        action: str,
    ) -> Optional[CapabilityAttestation]:
        """
        Match an action to a capability using multiple matching strategies.

        Matching strategies (in order):
        1. Direct match: action == capability name
        2. Hierarchical match: "read_users" matches "read_*"
        3. Semantic match: Future - using embeddings

        Args:
            chain: Trust chain to search
            action: Action to match

        Returns:
            Matching CapabilityAttestation or None
        """
        # Direct match
        for cap in chain.capabilities:
            if cap.capability == action:
                if not cap.is_expired():
                    return cap

        # Hierarchical match (wildcard patterns)
        for cap in chain.capabilities:
            if self._capability_matches_pattern(cap.capability, action):
                if not cap.is_expired():
                    return cap

        return None

    def _capability_matches_pattern(
        self,
        pattern: str,
        action: str,
    ) -> bool:
        """
        Check if action matches capability pattern.

        Supports wildcards:
        - "read_*" matches "read_users", "read_data"
        - "*_admin" matches "user_admin", "system_admin"
        - "*" matches everything

        Args:
            pattern: Capability pattern (may include *)
            action: Action to match

        Returns:
            True if action matches pattern
        """
        if pattern == "*":
            return True

        if "*" not in pattern:
            return pattern == action

        # Simple wildcard matching
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return action.startswith(prefix)

        if pattern.startswith("*"):
            suffix = pattern[1:]
            return action.endswith(suffix)

        # Middle wildcard (e.g., "read_*_data")
        parts = pattern.split("*")
        if len(parts) == 2:
            return action.startswith(parts[0]) and action.endswith(parts[1])

        return False

    def _evaluate_constraints(
        self,
        envelope: ConstraintEnvelope,
        action: str,
        resource: Optional[str],
        context: Dict[str, Any],
    ) -> ConstraintEvaluationResult:
        """
        Evaluate constraints for an action.

        Args:
            envelope: Constraint envelope
            action: Action being performed
            resource: Resource being accessed
            context: Additional context

        Returns:
            ConstraintEvaluationResult
        """
        violations = []

        # Check if envelope is valid
        if not envelope.is_valid():
            return ConstraintEvaluationResult(
                permitted=False,
                violations=[{"constraint": "envelope", "reason": "Constraint envelope expired"}],
            )

        # Evaluate each constraint
        for constraint in envelope.active_constraints:
            result = self._evaluate_single_constraint(
                constraint,
                action,
                resource,
                context,
            )
            if not result["permitted"]:
                violations.append(
                    {
                        "constraint_id": constraint.id,
                        "constraint_value": str(constraint.value),
                        "reason": result["reason"],
                    }
                )

        return ConstraintEvaluationResult(
            permitted=len(violations) == 0,
            violations=violations,
        )

    def _evaluate_single_constraint(
        self,
        constraint: Constraint,
        action: str,
        resource: Optional[str],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate a single constraint.

        Built-in constraint evaluators:
        - time_window: Check if current time is within allowed window
        - rate_limit: Check if rate limit is exceeded
        - resource_access: Check if resource access is allowed
        - read_only: Ensure only read operations

        Args:
            constraint: Constraint to evaluate
            action: Action being performed
            resource: Resource being accessed
            context: Additional context

        Returns:
            Dict with 'permitted' bool and optional 'reason'
        """
        # Get constraint value as string for matching
        value = str(constraint.value).lower()

        # Time window constraint
        if value == "business_hours_only" or value.startswith("time_window"):
            current_time = context.get("current_time", datetime.now(timezone.utc))
            if isinstance(current_time, datetime):
                hour = current_time.hour
                if hour < 9 or hour >= 17:  # 9 AM to 5 PM
                    return {
                        "permitted": False,
                        "reason": f"Action not permitted outside business hours (current hour: {hour})",
                    }

        # Read-only constraint
        if value == "read_only":
            write_actions = ["write", "update", "delete", "create", "modify"]
            for wa in write_actions:
                if wa in action.lower():
                    return {
                        "permitted": False,
                        "reason": f"Write action '{action}' not permitted under read_only constraint",
                    }

        # Audit required (always passes, but logs)
        if value == "audit_required":
            # This constraint doesn't block, just requires audit
            pass

        # No PII export constraint
        if value == "no_pii_export":
            if "export" in action.lower() and context.get("contains_pii", False):
                return {
                    "permitted": False,
                    "reason": "Cannot export data containing PII",
                }

        # Default: permit if constraint not recognized
        return {"permitted": True}

    async def _verify_signatures(
        self,
        chain: TrustLineageChain,
    ) -> VerificationResult:
        """
        Verify all signatures in a trust chain.

        Args:
            chain: Trust chain to verify

        Returns:
            VerificationResult
        """
        # Verify genesis signature
        authority = await self.authority_registry.get_authority(
            chain.genesis.authority_id,
            include_inactive=True,  # Allow inactive for historical verification
        )

        genesis_payload = serialize_for_signing(chain.genesis.to_signing_payload())
        if not await self.key_manager.verify(
            genesis_payload,
            chain.genesis.signature,
            authority.public_key,
        ):
            return VerificationResult(
                valid=False,
                reason="Invalid genesis signature",
                level=VerificationLevel.FULL,
            )

        # Verify capability signatures
        for cap in chain.capabilities:
            cap_payload = serialize_for_signing(cap.to_signing_payload())
            if not await self.key_manager.verify(
                cap_payload,
                cap.signature,
                authority.public_key,
            ):
                return VerificationResult(
                    valid=False,
                    reason=f"Invalid capability signature: {cap.id}",
                    level=VerificationLevel.FULL,
                )

        # Verify delegation signatures (CARE-002)
        for delegation in chain.delegations:
            # For delegations, we need the delegator's chain to get the authority
            try:
                delegator_chain = await self.trust_store.get_chain(delegation.delegator_id)
                # Verify delegation signature using the authority's key
                result = await self._verify_delegation_signature(delegation, delegator_chain)
                if not result.valid:
                    return result
            except TrustChainNotFoundError:
                return VerificationResult(
                    valid=False,
                    reason=f"Delegator chain not found: {delegation.delegator_id}",
                    level=VerificationLevel.FULL,
                )

        return VerificationResult(
            valid=True,
            level=VerificationLevel.FULL,
        )

    async def _verify_delegation_signature(
        self,
        delegation: DelegationRecord,
        delegator_chain: TrustLineageChain,
    ) -> VerificationResult:
        """
        Verify a single delegation signature (CARE-002).

        This method performs cryptographic verification of delegation signatures
        to ensure delegations have not been tampered with and were properly
        authorized by the delegating authority.

        Args:
            delegation: The DelegationRecord to verify
            delegator_chain: The trust chain of the delegator

        Returns:
            VerificationResult indicating whether the signature is valid

        Note:
            Delegation signatures are verified using the authority's key that
            established the delegator's trust chain. This ensures the delegation
            was properly signed by an authorized entity.
        """
        # Get the authority that established the delegator
        authority = await self.authority_registry.get_authority(
            delegator_chain.genesis.authority_id,
            include_inactive=True,  # Allow inactive for historical verification
        )

        # Build signing payload from delegation
        del_payload = serialize_for_signing(delegation.to_signing_payload())

        # Verify signature using authority's key
        if not verify_signature(del_payload, delegation.signature, authority.public_key):
            return VerificationResult(
                valid=False,
                reason=f"Invalid delegation signature: {delegation.id}",
                level=VerificationLevel.FULL,
            )

        return VerificationResult(valid=True, level=VerificationLevel.FULL)

    async def verify_delegation_chain(
        self,
        agent_id: str,
    ) -> VerificationResult:
        """
        Verify all delegation signatures from human origin to current agent (CARE-002).

        This method traverses the delegation chain for an agent and verifies
        each delegation signature cryptographically. This ensures:
        - All delegations in the chain are authentic
        - No delegations have been tampered with
        - The trust chain is unbroken from human origin

        Args:
            agent_id: The agent whose delegation chain to verify

        Returns:
            VerificationResult indicating whether all delegation signatures are valid

        Raises:
            TrustChainNotFoundError: If the agent's trust chain is not found

        Example:
            >>> # Verify delegation chain for agent-C
            >>> result = await trust_ops.verify_delegation_chain("agent-C")
            >>> if result.valid:
            ...     print("All delegations verified")
            ... else:
            ...     print(f"Verification failed: {result.reason}")
        """
        chain = await self.trust_store.get_chain(agent_id)

        # Agent with no delegations passes verification
        if not chain.delegations:
            return VerificationResult(valid=True, level=VerificationLevel.FULL)

        # Verify each delegation in the chain
        for delegation in chain.delegations:
            try:
                delegator_chain = await self.trust_store.get_chain(delegation.delegator_id)
                result = await self._verify_delegation_signature(delegation, delegator_chain)
                if not result.valid:
                    return result
            except TrustChainNotFoundError:
                return VerificationResult(
                    valid=False,
                    reason=f"Delegator chain not found: {delegation.delegator_id}",
                    level=VerificationLevel.FULL,
                )

        return VerificationResult(valid=True, level=VerificationLevel.FULL)

    # =========================================================================
    # Helper methods for integration
    # =========================================================================

    async def get_agent_capabilities(
        self,
        agent_id: str,
    ) -> List[str]:
        """
        Get list of capability names for an agent.

        Args:
            agent_id: Agent to query

        Returns:
            List of capability names

        Raises:
            TrustChainNotFoundError: If agent has no trust chain
        """
        chain = await self.trust_store.get_chain(agent_id)
        return [cap.capability for cap in chain.capabilities if not cap.is_expired()]

    def _calculate_delegation_depth(self, chain: TrustLineageChain) -> int:
        """
        Calculate delegation depth from human origin.

        CARE-004: This method calculates how deep in the delegation chain
        an agent is from the original human authority.

        Args:
            chain: Trust chain to calculate depth for

        Returns:
            Depth from human origin (0 = no delegations, 1+ = delegated agents)
        """
        if not chain.delegations:
            return 0
        return len(chain.get_delegation_chain())

    def _get_parent_constraint_dict(self, chain: TrustLineageChain) -> Dict[str, Any]:
        """
        Extract constraint dictionary from a trust chain for inheritance validation.

        CARE-009: Converts the chain's constraint envelope into a dictionary
        format suitable for constraint inheritance validation.

        Args:
            chain: Trust chain to extract constraints from

        Returns:
            Dictionary of constraint name -> value mappings
        """
        constraint_dict: Dict[str, Any] = {}

        # Extract constraints from the constraint envelope
        for constraint in chain.constraint_envelope.active_constraints:
            value_str = str(constraint.value).lower()

            # Parse common constraint patterns
            if "=" in value_str:
                # Format: "cost_limit=1000"
                parts = value_str.split("=", 1)
                key = parts[0].strip()
                try:
                    constraint_dict[key] = float(parts[1].strip())
                except ValueError:
                    constraint_dict[key] = parts[1].strip()
            elif ":" in value_str and not value_str.count(":") == 2:
                # Format: "key:value" but not time format
                parts = value_str.split(":", 1)
                key = parts[0].strip()
                constraint_dict[key] = parts[1].strip()
            else:
                # Store as-is for string constraints
                constraint_dict[value_str] = True

        # Also extract from genesis metadata if present
        genesis_meta = chain.genesis.metadata or {}
        if "constraints" in genesis_meta:
            for c in genesis_meta["constraints"]:
                if isinstance(c, dict):
                    constraint_dict.update(c)
                elif isinstance(c, str):
                    constraint_dict[c] = True

        return constraint_dict

    # =========================================================================
    # DELEGATE Operation
    # =========================================================================

    async def delegate(
        self,
        delegator_id: str,
        delegatee_id: str,
        task_id: str,
        capabilities: List[str],
        additional_constraints: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        context: Optional[ExecutionContext] = None,  # EATP: ExecutionContext parameter
        reasoning_trace: Optional[Any] = None,  # EATP: ReasoningTrace for WHY
    ) -> DelegationRecord:
        """
        DELEGATE: Transfer trust from one agent to another.

        Delegation enables agents to work together by allowing one agent
        (delegator) to temporarily grant a subset of its capabilities to
        another agent (delegatee) for a specific task.

        EATP Enhancement: Now accepts and propagates ExecutionContext.
        The human_origin from the context is stored in the delegation record.

        Key constraints:
        - Delegator can only delegate capabilities they possess
        - Delegatee's constraints can only be TIGHTER than delegator's
        - Delegations are time-limited and task-scoped
        - All delegations are cryptographically signed

        Args:
            delegator_id: Agent delegating trust
            delegatee_id: Agent receiving delegated trust
            task_id: Unique identifier for the delegated task
            capabilities: Capability names to delegate (subset of delegator's)
            additional_constraints: Additional constraints for delegatee
            expires_at: When delegation expires
            metadata: Additional context
            context: EATP ExecutionContext with human_origin (REQUIRED for new delegations)

        Returns:
            DelegationRecord: Signed delegation record with human_origin

        Raises:
            TrustChainNotFoundError: If delegator has no trust chain
            CapabilityNotFoundError: If capability not in delegator's chain
            DelegationError: If delegation violates constraints
        """
        additional_constraints = additional_constraints or []
        metadata = metadata or {}

        # EATP: Get context from parameter or context variable
        ctx = context or get_current_context()

        # EATP: Extract human origin information
        human_origin = None
        delegation_chain: List[str] = []
        delegation_depth = 0

        if ctx:
            human_origin = ctx.human_origin
            delegation_chain = ctx.delegation_chain + [delegatee_id]
            delegation_depth = ctx.delegation_depth + 1

        # 1. Get delegator's trust chain
        try:
            delegator_chain = await self.trust_store.get_chain(delegator_id)
        except TrustChainNotFoundError:
            raise TrustChainNotFoundError(delegator_id)

        # 2. Verify delegator has all requested capabilities
        delegator_caps = {cap.capability for cap in delegator_chain.capabilities}
        for requested_cap in capabilities:
            # Use pattern matching for wildcard capabilities
            if not any(self._capability_matches_pattern(dc, requested_cap) for dc in delegator_caps):
                raise CapabilityNotFoundError(
                    requested_cap,
                    f"Delegator {delegator_id} does not have capability '{requested_cap}'",
                )

        # 3. Verify delegator's trust is not expired
        if delegator_chain.is_expired():
            raise DelegationError(
                "Delegator's trust chain is expired",
                delegator_id=delegator_id,
                delegatee_id=delegatee_id,
            )

        # 4. Verify delegator can delegate (not explicitly restricted)
        delegator_constraints = [str(c.value).lower() for c in delegator_chain.constraint_envelope.active_constraints]
        if "no_delegation" in delegator_constraints:
            raise DelegationError(
                "Delegator is restricted from delegating trust",
                delegator_id=delegator_id,
                delegatee_id=delegatee_id,
            )

        # 4b. CARE-004: Enforce maximum delegation depth
        # Prevents DoS attacks through deep delegation chains and
        # ensures traceability can be maintained back to human origin.
        current_depth = self._calculate_delegation_depth(delegator_chain)
        new_depth = current_depth + 1
        if new_depth > self.max_delegation_depth:
            raise DelegationError(
                f"Delegation would create depth {new_depth}, exceeding "
                f"maximum {self.max_delegation_depth}. "
                f"Delegator '{delegator_id}' is already at depth "
                f"{current_depth}. Cannot delegate to '{delegatee_id}'.",
                delegator_id=delegator_id,
                delegatee_id=delegatee_id,
            )

        # 4c. CARE-009: Validate constraint inheritance (tightening-only rule)
        # Child constraints must be strictly tighter than or equal to parent's.
        # This prevents widening attacks where delegated agents gain more
        # permissions than their delegators.
        if "constraint_overrides" in metadata:
            child_constraint_dict = metadata["constraint_overrides"]
            parent_constraint_dict = self._get_parent_constraint_dict(delegator_chain)

            constraint_validator = ConstraintValidator()
            inheritance_result = constraint_validator.validate_inheritance(
                parent_constraints=parent_constraint_dict,
                child_constraints=child_constraint_dict,
            )

            if not inheritance_result.valid:
                violations_str = ", ".join(f"{v.value}" for v in inheritance_result.violations)
                details_str = "; ".join(f"{k}: {v}" for k, v in inheritance_result.details.items())
                raise ConstraintViolationError(
                    f"Delegation violates constraint inheritance: {violations_str}. Details: {details_str}",
                    violations=[
                        {
                            "type": v.value,
                            "detail": inheritance_result.details.get(
                                v.value.replace("_increased", "").replace("_expanded", "").replace("_removed", ""),
                                "",
                            ),
                        }
                        for v in inheritance_result.violations
                    ],
                    agent_id=delegatee_id,
                    action="delegate",
                )

        # 5. Build constraint subset (tightening only)
        # Start with delegator's constraints, add additional ones (deduplicated, order-preserved)
        seen_constraints: set = set()
        constraint_subset: list = []
        for c in list(delegator_constraints) + additional_constraints:
            if c not in seen_constraints:
                seen_constraints.add(c)
                constraint_subset.append(c)

        # 6. Calculate delegation expiry (can't exceed delegator's)
        if delegator_chain.genesis.expires_at:
            if expires_at is None:
                expires_at = delegator_chain.genesis.expires_at
            else:
                expires_at = min(expires_at, delegator_chain.genesis.expires_at)

        # 7. Create DelegationRecord with EATP fields
        delegation = DelegationRecord(
            id=f"del-{uuid4()}",
            delegator_id=delegator_id,
            delegatee_id=delegatee_id,
            task_id=task_id,
            capabilities_delegated=capabilities,
            constraint_subset=constraint_subset,
            delegated_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            signature="",  # Will be signed below
            # EATP fields
            human_origin=human_origin,
            delegation_chain=delegation_chain,
            delegation_depth=delegation_depth,
            # Reasoning trace extension (optional)
            reasoning_trace=reasoning_trace,
        )

        logger.info(
            f"Delegation created: {delegator_id} -> {delegatee_id} "
            f"(human_origin: {human_origin.human_id if human_origin else 'N/A'})"
        )

        # 8a. Compute reasoning trace hash BEFORE signing the record
        # (reasoning_trace_hash is part of the signing payload)
        if reasoning_trace:
            from kailash.trust.signing.crypto import hash_reasoning_trace

            delegation.reasoning_trace_hash = hash_reasoning_trace(reasoning_trace)

        # 8b. Sign the delegation record
        # Use the authority's key that established the delegator
        authority_id = delegator_chain.genesis.authority_id
        authority = await self.authority_registry.get_authority(authority_id)

        delegation_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = await self.key_manager.sign(
            delegation_payload,
            authority.signing_key_id,
        )

        # 8c. Sign reasoning trace separately (if provided)
        if reasoning_trace:
            reasoning_payload = serialize_for_signing(
                {
                    "parent_record_id": delegation.id,
                    "reasoning": reasoning_trace.to_signing_payload(),
                }
            )
            delegation.reasoning_signature = await self.key_manager.sign(
                reasoning_payload,
                authority.signing_key_id,
            )

        # 9. Get or create delegatee's trust chain
        try:
            delegatee_chain = await self.trust_store.get_chain(delegatee_id)
            # Add delegation to existing chain
            delegatee_chain.delegations.append(delegation)
            # Recompute constraint envelope
            delegatee_chain.constraint_envelope = self._compute_constraint_envelope(
                agent_id=delegatee_id,
                genesis=delegatee_chain.genesis,
                capabilities=delegatee_chain.capabilities,
                delegations=delegatee_chain.delegations,
            )
            await self.trust_store.update_chain(delegatee_id, delegatee_chain)
        except TrustChainNotFoundError:
            # Create a derived chain for the delegatee
            # The delegatee inherits trust through delegation, not direct establishment
            derived_genesis = GenesisRecord(
                id=f"gen-{uuid4()}",
                agent_id=delegatee_id,
                authority_id=authority_id,
                authority_type=delegator_chain.genesis.authority_type,
                created_at=datetime.now(timezone.utc),
                expires_at=expires_at,
                signature="",
                signature_algorithm="Ed25519",
                metadata={
                    "derived_from": delegator_id,
                    "delegation_id": delegation.id,
                },
            )

            # Sign derived genesis
            genesis_payload = serialize_for_signing(derived_genesis.to_signing_payload())
            derived_genesis.signature = await self.key_manager.sign(
                genesis_payload,
                authority.signing_key_id,
            )

            # Create capability attestations for delegated capabilities
            derived_capabilities = []
            for cap_name in capabilities:
                # Find matching capability from delegator
                source_cap = next(
                    (
                        c
                        for c in delegator_chain.capabilities
                        if self._capability_matches_pattern(c.capability, cap_name)
                    ),
                    None,
                )
                if source_cap:
                    derived_cap = CapabilityAttestation(
                        id=f"cap-{uuid4()}",
                        capability=cap_name,
                        capability_type=source_cap.capability_type,
                        constraints=constraint_subset,
                        attester_id=authority_id,
                        attested_at=datetime.now(timezone.utc),
                        expires_at=expires_at,
                        signature="",
                        scope=source_cap.scope,
                    )
                    cap_payload = serialize_for_signing(derived_cap.to_signing_payload())
                    derived_cap.signature = await self.key_manager.sign(
                        cap_payload,
                        authority.signing_key_id,
                    )
                    derived_capabilities.append(derived_cap)

            # Compute constraint envelope
            constraint_envelope = self._compute_constraint_envelope(
                agent_id=delegatee_id,
                genesis=derived_genesis,
                capabilities=derived_capabilities,
                delegations=[delegation],
            )

            # Create and store the derived chain
            delegatee_chain = TrustLineageChain(
                genesis=derived_genesis,
                capabilities=derived_capabilities,
                delegations=[delegation],
                constraint_envelope=constraint_envelope,
                audit_anchors=[],
            )
            await self.trust_store.store_chain(delegatee_chain, expires_at)

        return delegation

    # =========================================================================
    # AUDIT Operation
    # =========================================================================

    async def audit(
        self,
        agent_id: str,
        action: str,
        resource: Optional[str] = None,
        result: ActionResult = ActionResult.SUCCESS,
        context_data: Optional[Dict[str, Any]] = None,
        parent_anchor_id: Optional[str] = None,
        audit_store: Optional[Any] = None,
        context: Optional[ExecutionContext] = None,  # EATP: ExecutionContext parameter
        reasoning_trace: Optional[Any] = None,  # EATP: ReasoningTrace for WHY
    ) -> AuditAnchor:
        """
        AUDIT: Record an agent action in the audit trail.

        Every agent action that passes verification should be recorded
        in the audit trail for compliance and forensic analysis.

        EATP Enhancement: Now includes human_origin in audit records.
        Every audit record can answer "which human authorized this action?"

        Key features:
        - Append-only (immutable audit trail)
        - Cryptographically signed
        - Chain-linked via parent_anchor_id for causality
        - Includes trust chain hash for tamper detection
        - EATP: Includes human_origin for traceability

        Args:
            agent_id: Agent that performed the action
            action: Action that was performed
            resource: Resource that was accessed
            result: Outcome of the action
            context_data: Additional context (tool calls, inputs, etc.)
            parent_anchor_id: Link to parent action (for causal chains)
            audit_store: Optional audit store (uses default if not provided)
            context: EATP ExecutionContext with human_origin

        Returns:
            AuditAnchor: The recorded audit anchor with human_origin

        Raises:
            TrustChainNotFoundError: If agent has no trust chain
            AuditStoreError: If audit storage fails
        """
        context_data = context_data or {}

        # EATP: Get context from parameter or context variable
        ctx = context or get_current_context()

        # 1. Get agent's trust chain
        try:
            chain = await self.trust_store.get_chain(agent_id)
        except TrustChainNotFoundError:
            raise TrustChainNotFoundError(agent_id)

        # 2. Compute current trust chain hash
        trust_chain_hash = hash_chain(chain.to_dict())

        # 3. Create audit anchor with EATP human_origin
        anchor = AuditAnchor(
            id=f"aud-{uuid4()}",
            agent_id=agent_id,
            action=action,
            resource=resource,
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash=trust_chain_hash,
            result=result,
            parent_anchor_id=parent_anchor_id,
            signature="",  # Will be signed below
            context=context_data,
            # EATP field
            human_origin=ctx.human_origin if ctx else None,
            # Reasoning trace extension (optional)
            reasoning_trace=reasoning_trace,
        )

        logger.info(
            f"Audit anchor created: {agent_id} -> {action} on {resource} "
            f"(human_origin: {anchor.human_origin.human_id if anchor.human_origin else 'N/A'})"
        )

        # 4a. Compute reasoning trace hash BEFORE signing the record
        # (reasoning_trace_hash is part of the signing payload)
        if reasoning_trace:
            from kailash.trust.signing.crypto import hash_reasoning_trace

            anchor.reasoning_trace_hash = hash_reasoning_trace(reasoning_trace)

        # 4b. Sign the audit anchor
        authority_id = chain.genesis.authority_id
        authority = await self.authority_registry.get_authority(authority_id)

        anchor_payload = serialize_for_signing(anchor.to_signing_payload())
        anchor.signature = await self.key_manager.sign(
            anchor_payload,
            authority.signing_key_id,
        )

        # 4c. Sign reasoning trace separately (if provided)
        if reasoning_trace:
            reasoning_payload = serialize_for_signing(
                {
                    "parent_record_id": anchor.id,
                    "reasoning": reasoning_trace.to_signing_payload(),
                }
            )
            anchor.reasoning_signature = await self.key_manager.sign(
                reasoning_payload,
                authority.signing_key_id,
            )

        # 5. Store in audit store (if provided)
        if audit_store:
            await audit_store.append(anchor)

        # 6. Add to chain's audit anchors (in-memory)
        chain.audit_anchors.append(anchor)

        return anchor

    # =========================================================================
    # Helper methods for integration
    # =========================================================================

    async def get_agent_capabilities(
        self,
        agent_id: str,
    ) -> List[str]:
        """
        Get list of capability names for an agent.

        Args:
            agent_id: Agent to query

        Returns:
            List of capability names

        Raises:
            TrustChainNotFoundError: If agent has no trust chain
        """
        chain = await self.trust_store.get_chain(agent_id)
        return [cap.capability for cap in chain.capabilities if not cap.is_expired()]

    async def get_agent_constraints(
        self,
        agent_id: str,
    ) -> List[str]:
        """
        Get list of all constraint names for an agent.

        Args:
            agent_id: Agent to query

        Returns:
            List of constraint names

        Raises:
            TrustChainNotFoundError: If agent has no trust chain
        """
        chain = await self.trust_store.get_chain(agent_id)
        return [str(c.value) for c in chain.constraint_envelope.active_constraints]

    async def revoke_trust(
        self,
        agent_id: str,
        reason: Optional[str] = None,
    ) -> None:
        """
        Revoke trust for an agent (soft delete).

        Args:
            agent_id: Agent to revoke
            reason: Optional reason for revocation

        Raises:
            TrustChainNotFoundError: If agent has no trust chain
        """
        await self.trust_store.delete_chain(agent_id, soft_delete=True)

    async def get_delegation_chain(
        self,
        agent_id: str,
    ) -> List[DelegationRecord]:
        """
        Get all delegations for an agent.

        Args:
            agent_id: Agent to query

        Returns:
            List of DelegationRecords

        Raises:
            TrustChainNotFoundError: If agent has no trust chain
        """
        chain = await self.trust_store.get_chain(agent_id)
        return chain.delegations

    async def revoke_delegation(
        self,
        delegation_id: str,
        delegatee_id: str,
    ) -> None:
        """
        Revoke a specific delegation.

        Args:
            delegation_id: Delegation to revoke
            delegatee_id: Agent whose delegation to revoke

        Raises:
            TrustChainNotFoundError: If agent has no trust chain
            DelegationError: If delegation not found
        """
        chain = await self.trust_store.get_chain(delegatee_id)

        # Find and remove the delegation
        found = False
        for i, delegation in enumerate(chain.delegations):
            if delegation.id == delegation_id:
                chain.delegations.pop(i)
                found = True
                break

        if not found:
            raise DelegationError(
                f"Delegation {delegation_id} not found for agent {delegatee_id}",
                delegator_id="unknown",
                delegatee_id=delegatee_id,
            )

        # Recompute constraint envelope
        chain.constraint_envelope = self._compute_constraint_envelope(
            agent_id=delegatee_id,
            genesis=chain.genesis,
            capabilities=chain.capabilities,
            delegations=chain.delegations,
        )

        await self.trust_store.update_chain(delegatee_id, chain)

    # =========================================================================
    # EATP Cascade Revocation Operations
    # =========================================================================

    async def revoke_cascade(
        self,
        agent_id: str,
        reason: str,
    ) -> List[str]:
        """
        Revoke trust for an agent and CASCADE to all delegated agents.

        EATP Requirement: When trust is revoked, ALL downstream delegations
        must be immediately invalidated.

        This operation performs a breadth-first revocation, revoking the
        specified agent and all agents that received delegations from it,
        recursively.

        Args:
            agent_id: ID of the agent to revoke
            reason: Reason for revocation (for audit trail)

        Returns:
            List of all agent IDs that were revoked

        Example:
            >>> # Setup: Alice -> Agent A -> Agent B
            >>> #                        -> Agent C
            >>> #       -> Agent D
            >>>
            >>> # Revoking Agent A revokes A, B, C (but not D)
            >>> revoked = await trust_ops.revoke_cascade("agent-a", "test")
            >>> assert "agent-a" in revoked
            >>> assert "agent-b" in revoked
            >>> assert "agent-c" in revoked
            >>> assert "agent-d" not in revoked
        """
        revoked_agents: List[str] = []

        # Revoke this agent
        try:
            await self.trust_store.delete_chain(agent_id, soft_delete=True)
            revoked_agents.append(agent_id)
            logger.warning(f"Revoked trust for agent {agent_id}: {reason}")
        except TrustChainNotFoundError:
            # Agent doesn't exist - nothing to revoke
            return revoked_agents

        # Find all delegations FROM this agent
        try:
            chain = await self.trust_store.get_chain(agent_id)
            # Look for agents that have delegations from this agent
            # We need to scan all chains for delegations where delegator_id matches
            all_chains = await self.trust_store.list_chains()

            delegatee_ids = []
            for other_chain in all_chains:
                for delegation in other_chain.delegations:
                    if delegation.delegator_id == agent_id:
                        delegatee_ids.append(delegation.delegatee_id)

            # Recursively revoke (in parallel for performance)
            if delegatee_ids:
                cascade_tasks = [
                    self.revoke_cascade(delegatee_id, f"Cascade from {agent_id}: {reason}")
                    for delegatee_id in set(delegatee_ids)
                ]
                results = await asyncio.gather(*cascade_tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, list):
                        revoked_agents.extend(result)

        except Exception as e:
            logger.error(f"Error during cascade revocation from {agent_id}: {e}")

        return revoked_agents

    async def revoke_by_human(
        self,
        human_id: str,
        reason: str,
    ) -> List[str]:
        """
        Revoke ALL delegations from a specific human.

        EATP Requirement: When a human's access is revoked (e.g., employee
        leaves company), ALL agents they delegated to must be revoked.

        This is typically called when:
        - An employee is terminated
        - A human's session is invalidated
        - A security incident requires revoking all trust from a human

        Args:
            human_id: The human_id (email) to revoke
            reason: Reason for revocation (for audit trail)

        Returns:
            List of all agent IDs that were revoked

        Example:
            >>> # When Alice leaves the company
            >>> revoked = await trust_ops.revoke_by_human(
            ...     "alice@corp.com",
            ...     "Employee termination"
            ... )
            >>> print(f"Revoked {len(revoked)} agents")
        """
        revoked_agents: List[str] = []

        # Find all chains and their delegations with this human_origin
        try:
            all_chains = await self.trust_store.list_chains()
        except Exception:
            all_chains = []

        # Find root delegations from this human's pseudo-agent
        pseudo_agent_id = f"pseudo:{human_id}"

        # Find all delegatees of this pseudo-agent
        direct_delegatees = set()
        for chain in all_chains:
            for delegation in chain.delegations:
                if delegation.delegator_id == pseudo_agent_id:
                    direct_delegatees.add(delegation.delegatee_id)
                # Also check if human_origin matches
                if delegation.human_origin and delegation.human_origin.human_id == human_id:
                    # This delegation chain traces back to this human
                    if chain.genesis.agent_id not in revoked_agents:
                        direct_delegatees.add(chain.genesis.agent_id)

        # Cascade revoke each direct delegatee
        for delegatee_id in direct_delegatees:
            result = await self.revoke_cascade(delegatee_id, f"Human access revoked ({human_id}): {reason}")
            revoked_agents.extend(result)

        logger.warning(
            f"Revoked all delegations from human {human_id}: {len(revoked_agents)} agents affected. Reason: {reason}"
        )

        return revoked_agents

    async def find_delegations_by_human_origin(
        self,
        human_id: str,
    ) -> List[DelegationRecord]:
        """
        Find all delegations that trace back to a specific human.

        Args:
            human_id: The human_id to search for

        Returns:
            List of DelegationRecords with matching human_origin
        """
        matching_delegations: List[DelegationRecord] = []

        try:
            all_chains = await self.trust_store.list_chains()
            for chain in all_chains:
                for delegation in chain.delegations:
                    if delegation.human_origin and delegation.human_origin.human_id == human_id:
                        matching_delegations.append(delegation)
        except Exception as e:
            logger.error(f"Error finding delegations for human {human_id}: {e}")

        return matching_delegations
