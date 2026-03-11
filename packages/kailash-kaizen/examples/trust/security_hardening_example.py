"""
EATP Security Hardening Example (Week 11).

Demonstrates comprehensive security features:
1. Input validation for agent IDs, authority IDs, and capability URIs
2. Encrypted key storage with Fernet encryption
3. Per-authority rate limiting
4. Security audit logging
"""

import asyncio
import os
from datetime import datetime, timezone

# Set encryption key (in production, load from secure environment)
os.environ["KAIZEN_TRUST_ENCRYPTION_KEY"] = "secure-master-key-for-demo"

from kaizen.trust.security import (
    EncryptionError,
    RateLimitExceededError,
    SecureKeyStorage,
    SecurityAuditLogger,
    SecurityEvent,
    SecurityEventSeverity,
    SecurityEventType,
    TrustRateLimiter,
    TrustSecurityValidator,
    ValidationError,
)


def demo_input_validation():
    """Demonstrate input validation to prevent injection attacks."""
    print("=" * 80)
    print("1. INPUT VALIDATION")
    print("=" * 80)

    validator = TrustSecurityValidator()

    # Valid inputs
    print("\nValid Inputs:")
    valid_agent_id = "550e8400-e29b-41d4-a716-446655440000"
    print(f"  Agent ID (UUID): {valid_agent_id}")
    print(f"  Valid: {validator.validate_agent_id(valid_agent_id)}")

    valid_authority = "org-acme-corp"
    print(f"\n  Authority ID: {valid_authority}")
    print(f"  Valid: {validator.validate_authority_id(valid_authority)}")

    valid_uri = "urn:capability:read:data"
    print(f"\n  Capability URI: {valid_uri}")
    print(f"  Valid: {validator.validate_capability_uri(valid_uri)}")

    # Invalid inputs (injection attempts)
    print("\nInvalid Inputs (Injection Attempts):")
    invalid_agent_id = "agent<script>alert(1)</script>"
    print(f"  Malicious Agent ID: {invalid_agent_id}")
    print(f"  Valid: {validator.validate_agent_id(invalid_agent_id)}")

    invalid_authority = "org'; DROP TABLE trust_chains;--"
    print(f"\n  SQL Injection Authority: {invalid_authority}")
    print(f"  Valid: {validator.validate_authority_id(invalid_authority)}")

    invalid_uri = "javascript:alert('XSS')"
    print(f"\n  XSS Capability URI: {invalid_uri}")
    print(f"  Valid: {validator.validate_capability_uri(invalid_uri)}")

    # Metadata sanitization
    print("\nMetadata Sanitization:")
    unsafe_metadata = {
        "name": "Agent<script>alert(1)</script>",
        "description": "This is <script>malicious</script> content",
        "nested": {
            "field": "<img src=x onerror=alert(1)>",
            "safe": "This is safe content",
        },
        "count": 42,
    }
    print(f"  Unsafe metadata: {unsafe_metadata}")

    safe_metadata = validator.sanitize_metadata(unsafe_metadata)
    print(f"  Sanitized metadata: {safe_metadata}")
    print(f"  Script tags removed: {'<script>' not in str(safe_metadata)}")


def demo_encrypted_key_storage():
    """Demonstrate encrypted key storage with Fernet."""
    print("\n" + "=" * 80)
    print("2. ENCRYPTED KEY STORAGE")
    print("=" * 80)

    storage = SecureKeyStorage()

    # Store keys
    print("\nStoring Keys:")
    agent_keys = {
        "agent-001": b"private_key_data_for_agent_001",
        "agent-002": b"private_key_data_for_agent_002",
        "agent-003": b"private_key_data_for_agent_003",
    }

    for key_id, private_key in agent_keys.items():
        storage.store_key(key_id, private_key)
        print(f"  Stored encrypted key for: {key_id}")

    # Retrieve keys
    print("\nRetrieving Keys:")
    for key_id in agent_keys.keys():
        retrieved = storage.retrieve_key(key_id)
        matches = retrieved == agent_keys[key_id]
        print(
            f"  Retrieved key for {key_id}: {'✓ matches' if matches else '✗ mismatch'}"
        )

    # Delete key
    print("\nDeleting Key:")
    storage.delete_key("agent-003")
    print("  Deleted key for: agent-003")

    try:
        storage.retrieve_key("agent-003")
        print("  ✗ Key should have been deleted")
    except ValidationError:
        print("  ✓ Key successfully deleted (retrieval failed as expected)")


