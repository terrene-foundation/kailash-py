# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Security Hardening (Week 11).

Provides comprehensive security features for the Enterprise Agent Trust Protocol:
- Input validation to prevent injection attacks
- Encrypted key storage at rest using Fernet encryption
- Per-authority rate limiting for trust operations
- Security audit logging with event tracking

All security-critical operations are logged and rate-limited to prevent abuse.
"""

import asyncio
import base64
import hashlib
import logging
import os
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    Fernet = None
    PBKDF2HMAC = None
    hashes = None
    default_backend = None

from eatp.exceptions import TrustError

# ============================================================================
# Exceptions
# ============================================================================


class SecurityError(TrustError):
    """Base exception for security-related errors."""

    pass


class ValidationError(SecurityError):
    """Raised when input validation fails."""

    pass


class EncryptionError(SecurityError):
    """Raised when encryption/decryption operations fail."""

    pass


class RateLimitExceededError(SecurityError):
    """Raised when rate limit is exceeded."""

    def __init__(self, operation: str, authority_id: str, limit: int):
        super().__init__(
            f"Rate limit exceeded for {operation} by {authority_id}: {limit} ops/minute",
            details={
                "operation": operation,
                "authority_id": authority_id,
                "limit": limit,
            },
        )
        self.operation = operation
        self.authority_id = authority_id
        self.limit = limit


# ============================================================================
# Security Event Data Structures
# ============================================================================


class SecurityEventType(str, Enum):
    """Types of security events that can be logged."""

    # Authentication Events
    AUTHENTICATION_SUCCESS = "authentication_success"
    AUTHENTICATION_FAILURE = "authentication_failure"

    # Authorization Events
    AUTHORIZATION_SUCCESS = "authorization_success"
    AUTHORIZATION_FAILURE = "authorization_failure"

    # Trust Operation Events
    ESTABLISH_TRUST = "establish_trust"
    VERIFY_TRUST = "verify_trust"
    DELEGATE_CAPABILITY = "delegate_capability"
    REVOKE_DELEGATION = "revoke_delegation"

    # Security Validation Events
    VALIDATION_SUCCESS = "validation_success"
    VALIDATION_FAILURE = "validation_failure"

    # Key Management Events
    KEY_STORED = "key_stored"
    KEY_RETRIEVED = "key_retrieved"
    KEY_DELETED = "key_deleted"

    # Rate Limiting Events
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    RATE_LIMIT_WARNING = "rate_limit_warning"

    # Attack Detection
    INJECTION_ATTEMPT = "injection_attempt"
    REPLAY_ATTACK = "replay_attack"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"

    # Credential Rotation Events
    ROTATION_STARTED = "rotation_started"
    ROTATION_COMPLETED = "rotation_completed"
    ROTATION_FAILED = "rotation_failed"
    ROTATION_SCHEDULED = "rotation_scheduled"
    ROTATION_KEY_REVOKED = "rotation_key_revoked"
    SCHEDULED_ROTATION_FAILED = "scheduled_rotation_failed"
    CHAIN_RESIGN_INCONSISTENT_STATE = "chain_resign_inconsistent_state"  # CARE-048


class SecurityEventSeverity(str, Enum):
    """Severity levels for security events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class SecurityEvent:
    """
    Represents a security event for audit logging.

    Attributes:
        event_type: Type of security event
        timestamp: When the event occurred (UTC)
        authority_id: Authority involved in the event
        agent_id: Agent involved in the event (optional)
        details: Additional context about the event
        severity: Severity level of the event

    Example:
        >>> event = SecurityEvent(
        ...     event_type=SecurityEventType.ESTABLISH_TRUST,
        ...     timestamp=datetime.now(timezone.utc),
        ...     authority_id="org-acme",
        ...     agent_id="agent-001",
        ...     details={"capability": "analyze_data"},
        ...     severity=SecurityEventSeverity.INFO
        ... )
    """

    event_type: SecurityEventType
    timestamp: datetime
    authority_id: str
    agent_id: Optional[str] = None
    details: Dict = field(default_factory=dict)
    severity: SecurityEventSeverity = SecurityEventSeverity.INFO


# ============================================================================
# Input Validation
# ============================================================================


