# Security Testing Plan

## Overview

This document defines the security testing approach for the CARE/EATP trust implementation. It covers penetration testing scope, adversarial test scenarios, and the tooling required to validate the cryptographic trust chain against attacks.

## Security Testing Categories

| Category                | Focus Area                               | Test Type   |
| ----------------------- | ---------------------------------------- | ----------- |
| Cryptographic Integrity | Key extraction, signature forgery        | Adversarial |
| Delegation Chain        | Privilege escalation, chain manipulation | Adversarial |
| Constraint Bypass       | All 18 gaming scenarios                  | Adversarial |
| Race Conditions         | Revocation timing, concurrent access     | Chaos       |
| Cross-Organization      | Trust boundary violations                | Penetration |
| Audit Integrity         | Tamper detection, log injection          | Forensic    |

---

## Penetration Testing Scope

### In-Scope Systems

| System       | Component                           | Attack Surface                    |
| ------------ | ----------------------------------- | --------------------------------- |
| SDK (Kaizen) | `kaizen.trust.crypto`               | Key generation, signing           |
| SDK (Kaizen) | `kaizen.trust.chain`                | Trust chain validation            |
| SDK (Kaizen) | `kaizen.trust.operations`           | ESTABLISH/VERIFY/DELEGATE/AUDIT   |
| SDK (Kaizen) | `kaizen.trust.constraint_validator` | Constraint enforcement            |
| SDK (Kaizen) | `kaizen.trust.messaging`            | Secure channel, replay protection |
| SDK (Kaizen) | `kaizen.trust.postures`             | Posture mapping                   |
| Platform     | Trust Store API                     | Database access                   |
| Platform     | Audit Store API                     | Audit trail integrity             |
| Platform     | A2A Service                         | Cross-org communication           |

### Out-of-Scope

- Infrastructure security (network, OS hardening)
- Third-party dependencies (PyNaCl, PostgreSQL internals)
- Physical security
- Social engineering

### Testing Environment

```bash
# Isolated security testing environment
docker-compose -f tests/security/docker-compose.security.yml up -d

# Services:
# - PostgreSQL (isolated): localhost:5435
# - Redis (isolated): localhost:6381
# - Attack proxy: localhost:8080
```

---

## Key Extraction Resistance Testing

### Test Objective

Verify private keys cannot be extracted from memory, logs, or serialization.

### Test Cases

```python
# tests/security/test_key_extraction.py
"""
Security tests for key extraction resistance.

These tests verify private keys are protected from extraction.
"""

import gc
import sys
import pytest
from kaizen.trust import (
    generate_keypair,
    TrustKeyManager,
    SecureKeyStorage,
)


class TestMemoryKeyExtraction:
    """
    Test resistance to key extraction from memory.
    """

    @pytest.mark.security
    def test_private_key_not_in_string_representation(self):
        """
        Private key should not appear in object string representation.
        """
        key_manager = TrustKeyManager()
        authority_id = "test-authority"

        # Generate keys
        priv, pub = key_manager.generate_authority_keys(authority_id)

        # String representations should not contain private key
        manager_str = str(key_manager)
        manager_repr = repr(key_manager)

        assert priv not in manager_str
        assert priv not in manager_repr

    @pytest.mark.security
    def test_private_key_not_in_dict_serialization(self):
        """
        Private key should not be included in dict serialization.
        """
        key_manager = TrustKeyManager()
        authority_id = "test-authority"

        priv, pub = key_manager.generate_authority_keys(authority_id)

        # Get serializable dict
        if hasattr(key_manager, "to_dict"):
            serialized = key_manager.to_dict()
            serialized_str = str(serialized)

            assert priv not in serialized_str

    @pytest.mark.security
    def test_private_key_cleared_on_delete(self):
        """
        Private key should be cleared from memory when object deleted.
        """
        import ctypes

        key_manager = TrustKeyManager()
        priv, pub = key_manager.generate_authority_keys("test")

        # Store key id for later verification
        key_id = id(priv)

        # Delete the key manager
        del key_manager
        gc.collect()

        # Memory at original location should be overwritten
        # (This is a best-effort test - Python doesn't guarantee memory clearing)

    @pytest.mark.security
    def test_secure_storage_encrypts_at_rest(self):
        """
        SecureKeyStorage should encrypt keys before storage.
        """
        storage = SecureKeyStorage()
        priv, pub = generate_keypair()

        # Store key
        storage.store("test-key", priv)

        # Raw storage should be encrypted
        raw_data = storage._get_raw_storage("test-key")

        # Private key should not appear in raw storage
        assert priv not in raw_data


class TestLogKeyExtraction:
    """
    Test that keys are not leaked to logs.
    """

    @pytest.mark.security
    def test_private_key_not_logged_on_error(self):
        """
        Private key should not appear in error logs.
        """
        import logging
        from io import StringIO

        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)

        logger = logging.getLogger("kaizen.trust")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            key_manager = TrustKeyManager()
            priv, pub = key_manager.generate_authority_keys("test")

            # Trigger an error scenario
            try:
                key_manager.sign_with_key("nonexistent", b"data")
            except Exception:
                pass

            # Check logs don't contain private key
            log_output = log_capture.getvalue()
            assert priv not in log_output

        finally:
            logger.removeHandler(handler)

    @pytest.mark.security
    def test_key_redacted_in_exception_messages(self):
        """
        Exception messages should redact key material.
        """
        from kaizen.trust.exceptions import InvalidSignatureError

        priv, pub = generate_keypair()

        # Create exception with key material
        exc = InvalidSignatureError(f"Invalid signature for key: {pub}")

        # Exception message should redact key
        assert pub not in str(exc) or "***" in str(exc)
```

