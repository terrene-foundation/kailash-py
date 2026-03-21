# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Message Verifier - Verify incoming messages and trust.

This module provides the MessageVerifier for cryptographically
verifying incoming messages and checking sender trust.

Key Features:
- Ed25519 signature verification
- Trust chain validation
- Replay attack detection
- Message freshness checking
- Capability and constraint verification
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from kailash.trust.chain import VerificationLevel
from kailash.trust.signing.crypto import verify_signature
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.messaging.envelope import SecureMessageEnvelope
from kailash.trust.messaging.exceptions import PublicKeyNotFoundError
from kailash.trust.messaging.replay_protection import ReplayProtection
from kailash.trust.operations import TrustOperations
from kailash.trust.registry.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


# Clock skew tolerance (60 seconds)
CLOCK_SKEW_TOLERANCE_SECONDS = 60


@dataclass
class MessageVerificationResult:
    """
    Result of message verification.

    Contains detailed results for each verification step,
    enabling precise diagnosis of verification failures.

    Attributes:
        valid: Overall verification result. True only if ALL
            checks pass.

        signature_valid: True if Ed25519 signature is valid.

        trust_valid: True if sender has a valid trust chain.

        not_expired: True if message has not expired based on
            timestamp and TTL.

        not_replayed: True if message nonce has not been seen
            before.

        sender_verified: True if sender_agent_id matches the
            trust chain identity.

        errors: List of error messages for failed checks.

        warnings: List of warning messages for non-critical issues.

        verified_at: Timestamp when verification was performed.

    Example:
        >>> result = await verifier.verify_message(envelope)
        >>> if result.is_valid():
        ...     process_message(envelope)
        >>> else:
        ...     print(f"Verification failed: {result.get_failure_reason()}")
    """

    valid: bool
    signature_valid: bool = False
    trust_valid: bool = False
    not_expired: bool = False
    not_replayed: bool = False
    sender_verified: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        """
        Check if verification passed all checks.

        Returns:
            True only if ALL checks passed.
        """
        return (
            self.valid
            and self.signature_valid
            and self.trust_valid
            and self.not_expired
            and self.not_replayed
            and self.sender_verified
        )

    def get_failure_reason(self) -> str:
        """
        Get a human-readable failure summary.

        Returns:
            String describing why verification failed.
        """
        if self.is_valid():
            return "Verification passed"

        failed_checks = []
        if not self.signature_valid:
            failed_checks.append("invalid signature")
        if not self.trust_valid:
            failed_checks.append("invalid trust chain")
        if not self.not_expired:
            failed_checks.append("message expired")
        if not self.not_replayed:
            failed_checks.append("replay detected")
        if not self.sender_verified:
            failed_checks.append("sender not verified")

        summary = ", ".join(failed_checks)

        if self.errors:
            summary += f". Errors: {'; '.join(self.errors)}"

        return summary


