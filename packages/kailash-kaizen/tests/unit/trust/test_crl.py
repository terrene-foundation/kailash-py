"""
Unit Tests for Certificate Revocation List (CRL) (Tier 1)

Tests the snapshot-based Certificate Revocation List for offline
and distributed revocation checking of delegation certificates.

Part of CARE-013: Certificate Revocation List (CRL).

Coverage:
- CRLEntry dataclass
- CRLMetadata dataclass
- CRLVerificationResult dataclass
- CertificateRevocationList class
- verify_delegation_with_crl helper function
"""

from datetime import datetime, timedelta, timezone

import pytest
from kailash.trust.signing.crl import (
    CertificateRevocationList,
    CRLEntry,
    CRLMetadata,
    CRLVerificationResult,
    verify_delegation_with_crl,
)
from kailash.trust.signing.crypto import generate_keypair


class TestCRLEntry:
    """Test CRLEntry dataclass."""

    def test_crl_entry_creation(self):
        """Test creating a CRL entry with all fields."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)

        entry = CRLEntry(
            delegation_id="del-001",
            agent_id="agent-001",
            revoked_at=now,
            reason="Key compromise",
            revoked_by="admin",
            expires_at=expires,
        )

        assert entry.delegation_id == "del-001"
        assert entry.agent_id == "agent-001"
        assert entry.revoked_at == now
        assert entry.reason == "Key compromise"
        assert entry.revoked_by == "admin"
        assert entry.expires_at == expires

    def test_crl_entry_defaults(self):
        """Test default values for optional fields."""
        now = datetime.now(timezone.utc)

        entry = CRLEntry(
            delegation_id="del-001",
            agent_id="agent-001",
            revoked_at=now,
            reason="Test",
            revoked_by="system",
        )

        assert entry.expires_at is None

    def test_crl_entry_with_expiry(self):
        """Test CRL entry with expiry date."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)

        entry = CRLEntry(
            delegation_id="del-001",
            agent_id="agent-001",
            revoked_at=now,
            reason="Test",
            revoked_by="admin",
            expires_at=expires,
        )

        assert entry.expires_at == expires
        assert not entry.is_expired()

    def test_crl_entry_is_expired(self):
        """Test is_expired method with past expiry."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(days=1)

        entry = CRLEntry(
            delegation_id="del-001",
            agent_id="agent-001",
            revoked_at=past - timedelta(days=30),
            reason="Test",
            revoked_by="admin",
            expires_at=past,
        )

        assert entry.is_expired()

    def test_crl_entry_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)

        entry = CRLEntry(
            delegation_id="del-001",
            agent_id="agent-001",
            revoked_at=now,
            reason="Key compromise",
            revoked_by="admin",
            expires_at=expires,
        )

        d = entry.to_dict()

        assert d["delegation_id"] == "del-001"
        assert d["agent_id"] == "agent-001"
        assert d["revoked_at"] == now.isoformat()
        assert d["reason"] == "Key compromise"
        assert d["revoked_by"] == "admin"
        assert d["expires_at"] == expires.isoformat()

    def test_crl_entry_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)

        data = {
            "delegation_id": "del-001",
            "agent_id": "agent-001",
            "revoked_at": now.isoformat(),
            "reason": "Key compromise",
            "revoked_by": "admin",
            "expires_at": expires.isoformat(),
        }

        entry = CRLEntry.from_dict(data)

        assert entry.delegation_id == "del-001"
        assert entry.agent_id == "agent-001"
        assert entry.reason == "Key compromise"
        assert entry.revoked_by == "admin"

    def test_crl_entry_from_dict_no_expiry(self):
        """Test deserialization without expiry field."""
        now = datetime.now(timezone.utc)

        data = {
            "delegation_id": "del-001",
            "agent_id": "agent-001",
            "revoked_at": now.isoformat(),
            "reason": "Test",
            "revoked_by": "system",
            "expires_at": None,
        }

        entry = CRLEntry.from_dict(data)

        assert entry.expires_at is None


class TestCRLMetadata:
    """Test CRLMetadata dataclass."""

    def test_metadata_creation(self):
        """Test creating CRL metadata with all fields."""
        now = datetime.now(timezone.utc)
        next_update = now + timedelta(hours=1)

        metadata = CRLMetadata(
            crl_id="crl-001",
            issuer_id="org-acme",
            issued_at=now,
            next_update=next_update,
            entry_count=10,
            signature="sig123",
        )

        assert metadata.crl_id == "crl-001"
        assert metadata.issuer_id == "org-acme"
        assert metadata.issued_at == now
        assert metadata.next_update == next_update
        assert metadata.entry_count == 10
        assert metadata.signature == "sig123"

    def test_metadata_defaults(self):
        """Test default values for optional fields."""
        now = datetime.now(timezone.utc)

        metadata = CRLMetadata(
            crl_id="crl-001",
            issuer_id="org-acme",
            issued_at=now,
        )

        assert metadata.next_update is None
        assert metadata.entry_count == 0
        assert metadata.signature is None

    def test_metadata_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime.now(timezone.utc)
        next_update = now + timedelta(hours=1)

        metadata = CRLMetadata(
            crl_id="crl-001",
            issuer_id="org-acme",
            issued_at=now,
            next_update=next_update,
            entry_count=5,
            signature="sig123",
        )

        d = metadata.to_dict()

        assert d["crl_id"] == "crl-001"
        assert d["issuer_id"] == "org-acme"
        assert d["issued_at"] == now.isoformat()
        assert d["next_update"] == next_update.isoformat()
        assert d["entry_count"] == 5
        assert d["signature"] == "sig123"

    def test_metadata_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(timezone.utc)
        next_update = now + timedelta(hours=1)

        data = {
            "crl_id": "crl-001",
            "issuer_id": "org-acme",
            "issued_at": now.isoformat(),
            "next_update": next_update.isoformat(),
            "entry_count": 5,
            "signature": "sig123",
        }

        metadata = CRLMetadata.from_dict(data)

        assert metadata.crl_id == "crl-001"
        assert metadata.issuer_id == "org-acme"
        assert metadata.entry_count == 5
        assert metadata.signature == "sig123"


class TestCertificateRevocationListBasic:
    """Test CertificateRevocationList basic operations."""

    @pytest.fixture
    def crl(self):
        """Create a fresh CRL for testing."""
        return CertificateRevocationList(issuer_id="org-acme")

    def test_add_revocation(self, crl):
        """Test adding a revocation entry."""
        entry = crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Key compromise",
            revoked_by="admin",
        )

        assert entry.delegation_id == "del-001"
        assert entry.agent_id == "agent-001"
        assert crl.entry_count == 1

    def test_add_revocation_returns_entry(self, crl):
        """Test that add_revocation returns the created entry."""
        entry = crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )

        assert isinstance(entry, CRLEntry)
        assert entry.delegation_id == "del-001"

    def test_add_duplicate_updates(self, crl):
        """Test that adding same delegation_id updates the entry."""
        entry1 = crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Original reason",
            revoked_by="admin",
        )

        entry2 = crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Updated reason",
            revoked_by="admin",
        )

        assert crl.entry_count == 1
        stored = crl.get_entry("del-001")
        assert stored.reason == "Updated reason"

    def test_remove_revocation(self, crl):
        """Test removing a revocation entry."""
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )

        assert crl.entry_count == 1

        result = crl.remove_revocation("del-001")

        assert result is True
        assert crl.entry_count == 0

    def test_remove_nonexistent(self, crl):
        """Test removing non-existent entry returns False."""
        result = crl.remove_revocation("nonexistent")

        assert result is False

    def test_is_revoked_true(self, crl):
        """Test is_revoked returns True for revoked delegation."""
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )

        assert crl.is_revoked("del-001") is True

    def test_is_revoked_false(self, crl):
        """Test is_revoked returns False for non-revoked delegation."""
        assert crl.is_revoked("del-001") is False

    def test_is_agent_revoked(self, crl):
        """Test is_agent_revoked returns True when agent has revocations."""
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )

        assert crl.is_agent_revoked("agent-001") is True

    def test_is_agent_not_revoked(self, crl):
        """Test is_agent_revoked returns False for non-revoked agent."""
        assert crl.is_agent_revoked("agent-001") is False

    def test_get_entry_exists(self, crl):
        """Test getting an existing entry."""
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Key compromise",
            revoked_by="admin",
        )

        entry = crl.get_entry("del-001")

        assert entry is not None
        assert entry.delegation_id == "del-001"
        assert entry.reason == "Key compromise"

    def test_get_entry_not_found(self, crl):
        """Test getting a non-existent entry returns None."""
        entry = crl.get_entry("nonexistent")

        assert entry is None

    def test_get_entries_for_agent(self, crl):
        """Test getting all entries for an agent."""
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test 1",
            revoked_by="admin",
        )
        crl.add_revocation(
            delegation_id="del-002",
            agent_id="agent-001",
            reason="Test 2",
            revoked_by="admin",
        )
        crl.add_revocation(
            delegation_id="del-003",
            agent_id="agent-002",
            reason="Test 3",
            revoked_by="admin",
        )

        entries = crl.get_entries_for_agent("agent-001")

        assert len(entries) == 2
        delegation_ids = {e.delegation_id for e in entries}
        assert delegation_ids == {"del-001", "del-002"}

    def test_get_entries_for_agent_empty(self, crl):
        """Test getting entries for agent with no revocations."""
        entries = crl.get_entries_for_agent("nonexistent")

        assert entries == []

    def test_list_entries(self, crl):
        """Test listing all entries."""
        for i in range(5):
            crl.add_revocation(
                delegation_id=f"del-{i}",
                agent_id=f"agent-{i}",
                reason=f"Test {i}",
                revoked_by="admin",
            )

        entries = crl.list_entries()

        assert len(entries) == 5

    def test_list_entries_with_pagination(self, crl):
        """Test listing entries with pagination."""
        for i in range(10):
            crl.add_revocation(
                delegation_id=f"del-{i:02d}",
                agent_id=f"agent-{i}",
                reason=f"Test {i}",
                revoked_by="admin",
            )

        # First page
        page1 = crl.list_entries(limit=3, offset=0)
        assert len(page1) == 3

        # Second page
        page2 = crl.list_entries(limit=3, offset=3)
        assert len(page2) == 3

        # Last page
        page3 = crl.list_entries(limit=3, offset=6)
        assert len(page3) == 3

        # Beyond data
        page4 = crl.list_entries(limit=3, offset=12)
        assert len(page4) == 0


class TestCertificateRevocationListProperties:
    """Test CertificateRevocationList properties."""

    @pytest.fixture
    def crl(self):
        """Create a fresh CRL for testing."""
        return CertificateRevocationList(issuer_id="org-acme", cache_ttl_seconds=3600)

    def test_entry_count(self, crl):
        """Test entry_count property."""
        assert crl.entry_count == 0

        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )

        assert crl.entry_count == 1

        crl.add_revocation(
            delegation_id="del-002",
            agent_id="agent-002",
            reason="Test",
            revoked_by="admin",
        )

        assert crl.entry_count == 2

    def test_metadata_populated(self, crl):
        """Test metadata is properly populated."""
        metadata = crl.metadata

        assert metadata.crl_id.startswith("crl-")
        assert metadata.issuer_id == "org-acme"
        assert metadata.issued_at is not None
        assert metadata.next_update is not None
        assert metadata.entry_count == 0

    def test_metadata_entry_count_updated(self, crl):
        """Test that metadata entry_count stays in sync."""
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )

        assert crl.metadata.entry_count == 1

    def test_cache_valid_within_ttl(self):
        """Test cache is valid within TTL."""
        crl = CertificateRevocationList(cache_ttl_seconds=3600)

        # Initially not valid (no refresh yet)
        assert not crl.is_cache_valid()

        # Simulate refresh by manually setting last_refresh
        crl._last_refresh = datetime.now(timezone.utc)

        assert crl.is_cache_valid()

    def test_cache_expired_after_ttl(self):
        """Test cache is expired after TTL."""
        crl = CertificateRevocationList(cache_ttl_seconds=60)

        # Set refresh time to past
        crl._last_refresh = datetime.now(timezone.utc) - timedelta(seconds=120)

        assert not crl.is_cache_valid()


class TestCertificateRevocationListSync:
    """Test CertificateRevocationList sync operations."""

    @pytest.fixture
    def crl(self):
        """Create a fresh CRL for testing."""
        return CertificateRevocationList(issuer_id="org-acme")

    def test_refresh_from_broadcaster(self, crl):
        """Test syncing CRL from broadcaster event history."""
        from kailash.trust.revocation import RevocationEvent, RevocationType

        # Create mock history
        history = [
            RevocationEvent(
                event_id="rev-001",
                revocation_type=RevocationType.AGENT_REVOKED,
                target_id="agent-001",
                revoked_by="admin",
                reason="Test 1",
            ),
            RevocationEvent(
                event_id="rev-002",
                revocation_type=RevocationType.DELEGATION_REVOKED,
                target_id="agent-002",
                revoked_by="admin",
                reason="Test 2",
            ),
        ]

        count = crl.refresh_from_broadcaster(history)

        assert count == 2
        assert crl.entry_count == 2
        assert crl.is_cache_valid()

    def test_refresh_from_broadcaster_skips_duplicates(self, crl):
        """Test that refresh skips already-added entries."""
        from kailash.trust.revocation import RevocationEvent, RevocationType

        history = [
            RevocationEvent(
                event_id="rev-001",
                revocation_type=RevocationType.AGENT_REVOKED,
                target_id="agent-001",
                revoked_by="admin",
                reason="Test",
            ),
        ]

        count1 = crl.refresh_from_broadcaster(history)
        count2 = crl.refresh_from_broadcaster(history)

        assert count1 == 1
        assert count2 == 0
        assert crl.entry_count == 1

    def test_cleanup_expired_entries(self, crl):
        """Test removing expired CRL entries."""
        past = datetime.now(timezone.utc) - timedelta(days=1)

        # Add entry that's already expired
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
            expires_at=past,
        )

        # Add entry that's not expired
        crl.add_revocation(
            delegation_id="del-002",
            agent_id="agent-002",
            reason="Test",
            revoked_by="admin",
        )

        assert crl.entry_count == 2

        count = crl.cleanup_expired()

        assert count == 1
        assert crl.entry_count == 1
        assert not crl.is_revoked("del-001")
        assert crl.is_revoked("del-002")


class TestCertificateRevocationListSigning:
    """Test CertificateRevocationList signing operations."""

    @pytest.fixture
    def crl(self):
        """Create a fresh CRL for testing."""
        return CertificateRevocationList(issuer_id="org-acme")

    @pytest.fixture
    def keypair(self):
        """Generate a keypair for signing tests."""
        return generate_keypair()

    def test_sign_crl(self, crl, keypair):
        """Test that CRL can be signed."""
        private_key, public_key = keypair

        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )

        signature = crl.sign(private_key)

        assert signature is not None
        assert len(signature) > 0
        assert crl.metadata.signature == signature

    def test_verify_signature_valid(self, crl, keypair):
        """Test signature verification with valid key."""
        private_key, public_key = keypair

        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )

        crl.sign(private_key)

        assert crl.verify_signature(public_key) is True

    def test_verify_signature_tampered(self, crl, keypair):
        """Test signature verification fails after tampering."""
        private_key, public_key = keypair

        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Original",
            revoked_by="admin",
        )

        crl.sign(private_key)

        # Tamper with the CRL - directly modify entry
        crl._entries["del-001"] = CRLEntry(
            delegation_id="del-001",
            agent_id="agent-001",
            revoked_at=datetime.now(timezone.utc),
            reason="Tampered",
            revoked_by="admin",
        )

        # Signature should fail
        assert crl.verify_signature(public_key) is False

    def test_verify_signature_wrong_key(self, crl, keypair):
        """Test signature verification fails with wrong key."""
        private_key, public_key = keypair
        _, wrong_public_key = generate_keypair()

        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )

        crl.sign(private_key)

        assert crl.verify_signature(wrong_public_key) is False

    def test_verify_signature_no_signature(self, crl, keypair):
        """Test verification fails when no signature present."""
        _, public_key = keypair

        assert crl.verify_signature(public_key) is False


class TestCertificateRevocationListSerialization:
    """Test CertificateRevocationList serialization."""

    @pytest.fixture
    def crl(self):
        """Create a populated CRL for testing."""
        crl = CertificateRevocationList(issuer_id="org-acme", cache_ttl_seconds=3600)

        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test 1",
            revoked_by="admin",
        )
        crl.add_revocation(
            delegation_id="del-002",
            agent_id="agent-001",
            reason="Test 2",
            revoked_by="admin",
        )
        crl.add_revocation(
            delegation_id="del-003",
            agent_id="agent-002",
            reason="Test 3",
            revoked_by="admin",
        )

        return crl

    def test_to_dict(self, crl):
        """Test full serialization."""
        d = crl.to_dict()

        assert "metadata" in d
        assert "entries" in d
        assert "agent_index" in d
        assert "cache_ttl_seconds" in d
        assert "version" in d

        assert d["version"] == "1.0"
        assert len(d["entries"]) == 3
        assert d["cache_ttl_seconds"] == 3600

    def test_from_dict(self, crl):
        """Test full deserialization."""
        d = crl.to_dict()

        restored = CertificateRevocationList.from_dict(d)

        assert restored.entry_count == 3
        assert restored.is_revoked("del-001")
        assert restored.is_revoked("del-002")
        assert restored.is_revoked("del-003")
        assert restored.metadata.issuer_id == "org-acme"

    def test_round_trip(self, crl):
        """Test to_dict then from_dict preserves data."""
        # Add more data
        crl._last_refresh = datetime.now(timezone.utc)

        # Serialize and deserialize
        d = crl.to_dict()
        restored = CertificateRevocationList.from_dict(d)

        # Verify all data preserved
        assert restored.entry_count == crl.entry_count
        assert restored.metadata.issuer_id == crl.metadata.issuer_id
        assert restored.metadata.crl_id == crl.metadata.crl_id

        # Verify all entries match
        for del_id in ["del-001", "del-002", "del-003"]:
            original = crl.get_entry(del_id)
            restored_entry = restored.get_entry(del_id)
            assert original.delegation_id == restored_entry.delegation_id
            assert original.agent_id == restored_entry.agent_id
            assert original.reason == restored_entry.reason

    def test_round_trip_with_signature(self, crl):
        """Test round trip preserves signature."""
        private_key, public_key = generate_keypair()
        crl.sign(private_key)

        d = crl.to_dict()
        restored = CertificateRevocationList.from_dict(d)

        assert restored.metadata.signature == crl.metadata.signature
        assert restored.verify_signature(public_key) is True

    def test_export_pem_style(self, crl):
        """Test PEM-style export."""
        output = crl.export_pem_style()

        assert "-----BEGIN CERTIFICATE REVOCATION LIST-----" in output
        assert "-----END CERTIFICATE REVOCATION LIST-----" in output
        assert "CRL ID:" in output
        assert "Issuer: org-acme" in output
        assert "del-001" in output
        assert "del-002" in output
        assert "del-003" in output


class TestCRLVerificationResult:
    """Test CRLVerificationResult dataclass."""

    def test_verification_result_valid(self):
        """Test creating a valid verification result."""
        result = CRLVerificationResult(
            valid=True,
            reason="Not in CRL",
            delegation_id="del-001",
            entry=None,
        )

        assert result.valid is True
        assert result.reason == "Not in CRL"
        assert result.delegation_id == "del-001"
        assert result.entry is None

    def test_verification_result_invalid(self):
        """Test creating an invalid verification result."""
        entry = CRLEntry(
            delegation_id="del-001",
            agent_id="agent-001",
            revoked_at=datetime.now(timezone.utc),
            reason="Key compromise",
            revoked_by="admin",
        )

        result = CRLVerificationResult(
            valid=False,
            reason="Delegation revoked",
            delegation_id="del-001",
            entry=entry,
        )

        assert result.valid is False
        assert result.entry is not None
        assert result.entry.reason == "Key compromise"


class TestVerifyDelegationWithCRL:
    """Test verify_delegation_with_crl helper function."""

    @pytest.fixture
    def crl(self):
        """Create a CRL with some revocations."""
        crl = CertificateRevocationList(issuer_id="org-acme")
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Key compromise",
            revoked_by="admin",
        )
        return crl

    def test_verify_delegation_revoked(self, crl):
        """Test verification of revoked delegation."""
        result = verify_delegation_with_crl("del-001", crl)

        assert result.valid is False
        assert "revoked" in result.reason.lower()
        assert result.delegation_id == "del-001"
        assert result.entry is not None
        assert result.entry.reason == "Key compromise"

    def test_verify_delegation_not_revoked(self, crl):
        """Test verification of non-revoked delegation."""
        result = verify_delegation_with_crl("del-999", crl)

        assert result.valid is True
        assert result.delegation_id == "del-999"
        assert result.entry is None

    def test_verify_returns_entry_info(self, crl):
        """Test that verification returns full entry info when revoked."""
        result = verify_delegation_with_crl("del-001", crl)

        assert result.entry is not None
        assert result.entry.delegation_id == "del-001"
        assert result.entry.agent_id == "agent-001"
        assert result.entry.reason == "Key compromise"
        assert result.entry.revoked_by == "admin"


class TestCRLIntegration:
    """Integration tests for CRL."""

    def test_full_crl_lifecycle(self):
        """Test full CRL lifecycle: Add, verify, remove, re-verify."""
        crl = CertificateRevocationList(issuer_id="org-acme")

        # Initially not revoked
        result1 = verify_delegation_with_crl("del-001", crl)
        assert result1.valid is True

        # Add revocation
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Security issue",
            revoked_by="admin",
        )

        # Now revoked
        result2 = verify_delegation_with_crl("del-001", crl)
        assert result2.valid is False
        assert result2.entry.reason == "Security issue"

        # Remove revocation
        crl.remove_revocation("del-001")

        # Not revoked again
        result3 = verify_delegation_with_crl("del-001", crl)
        assert result3.valid is True

    def test_crl_with_broadcaster_sync(self):
        """Test CRL syncing with broadcaster history."""
        from kailash.trust.revocation import (
            CascadeRevocationManager,
            InMemoryDelegationRegistry,
            InMemoryRevocationBroadcaster,
        )

        # Set up revocation system
        broadcaster = InMemoryRevocationBroadcaster()
        registry = InMemoryDelegationRegistry()
        registry.register_delegation("agent-A", "agent-B")
        manager = CascadeRevocationManager(broadcaster, registry)

        # Perform revocation
        manager.cascade_revoke(
            target_id="agent-A",
            revoked_by="admin",
            reason="Test revocation",
        )

        # Sync to CRL
        crl = CertificateRevocationList(issuer_id="org-acme")
        count = crl.refresh_from_broadcaster(broadcaster.get_history())

        assert count == 2  # agent-A and agent-B

    def test_crl_serialize_and_verify(self):
        """Test CRL serialization preserves integrity."""
        private_key, public_key = generate_keypair()

        # Create and sign CRL
        crl1 = CertificateRevocationList(issuer_id="org-acme")
        crl1.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
        )
        crl1.sign(private_key)

        # Serialize and restore
        data = crl1.to_dict()
        crl2 = CertificateRevocationList.from_dict(data)

        # Verify signature still valid
        assert crl2.verify_signature(public_key) is True

        # Verify data intact
        assert crl2.is_revoked("del-001")
        entry = crl2.get_entry("del-001")
        assert entry.reason == "Test"

    def test_multiple_agents_same_delegation_update(self):
        """Test updating delegation to different agent updates index."""
        crl = CertificateRevocationList(issuer_id="org-acme")

        # Add for agent-001
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Original",
            revoked_by="admin",
        )

        assert crl.is_agent_revoked("agent-001")
        assert len(crl.get_entries_for_agent("agent-001")) == 1

        # Update to agent-002
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-002",
            reason="Updated",
            revoked_by="admin",
        )

        # agent-001 should no longer have this delegation
        assert len(crl.get_entries_for_agent("agent-001")) == 0
        # agent-002 should have it
        assert crl.is_agent_revoked("agent-002")
        assert len(crl.get_entries_for_agent("agent-002")) == 1


class TestCRLEdgeCases:
    """Test edge cases for CRL."""

    def test_empty_crl_operations(self):
        """Test operations on empty CRL."""
        crl = CertificateRevocationList()

        assert crl.entry_count == 0
        assert not crl.is_revoked("any-id")
        assert not crl.is_agent_revoked("any-agent")
        assert crl.get_entry("any-id") is None
        assert crl.get_entries_for_agent("any-agent") == []
        assert crl.list_entries() == []
        assert crl.cleanup_expired() == 0

    def test_crl_with_special_characters(self):
        """Test CRL handles special characters in IDs and reasons."""
        crl = CertificateRevocationList()

        crl.add_revocation(
            delegation_id="del:001/test",
            agent_id="agent@example.com",
            reason="Reason with 'quotes' and \"double quotes\"",
            revoked_by="admin<script>alert('xss')</script>",
        )

        assert crl.is_revoked("del:001/test")
        entry = crl.get_entry("del:001/test")
        assert entry.agent_id == "agent@example.com"

    def test_crl_verification_with_empty_crl(self):
        """Test verification against empty CRL."""
        crl = CertificateRevocationList()

        result = verify_delegation_with_crl("any-delegation", crl)

        assert result.valid is True
        assert result.entry is None