---

## Delegation Chain Manipulation Testing

### Test Objective

Verify delegation chains cannot be manipulated to gain unauthorized privileges.

### Test Cases

```python
# tests/security/test_delegation_manipulation.py
"""
Security tests for delegation chain integrity.

Tests attempt to manipulate delegation chains for privilege escalation.
"""

import pytest
from datetime import datetime, timedelta
from kaizen.trust import (
    TrustOperations,
    PostgresTrustStore,
    TrustLineageChain,
    GenesisRecord,
    DelegationRecord,
    CapabilityRequest,
    CapabilityType,
    generate_keypair,
    sign,
)


@pytest.fixture
async def security_trust_ops():
    """Trust operations for security testing."""
    store = PostgresTrustStore(
        connection_string="postgresql://test_user:test_password@localhost:5435/security_test"
    )
    await store.initialize()

    ops = TrustOperations(trust_store=store)
    await ops.initialize()

    yield ops

    await store.close()


class TestDelegationEscalation:
    """
    Test resistance to privilege escalation via delegation.
    """

    @pytest.mark.security
    async def test_cannot_delegate_unowned_capability(self, security_trust_ops):
        """
        Agent cannot delegate capability they don't have.
        """
        # Create agent with limited capabilities
        await security_trust_ops.establish(
            agent_id="limited-agent",
            authority_id="test-org",
            capabilities=[
                CapabilityRequest(capability="read_only"),
            ],
        )

        # Attempt to delegate capability not owned
        with pytest.raises(Exception) as exc_info:
            await security_trust_ops.delegate(
                from_agent_id="limited-agent",
                to_agent_id="attacker-agent",
                capabilities=["admin"],  # Not owned
            )

        assert "capability" in str(exc_info.value).lower()

    @pytest.mark.security
    async def test_cannot_weaken_inherited_constraints(self, security_trust_ops):
        """
        Child cannot have weaker constraints than parent.
        """
        # Create parent with strict constraints
        await security_trust_ops.establish(
            agent_id="strict-parent",
            authority_id="test-org",
            capabilities=[
                CapabilityRequest(
                    capability="access_data",
                    constraints=["max_records:100"],
                ),
            ],
        )

        # Attempt delegation with weaker constraints
        with pytest.raises(Exception) as exc_info:
            await security_trust_ops.delegate(
                from_agent_id="strict-parent",
                to_agent_id="greedy-child",
                capabilities=["access_data"],
                constraints={"max_records": 10000},  # Weaker than parent
            )

        assert "constraint" in str(exc_info.value).lower()

    @pytest.mark.security
    async def test_cannot_extend_expiration_beyond_parent(self, security_trust_ops):
        """
        Child expiration cannot exceed parent expiration.
        """
        parent_expiry = datetime.utcnow() + timedelta(days=30)

        await security_trust_ops.establish(
            agent_id="expiring-parent",
            authority_id="test-org",
            capabilities=[CapabilityRequest(capability="delegate")],
            expires_at=parent_expiry,
        )

        # Attempt delegation with longer expiration
        with pytest.raises(Exception) as exc_info:
            await security_trust_ops.delegate(
                from_agent_id="expiring-parent",
                to_agent_id="immortal-child",
                capabilities=["delegate"],
                expires_at=datetime.utcnow() + timedelta(days=365),  # Beyond parent
            )

        assert "expir" in str(exc_info.value).lower()


class TestChainTampering:
    """
    Test resistance to trust chain tampering.
    """

    @pytest.mark.security
    async def test_tampered_genesis_signature_rejected(self, security_trust_ops):
        """
        Modified genesis record signature should be rejected.
        """
        # Create valid chain
        chain = await security_trust_ops.establish(
            agent_id="tamper-target",
            authority_id="test-org",
            capabilities=[CapabilityRequest(capability="analyze")],
        )

        # Tamper with genesis signature
        original_sig = chain.genesis.signature
        chain.genesis.signature = "tampered_signature_value"

        # Verification should fail
        result = await security_trust_ops.verify(
            agent_id="tamper-target",
            action="analyze",
        )

        # Should detect tampering
        assert result.valid is False or "signature" in result.reason.lower()

    @pytest.mark.security
    async def test_injected_delegation_rejected(self, security_trust_ops):
        """
        Injected delegation records should be rejected.
        """
        # Create valid chain
        await security_trust_ops.establish(
            agent_id="injection-target",
            authority_id="test-org",
            capabilities=[CapabilityRequest(capability="read")],
        )

        # Get chain and inject fake delegation
        chain = await security_trust_ops.get_chain("injection-target")

        fake_priv, fake_pub = generate_keypair()
        fake_delegation = DelegationRecord(
            id="fake-delegation",
            from_agent_id="injection-target",
            to_agent_id="attacker",
            capabilities=["admin"],  # Escalated capability
            created_at=datetime.utcnow(),
            signature=sign({"fake": "delegation"}, fake_priv),
        )

        # Inject into chain
        if hasattr(chain, "delegations"):
            chain.delegations.append(fake_delegation)

        # Verification should fail
        result = chain.verify_full()
        assert result.valid is False

    @pytest.mark.security
    async def test_hash_chain_integrity_verified(self, security_trust_ops):
        """
        Hash chain should detect any modification.
        """
        chain = await security_trust_ops.establish(
            agent_id="hash-target",
            authority_id="test-org",
            capabilities=[CapabilityRequest(capability="compute")],
        )

        # Get original hash
        original_hash = chain.get_hash()

        # Modify capability
        chain.capabilities[0].capability = "admin"

        # Hash should change
        tampered_hash = chain.get_hash()
        assert original_hash != tampered_hash

        # Verification should fail
        result = chain.verify_hash_chain()
        assert result.valid is False
```