class TrustSecurityValidator:
    """
    Validates input to prevent injection attacks and ensure data integrity.

    Provides validation for:
    - Agent IDs (UUID format)
    - Authority IDs (alphanumeric with hyphens)
    - Capability URIs (valid URI format)
    - Metadata sanitization (remove unsafe content)

    Example:
        >>> validator = TrustSecurityValidator()
        >>> validator.validate_agent_id("550e8400-e29b-41d4-a716-446655440000")
        True
        >>> validator.validate_agent_id("invalid<script>")
        False
    """

    # Regex patterns for validation
    UUID_PATTERN = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )
    AUTHORITY_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-_]{0,63}$")

    # Unsafe characters/patterns in metadata
    UNSAFE_PATTERNS = [
        re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
        re.compile(r"javascript:", re.IGNORECASE),
        re.compile(r"on\w+\s*=", re.IGNORECASE),  # Event handlers
        re.compile(r"data:text/html", re.IGNORECASE),
    ]

    def validate_agent_id(self, agent_id: str) -> bool:
        """
        Validate agent ID is in UUID format.

        Args:
            agent_id: Agent identifier to validate

        Returns:
            True if valid UUID format, False otherwise

        Example:
            >>> validator = TrustSecurityValidator()
            >>> validator.validate_agent_id("550e8400-e29b-41d4-a716-446655440000")
            True
            >>> validator.validate_agent_id("invalid-id")
            False
        """
        if not isinstance(agent_id, str):
            return False
        return bool(self.UUID_PATTERN.match(agent_id))

    def validate_authority_id(self, authority_id: str) -> bool:
        """
        Validate authority ID is alphanumeric with hyphens/underscores.

        Authority IDs must:
        - Start with alphanumeric character
        - Contain only alphanumeric, hyphens, or underscores
        - Be 1-64 characters long

        Args:
            authority_id: Authority identifier to validate

        Returns:
            True if valid format, False otherwise

        Example:
            >>> validator = TrustSecurityValidator()
            >>> validator.validate_authority_id("org-acme-corp")
            True
            >>> validator.validate_authority_id("org<script>")
            False
        """
        if not isinstance(authority_id, str):
            return False
        if not authority_id or len(authority_id) > 64:
            return False
        return bool(self.AUTHORITY_ID_PATTERN.match(authority_id))

    def validate_capability_uri(self, uri: str) -> bool:
        """
        Validate capability URI is in valid URI format.

        Checks that:
        - URI has valid scheme (http, https, urn, etc.)
        - URI structure is well-formed
        - No unsafe characters present

        Args:
            uri: Capability URI to validate

        Returns:
            True if valid URI format, False otherwise

        Example:
            >>> validator = TrustSecurityValidator()
            >>> validator.validate_capability_uri("urn:capability:read")
            True
            >>> validator.validate_capability_uri("javascript:alert(1)")
            False
        """
        if not isinstance(uri, str):
            return False

        try:
            parsed = urlparse(uri)

            # Must have a scheme
            if not parsed.scheme:
                return False

            # Block dangerous schemes
            dangerous_schemes = ["javascript", "data", "vbscript"]
            if parsed.scheme.lower() in dangerous_schemes:
                return False

            # For http/https, must have netloc
            if parsed.scheme.lower() in ["http", "https"]:
                if not parsed.netloc:
                    return False

            return True

        except Exception:
            return False

    def sanitize_metadata(self, metadata: Dict) -> Dict:
        """
        Remove unsafe content from metadata dictionary.

        Recursively sanitizes:
        - String values: Removes script tags, event handlers, etc.
        - Nested dictionaries: Recursively sanitizes all values
        - Lists: Sanitizes each element

        Args:
            metadata: Metadata dictionary to sanitize

        Returns:
            Sanitized metadata dictionary

        Example:
            >>> validator = TrustSecurityValidator()
            >>> unsafe = {"name": "Test<script>alert(1)</script>", "count": 5}
            >>> safe = validator.sanitize_metadata(unsafe)
            >>> "<script>" not in safe["name"]
            True
        """
        if not isinstance(metadata, dict):
            return {}

        sanitized = {}
        for key, value in metadata.items():
            sanitized_key = self._sanitize_string(str(key))

            if isinstance(value, dict):
                sanitized[sanitized_key] = self.sanitize_metadata(value)
            elif isinstance(value, list):
                sanitized[sanitized_key] = [
                    self._sanitize_value(item) for item in value
                ]
            else:
                sanitized[sanitized_key] = self._sanitize_value(value)

        return sanitized

    def _sanitize_value(self, value):
        """Sanitize a single value."""
        if isinstance(value, str):
            return self._sanitize_string(value)
        elif isinstance(value, dict):
            return self.sanitize_metadata(value)
        elif isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        else:
            return value

    def _sanitize_string(self, text: str) -> str:
        """Remove unsafe patterns from string."""
        for pattern in self.UNSAFE_PATTERNS:
            text = pattern.sub("", text)
        return text


