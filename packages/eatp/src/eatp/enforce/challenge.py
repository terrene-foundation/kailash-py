# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Challenge-Response Protocol for Live Trust Verification.

Implements a cryptographic challenge-response protocol that proves an agent
currently possesses its private key and holds a specific capability. This
provides live verification beyond static trust chain inspection.

Protocol flow:
    1. Verifier creates a challenge with a random nonce and required capability
    2. Target agent signs the nonce with its private key and provides capability proof
    3. Verifier checks the signature, capability proof, expiration, and nonce freshness

Security properties:
    - **Key possession proof**: Signing the nonce proves the agent holds the private key
    - **Freshness**: Challenge expiration prevents stale challenges from being accepted
    - **Replay protection**: Each nonce is tracked and rejected on second use
    - **Rate limiting**: Per-agent challenge rate limiting prevents abuse
    - **Capability binding**: Response includes cryptographic proof of capability from chain

Example:
    >>> from eatp.crypto import generate_keypair
    >>> from eatp.enforce.challenge import ChallengeProtocol
    >>>
    >>> protocol = ChallengeProtocol()
    >>> private_key, public_key = generate_keypair()
    >>>
    >>> # Verifier creates challenge
    >>> challenge = protocol.create_challenge("verifier-001", "agent-001", "analyze_data")
    >>>
    >>> # Agent responds (requires trust chain with the capability)
    >>> response = protocol.respond_to_challenge(challenge, private_key, chain)
    >>>
    >>> # Verifier verifies
    >>> is_valid = protocol.verify_response(challenge, response, public_key)