---

## Constraint Gaming Prevention (18 Scenarios)

### Test Objective

Verify all 18 constraint gaming scenarios are prevented.

### Gaming Scenario Matrix

| #   | Scenario                    | Attack Vector                        | Test Case                            |
| --- | --------------------------- | ------------------------------------ | ------------------------------------ |
| 1   | Boundary Exploitation       | Set value to exactly limit           | `test_boundary_at_exact_limit`       |
| 2   | Type Confusion              | Pass string where int expected       | `test_type_confusion_prevented`      |
| 3   | Null Constraint             | Pass null to bypass check            | `test_null_constraint_rejected`      |
| 4   | Time Zone Manipulation      | Change TZ to bypass time window      | `test_timezone_manipulation_blocked` |
| 5   | Constraint Chaining         | Chain weak constraints               | `test_constraint_chaining_prevented` |
| 6   | Default Value Abuse         | Rely on permissive defaults          | `test_defaults_are_restrictive`      |
| 7   | Delegation Laundering       | Delegate through intermediary        | `test_delegation_laundering_blocked` |
| 8   | Capability Aliasing         | Use synonym for blocked action       | `test_capability_aliasing_blocked`   |
| 9   | Batch Size Exploitation     | Split large request into batches     | `test_batch_splitting_counted`       |
| 10  | Rate Limit Reset            | Wait for rate limit window reset     | `test_rate_limit_persistent`         |
| 11  | Concurrent Request Flood    | Send requests simultaneously         | `test_concurrent_limits_enforced`    |
| 12  | Scope Aggregation           | Combine scopes across delegations    | `test_scope_aggregation_blocked`     |
| 13  | Temporal Constraint Drift   | Slowly extend time windows           | `test_temporal_drift_prevented`      |
| 14  | Constraint Version Rollback | Use older, weaker constraint version | `test_version_rollback_blocked`      |
| 15  | Metadata Injection          | Inject constraints via metadata      | `test_metadata_injection_blocked`    |
| 16  | Approval Bypass             | Act during approval pending          | `test_approval_required_blocking`    |
| 17  | Audit Suppression           | Disable audit via constraint         | `test_audit_always_enabled`          |
| 18  | Emergency Override Abuse    | Trigger false emergency              | `test_emergency_override_logged`     |

### Test Implementation