# ============================================================================
# Encrypted Key Storage
# ============================================================================


class SecureKeyStorage:
    """
    Encrypted storage for cryptographic keys using Fernet encryption.

    Keys are encrypted at rest using a master key derived from an
    environment variable. Provides secure storage, retrieval, and deletion.

    Args:
        master_key_source: Environment variable name for master key

    Example:
        >>> import os
        >>> os.environ['KAIZEN_TRUST_ENCRYPTION_KEY'] = 'test-master-key'
        >>> storage = SecureKeyStorage()
        >>> storage.store_key("key-001", b"private_key_bytes")
        >>> retrieved = storage.retrieve_key("key-001")
        >>> storage.delete_key("key-001")
    """

    def __init__(
        self,
        master_key_source: str = "KAIZEN_TRUST_ENCRYPTION_KEY",
        salt: Optional[bytes] = None,
    ):
        """
        Initialize secure key storage.

        Args:
            master_key_source: Environment variable name containing master key
            salt: Optional per-instance salt (CARE-001). If None, generates random salt
                  or uses salt from environment variable {master_key_source}_SALT.

        Raises:
            ImportError: If cryptography library is not installed
            EncryptionError: If master key cannot be derived
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError(
                "cryptography is required for secure key storage. "
                "Install with: pip install cryptography"
            )

        self.master_key_source = master_key_source
        self._keys: Dict[str, bytes] = {}  # Encrypted keys in memory
        self._salt = salt  # CARE-001: per-instance salt
        self._fernet = self._initialize_fernet()

    def _initialize_fernet(self) -> Fernet:
        """
        Initialize Fernet cipher with derived key.

        Derives a 32-byte encryption key from the master key using PBKDF2
        with a per-instance random salt (CARE-001 fix).

        Returns:
            Fernet cipher instance

        Raises:
            EncryptionError: If master key is not set or invalid
        """
        master_key = os.environ.get(self.master_key_source)
        if not master_key:
            raise EncryptionError(
                f"Master key not found. Set {self.master_key_source} environment variable."
            )

        # CARE-001: Use per-instance salt instead of static salt
        # Priority: 1) explicit salt from __init__, 2) env var, 3) generate new
        if self._salt is not None:
            salt = self._salt
        else:
            salt_env_key = f"{self.master_key_source}_SALT"
            salt_b64 = os.environ.get(salt_env_key)
            if salt_b64:
                salt = base64.b64decode(salt_b64)
            else:
                salt = os.urandom(32)
                logger.warning(
                    "No salt configured for %s. Generated random salt - "
                    "keys will not be recoverable across restarts. "
                    "For production, set %s environment variable.",
                    salt_env_key,
                    salt_env_key,
                )
            # Store salt for this instance (needed for re-initialization)
            self._salt = salt

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(key)

    def store_key(self, key_id: str, private_key: bytes) -> None:
        """
        Store a private key with encryption.

        Args:
            key_id: Unique identifier for the key
            private_key: Private key bytes to store

        Raises:
            ValidationError: If key_id or private_key is invalid
            EncryptionError: If encryption fails

        Example:
            >>> storage = SecureKeyStorage()
            >>> storage.store_key("agent-001", b"private_key_data")
        """
        if not key_id or not isinstance(key_id, str):
            raise ValidationError("Invalid key_id: must be non-empty string")

        if not private_key or not isinstance(private_key, bytes):
            raise ValidationError("Invalid private_key: must be non-empty bytes")

        try:
            # Encrypt the private key
            encrypted_key = self._fernet.encrypt(private_key)
            self._keys[key_id] = encrypted_key

        except Exception as e:
            raise EncryptionError(f"Failed to store key: {e}")

    def retrieve_key(self, key_id: str) -> bytes:
        """
        Retrieve and decrypt a private key.

        Args:
            key_id: Unique identifier for the key

        Returns:
            Decrypted private key bytes

        Raises:
            ValidationError: If key_id is invalid or key not found
            EncryptionError: If decryption fails

        Example:
            >>> storage = SecureKeyStorage()
            >>> storage.store_key("agent-001", b"private_key_data")
            >>> key = storage.retrieve_key("agent-001")
        """
        if not key_id or not isinstance(key_id, str):
            raise ValidationError("Invalid key_id: must be non-empty string")

        encrypted_key = self._keys.get(key_id)
        if encrypted_key is None:
            raise ValidationError(f"Key not found: {key_id}")

        try:
            # Decrypt the private key
            decrypted_key = self._fernet.decrypt(encrypted_key)
            return decrypted_key

        except Exception as e:
            raise EncryptionError(f"Failed to retrieve key: {e}")

    def delete_key(self, key_id: str) -> None:
        """
        Securely delete a private key.

        Args:
            key_id: Unique identifier for the key

        Raises:
            ValidationError: If key_id is invalid or key not found

        Example:
            >>> storage = SecureKeyStorage()
            >>> storage.store_key("agent-001", b"private_key_data")
            >>> storage.delete_key("agent-001")
        """
        if not key_id or not isinstance(key_id, str):
            raise ValidationError("Invalid key_id: must be non-empty string")

        if key_id not in self._keys:
            raise ValidationError(f"Key not found: {key_id}")

        # Remove the key
        del self._keys[key_id]


# ============================================================================
# Rate Limiting
# ============================================================================


class TrustRateLimiter:
    """
    Per-authority rate limiting for trust operations.

    Implements sliding window rate limiting to prevent abuse of trust
    operations like establish and verify. Rate limits are per-authority
    to prevent a single authority from overwhelming the system.

    SECURITY (ROUND5-007): Limits tracked authorities to MAX_TRACKED_AUTHORITIES
    to prevent memory exhaustion attacks via unique authority IDs.

    Args:
        establish_per_minute: Max establish operations per authority per minute
        verify_per_minute: Max verify operations per authority per minute

    Example:
        >>> limiter = TrustRateLimiter(establish_per_minute=100, verify_per_minute=1000)
        >>> await limiter.check_rate("establish", "org-acme")
        True
        >>> await limiter.record_operation("establish", "org-acme")
    """

    # ROUND5-007: Maximum tracked authorities to prevent memory DoS
    MAX_TRACKED_AUTHORITIES = 10000

    def __init__(self, establish_per_minute: int = 100, verify_per_minute: int = 1000):
        """
        Initialize rate limiter with per-operation limits.

        Args:
            establish_per_minute: Max establish operations per authority per minute
            verify_per_minute: Max verify operations per authority per minute
        """
        self.establish_per_minute = establish_per_minute
        self.verify_per_minute = verify_per_minute

        # Track operations: {operation: {authority_id: [timestamps]}}
        self._operations: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._lock = asyncio.Lock()

    async def check_rate(self, operation: str, authority_id: str) -> bool:
        """
        Check if an operation is within rate limits.

        Args:
            operation: Operation type ("establish" or "verify")
            authority_id: Authority performing the operation

        Returns:
            True if within limits, False if rate limit exceeded

        Example:
            >>> limiter = TrustRateLimiter()
            >>> await limiter.check_rate("establish", "org-acme")
            True
        """
        async with self._lock:
            limit = self._get_limit(operation)
            timestamps = self._operations[operation][authority_id]

            # Remove timestamps older than 1 minute
            current_time = time.time()
            cutoff_time = current_time - 60  # 1 minute ago
            timestamps[:] = [ts for ts in timestamps if ts > cutoff_time]

            # Check if under limit
            return len(timestamps) < limit

    async def record_operation(self, operation: str, authority_id: str) -> None:
        """
        Record an operation for rate limiting.

        Args:
            operation: Operation type ("establish" or "verify")
            authority_id: Authority performing the operation

        Raises:
            RateLimitExceededError: If rate limit is exceeded

        Example:
            >>> limiter = TrustRateLimiter()
            >>> await limiter.record_operation("establish", "org-acme")
        """
        async with self._lock:
            limit = self._get_limit(operation)
            timestamps = self._operations[operation][authority_id]

            # Remove timestamps older than 1 minute
            current_time = time.time()
            cutoff_time = current_time - 60  # 1 minute ago
            timestamps[:] = [ts for ts in timestamps if ts > cutoff_time]

            # Check if under limit
            if len(timestamps) >= limit:
                raise RateLimitExceededError(operation, authority_id, limit)

            # ROUND5-007: Evict oldest authority if at capacity
            op_dict = self._operations[operation]
            if len(op_dict) >= self.MAX_TRACKED_AUTHORITIES:
                self._evict_oldest_authority(op_dict)

            # Record the operation
            timestamps.append(current_time)

    def _evict_oldest_authority(self, op_dict: Dict[str, List[float]]) -> None:
        """Evict the authority with the oldest most-recent timestamp.

        Prevents memory exhaustion from tracking unlimited unique
        authority IDs (ROUND5-007).

        Args:
            op_dict: Dictionary mapping authority_id to timestamp list
        """
        if not op_dict:
            return

        oldest_authority = None
        oldest_timestamp = float("inf")

        for authority_id, timestamps in op_dict.items():
            if timestamps:
                most_recent = max(timestamps)
                if most_recent < oldest_timestamp:
                    oldest_timestamp = most_recent
                    oldest_authority = authority_id
            else:
                # Empty timestamp list - evict immediately
                oldest_authority = authority_id
                break

        if oldest_authority:
            del op_dict[oldest_authority]
            logger.debug(
                "ROUND5-007: Evicted oldest authority %s to prevent memory DoS",
                oldest_authority,
            )

    def _get_limit(self, operation: str) -> int:
        """Get rate limit for an operation type."""
        if operation == "establish":
            return self.establish_per_minute
        elif operation == "verify":
            return self.verify_per_minute
        else:
            return 100  # Default limit


# ============================================================================
# Security Audit Logger
# ============================================================================


class SecurityAuditLogger:
    """
    Logs security events for audit trails and compliance.

    Maintains an in-memory log of security events with automatic cleanup
    of old events. In production, this should be backed by persistent storage.

    Args:
        max_events: Maximum events to keep in memory (older events are dropped)

    Example:
        >>> logger = SecurityAuditLogger()
        >>> logger.log_security_event(
        ...     event_type=SecurityEventType.ESTABLISH_TRUST,
        ...     details={"agent_id": "agent-001"}
        ... )
        >>> events = logger.get_recent_events(count=10)
    """

    def __init__(self, max_events: int = 10000):
        """
        Initialize security audit logger.

        Args:
            max_events: Maximum events to keep in memory
        """
        self.max_events = max_events
        self._events: List[SecurityEvent] = []
        # ROUND5-005: Use threading.Lock for sync methods, not asyncio.Lock
        self._lock = threading.Lock()

    def log_security_event(
        self,
        event_type: str,
        details: Dict,
        authority_id: str = "",
        agent_id: Optional[str] = None,
        severity: SecurityEventSeverity = SecurityEventSeverity.INFO,
    ) -> None:
        """
        Log a security event.

        Args:
            event_type: Type of security event
            details: Additional context about the event
            authority_id: Authority involved in the event
            agent_id: Agent involved in the event (optional)
            severity: Severity level of the event

        Example:
            >>> logger = SecurityAuditLogger()
            >>> logger.log_security_event(
            ...     event_type=SecurityEventType.ESTABLISH_TRUST,
            ...     details={"capability": "read"},
            ...     authority_id="org-acme",
            ...     agent_id="agent-001"
            ... )
        """
        event = SecurityEvent(
            event_type=SecurityEventType(event_type),
            timestamp=datetime.now(timezone.utc),
            authority_id=authority_id,
            agent_id=agent_id,
            details=details,
            severity=severity,
        )

        # ROUND5-005: Thread-safe append and trimming
        with self._lock:
            self._events.append(event)

            # Trim old events if over limit
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events :]

    def get_recent_events(
        self,
        count: int = 100,
        event_type: Optional[SecurityEventType] = None,
        authority_id: Optional[str] = None,
        severity: Optional[SecurityEventSeverity] = None,
    ) -> List[SecurityEvent]:
        """
        Get recent security events with optional filtering.

        Args:
            count: Maximum number of events to return
            event_type: Filter by event type (optional)
            authority_id: Filter by authority ID (optional)
            severity: Filter by severity level (optional)

        Returns:
            List of security events (most recent first)

        Example:
            >>> logger = SecurityAuditLogger()
            >>> events = logger.get_recent_events(count=10)
            >>> critical_events = logger.get_recent_events(
            ...     severity=SecurityEventSeverity.CRITICAL
            ... )
        """
        # ROUND5-005: Thread-safe copy and filtering
        with self._lock:
            filtered = self._events[:]

        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]

        if authority_id:
            filtered = [e for e in filtered if e.authority_id == authority_id]

        if severity:
            filtered = [e for e in filtered if e.severity == severity]

        # Return most recent events
        return list(reversed(filtered[-count:]))