"""

from __future__ import annotations

import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from eatp.chain import TrustLineageChain
from eatp.crypto import sign, verify_signature
from eatp.exceptions import TrustError

logger = logging.getLogger(__name__)


class ChallengeError(TrustError):
    """Raised when a challenge-response protocol violation occurs.

    Covers all protocol errors including:
    - Invalid or empty parameters
    - Expired challenges
    - Missing capabilities
    - Nonce replay attempts
    - Rate limit violations

    Inherits from TrustError for consistent exception hierarchy.
    """

    pass


@dataclass
class ChallengeRequest:
    """A cryptographic challenge issued to an agent for live verification.

    The challenge contains a random nonce that the target agent must sign
    to prove possession of its private key, along with the capability
    that must be demonstrated.

    Attributes:
        challenger_id: ID of the entity issuing the challenge
        target_agent_id: ID of the agent being challenged
        nonce: Cryptographically random nonce (hex-encoded, 32+ bytes)
        timestamp: UTC timestamp of challenge creation
        required_proof: Capability the agent must prove (e.g., "analyze_data")
        timeout_seconds: Seconds until the challenge expires
        challenge_id: Unique identifier for this challenge (auto-generated)
        expires_at: UTC timestamp when this challenge expires (computed)
    """

    challenger_id: str
    target_agent_id: str
    nonce: str
    timestamp: datetime
    required_proof: str
    timeout_seconds: int = 30
    challenge_id: str = field(default_factory=lambda: f"ch-{uuid.uuid4().hex[:16]}")
    expires_at: datetime = field(init=False)

    def __post_init__(self) -> None:
        """Compute expires_at from timestamp and timeout_seconds."""
        self.expires_at = self.timestamp + timedelta(seconds=self.timeout_seconds)

    def is_expired(self) -> bool:
        """Check if this challenge has expired.

        Returns:
            True if the current UTC time is past expires_at
        """
        return datetime.now(timezone.utc) > self.expires_at


@dataclass
class ChallengeResponse:
    """A response to a cryptographic challenge proving key possession.

    The response contains the signed nonce (proving the agent holds its
    private key) and capability proof from the agent's trust chain.

    Attributes:
        challenge_id: ID of the challenge being responded to
        agent_id: ID of the responding agent
        signed_nonce: The challenge nonce signed with the agent's private key
        capability_proof: Proof of capability from the trust chain
        timestamp: UTC timestamp of response creation
    """

    challenge_id: str
    agent_id: str
    signed_nonce: str
    capability_proof: Dict[str, Any]
    timestamp: datetime


class ChallengeProtocol:
    """Challenge-response protocol for live agent trust verification.

    Manages the full lifecycle of challenge-response verification:
    creating challenges, producing responses, and verifying them.
    Includes nonce replay protection and per-agent rate limiting.

    Args:
        challenge_timeout_seconds: Seconds until challenges expire (default: 30).
            Must be non-negative.
        max_challenges_per_agent: Maximum challenges per agent within the rate
            limit window (default: 100).
        rate_limit_window_seconds: Duration of the rate limit window in seconds
            (default: 60).

    Raises:
        ValueError: If challenge_timeout_seconds is negative

    Example:
        >>> protocol = ChallengeProtocol(challenge_timeout_seconds=60)
        >>> challenge = protocol.create_challenge("verifier", "agent", "read_data")
    """

    def __init__(
        self,
        challenge_timeout_seconds: int = 30,
        max_challenges_per_agent: int = 100,
        rate_limit_window_seconds: int = 60,
    ) -> None:
        if challenge_timeout_seconds < 0:
            raise ValueError(f"challenge_timeout_seconds must be non-negative, got {challenge_timeout_seconds}")

        self._challenge_timeout_seconds = challenge_timeout_seconds
        self._max_challenges_per_agent = max_challenges_per_agent
        self._rate_limit_window_seconds = rate_limit_window_seconds

        # Nonce replay protection: dict of nonce -> expiry for time-based eviction
        self._used_nonces: Dict[str, datetime] = {}
        self._max_nonces = 100_000  # Hard cap to prevent memory exhaustion

        # Rate limiting: per-agent list of challenge creation timestamps
        self._challenge_timestamps: Dict[str, List[datetime]] = {}

    @property
    def used_nonces(self) -> Set[str]:
        """Get the set of nonces that have been consumed by successful verifications."""
        return set(self._used_nonces.keys())

    def clear_used_nonces(self) -> None:
        """Clear all tracked nonces."""
        self._used_nonces.clear()
        logger.info("[CHALLENGE] Cleared used nonces")

    def _evict_expired_nonces(self) -> None:
        """Remove nonces older than challenge_timeout + 60s grace period."""
        now = datetime.now(timezone.utc)
        grace = timedelta(seconds=self._challenge_timeout_seconds + 60)
        expired = [n for n, exp in self._used_nonces.items() if now - exp > grace]
        for n in expired:
            del self._used_nonces[n]
        if expired:
            logger.debug(f"[CHALLENGE] Evicted {len(expired)} expired nonces")

    def create_challenge(
        self,
        challenger_id: str,
        target_agent_id: str,
        required_proof: str,
    ) -> ChallengeRequest:
        """Create a new challenge for a target agent.

        Generates a cryptographically random nonce and creates a time-bound
        challenge that the target agent must respond to.

        Args:
            challenger_id: ID of the entity issuing the challenge.
                Must be non-empty and non-whitespace.
            target_agent_id: ID of the agent to challenge.
                Must be non-empty and non-whitespace.
            required_proof: Capability the agent must prove.
                Must be non-empty and non-whitespace.

        Returns:
            A ChallengeRequest with a random nonce and computed expiration

        Raises:
            ChallengeError: If any parameter is empty/whitespace or rate limit exceeded
        """
        # Validate inputs explicitly
        if not challenger_id or not challenger_id.strip():
            raise ChallengeError(
                "challenger_id must not be empty or whitespace",
                details={"challenger_id": repr(challenger_id)},
            )
        if not target_agent_id or not target_agent_id.strip():
            raise ChallengeError(
                "target_agent_id must not be empty or whitespace",
                details={"target_agent_id": repr(target_agent_id)},
            )
        if not required_proof or not required_proof.strip():
            raise ChallengeError(
                "required_proof must not be empty or whitespace",
                details={"required_proof": repr(required_proof)},
            )

        # Check rate limiting for the target agent
        self._enforce_rate_limit(target_agent_id)

        # Generate cryptographically secure random nonce (32 bytes = 64 hex chars)
        nonce = secrets.token_hex(32)

        now = datetime.now(timezone.utc)

        challenge = ChallengeRequest(
            challenger_id=challenger_id,
            target_agent_id=target_agent_id,
            nonce=nonce,
            timestamp=now,
            required_proof=required_proof,
            timeout_seconds=self._challenge_timeout_seconds,
        )

        # Record this challenge for rate limiting
        if target_agent_id not in self._challenge_timestamps:
            self._challenge_timestamps[target_agent_id] = []
        self._challenge_timestamps[target_agent_id].append(now)

        logger.debug(
            f"[CHALLENGE] Created challenge {challenge.challenge_id}: "
            f"challenger={challenger_id} target={target_agent_id} "
            f"required_proof={required_proof} expires_at={challenge.expires_at.isoformat()}"
        )

        return challenge

    def respond_to_challenge(
        self,
        challenge: ChallengeRequest,
        agent_key: str,
        chain: TrustLineageChain,
    ) -> ChallengeResponse:
        """Respond to a challenge by signing the nonce and providing capability proof.

        The agent signs a payload composed of the nonce, timestamp, and challenger_id
        to prove possession of its private key. It also extracts capability proof
        from its trust chain.

        Args:
            challenge: The ChallengeRequest to respond to
            agent_key: The agent's base64-encoded Ed25519 private key
            chain: The agent's TrustLineageChain containing capability attestations

        Returns:
            A ChallengeResponse with the signed nonce and capability proof

        Raises:
            ChallengeError: If the challenge has expired or the agent lacks
                the required capability in its trust chain
        """
        # Check challenge expiration
        if challenge.is_expired():
            raise ChallengeError(
                f"Challenge {challenge.challenge_id} has expired at {challenge.expires_at.isoformat()}",
                details={
                    "challenge_id": challenge.challenge_id,
                    "expires_at": challenge.expires_at.isoformat(),
                    "now": datetime.now(timezone.utc).isoformat(),
                },
            )

        # Check capability exists in trust chain
        capability_attestation = chain.get_capability(challenge.required_proof)
        if capability_attestation is None:
            raise ChallengeError(
                f"Agent does not have required capability '{challenge.required_proof}' in its trust chain",
                details={
                    "agent_id": chain.genesis.agent_id,
                    "required_proof": challenge.required_proof,
                    "available_capabilities": [cap.capability for cap in chain.capabilities if not cap.is_expired()],
                },
            )

        # Sign the payload: nonce + timestamp + challenger_id
        # This binds the signature to this specific challenge, preventing
        # signature reuse across different challenges
        payload = f"{challenge.nonce}:{challenge.timestamp.isoformat()}:{challenge.challenger_id}"
        signed_nonce = sign(payload, agent_key)

        # Build capability proof from chain
        capability_proof: Dict[str, Any] = {
            "capability": capability_attestation.capability,
            "attestation_id": capability_attestation.id,
            "capability_type": capability_attestation.capability_type.value,
            "attester_id": capability_attestation.attester_id,
            "constraints": capability_attestation.constraints,
        }

        now = datetime.now(timezone.utc)

        response = ChallengeResponse(
            challenge_id=challenge.challenge_id,
            agent_id=chain.genesis.agent_id,
            signed_nonce=signed_nonce,
            capability_proof=capability_proof,
            timestamp=now,
        )

        logger.debug(
            f"[CHALLENGE] Responded to challenge {challenge.challenge_id}: "
            f"agent={chain.genesis.agent_id} capability={challenge.required_proof}"
        )

        return response

    def verify_response(
        self,
        challenge: ChallengeRequest,
        response: ChallengeResponse,
        agent_public_key: str,
    ) -> bool:
        """Verify a challenge response for authenticity and correctness.

        Performs the following checks in order:
        1. Challenge expiration
        2. Nonce replay (has this nonce been used before?)
        3. Challenge ID match
        4. Agent ID matches the challenge target
        5. Capability proof matches the required proof
        6. Cryptographic signature verification

        On success, the nonce is recorded as used to prevent replay.

        Args:
            challenge: The original ChallengeRequest
            response: The ChallengeResponse to verify
            agent_public_key: The agent's base64-encoded Ed25519 public key

        Returns:
            True if the response is valid, False if signature or field checks fail

        Raises:
            ChallengeError: If the challenge has expired or the nonce has been replayed
        """
        # 1. Check challenge expiration
        if challenge.is_expired():
            raise ChallengeError(
                f"Challenge {challenge.challenge_id} has expired at "
                f"{challenge.expires_at.isoformat()} and cannot be verified",
                details={
                    "challenge_id": challenge.challenge_id,
                    "expires_at": challenge.expires_at.isoformat(),
                    "now": datetime.now(timezone.utc).isoformat(),
                },
            )

        # 2. Evict expired nonces to bound memory, then check replay
        self._evict_expired_nonces()
        if challenge.nonce in self._used_nonces:
            raise ChallengeError(
                f"Nonce has already been used — possible replay attack for challenge {challenge.challenge_id}",
                details={
                    "challenge_id": challenge.challenge_id,
                    "nonce_prefix": challenge.nonce[:16] + "...",
                },
            )

        # 3. Check challenge ID match (constant-time to prevent timing attacks)
        if not hmac.compare_digest(response.challenge_id, challenge.challenge_id):
            logger.warning(
                f"[CHALLENGE] Challenge ID mismatch: expected={challenge.challenge_id} got={response.challenge_id}"
            )
            return False

        # 4. Check agent ID matches challenge target (constant-time)
        if not hmac.compare_digest(response.agent_id, challenge.target_agent_id):
            logger.warning(
                f"[CHALLENGE] Agent ID mismatch: challenge targets "
                f"'{challenge.target_agent_id}' but response from '{response.agent_id}'"
            )
            return False

        # 5. Check capability proof matches required proof (constant-time)
        response_capability = response.capability_proof.get("capability", "")
        if not hmac.compare_digest(str(response_capability), challenge.required_proof):
            logger.warning(
                f"[CHALLENGE] Capability mismatch: required='{challenge.required_proof}' got='{response_capability}'"
            )
            return False

        # 6. Verify cryptographic signature
        payload = f"{challenge.nonce}:{challenge.timestamp.isoformat()}:{challenge.challenger_id}"
        try:
            signature_valid = verify_signature(payload, response.signed_nonce, agent_public_key)
        except Exception as exc:
            logger.warning(f"[CHALLENGE] Signature verification error for challenge {challenge.challenge_id}: {exc}")
            return False

        if not signature_valid:
            logger.warning(
                f"[CHALLENGE] Invalid signature for challenge {challenge.challenge_id} from agent {response.agent_id}"
            )
            return False

        # All checks passed — record nonce as used (with timestamp for eviction)
        if len(self._used_nonces) >= self._max_nonces:
            self._evict_expired_nonces()
            if len(self._used_nonces) >= self._max_nonces:
                # Still at capacity after eviction — remove oldest entries
                oldest = sorted(self._used_nonces.items(), key=lambda x: x[1])
                for k, _ in oldest[: len(oldest) // 4]:
                    del self._used_nonces[k]
        self._used_nonces[challenge.nonce] = datetime.now(timezone.utc)

        logger.info(
            f"[CHALLENGE] Verified challenge {challenge.challenge_id}: "
            f"agent={response.agent_id} capability={challenge.required_proof}"
        )

        return True

    def _enforce_rate_limit(self, target_agent_id: str) -> None:
        """Check and enforce per-agent rate limiting.

        Counts challenges issued to the target agent within the current
        rate limit window and raises if the limit is exceeded.

        Args:
            target_agent_id: The agent to check rate limits for

        Raises:
            ChallengeError: If the rate limit has been exceeded
        """
        if target_agent_id not in self._challenge_timestamps:
            return

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self._rate_limit_window_seconds)

        # Filter to only timestamps within the current window
        recent_timestamps = [ts for ts in self._challenge_timestamps[target_agent_id] if ts > window_start]

        # Update stored timestamps to only keep recent ones (garbage collection)
        self._challenge_timestamps[target_agent_id] = recent_timestamps

        if len(recent_timestamps) >= self._max_challenges_per_agent:
            raise ChallengeError(
                f"Rate limit exceeded for agent '{target_agent_id}': "
                f"{len(recent_timestamps)} challenges in the last "
                f"{self._rate_limit_window_seconds}s (limit: {self._max_challenges_per_agent})",
                details={
                    "target_agent_id": target_agent_id,
                    "challenge_count": len(recent_timestamps),
                    "max_allowed": self._max_challenges_per_agent,
                    "window_seconds": self._rate_limit_window_seconds,
                },
            )


__all__ = [
    "ChallengeError",
    "ChallengeProtocol",
    "ChallengeRequest",
    "ChallengeResponse",
]