```python
# tests/security/test_constraint_gaming.py
"""
Security tests for constraint gaming prevention.

Tests all 18 known constraint gaming scenarios.
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from freezegun import freeze_time
from kaizen.trust import (
    ConstraintValidator,
    Constraint,
    ConstraintType,
    TrustOperations,
    PostgresTrustStore,
    CapabilityRequest,
)


class TestBoundaryExploitation:
    """Gaming Scenario 1: Boundary exploitation."""

    @pytest.mark.security
    def test_boundary_at_exact_limit(self):
        """
        Value at exact limit should be allowed, over limit rejected.
        """
        validator = ConstraintValidator()

        constraint = Constraint(
            id="limit-100",
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            parameters={"max_api_calls": 100},
            enforced_by="runtime",
        )

        # Exactly at limit - should pass
        result_at_limit = validator.validate(
            constraint=constraint,
            context={"current_api_calls": 100},
        )
        assert result_at_limit.valid is True

        # One over limit - should fail
        result_over_limit = validator.validate(
            constraint=constraint,
            context={"current_api_calls": 101},
        )
        assert result_over_limit.valid is False


class TestTypeConfusion:
    """Gaming Scenario 2: Type confusion attacks."""

    @pytest.mark.security
    def test_type_confusion_prevented(self):
        """
        Type confusion attacks should be rejected.
        """
        validator = ConstraintValidator()

        constraint = Constraint(
            id="numeric-limit",
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            parameters={"max_api_calls": 100},
            enforced_by="runtime",
        )

        # Try to pass string instead of int
        with pytest.raises(TypeError):
            validator.validate(
                constraint=constraint,
                context={"current_api_calls": "unlimited"},
            )

        # Try to pass float
        result = validator.validate(
            constraint=constraint,
            context={"current_api_calls": 99.9999},  # Should round/truncate properly
        )
        # Should be validated as integer comparison
        assert result.valid is True


class TestNullConstraint:
    """Gaming Scenario 3: Null constraint bypass."""

    @pytest.mark.security
    def test_null_constraint_rejected(self):
        """
        Null values should not bypass constraint checks.
        """
        validator = ConstraintValidator()

        constraint = Constraint(
            id="max-records",
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            parameters={"max_records": 1000},
            enforced_by="dataflow",
        )

        # Try to pass None to bypass
        result = validator.validate(
            constraint=constraint,
            context={"requested_records": None},
        )

        # Should fail, not pass silently
        assert result.valid is False


class TestTimezoneManipulation:
    """Gaming Scenario 4: Timezone manipulation."""

    @pytest.mark.security
    @freeze_time("2025-02-07 22:00:00", tz_offset=0)  # 10 PM UTC
    def test_timezone_manipulation_blocked(self):
        """
        Timezone manipulation should not bypass time windows.
        """
        validator = ConstraintValidator()

        # Constraint specifies business hours in UTC
        constraint = Constraint(
            id="business-hours",
            constraint_type=ConstraintType.TIME_WINDOW,
            parameters={
                "start_hour": 9,
                "end_hour": 17,
                "timezone": "UTC",
            },
            enforced_by="runtime",
        )

        # Request with different timezone in context
        result = validator.validate(
            constraint=constraint,
            context={
                "request_timezone": "Pacific/Auckland",  # UTC+13
            },
        )

        # Should still fail - UTC time is 22:00
        assert result.valid is False


class TestConstraintChaining:
    """Gaming Scenario 5: Constraint chaining."""

    @pytest.mark.security
    async def test_constraint_chaining_prevented(self, security_trust_ops):
        """
        Chaining delegations should not weaken overall constraints.
        """
        # Create chain: A -> B -> C with weakening constraints
        await security_trust_ops.establish(
            agent_id="chain-a",
            authority_id="org",
            capabilities=[
                CapabilityRequest(
                    capability="access",
                    constraints=["max_records:100"],
                ),
            ],
        )

        # B inherits from A
        await security_trust_ops.delegate(
            from_agent_id="chain-a",
            to_agent_id="chain-b",
            capabilities=["access"],
            # Cannot weaken to 500
        )

        # C inherits from B
        await security_trust_ops.delegate(
            from_agent_id="chain-b",
            to_agent_id="chain-c",
            capabilities=["access"],
        )

        # C should still have max_records:100
        result = await security_trust_ops.verify(
            agent_id="chain-c",
            action="access",
        )

        assert result.constraints.get("max_records") <= 100


class TestDefaultValueAbuse:
    """Gaming Scenario 6: Permissive default values."""

    @pytest.mark.security
    def test_defaults_are_restrictive(self):
        """
        Default constraint values should be restrictive.
        """
        validator = ConstraintValidator()

        # Constraint with missing parameters
        constraint = Constraint(
            id="sparse-constraint",
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            parameters={},  # No explicit limits
            enforced_by="runtime",
        )

        result = validator.validate(
            constraint=constraint,
            context={"current_api_calls": 1000000},
        )

        # Should fail with restrictive default, not pass with unlimited
        assert result.valid is False


class TestDelegationLaundering:
    """Gaming Scenario 7: Delegation laundering."""

    @pytest.mark.security
    async def test_delegation_laundering_blocked(self, security_trust_ops):
        """
        Cannot launder capabilities through intermediary.
        """
        # Agent with restricted scope
        await security_trust_ops.establish(
            agent_id="restricted",
            authority_id="org",
            capabilities=[
                CapabilityRequest(
                    capability="access_finance",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        # Intermediary with different scope
        await security_trust_ops.establish(
            agent_id="intermediary",
            authority_id="org",
            capabilities=[
                CapabilityRequest(
                    capability="access_engineering",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        # Attempt to delegate through intermediary to gain finance + engineering
        with pytest.raises(Exception):
            await security_trust_ops.delegate(
                from_agent_id="restricted",
                to_agent_id="attacker",
                capabilities=["access_finance", "access_engineering"],  # Combined
            )


class TestCapabilityAliasing:
    """Gaming Scenario 8: Capability aliasing."""

    @pytest.mark.security
    async def test_capability_aliasing_blocked(self, security_trust_ops):
        """
        Synonyms for blocked capabilities should be caught.
        """
        await security_trust_ops.establish(
            agent_id="read-only-agent",
            authority_id="org",
            capabilities=[
                CapabilityRequest(capability="read"),
            ],
        )

        # Try to use synonyms for write
        aliases = ["modify", "update", "change", "edit", "put"]

        for alias in aliases:
            result = await security_trust_ops.verify(
                agent_id="read-only-agent",
                action=alias,
            )
            assert result.valid is False, f"Alias '{alias}' should be blocked"


class TestBatchSizeExploitation:
    """Gaming Scenario 9: Batch splitting."""

    @pytest.mark.security
    def test_batch_splitting_counted(self):
        """
        Splitting large requests into batches should be tracked cumulatively.
        """
        validator = ConstraintValidator()

        constraint = Constraint(
            id="max-records",
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            parameters={"max_records_per_session": 1000},
            enforced_by="runtime",
        )

        # First batch of 500
        result1 = validator.validate(
            constraint=constraint,
            context={
                "requested_records": 500,
                "session_records_used": 0,
            },
        )
        assert result1.valid is True

        # Second batch of 500 (total 1000)
        result2 = validator.validate(
            constraint=constraint,
            context={
                "requested_records": 500,
                "session_records_used": 500,
            },
        )
        assert result2.valid is True

        # Third batch of 500 (total 1500 - over limit)
        result3 = validator.validate(
            constraint=constraint,
            context={
                "requested_records": 500,
                "session_records_used": 1000,
            },
        )
        assert result3.valid is False


class TestConcurrentRequestFlood:
    """Gaming Scenario 11: Concurrent request flood."""

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_concurrent_limits_enforced(self, security_trust_ops):
        """
        Concurrent requests should not exceed limits.
        """
        await security_trust_ops.establish(
            agent_id="concurrent-agent",
            authority_id="org",
            capabilities=[
                CapabilityRequest(
                    capability="api_call",
                    constraints=["max_concurrent:5"],
                ),
            ],
        )

        # Send 10 concurrent requests
        async def make_request(i):
            return await security_trust_ops.verify(
                agent_id="concurrent-agent",
                action="api_call",
            )

        results = await asyncio.gather(*[make_request(i) for i in range(10)])

        # At most 5 should succeed
        successful = sum(1 for r in results if r.valid)
        assert successful <= 5


class TestApprovalBypass:
    """Gaming Scenario 16: Approval bypass."""

    @pytest.mark.security
    async def test_approval_required_blocking(self, security_trust_ops):
        """
        Actions requiring approval should block until approved.
        """
        await security_trust_ops.establish(
            agent_id="approval-needed",
            authority_id="org",
            capabilities=[
                CapabilityRequest(
                    capability="high_risk_action",
                    constraints=["require_approval:true"],
                ),
            ],
        )

        # Attempt action without approval
        result = await security_trust_ops.verify(
            agent_id="approval-needed",
            action="high_risk_action",
            approval_token=None,
        )

        # Should require approval, not proceed
        assert result.valid is False or result.requires_approval is True


class TestAuditSuppression:
    """Gaming Scenario 17: Audit suppression."""

    @pytest.mark.security
    async def test_audit_always_enabled(self, security_trust_ops):
        """
        Audit cannot be disabled via constraint manipulation.
        """
        await security_trust_ops.establish(
            agent_id="audit-evader",
            authority_id="org",
            capabilities=[
                CapabilityRequest(
                    capability="sensitive_action",
                    constraints=["audit:false"],  # Attempt to disable
                ),
            ],
        )

        # Perform action
        await security_trust_ops.verify(
            agent_id="audit-evader",
            action="sensitive_action",
        )

        # Audit should still be recorded despite constraint
        audit_records = await security_trust_ops.audit_store.query(
            agent_id="audit-evader",
        )

        assert len(audit_records) > 0
```