async def demo_rate_limiting():
    """Demonstrate per-authority rate limiting."""
    print("\n" + "=" * 80)
    print("3. RATE LIMITING")
    print("=" * 80)

    limiter = TrustRateLimiter(establish_per_minute=5, verify_per_minute=10)

    # Test establish operations
    print("\nEstablish Operations (limit: 5/minute):")
    for i in range(6):
        authority_id = "org-acme"
        operation = "establish"

        can_proceed = await limiter.check_rate(operation, authority_id)
        print(f"  Operation {i+1}: can_proceed={can_proceed}")

        if can_proceed:
            try:
                await limiter.record_operation(operation, authority_id)
                print("    ✓ Recorded")
            except RateLimitExceededError as e:
                print(f"    ✗ Rate limit exceeded: {e.message}")
        else:
            print("    ✗ Rate limit would be exceeded")

    # Test verify operations (different limit)
    print("\nVerify Operations (limit: 10/minute):")
    for i in range(10):
        authority_id = "org-acme"
        operation = "verify"

        can_proceed = await limiter.check_rate(operation, authority_id)
        if can_proceed:
            await limiter.record_operation(operation, authority_id)

    print("  ✓ Recorded 10 verify operations")

    # Test per-authority isolation
    print("\nPer-Authority Isolation:")
    other_authority = "org-other"
    can_proceed = await limiter.check_rate("establish", other_authority)
    print(f"  Can 'org-other' establish? {can_proceed}")
    print("  ✓ Different authority has independent limit")


def demo_security_audit_logging():
    """Demonstrate security event logging."""
    print("\n" + "=" * 80)
    print("4. SECURITY AUDIT LOGGING")
    print("=" * 80)

    logger = SecurityAuditLogger(max_events=1000)

    # Log various security events
    print("\nLogging Security Events:")
    events_to_log = [
        (
            SecurityEventType.ESTABLISH_TRUST,
            {"agent_id": "agent-001", "capability": "read"},
            SecurityEventSeverity.INFO,
        ),
        (
            SecurityEventType.VERIFY_TRUST,
            {"agent_id": "agent-001", "action": "read_data"},
            SecurityEventSeverity.INFO,
        ),
        (
            SecurityEventType.DELEGATE_CAPABILITY,
            {"from": "agent-001", "to": "agent-002"},
            SecurityEventSeverity.INFO,
        ),
        (
            SecurityEventType.VALIDATION_FAILURE,
            {"reason": "Invalid UUID"},
            SecurityEventSeverity.WARNING,
        ),
        (
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            {"authority": "org-acme", "operation": "establish"},
            SecurityEventSeverity.WARNING,
        ),
        (
            SecurityEventType.INJECTION_ATTEMPT,
            {"input": "'; DROP TABLE users;--"},
            SecurityEventSeverity.CRITICAL,
        ),
    ]

    for event_type, details, severity in events_to_log:
        logger.log_security_event(
            event_type=event_type,
            details=details,
            authority_id="org-acme",
            agent_id=details.get("agent_id"),
            severity=severity,
        )
        print(f"  Logged: {event_type.value} (severity: {severity.value})")

    # Query recent events
    print("\nRecent Events (all):")
    recent = logger.get_recent_events(count=10)
    for event in recent[:3]:  # Show first 3
        print(f"  [{event.timestamp.isoformat()}] {event.event_type.value}")
        print(f"    Authority: {event.authority_id}, Severity: {event.severity.value}")

    # Query by severity
    print("\nCritical Events Only:")
    critical = logger.get_recent_events(
        count=10, severity=SecurityEventSeverity.CRITICAL
    )
    for event in critical:
        print(f"  [{event.timestamp.isoformat()}] {event.event_type.value}")
        print(f"    Details: {event.details}")

    # Query by event type
    print("\nRate Limit Events Only:")
    rate_limit_events = logger.get_recent_events(
        count=10, event_type=SecurityEventType.RATE_LIMIT_EXCEEDED
    )
    print(f"  Found {len(rate_limit_events)} rate limit event(s)")


async def main():
    """Run all security hardening demonstrations."""
    print("\n" + "=" * 80)
    print("EATP SECURITY HARDENING DEMONSTRATION (Week 11)")
    print("=" * 80)

    # 1. Input Validation
    demo_input_validation()

    # 2. Encrypted Key Storage
    demo_encrypted_key_storage()

    # 3. Rate Limiting
    await demo_rate_limiting()

    # 4. Security Audit Logging
    demo_security_audit_logging()

    print("\n" + "=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)
    print("\nKey Features Demonstrated:")
    print("  ✓ Input validation prevents injection attacks")
    print("  ✓ Keys encrypted at rest using Fernet")
    print("  ✓ Rate limiting is per-authority")
    print("  ✓ All security events logged with severity")
    print("\nFor production use:")
    print("  1. Set KAIZEN_TRUST_ENCRYPTION_KEY environment variable")
    print("  2. Integrate with persistent audit storage (e.g., PostgreSQL)")
    print("  3. Set appropriate rate limits based on load")
    print("  4. Monitor critical security events for alerting")


if __name__ == "__main__":
    asyncio.run(main())