class MessageVerifier:
    """
    Verifies incoming messages for authenticity and trust.

    The MessageVerifier performs comprehensive verification:
    1. Signature verification (Ed25519)
    2. Trust chain validation
    3. Message freshness checking
    4. Replay attack detection
    5. Capability and constraint verification

    Attributes:
        verification_level: Level of trust verification to perform.

    Example:
        >>> verifier = MessageVerifier(
        ...     trust_operations=trust_ops,
        ...     agent_registry=registry,
        ...     replay_protection=replay_protection
        ... )
        >>> result = await verifier.verify_message(envelope)
        >>> if result.is_valid():
        ...     print("Message verified!")
    """

    def __init__(
        self,
        trust_operations: TrustOperations,
        agent_registry: AgentRegistry,
        replay_protection: ReplayProtection,
        verification_level: VerificationLevel = VerificationLevel.STANDARD,
    ):
        """
        Initialize the MessageVerifier.

        Args:
            trust_operations: TrustOperations for trust chain retrieval
                and verification.

            agent_registry: AgentRegistry for agent metadata and
                public key retrieval.

            replay_protection: ReplayProtection for detecting
                replayed messages.

            verification_level: Level of trust verification.
                QUICK: Signature only
                STANDARD: Signature + trust + constraints (default)
                FULL: All checks including delegation chain
        """
        self._trust_ops = trust_operations
        self._registry = agent_registry
        self._replay_protection = replay_protection
        self._verification_level = verification_level

    async def verify_message(
        self,
        envelope: SecureMessageEnvelope,
    ) -> MessageVerificationResult:
        """
        Verify a message envelope.

        Performs multi-step verification:
        1. Verify signature cryptographically
        2. Verify sender trust chain
        3. Verify message freshness
        4. Verify nonce not replayed

        Args:
            envelope: The message envelope to verify.

        Returns:
            MessageVerificationResult with detailed results.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Step 1: Verify signature
        signature_valid = await self._verify_signature(envelope, errors, warnings)

        # Step 2: Verify trust chain
        trust_valid, sender_verified = await self._verify_trust(envelope, errors, warnings)

        # Step 3: Verify message freshness
        not_expired = self._verify_freshness(envelope, errors, warnings)

        # Step 4: Verify replay protection
        not_replayed = await self._verify_replay(envelope, errors, warnings)

        # Aggregate result
        valid = signature_valid and trust_valid and not_expired and not_replayed and sender_verified

        result = MessageVerificationResult(
            valid=valid,
            signature_valid=signature_valid,
            trust_valid=trust_valid,
            not_expired=not_expired,
            not_replayed=not_replayed,
            sender_verified=sender_verified,
            errors=errors,
            warnings=warnings,
        )

        logger.debug(
            f"Verification for message {envelope.message_id}: "
            f"valid={valid}, signature={signature_valid}, trust={trust_valid}, "
            f"not_expired={not_expired}, not_replayed={not_replayed}"
        )

        return result

    async def verify_sender_capability(
        self,
        envelope: SecureMessageEnvelope,
        required_capability: str,
    ) -> bool:
        """
        Verify that the sender has a specific capability.

        Args:
            envelope: The message envelope.
            required_capability: The capability to check for.

        Returns:
            True if sender has the capability, False otherwise.
        """
        try:
            chain = await self._trust_ops.get_chain(envelope.sender_agent_id)

            if not chain:
                logger.warning(f"Cannot verify capability for {envelope.sender_agent_id}: no trust chain")
                return False

            # Check capability attestations
            for attestation in chain.capability_attestations:
                if attestation.capability == required_capability:
                    # Check if not expired
                    if attestation.expires_at and attestation.expires_at < datetime.now(timezone.utc):
                        continue
                    return True

            logger.debug(f"Sender {envelope.sender_agent_id} does not have capability {required_capability}")
            return False

        except Exception as e:
            logger.error(f"Error verifying sender capability: {e}")
            return False

    async def verify_sender_constraints(
        self,
        envelope: SecureMessageEnvelope,
        action: str,
        resource: str,
    ) -> bool:
        """
        Verify that sender's constraints allow an action.

        Args:
            envelope: The message envelope.
            action: The action to check (e.g., "read", "write").
            resource: The resource being accessed.

        Returns:
            True if action is allowed, False if constrained.
        """
        try:
            # Use TrustOperations.verify() for constraint checking
            result = await self._trust_ops.verify(
                agent_id=envelope.sender_agent_id,
                action=action,
                resource=resource,
                level=self._verification_level,
            )

            return result.valid

        except Exception as e:
            logger.error(f"Error verifying sender constraints: {e}")
            return False

    async def _verify_signature(
        self,
        envelope: SecureMessageEnvelope,
        errors: List[str],
        warnings: List[str],
    ) -> bool:
        """Verify the envelope's Ed25519 signature."""
        try:
            # Get sender's public key
            public_key = await self._get_sender_public_key(envelope.sender_agent_id)

            # Get signing payload
            signing_payload = envelope.get_signing_payload()

            # Verify signature (verify_signature handles base64 decoding internally)
            is_valid = verify_signature(signing_payload, envelope.signature, public_key)

            if not is_valid:
                errors.append("Invalid signature")
                logger.warning(f"Invalid signature for message {envelope.message_id} from {envelope.sender_agent_id}")

            return is_valid

        except PublicKeyNotFoundError as e:
            errors.append(f"Public key not found for sender: {e.agent_id}")
            logger.warning(f"Public key not found for {envelope.sender_agent_id}")
            return False
        except ValueError as e:
            errors.append(f"Invalid signature format: {e}")
            return False
        except Exception as e:
            errors.append(f"Signature verification error: {e}")
            logger.error(f"Signature verification error: {e}")
            return False

    async def _verify_trust(
        self,
        envelope: SecureMessageEnvelope,
        errors: List[str],
        warnings: List[str],
    ) -> tuple[bool, bool]:
        """
        Verify sender's trust chain.

        Returns:
            Tuple of (trust_valid, sender_verified).
        """
        try:
            # Get sender's trust chain
            chain = await self._trust_ops.get_chain(envelope.sender_agent_id)

            if not chain:
                errors.append("Sender has no trust chain")
                return False, False

            # Verify chain is valid
            result = await self._trust_ops.verify(
                agent_id=envelope.sender_agent_id,
                action="messaging",
                level=self._verification_level,
            )

            if not result.valid:
                errors.append(f"Trust verification failed: {result.reason}")
                return False, False

            # Verify chain hash matches
            current_hash = chain.compute_hash()
            if current_hash != envelope.trust_chain_hash:
                warnings.append("Trust chain hash mismatch - chain may have been updated")
                # This is a warning, not an error - chain can be updated

            # Verify sender matches chain identity
            if chain.genesis.agent_id != envelope.sender_agent_id:
                errors.append("Sender agent_id does not match trust chain")
                return True, False

            return True, True

        except TrustChainNotFoundError:
            errors.append("Sender trust chain not found")
            return False, False
        except Exception as e:
            errors.append(f"Trust verification error: {e}")
            logger.error(f"Trust verification error: {e}")
            return False, False

    def _verify_freshness(
        self,
        envelope: SecureMessageEnvelope,
        errors: List[str],
        warnings: List[str],
    ) -> bool:
        """Verify message has not expired."""
        now = datetime.now(timezone.utc)

        # Check timestamp is not in future (allow clock skew)
        max_future = now + timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS)
        if envelope.timestamp > max_future:
            errors.append("Message timestamp is in the future")
            return False

        # Check message not expired
        if envelope.is_expired(now):
            errors.append("Message has expired")
            return False

        # Warn if message is near expiration
        ttl_seconds = 300
        if envelope.metadata:
            ttl_seconds = envelope.metadata.ttl_seconds

        remaining = (envelope.timestamp + timedelta(seconds=ttl_seconds)) - now
        if remaining.total_seconds() < 30:
            warnings.append(f"Message expires in {remaining.total_seconds():.0f}s")

        return True

    async def _verify_replay(
        self,
        envelope: SecureMessageEnvelope,
        errors: List[str],
        warnings: List[str],
    ) -> bool:
        """Verify message is not a replay."""
        try:
            is_new = await self._replay_protection.check_nonce(
                envelope.message_id,
                envelope.nonce,
                envelope.timestamp,
            )

            if not is_new:
                errors.append("Message is a replay (nonce already seen)")
                return False

            return True

        except Exception as e:
            errors.append(f"Replay check error: {e}")
            logger.error(f"Replay check error: {e}")
            return False

    async def _get_sender_public_key(self, agent_id: str) -> bytes:
        """
        Retrieve sender's public key.

        First checks agent registry, then falls back to trust chain.

        Args:
            agent_id: The sender's agent ID.

        Returns:
            Ed25519 public key (32 bytes).

        Raises:
            PublicKeyNotFoundError: If public key cannot be found.
        """
        # Try agent registry first
        try:
            agent_metadata = await self._registry.get(agent_id)
            if agent_metadata and agent_metadata.public_key:
                # Assume hex-encoded public key in registry
                return bytes.fromhex(agent_metadata.public_key)
        except Exception as e:
            logger.debug(f"Could not get public key from registry: {e}")

        # Fall back to trust chain
        try:
            chain = await self._trust_ops.get_chain(agent_id)
            if chain and chain.genesis.public_key:
                return bytes.fromhex(chain.genesis.public_key)
        except Exception as e:
            logger.debug(f"Could not get public key from trust chain: {e}")

        raise PublicKeyNotFoundError(agent_id)