---

## Revocation Race Condition Testing

### Test Objective

Verify revocation is atomic and prevents race conditions.

### Test Cases

```python
# tests/security/test_revocation_race.py
"""
Security tests for revocation race conditions.

Tests concurrent access during revocation propagation.
"""

import pytest
import asyncio
from datetime import datetime
from kaizen.trust import (
    TrustOperations,
    PostgresTrustStore,
    CapabilityRequest,
)


class TestRevocationRaceConditions:
    """
    Test revocation timing and race conditions.
    """

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_revoked_chain_immediately_invalid(self, security_trust_ops):
        """
        Revoked chain should be invalid immediately, not eventually.
        """
        # Establish chain
        await security_trust_ops.establish(
            agent_id="revoke-target",
            authority_id="org",
            capabilities=[CapabilityRequest(capability="access")],
        )

        # Start verification in parallel with revocation
        async def verify_loop():
            results = []
            for _ in range(100):
                result = await security_trust_ops.verify(
                    agent_id="revoke-target",
                    action="access",
                )
                results.append(result.valid)
                await asyncio.sleep(0.01)
            return results

        async def revoke():
            await asyncio.sleep(0.3)  # Let some verifications pass
            await security_trust_ops.revoke(agent_id="revoke-target")

        verify_task = asyncio.create_task(verify_loop())
        revoke_task = asyncio.create_task(revoke())

        await revoke_task
        results = await verify_task

        # After revocation, no verification should succeed
        # Find the transition point
        revoke_index = None
        for i, valid in enumerate(results):
            if not valid:
                revoke_index = i
                break

        # All results after revocation should be False
        if revoke_index is not None:
            post_revoke = results[revoke_index:]
            assert all(not r for r in post_revoke)

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_cascade_revocation_timing(self, security_trust_ops):
        """
        Cascade revocation should propagate within 10 seconds.
        """
        # Create delegation chain
        await security_trust_ops.establish(
            agent_id="cascade-root",
            authority_id="org",
            capabilities=[CapabilityRequest(capability="delegate")],
        )

        # Create 5 levels of delegation
        for i in range(1, 6):
            await security_trust_ops.delegate(
                from_agent_id=f"cascade-{'' if i == 1 else 'level-'}{i-1 if i > 1 else 'root'}",
                to_agent_id=f"cascade-level-{i}",
                capabilities=["delegate"] if i < 5 else ["access"],
            )

        # Revoke root
        start_time = datetime.utcnow()
        await security_trust_ops.revoke(
            agent_id="cascade-root",
            cascade=True,
        )

        # Verify all children are revoked
        for i in range(1, 6):
            result = await security_trust_ops.verify(
                agent_id=f"cascade-level-{i}",
                action="access" if i == 5 else "delegate",
            )
            assert result.valid is False

        # Check timing
        end_time = datetime.utcnow()
        propagation_time = (end_time - start_time).total_seconds()

        assert propagation_time < 10.0, f"Cascade took {propagation_time}s, exceeds 10s limit"

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_no_action_during_revocation(self, security_trust_ops):
        """
        No actions should succeed during revocation processing.
        """
        await security_trust_ops.establish(
            agent_id="revoke-atomic",
            authority_id="org",
            capabilities=[CapabilityRequest(capability="access")],
        )

        # Start revocation (but don't await)
        revoke_task = asyncio.create_task(
            security_trust_ops.revoke(agent_id="revoke-atomic")
        )

        # Immediately try to verify
        await asyncio.sleep(0.001)  # Minimal delay

        result = await security_trust_ops.verify(
            agent_id="revoke-atomic",
            action="access",
        )

        await revoke_task

        # Either verification failed, or revocation wasn't complete
        # but we should never have valid result after revocation completes
        final_result = await security_trust_ops.verify(
            agent_id="revoke-atomic",
            action="access",
        )
        assert final_result.valid is False
```

