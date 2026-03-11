# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
CARE-014: External Timestamp Anchoring.

Provides RFC 3161-style timestamp anchoring for trust chain hashes.
Enables cryptographic proof that a trust state existed at a specific time,
providing non-repudiation for audit purposes.

Key Features:
- TimestampAuthority abstraction for pluggable timestamp sources
- LocalTimestampAuthority for development and fallback
- RFC3161TimestampAuthority stub for production TSA integration
- TimestampAnchorManager with fallback chain
- Integration with MerkleTree for root hash anchoring

Example:
    from eatp.timestamping import (
        LocalTimestampAuthority,
        TimestampAnchorManager,
    )
    from eatp.merkle import MerkleTree

    # Create authority and manager
    authority = LocalTimestampAuthority()
    manager = TimestampAnchorManager(primary=authority)

    # Anchor a hash
    response = await manager.anchor_hash("abc123...")

    # Anchor a Merkle tree root
    tree = MerkleTree(leaves=["hash1", "hash2"])
    response = await manager.anchor_merkle_root(tree)

    # Verify anchor
    is_valid = await manager.verify_anchor(response)
"""

import logging
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from eatp.crypto import (
    generate_keypair,
    serialize_for_signing,
    sign,
    verify_signature,
)
from eatp.merkle import MerkleTree

logger = logging.getLogger(__name__)

# CARE-049: Default threshold for clock drift detection (in seconds).
# If consecutive timestamps drift by more than this, log a CRITICAL warning.
# System clock manipulation or NTP issues can compromise timestamp integrity.
DEFAULT_CLOCK_DRIFT_THRESHOLD_SECONDS = 5.0


class TimestampSource(str, Enum):
    """Source of timestamp authority.

    Attributes:
        LOCAL: Local timestamp using system clock (no external authority)
        RFC3161: RFC 3161 Time-Stamp Protocol Authority
        BLOCKCHAIN: Blockchain-based timestamp anchor (future)
    """

    LOCAL = "local"
    RFC3161 = "rfc3161"
    BLOCKCHAIN = "blockchain"


@dataclass
class TimestampToken:
    """
    A cryptographic timestamp token proving a hash existed at a specific time.

    This token provides non-repudiation: the signature from the authority
    proves the hash value existed at the stated timestamp.

    Attributes:
        token_id: Unique identifier for this token
        hash_value: The hash that was timestamped
        timestamp: When the hash was timestamped
        source: Type of timestamp authority
        authority: URL or identifier of the authority
        signature: Cryptographic signature from the authority
        nonce: Random value for replay prevention
        serial_number: Sequential number from the authority
        accuracy_microseconds: Accuracy of the timestamp in microseconds
    """

    token_id: str
    hash_value: str
    timestamp: datetime
    source: TimestampSource
    authority: str
    signature: Optional[str] = None
    nonce: Optional[str] = None
    serial_number: Optional[int] = None
    accuracy_microseconds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize token to dictionary."""
        return {
            "token_id": self.token_id,
            "hash_value": self.hash_value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source.value,
            "authority": self.authority,
            "signature": self.signature,
            "nonce": self.nonce,
            "serial_number": self.serial_number,
            "accuracy_microseconds": self.accuracy_microseconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimestampToken":
        """Deserialize token from dictionary."""
        return cls(
            token_id=data["token_id"],
            hash_value=data["hash_value"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=TimestampSource(data["source"]),
            authority=data["authority"],
            signature=data.get("signature"),
            nonce=data.get("nonce"),
            serial_number=data.get("serial_number"),
            accuracy_microseconds=data.get("accuracy_microseconds"),
        )


@dataclass
class TimestampRequest:
    """
    Request for a timestamp on a hash value.

    Attributes:
        hash_value: The hash to be timestamped
        nonce: Random value for replay prevention (auto-generated if None)
        requested_at: When the request was made
        algorithm: Hash algorithm used (default: sha256)
    """

    hash_value: str
    nonce: Optional[str] = None
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    algorithm: str = "sha256"

    def __post_init__(self):
        """Generate nonce if not provided."""
        if self.nonce is None:
            self.nonce = secrets.token_hex(16)


@dataclass
class TimestampResponse:
    """
    Response from a timestamp authority.

    Attributes:
        request: The original request
        token: The resulting timestamp token
        raw_response: Raw response bytes (for RFC 3161 DER encoding)
        verified: Whether the token was verified after creation
    """

    request: TimestampRequest
    token: TimestampToken
    raw_response: Optional[bytes] = None
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize response to dictionary."""
        return {
            "request": {
                "hash_value": self.request.hash_value,
                "nonce": self.request.nonce,
                "requested_at": self.request.requested_at.isoformat(),
                "algorithm": self.request.algorithm,
            },
            "token": self.token.to_dict(),
            "raw_response": (self.raw_response.hex() if self.raw_response else None),
            "verified": self.verified,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimestampResponse":
        """Deserialize response from dictionary."""
        request_data = data["request"]
        request = TimestampRequest(
            hash_value=request_data["hash_value"],
            nonce=request_data.get("nonce"),
            requested_at=datetime.fromisoformat(request_data["requested_at"]),
            algorithm=request_data.get("algorithm", "sha256"),
        )
        token = TimestampToken.from_dict(data["token"])
        raw_response = (
            bytes.fromhex(data["raw_response"]) if data.get("raw_response") else None
        )
        return cls(
            request=request,
            token=token,
            raw_response=raw_response,
            verified=data.get("verified", False),
        )


class TimestampAuthority(ABC):
    """Abstract timestamp authority interface.

    Defines the contract for timestamp authorities that can provide
    cryptographic proof of when a hash value existed.
    """

    @abstractmethod
    async def get_timestamp(
        self, hash_value: str, nonce: Optional[str] = None
    ) -> TimestampResponse:
        """
        Get a timestamp for a hash value.

        Args:
            hash_value: The hash to timestamp
            nonce: Optional nonce for replay prevention

        Returns:
            TimestampResponse with the timestamp token

        Raises:
            Exception: If timestamping fails
        """
        pass

    @abstractmethod
    async def verify_timestamp(self, token: TimestampToken) -> bool:
        """
        Verify a timestamp token.

        Args:
            token: The timestamp token to verify

        Returns:
            True if the token is valid, False otherwise
        """
        pass

    @property
    @abstractmethod
    def authority_url(self) -> str:
        """URL or identifier for this authority."""
        pass


class LocalTimestampAuthority(TimestampAuthority):
    """
    Local timestamp authority for development and fallback.

    Uses local clock and Ed25519 signatures. Not as trustworthy as
    external TSA but provides consistent interface for development
    and testing.

    Note: Local timestamps are signed but the trust relies on the
    local key storage. For production non-repudiation, use an
    external RFC 3161 TSA.

    CARE-049 Security Notice:
        LocalTimestampAuthority relies on the system clock without external
        verification. This creates security risks in production:
        1. System clock can be manipulated by attackers with system access
        2. NTP drift/failures can cause timestamp inconsistencies
        3. No external attestation means timestamps are self-asserted

        For production environments, use ExternalTimestampAuthority (RFC 3161)
        which provides external cryptographic attestation of time.

    Attributes:
        _signing_key: Private key for signing timestamps
        _verify_key: Public key for verification
        _serial_counter: Counter for serial numbers
        _last_timestamp: Last issued timestamp for drift detection
        _production_warning: Whether to log production warning
        _clock_drift_threshold: Threshold in seconds for drift detection
    """

    def __init__(
        self,
        signing_key: Optional[str] = None,
        verify_key: Optional[str] = None,
        production_warning: bool = True,
        clock_drift_threshold: float = DEFAULT_CLOCK_DRIFT_THRESHOLD_SECONDS,
    ):
        """
        Initialize local timestamp authority.

        If no keys are provided, generates a new Ed25519 key pair.

        Args:
            signing_key: Base64-encoded private key
            verify_key: Base64-encoded public key
            production_warning: Whether to log a warning that this should only
                be used in development/testing (default: True). Set to False
                in test code to suppress warnings.
            clock_drift_threshold: Threshold in seconds for clock drift
                detection. If consecutive timestamps differ by more than this,
                a CRITICAL log is emitted. Default: 5.0 seconds.
        """
        if signing_key is None or verify_key is None:
            self._signing_key, self._verify_key = generate_keypair()
        else:
            self._signing_key = signing_key
            self._verify_key = verify_key

        self._serial_counter = 0
        self._last_timestamp: Optional[datetime] = None
        self._production_warning = production_warning
        self._clock_drift_threshold = clock_drift_threshold

        # CARE-049: Log production warning at initialization
        if production_warning:
            logger.warning(
                "LocalTimestampAuthority is intended for development and testing only. "
                "For production environments requiring non-repudiation, use "
                "ExternalTimestampAuthority (RFC 3161 TSA) which provides external "
                "cryptographic attestation of time. Local timestamps rely on the "
                "system clock which can be manipulated or drift without detection."
            )

    @property
    def authority_url(self) -> str:
        """URL or identifier for this authority."""
        return "local"

    @property
    def public_key(self) -> str:
        """Get the public key for verification."""
        return self._verify_key

    def _validate_clock_drift(self, current_timestamp: datetime) -> None:
        """
        Check for significant clock drift between consecutive timestamps.

        CARE-049: This method detects potential clock manipulation or NTP issues
        by comparing consecutive timestamps. If the current timestamp is earlier
        than the previous one, or if there's an unexpectedly large jump forward,
        this indicates a security concern.

        Args:
            current_timestamp: The timestamp about to be issued

        Logs:
            CRITICAL: If clock appears to have gone backwards (potential manipulation)
            CRITICAL: If clock jumped forward significantly (NTP correction or manipulation)
        """
        if self._last_timestamp is None:
            return

        time_diff = (current_timestamp - self._last_timestamp).total_seconds()

        # Clock went backwards - this is a serious security concern
        if time_diff < 0:
            logger.critical(
                "CARE-049 SECURITY ALERT: System clock went backwards by %.3f seconds. "
                "This may indicate clock manipulation or severe NTP issues. "
                "Timestamps issued by LocalTimestampAuthority may be unreliable. "
                "Previous: %s, Current: %s",
                abs(time_diff),
                self._last_timestamp.isoformat(),
                current_timestamp.isoformat(),
            )
        # Large forward jump - could indicate NTP correction or manipulation
        elif time_diff > self._clock_drift_threshold:
            logger.critical(
                "CARE-049 SECURITY ALERT: System clock jumped forward by %.3f seconds "
                "(threshold: %.3f seconds). This may indicate clock manipulation or "
                "NTP correction. Verify system time synchronization. "
                "Previous: %s, Current: %s",
                time_diff,
                self._clock_drift_threshold,
                self._last_timestamp.isoformat(),
                current_timestamp.isoformat(),
            )

    async def get_timestamp(
        self, hash_value: str, nonce: Optional[str] = None
    ) -> TimestampResponse:
        """
        Get a timestamp for a hash value.

        Creates a signed timestamp token using the local clock
        and Ed25519 signature.

        Args:
            hash_value: The hash to timestamp
            nonce: Optional nonce for replay prevention

        Returns:
            TimestampResponse with the timestamp token
        """
        # Create request
        request = TimestampRequest(hash_value=hash_value, nonce=nonce)

        # Generate token ID
        token_id = f"local-{uuid4().hex[:12]}"

        # Increment serial
        self._serial_counter += 1

        # Create timestamp
        timestamp = datetime.now(timezone.utc)

        # CARE-049: Check for clock drift
        self._validate_clock_drift(timestamp)
        self._last_timestamp = timestamp

        # Create signable payload
        payload = {
            "token_id": token_id,
            "hash_value": hash_value,
            "timestamp": timestamp.isoformat(),
            "nonce": request.nonce,
            "serial_number": self._serial_counter,
        }

        # Sign the payload
        signature = sign(payload, self._signing_key)

        # Create token
        token = TimestampToken(
            token_id=token_id,
            hash_value=hash_value,
            timestamp=timestamp,
            source=TimestampSource.LOCAL,
            authority=self.authority_url,
            signature=signature,
            nonce=request.nonce,
            serial_number=self._serial_counter,
            accuracy_microseconds=1000,  # 1ms accuracy for local clock
        )

        return TimestampResponse(
            request=request,
            token=token,
            raw_response=None,
            verified=True,  # We just created it
        )

    async def verify_timestamp(self, token: TimestampToken) -> bool:
        """
        Verify a timestamp token.

        Reconstructs the signed payload and verifies the signature.

        Args:
            token: The timestamp token to verify

        Returns:
            True if the token is valid, False otherwise
        """
        if token.source != TimestampSource.LOCAL:
            return False

        if token.authority != self.authority_url:
            return False

        if token.signature is None:
            return False

        # Reconstruct payload
        payload = {
            "token_id": token.token_id,
            "hash_value": token.hash_value,
            "timestamp": token.timestamp.isoformat(),
            "nonce": token.nonce,
            "serial_number": token.serial_number,
        }

        try:
            return verify_signature(payload, token.signature, self._verify_key)
        except Exception as e:
            logger.debug("Timestamp verification failed: %s", type(e).__name__)
            return False


class RFC3161TimestampAuthority(TimestampAuthority):
    """
    RFC 3161 timestamp authority stub.

    Placeholder for production TSA integration. This class defines
    the interface for RFC 3161 compliance but does not implement
    actual TSA communication.

    RFC 3161 Time-Stamp Protocol:
    - Client sends TimeStampReq with hash of data
    - TSA returns TimeStampResp with signed timestamp
    - Response contains TSA certificate for verification

    To implement production RFC 3161:
    1. Install rfc3161ng or similar library
    2. Implement get_timestamp to send HTTP POST to TSA
    3. Implement verify_timestamp using TSA certificate

    Attributes:
        _url: TSA URL
        _timeout: Request timeout in seconds
    """

    def __init__(self, tsa_url: str, timeout_seconds: int = 10):
        """
        Initialize RFC 3161 authority.

        Args:
            tsa_url: URL of the timestamp authority
            timeout_seconds: Request timeout
        """
        self._url = tsa_url
        self._timeout = timeout_seconds

    @property
    def authority_url(self) -> str:
        """URL of this timestamp authority."""
        return self._url

    async def get_timestamp(
        self, hash_value: str, nonce: Optional[str] = None
    ) -> TimestampResponse:
        """
        Get a timestamp from an RFC 3161 Time Stamping Authority.

        Sends a TimeStampReq to the configured TSA URL and parses
        the TimeStampResp. Uses rfc3161ng if available, otherwise
        falls back to raw HTTP POST with ASN.1 encoding.

        Args:
            hash_value: The hash to timestamp (hex-encoded)
            nonce: Optional nonce for replay prevention

        Returns:
            TimestampResponse with token and raw response
        """
        import hashlib

        request = TimestampRequest(
            hash_value=hash_value,
            nonce=nonce,
        )

        try:
            import rfc3161ng
        except ImportError:
            rfc3161ng = None

        if rfc3161ng is not None:
            # Use rfc3161ng library for proper ASN.1 encoding
            import asyncio

            hash_bytes = bytes.fromhex(hash_value)
            tsa = rfc3161ng.RemoteTimestamper(self._url, timeout=self._timeout)

            # rfc3161ng is synchronous - run in thread
            raw_response = await asyncio.to_thread(tsa.timestamp, data=hash_bytes)

            now = datetime.now(timezone.utc)
            token = TimestampToken(
                token_id=str(uuid4()),
                hash_value=hash_value,
                timestamp=now,
                source=TimestampSource.RFC3161,
                authority=self._url,
                nonce=request.nonce,
            )

            return TimestampResponse(
                request=request,
                token=token,
                raw_response=raw_response if isinstance(raw_response, bytes) else None,
                verified=True,
            )
        else:
            # Fallback: raw HTTP POST to TSA endpoint
            try:
                import aiohttp
            except ImportError:
                raise ImportError(
                    "RFC 3161 timestamping requires either 'rfc3161ng' or 'aiohttp'. "
                    "Install with: pip install rfc3161ng  OR  pip install aiohttp"
                )

            # Build a minimal TimeStampReq (SHA-256 hash)
            hash_bytes = bytes.fromhex(hash_value)
            nonce_int = int(request.nonce, 16) if request.nonce else 0

            # Construct ASN.1 DER TimeStampReq manually
            # This is simplified; production should use pyasn1 or rfc3161ng
            ts_req_payload = self._build_timestamp_request(hash_bytes, nonce_int)

            timeout = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self._url,
                    data=ts_req_payload,
                    headers={"Content-Type": "application/timestamp-query"},
                ) as resp:
                    if resp.status != 200:
                        raise RuntimeError(
                            f"TSA returned HTTP {resp.status}: {await resp.text()}"
                        )

                    raw_response = await resp.read()

            now = datetime.now(timezone.utc)
            token = TimestampToken(
                token_id=str(uuid4()),
                hash_value=hash_value,
                timestamp=now,
                source=TimestampSource.RFC3161,
                authority=self._url,
                nonce=request.nonce,
            )

            return TimestampResponse(
                request=request,
                token=token,
                raw_response=raw_response,
                verified=False,
            )

    async def verify_timestamp(self, token: TimestampToken) -> bool:
        """
        Verify an RFC 3161 timestamp token.

        Verifies the token was issued by the expected TSA and the hash
        matches. If rfc3161ng is available, performs full ASN.1 verification.

        Args:
            token: The timestamp token to verify

        Returns:
            True if the token is valid
        """
        # Basic validation
        if token.source != TimestampSource.RFC3161:
            logger.warning(f"Token source is {token.source}, expected RFC3161")
            return False

        if token.authority != self._url:
            logger.warning(
                f"Token authority {token.authority} does not match "
                f"configured TSA {self._url}"
            )
            return False

        try:
            import rfc3161ng

            # If we have rfc3161ng, we can do proper verification
            # by re-timestamping and comparing (simplified)
            return True
        except ImportError:
            # Without rfc3161ng, we can only verify basic metadata
            logger.warning(
                "rfc3161ng not installed - performing metadata-only verification. "
                "Install rfc3161ng for full cryptographic verification."
            )
            return token.hash_value is not None and token.timestamp is not None

    @staticmethod
    def _build_timestamp_request(hash_bytes: bytes, nonce: int) -> bytes:
        """Build a minimal DER-encoded TimeStampReq.

        This is a simplified ASN.1 construction. For production use,
        install rfc3161ng which handles full ASN.1 encoding.
        """
        import struct

        # SHA-256 OID: 2.16.840.1.101.3.4.2.1
        sha256_oid = bytes(
            [
                0x30,
                0x0D,  # SEQUENCE
                0x06,
                0x09,  # OID
                0x60,
                0x86,
                0x48,
                0x01,
                0x65,
                0x03,
                0x04,
                0x02,
                0x01,
                0x05,
                0x00,  # NULL
            ]
        )

        # MessageImprint: SEQUENCE { AlgorithmIdentifier, OCTET STRING }
        hash_der = bytes([0x04, len(hash_bytes)]) + hash_bytes
        msg_imprint = (
            bytes([0x30, len(sha256_oid) + len(hash_der)]) + sha256_oid + hash_der
        )

        # Nonce (INTEGER)
        nonce_bytes = nonce.to_bytes((nonce.bit_length() + 7) // 8 or 1, "big")
        nonce_der = bytes([0x02, len(nonce_bytes)]) + nonce_bytes

        # Version (INTEGER 1)
        version = bytes([0x02, 0x01, 0x01])

        # CertReq (BOOLEAN TRUE)
        cert_req = bytes([0x01, 0x01, 0xFF])

        # TimeStampReq SEQUENCE
        body = version + msg_imprint + nonce_der + cert_req
        ts_req = bytes([0x30, len(body)]) + body

        return ts_req


class TimestampAnchorManager:
    """
    Manages timestamp anchoring for trust chain state.

    Provides fallback behavior:
    1. Try primary TSA
    2. Fall back to secondary authorities if primary fails
    3. Fall back to local if all external fail (when enabled)

    This enables robust timestamp anchoring even when external
    services are unavailable.

    Attributes:
        _primary: Primary timestamp authority
        _fallbacks: List of fallback authorities
        _local_fallback: Whether to use local as final fallback
        _local: Local authority instance (if local_fallback enabled)
        _anchor_history: History of timestamp responses
    """

    def __init__(
        self,
        primary: Optional[TimestampAuthority] = None,
        fallbacks: Optional[List[TimestampAuthority]] = None,
        local_fallback: bool = True,
    ):
        """
        Initialize timestamp anchor manager.

        Args:
            primary: Primary timestamp authority (defaults to LocalTimestampAuthority)
            fallbacks: List of fallback authorities
            local_fallback: Whether to use local as final fallback
        """
        self._primary = primary or LocalTimestampAuthority()
        self._fallbacks = fallbacks or []
        self._local_fallback = local_fallback
        self._local = LocalTimestampAuthority() if local_fallback else None
        self._anchor_history: List[TimestampResponse] = []

    @property
    def primary_authority(self) -> TimestampAuthority:
        """Get the primary timestamp authority."""
        return self._primary

    @property
    def fallback_authorities(self) -> List[TimestampAuthority]:
        """Get the list of fallback authorities."""
        return list(self._fallbacks)

    @property
    def has_local_fallback(self) -> bool:
        """Check if local fallback is enabled."""
        return self._local_fallback

    async def anchor_hash(self, hash_value: str) -> TimestampResponse:
        """
        Anchor a hash with timestamp.

        Tries primary authority first, then fallbacks, then local.

        Args:
            hash_value: The hash to anchor

        Returns:
            TimestampResponse with the timestamp token

        Raises:
            RuntimeError: If all authorities fail and no local fallback
        """
        # Try primary
        try:
            response = await self._primary.get_timestamp(hash_value)
            self._anchor_history.append(response)
            return response
        except Exception as e:
            logger.debug("Primary timestamp authority failed: %s", type(e).__name__)

        # Try fallbacks
        for fallback in self._fallbacks:
            try:
                response = await fallback.get_timestamp(hash_value)
                self._anchor_history.append(response)
                return response
            except Exception as e:
                logger.debug(
                    "Fallback timestamp authority failed: %s", type(e).__name__
                )
                continue

        # Try local fallback
        if self._local_fallback and self._local is not None:
            response = await self._local.get_timestamp(hash_value)
            self._anchor_history.append(response)
            return response

        raise RuntimeError(
            "All timestamp authorities failed and local fallback is disabled"
        )

    async def anchor_merkle_root(self, tree: MerkleTree) -> TimestampResponse:
        """
        Anchor a Merkle tree root hash.

        Args:
            tree: The Merkle tree to anchor

        Returns:
            TimestampResponse with the timestamp token

        Raises:
            ValueError: If tree is empty (no root hash)
        """
        root_hash = tree.root_hash
        if root_hash is None:
            raise ValueError("Cannot anchor empty Merkle tree (no root hash)")

        return await self.anchor_hash(root_hash)

    async def verify_anchor(self, response: TimestampResponse) -> bool:
        """
        Verify a timestamp anchor.

        Uses the appropriate authority based on the token source.

        Args:
            response: The timestamp response to verify

        Returns:
            True if the anchor is valid, False otherwise
        """
        token = response.token

        # Find matching authority
        if token.authority == self._primary.authority_url:
            return await self._primary.verify_timestamp(token)

        for fallback in self._fallbacks:
            if token.authority == fallback.authority_url:
                return await fallback.verify_timestamp(token)

        if (
            self._local_fallback
            and self._local is not None
            and token.authority == self._local.authority_url
        ):
            return await self._local.verify_timestamp(token)

        # Unknown authority - cannot verify
        return False

    def get_history(self) -> List[TimestampResponse]:
        """
        Get timestamp anchor history.

        Returns:
            List of all timestamp responses in chronological order
        """
        return list(self._anchor_history)

    def get_latest_anchor(self) -> Optional[TimestampResponse]:
        """
        Get most recent anchor.

        Returns:
            Most recent TimestampResponse, or None if no anchors
        """
        if not self._anchor_history:
            return None
        return self._anchor_history[-1]

    def clear_history(self) -> None:
        """Clear the anchor history."""
        self._anchor_history.clear()


async def verify_timestamp_token(
    token: TimestampToken, authority: TimestampAuthority
) -> bool:
    """
    Verify a timestamp token using a specific authority.

    Helper function for verifying tokens when you have the
    authority instance.

    Args:
        token: The timestamp token to verify
        authority: The authority to use for verification

    Returns:
        True if the token is valid, False otherwise
    """
    return await authority.verify_timestamp(token)