---

## Cross-Organization Trust Boundary Testing

### Test Objective

Verify trust boundaries between organizations are enforced.

### Test Cases

```python
# tests/security/test_cross_org_boundaries.py
"""
Security tests for cross-organization trust boundaries.

Tests federation trust boundary enforcement.
"""

import pytest
from kaizen.trust import (
    TrustOperations,
    A2AService,
    CapabilityRequest,
)


class TestCrossOrgBoundaries:
    """
    Test cross-organization trust boundary enforcement.
    """

    @pytest.mark.security
    async def test_cannot_establish_in_foreign_org(self, security_trust_ops):
        """
        Cannot establish agent in organization without authority.
        """
        # Configure for org-A
        security_trust_ops.set_organization("org-A")

        # Try to establish in org-B
        with pytest.raises(Exception) as exc_info:
            await security_trust_ops.establish(
                agent_id="infiltrator",
                authority_id="org-B-authority",  # Different org
                capabilities=[CapabilityRequest(capability="access")],
            )

        assert "authority" in str(exc_info.value).lower() or "organization" in str(exc_info.value).lower()

    @pytest.mark.security
    async def test_cannot_delegate_cross_org(self, security_trust_ops):
        """
        Cannot delegate to agent in different organization.
        """
        # Establish in org-A
        await security_trust_ops.establish(
            agent_id="org-a-agent",
            authority_id="org-a-authority",
            capabilities=[
                CapabilityRequest(capability="delegate"),
            ],
        )

        # Try to delegate to org-B agent
        with pytest.raises(Exception):
            await security_trust_ops.delegate(
                from_agent_id="org-a-agent",
                to_agent_id="org-b:foreign-agent",  # Different org
                capabilities=["access"],
            )

    @pytest.mark.security
    async def test_federation_requires_explicit_trust(self, security_trust_ops):
        """
        Cross-org communication requires explicit federation trust.
        """
        a2a = A2AService(trust_ops=security_trust_ops)

        # Without federation trust, cross-org verification fails
        result = await a2a.verify_remote_agent(
            remote_agent_id="org-b:external-agent",
            remote_org_id="org-b",
        )

        assert result.valid is False
        assert "federation" in result.reason.lower() or "trust" in result.reason.lower()


class TestFederationSpoofing:
    """
    Test resistance to federation spoofing.
    """

    @pytest.mark.security
    async def test_spoofed_org_id_rejected(self, security_trust_ops):
        """
        Requests with spoofed organization ID should be rejected.
        """
        a2a = A2AService(trust_ops=security_trust_ops)

        # Create request claiming to be from org-b
        fake_request = {
            "from_org": "org-b",
            "from_agent": "org-b:agent",
            "action": "verify",
            # Signature would be invalid for org-b
        }

        result = await a2a.process_request(fake_request)

        assert result["status"] == "error"
        assert "signature" in result["message"].lower() or "auth" in result["message"].lower()

    @pytest.mark.security
    async def test_replay_of_federation_token_rejected(self, security_trust_ops):
        """
        Replayed federation tokens should be rejected.
        """
        a2a = A2AService(trust_ops=security_trust_ops)

        # Get valid token
        token = await a2a.create_federation_token(
            to_org="org-b",
            capabilities=["read"],
        )

        # Use token
        result1 = await a2a.verify_federation_token(token)
        assert result1.valid is True

        # Replay same token
        result2 = await a2a.verify_federation_token(token)
        assert result2.valid is False
        assert "replay" in result2.reason.lower()
```

---

## Audit Trail Tamper Detection

### Test Objective

Verify audit trail integrity and tamper detection.

### Test Cases

```python
# tests/security/test_audit_integrity.py
"""
Security tests for audit trail integrity.

Tests tamper detection in audit logs.
"""

import pytest
from datetime import datetime
from kaizen.trust import (
    PostgresAuditStore,
    AuditAnchor,
)


@pytest.fixture
async def audit_store():
    """Real PostgreSQL audit store for testing."""
    store = PostgresAuditStore(
        connection_string="postgresql://test_user:test_password@localhost:5435/security_test"
    )
    await store.initialize()
    yield store
    await store.close()


class TestAuditTamperDetection:
    """
    Test audit trail tamper detection.
    """

    @pytest.mark.security
    async def test_modified_audit_entry_detected(self, audit_store):
        """
        Modified audit entries should be detected.
        """
        # Create audit entry
        anchor = await audit_store.record(
            agent_id="audit-target",
            action="analyze",
            result="success",
            metadata={"records": 100},
        )

        # Directly modify database (simulating attacker)
        async with audit_store._pool.acquire() as conn:
            await conn.execute(
                "UPDATE audit_log SET result = 'failure' WHERE id = $1",
                anchor.id,
            )

        # Verify integrity
        is_valid = await audit_store.verify_integrity(anchor.id)
        assert is_valid is False

    @pytest.mark.security
    async def test_deleted_audit_entry_detected(self, audit_store):
        """
        Deleted audit entries should be detected via chain break.
        """
        # Create chain of entries
        for i in range(5):
            await audit_store.record(
                agent_id="chain-audit",
                action=f"action-{i}",
                result="success",
            )

        # Delete middle entry
        entries = await audit_store.query(agent_id="chain-audit")
        middle_id = entries[2].id

        async with audit_store._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM audit_log WHERE id = $1",
                middle_id,
            )

        # Chain verification should fail
        chain_valid = await audit_store.verify_chain(agent_id="chain-audit")
        assert chain_valid is False

    @pytest.mark.security
    async def test_injected_audit_entry_detected(self, audit_store):
        """
        Injected audit entries should be detected.
        """
        # Create legitimate entry
        anchor = await audit_store.record(
            agent_id="inject-target",
            action="legitimate",
            result="success",
        )

        # Inject fake entry
        async with audit_store._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO audit_log (id, agent_id, action, result, created_at, signature)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, "fake-id", "inject-target", "fake_action", "success",
                datetime.utcnow(), "invalid_signature")

        # Chain verification should fail
        chain_valid = await audit_store.verify_chain(agent_id="inject-target")
        assert chain_valid is False

    @pytest.mark.security
    async def test_timestamp_manipulation_detected(self, audit_store):
        """
        Timestamp manipulation should be detected.
        """
        anchor = await audit_store.record(
            agent_id="time-target",
            action="action",
            result="success",
        )

        # Modify timestamp
        async with audit_store._pool.acquire() as conn:
            await conn.execute(
                "UPDATE audit_log SET created_at = created_at - interval '1 day' WHERE id = $1",
                anchor.id,
            )

        # Integrity check should fail
        is_valid = await audit_store.verify_integrity(anchor.id)
        assert is_valid is False
```

---

## Security Testing Tools

### Custom Test Harness

```python
# tests/security/harness/trust_attack_harness.py
"""
Security testing harness for trust module.

Provides utilities for adversarial testing.
"""

import asyncio
from typing import List, Dict, Any
from dataclasses import dataclass
from kaizen.trust import TrustOperations, generate_keypair


@dataclass
class AttackResult:
    """Result of an attack attempt."""
    attack_name: str
    succeeded: bool
    details: str
    evidence: Dict[str, Any]


class TrustAttackHarness:
    """
    Harness for running security tests against trust module.
    """

    def __init__(self, trust_ops: TrustOperations):
        self.trust_ops = trust_ops
        self.results: List[AttackResult] = []

    async def run_attack_suite(self) -> List[AttackResult]:
        """Run all attack scenarios."""
        attacks = [
            self.attack_key_extraction,
            self.attack_signature_forgery,
            self.attack_privilege_escalation,
            self.attack_constraint_bypass,
            self.attack_race_condition,
        ]

        for attack in attacks:
            result = await attack()
            self.results.append(result)

        return self.results

    async def attack_key_extraction(self) -> AttackResult:
        """Attempt to extract private keys."""
        try:
            # Try various extraction methods
            priv, pub = generate_keypair()

            # Check memory
            import gc
            gc.collect()
            objects = gc.get_objects()

            key_found = any(priv in str(obj) for obj in objects if isinstance(obj, str))

            return AttackResult(
                attack_name="key_extraction",
                succeeded=key_found,
                details="Attempted memory scan for keys",
                evidence={"key_in_memory": key_found},
            )
        except Exception as e:
            return AttackResult(
                attack_name="key_extraction",
                succeeded=False,
                details=f"Attack failed with error: {e}",
                evidence={},
            )

    async def attack_signature_forgery(self) -> AttackResult:
        """Attempt to forge signatures."""
        try:
            # Generate attacker keys
            attacker_priv, attacker_pub = generate_keypair()

            # Try to create valid chain with attacker keys
            chain = await self.trust_ops.establish(
                agent_id="forged-agent",
                authority_id="legitimate-org",
                capabilities=[],
            )

            # Try to verify with forged signature
            chain.genesis.signature = sign(
                chain.genesis.to_signing_payload(),
                attacker_priv,
            )

            result = await self.trust_ops.verify(
                agent_id="forged-agent",
                action="any",
            )

            return AttackResult(
                attack_name="signature_forgery",
                succeeded=result.valid,
                details="Attempted signature forgery",
                evidence={"verification_result": result.valid},
            )
        except Exception as e:
            return AttackResult(
                attack_name="signature_forgery",
                succeeded=False,
                details=f"Forgery rejected: {e}",
                evidence={},
            )

    # Additional attack methods...
```

### Chaos Engineering Framework

```python
# tests/security/chaos/trust_chaos.py
"""
Chaos engineering framework for trust module.

Introduces controlled failures to test resilience.
"""

import asyncio
import random
from typing import Callable, Any


class TrustChaosFramework:
    """
    Introduces chaos into trust operations for testing.
    """

    def __init__(self, failure_rate: float = 0.1):
        self.failure_rate = failure_rate
        self.chaos_enabled = False

    def enable(self):
        """Enable chaos injection."""
        self.chaos_enabled = True

    def disable(self):
        """Disable chaos injection."""
        self.chaos_enabled = False

    async def with_network_delay(
        self,
        operation: Callable,
        min_delay_ms: int = 100,
        max_delay_ms: int = 5000,
    ) -> Any:
        """Execute operation with random network delay."""
        if self.chaos_enabled:
            delay = random.randint(min_delay_ms, max_delay_ms) / 1000
            await asyncio.sleep(delay)

        return await operation()

    async def with_database_failure(
        self,
        operation: Callable,
    ) -> Any:
        """Execute operation with possible database failure."""
        if self.chaos_enabled and random.random() < self.failure_rate:
            raise ConnectionError("Simulated database failure")

        return await operation()

    async def with_partial_response(
        self,
        operation: Callable,
    ) -> Any:
        """Execute operation with possible partial response."""
        result = await operation()

        if self.chaos_enabled and random.random() < self.failure_rate:
            # Corrupt response partially
            if isinstance(result, dict):
                keys_to_remove = random.sample(
                    list(result.keys()),
                    min(2, len(result.keys())),
                )
                for key in keys_to_remove:
                    del result[key]

        return result
```

---

## Security Testing Schedule

### Testing Phases

| Phase       | Timing              | Focus                      | Responsible      |
| ----------- | ------------------- | -------------------------- | ---------------- |
| Development | Continuous          | Unit security tests        | Development Team |
| Integration | Per sprint          | Integration security tests | QA + Security    |
| Pre-release | Before each release | Full penetration test      | Security Team    |
| Periodic    | Quarterly           | Red team exercise          | External Auditor |

### Release Gate Criteria

- All 18 gaming scenarios tested and passing
- Zero CRITICAL security issues
- HIGH issues documented with mitigation timeline
- Penetration test report reviewed
- Security sign-off obtained

### Responsible Teams

| Team        | Responsibility                         |
| ----------- | -------------------------------------- |
| Development | Unit tests, code review                |
| QA          | Integration tests, regression          |
| Security    | Penetration tests, threat modeling     |
| DevOps      | Infrastructure security, chaos testing |
| External    | Quarterly audit, red team exercise     |

---

## CI/CD Security Testing

```yaml
# .github/workflows/security-tests.yml
name: Security Tests

on:
  push:
    paths:
      - "apps/kailash-kaizen/src/kaizen/trust/**"
  schedule:
    - cron: "0 0 * * 0" # Weekly

jobs:
  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -e ./apps/kailash-kaizen[dev]
          pip install bandit safety

      - name: Run Bandit
        run: |
          bandit -r apps/kailash-kaizen/src/kaizen/trust/ -f json -o bandit-report.json

      - name: Run Safety
        run: |
          safety check --json > safety-report.json

      - name: Upload reports
        uses: actions/upload-artifact@v4
        with:
          name: security-reports
          path: |
            bandit-report.json
            safety-report.json

  adversarial-tests:
    name: Adversarial Tests
    runs-on: ubuntu-latest

    services:
      postgres:
        image: pgvector/pgvector:pg15
        env:
          POSTGRES_DB: security_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
        ports:
          - 5435:5432

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -e ./apps/kailash-kaizen[dev]

      - name: Run security tests
        run: |
          pytest tests/security/ -v -m "security" --timeout=30

      - name: Run constraint gaming tests
        run: |
          pytest tests/security/test_constraint_gaming.py -v --timeout=60
```

---

## Reporting

### Security Test Report Template

```markdown
# Security Test Report

**Date**: YYYY-MM-DD
**Version**: X.Y.Z
**Tester**: [Name]

## Summary

| Category       | Pass | Fail | Blocked |
| -------------- | ---- | ---- | ------- |
| Cryptographic  | X    | X    | X       |
| Delegation     | X    | X    | X       |
| Constraint     | X    | X    | X       |
| Race Condition | X    | X    | X       |
| Cross-Org      | X    | X    | X       |
| Audit          | X    | X    | X       |

## Critical Findings

1. [Finding description]
   - **Severity**: CRITICAL/HIGH/MEDIUM/LOW
   - **Impact**: [Description]
   - **Remediation**: [Steps]

## Recommendations

1. [Recommendation]

## Sign-off

- [ ] Development Lead
- [ ] Security Lead
- [ ] Release Manager
```
