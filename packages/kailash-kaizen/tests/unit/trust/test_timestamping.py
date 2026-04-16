"""
Unit tests for CARE-014: External Timestamp Anchoring.

Tests the timestamp anchoring implementation for trust chain hashes:
- TimestampToken creation and serialization
- TimestampRequest auto-generation
- LocalTimestampAuthority signing and verification
- RFC3161TimestampAuthority stub behavior
- TimestampAnchorManager with fallback chain
- Integration with MerkleTree
- Edge cases and error handling
"""

import asyncio
import hashlib
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from kailash.trust.signing.merkle import MerkleTree
from kailash.trust.signing.timestamping import (
    LocalTimestampAuthority,
    RFC3161TimestampAuthority,
    TimestampAnchorManager,
    TimestampRequest,
    TimestampResponse,
    TimestampSource,
    TimestampToken,
    verify_timestamp_token,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_hash():
    """Create a sample SHA-256 hash."""
    return hashlib.sha256(b"test data").hexdigest()


@pytest.fixture
def sample_hashes():
    """Create multiple sample hashes."""
    return [hashlib.sha256(f"data_{i}".encode()).hexdigest() for i in range(4)]


@pytest.fixture
def local_authority():
    """Create a local timestamp authority with production warnings disabled for tests."""
    return LocalTimestampAuthority(production_warning=False)


@pytest.fixture
def local_authority_with_keys():
    """Create a local authority with pre-generated keys."""
    from kailash.trust.signing.crypto import generate_keypair

    private_key, public_key = generate_keypair()
    return LocalTimestampAuthority(
        signing_key=private_key, verify_key=public_key, production_warning=False
    )


@pytest.fixture
def rfc3161_authority():
    """Create an RFC 3161 timestamp authority stub."""
    return RFC3161TimestampAuthority(tsa_url="https://example.com/tsa")


@pytest.fixture
def sample_merkle_tree(sample_hashes):
    """Create a sample Merkle tree."""
    return MerkleTree(leaves=sample_hashes)


# =============================================================================
# TimestampToken Tests
# =============================================================================


class TestTimestampToken:
    """Tests for TimestampToken dataclass."""

    def test_token_creation(self, sample_hash):
        """TimestampToken can be created with required fields."""
        token = TimestampToken(
            token_id="tok-001",
            hash_value=sample_hash,
            timestamp=datetime.now(timezone.utc),
            source=TimestampSource.LOCAL,
            authority="local",
        )

        assert token.token_id == "tok-001"
        assert token.hash_value == sample_hash
        assert token.source == TimestampSource.LOCAL
        assert token.authority == "local"

    def test_token_defaults(self, sample_hash):
        """TimestampToken optional fields default to None."""
        token = TimestampToken(
            token_id="tok-001",
            hash_value=sample_hash,
            timestamp=datetime.now(timezone.utc),
            source=TimestampSource.LOCAL,
            authority="local",
        )

        assert token.signature is None
        assert token.nonce is None
        assert token.serial_number is None
        assert token.accuracy_microseconds is None

    def test_token_source_values(self):
        """TimestampSource enum has expected values."""
        assert TimestampSource.LOCAL.value == "local"
        assert TimestampSource.RFC3161.value == "rfc3161"
        assert TimestampSource.BLOCKCHAIN.value == "blockchain"

    def test_token_to_dict(self, sample_hash):
        """TimestampToken serializes to dictionary."""
        timestamp = datetime.now(timezone.utc)
        token = TimestampToken(
            token_id="tok-001",
            hash_value=sample_hash,
            timestamp=timestamp,
            source=TimestampSource.LOCAL,
            authority="local",
            signature="sig123",
            nonce="nonce123",
            serial_number=42,
            accuracy_microseconds=1000,
        )

        data = token.to_dict()

        assert data["token_id"] == "tok-001"
        assert data["hash_value"] == sample_hash
        assert data["timestamp"] == timestamp.isoformat()
        assert data["source"] == "local"
        assert data["authority"] == "local"
        assert data["signature"] == "sig123"
        assert data["nonce"] == "nonce123"
        assert data["serial_number"] == 42
        assert data["accuracy_microseconds"] == 1000

    def test_token_from_dict(self, sample_hash):
        """TimestampToken deserializes from dictionary."""
        timestamp = datetime.now(timezone.utc)
        data = {
            "token_id": "tok-001",
            "hash_value": sample_hash,
            "timestamp": timestamp.isoformat(),
            "source": "local",
            "authority": "local",
            "signature": "sig123",
            "nonce": "nonce123",
            "serial_number": 42,
            "accuracy_microseconds": 1000,
        }

        token = TimestampToken.from_dict(data)

        assert token.token_id == "tok-001"
        assert token.hash_value == sample_hash
        assert token.source == TimestampSource.LOCAL
        assert token.serial_number == 42


# =============================================================================
# TimestampRequest Tests
# =============================================================================


class TestTimestampRequest:
    """Tests for TimestampRequest dataclass."""

    def test_request_creation(self, sample_hash):
        """TimestampRequest can be created with hash."""
        request = TimestampRequest(hash_value=sample_hash)

        assert request.hash_value == sample_hash
        assert request.algorithm == "sha256"

    def test_request_auto_nonce(self, sample_hash):
        """TimestampRequest auto-generates nonce."""
        request = TimestampRequest(hash_value=sample_hash)

        assert request.nonce is not None
        assert len(request.nonce) == 32  # 16 bytes = 32 hex chars

    def test_request_auto_timestamp(self, sample_hash):
        """TimestampRequest auto-generates requested_at timestamp."""
        before = datetime.now(timezone.utc)
        request = TimestampRequest(hash_value=sample_hash)
        after = datetime.now(timezone.utc)

        assert request.requested_at >= before
        assert request.requested_at <= after

    def test_request_explicit_nonce(self, sample_hash):
        """TimestampRequest uses explicit nonce when provided."""
        request = TimestampRequest(hash_value=sample_hash, nonce="my-custom-nonce")

        assert request.nonce == "my-custom-nonce"


# =============================================================================
# LocalTimestampAuthority Tests
# =============================================================================


class TestLocalTimestampAuthority:
    """Tests for LocalTimestampAuthority."""

    def test_local_init_generates_keys(self):
        """LocalTimestampAuthority generates keys on init."""
        authority = LocalTimestampAuthority()

        assert authority._signing_key is not None
        assert authority._verify_key is not None
        assert len(authority._signing_key) > 0
        assert len(authority._verify_key) > 0

    def test_local_init_with_keys(self, local_authority_with_keys):
        """LocalTimestampAuthority uses provided keys."""
        assert local_authority_with_keys._signing_key is not None
        assert local_authority_with_keys._verify_key is not None

    @pytest.mark.asyncio
    async def test_local_get_timestamp(self, local_authority, sample_hash):
        """LocalTimestampAuthority returns valid timestamp response."""
        response = await local_authority.get_timestamp(sample_hash)

        assert isinstance(response, TimestampResponse)
        assert response.token.hash_value == sample_hash
        assert response.token.source == TimestampSource.LOCAL
        assert response.token.authority == "local"
        assert response.token.signature is not None
        assert response.verified is True

    @pytest.mark.asyncio
    async def test_local_get_timestamp_with_nonce(self, local_authority, sample_hash):
        """LocalTimestampAuthority uses provided nonce."""
        response = await local_authority.get_timestamp(
            sample_hash, nonce="custom-nonce"
        )

        assert response.request.nonce == "custom-nonce"
        assert response.token.nonce == "custom-nonce"

    @pytest.mark.asyncio
    async def test_local_verify_timestamp_valid(self, local_authority, sample_hash):
        """LocalTimestampAuthority verifies its own tokens."""
        response = await local_authority.get_timestamp(sample_hash)
        is_valid = await local_authority.verify_timestamp(response.token)

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_local_verify_timestamp_tampered_hash(
        self, local_authority, sample_hash
    ):
        """LocalTimestampAuthority rejects token with tampered hash."""
        response = await local_authority.get_timestamp(sample_hash)

        # Tamper with hash
        token = response.token
        tampered_token = TimestampToken(
            token_id=token.token_id,
            hash_value="tampered_hash_value",  # Changed
            timestamp=token.timestamp,
            source=token.source,
            authority=token.authority,
            signature=token.signature,
            nonce=token.nonce,
            serial_number=token.serial_number,
        )

        is_valid = await local_authority.verify_timestamp(tampered_token)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_local_verify_timestamp_tampered_sig(
        self, local_authority, sample_hash
    ):
        """LocalTimestampAuthority rejects token with tampered signature."""
        response = await local_authority.get_timestamp(sample_hash)

        # Tamper with signature
        token = response.token
        tampered_token = TimestampToken(
            token_id=token.token_id,
            hash_value=token.hash_value,
            timestamp=token.timestamp,
            source=token.source,
            authority=token.authority,
            signature="invalid_signature",  # Changed
            nonce=token.nonce,
            serial_number=token.serial_number,
        )

        is_valid = await local_authority.verify_timestamp(tampered_token)
        assert is_valid is False

    def test_local_authority_url(self, local_authority):
        """LocalTimestampAuthority has correct authority URL."""
        assert local_authority.authority_url == "local"

    @pytest.mark.asyncio
    async def test_local_timestamps_unique_ids(self, local_authority, sample_hash):
        """Each timestamp has a unique token ID."""
        response1 = await local_authority.get_timestamp(sample_hash)
        response2 = await local_authority.get_timestamp(sample_hash)

        assert response1.token.token_id != response2.token.token_id

    @pytest.mark.asyncio
    async def test_local_serial_numbers_increment(self, local_authority, sample_hash):
        """Serial numbers increment with each timestamp."""
        response1 = await local_authority.get_timestamp(sample_hash)
        response2 = await local_authority.get_timestamp(sample_hash)

        assert response2.token.serial_number == response1.token.serial_number + 1

    @pytest.mark.asyncio
    async def test_local_verify_wrong_source(self, local_authority, sample_hash):
        """LocalTimestampAuthority rejects tokens from other sources."""
        response = await local_authority.get_timestamp(sample_hash)
        token = response.token

        # Change source
        wrong_source_token = TimestampToken(
            token_id=token.token_id,
            hash_value=token.hash_value,
            timestamp=token.timestamp,
            source=TimestampSource.RFC3161,  # Wrong source
            authority=token.authority,
            signature=token.signature,
            nonce=token.nonce,
            serial_number=token.serial_number,
        )

        is_valid = await local_authority.verify_timestamp(wrong_source_token)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_local_verify_no_signature(self, local_authority, sample_hash):
        """LocalTimestampAuthority rejects tokens without signature."""
        token = TimestampToken(
            token_id="tok-001",
            hash_value=sample_hash,
            timestamp=datetime.now(timezone.utc),
            source=TimestampSource.LOCAL,
            authority="local",
            signature=None,  # No signature
        )

        is_valid = await local_authority.verify_timestamp(token)
        assert is_valid is False


# =============================================================================
# RFC3161 Implementation Tests
# =============================================================================


class TestRFC3161TimestampAuthority:
    """Tests for RFC3161TimestampAuthority implementation."""

    @pytest.mark.asyncio
    async def test_rfc3161_get_raises_on_unreachable_tsa(
        self, rfc3161_authority, sample_hash
    ):
        """RFC3161 get_timestamp raises error when TSA is unreachable or returns error."""
        with pytest.raises((RuntimeError, ImportError, Exception)):
            await rfc3161_authority.get_timestamp(sample_hash)

    @pytest.mark.asyncio
    async def test_rfc3161_verify_metadata_only_without_rfc3161ng(
        self, rfc3161_authority, sample_hash
    ):
        """RFC3161 verify_timestamp performs metadata-only verification without rfc3161ng."""
        token = TimestampToken(
            token_id="tok-001",
            hash_value=sample_hash,
            timestamp=datetime.now(timezone.utc),
            source=TimestampSource.RFC3161,
            authority="https://example.com/tsa",
        )

        result = await rfc3161_authority.verify_timestamp(token)
        # Without rfc3161ng, returns True if hash_value and timestamp are present
        assert result is True

    @pytest.mark.asyncio
    async def test_rfc3161_verify_rejects_wrong_authority(
        self, rfc3161_authority, sample_hash
    ):
        """RFC3161 verify_timestamp rejects tokens from wrong authority."""
        token = TimestampToken(
            token_id="tok-001",
            hash_value=sample_hash,
            timestamp=datetime.now(timezone.utc),
            source=TimestampSource.RFC3161,
            authority="https://wrong-tsa.example.com/tsa",
        )

        result = await rfc3161_authority.verify_timestamp(token)
        assert result is False

    def test_rfc3161_authority_url(self, rfc3161_authority):
        """RFC3161 authority has correct URL."""
        assert rfc3161_authority.authority_url == "https://example.com/tsa"


# =============================================================================
# TimestampAnchorManager Tests
# =============================================================================


class TestTimestampAnchorManager:
    """Tests for TimestampAnchorManager."""

    @pytest.mark.asyncio
    async def test_anchor_hash_with_local(self, sample_hash):
        """TimestampAnchorManager anchors hash with local authority."""
        manager = TimestampAnchorManager()

        response = await manager.anchor_hash(sample_hash)

        assert response.token.hash_value == sample_hash
        assert response.token.source == TimestampSource.LOCAL

    @pytest.mark.asyncio
    async def test_anchor_hash_fallback_on_failure(self, sample_hash):
        """TimestampAnchorManager falls back when primary fails."""

        # Create a failing primary
        class FailingAuthority(LocalTimestampAuthority):
            async def get_timestamp(self, hash_value, nonce=None):
                raise RuntimeError("Primary failed")

        primary = FailingAuthority()
        fallback = LocalTimestampAuthority()

        manager = TimestampAnchorManager(primary=primary, fallbacks=[fallback])

        response = await manager.anchor_hash(sample_hash)

        # Should have used fallback
        assert response.token.hash_value == sample_hash

    @pytest.mark.asyncio
    async def test_anchor_hash_all_fail_uses_local(self, sample_hash):
        """TimestampAnchorManager uses local when all fail."""

        class FailingAuthority(LocalTimestampAuthority):
            async def get_timestamp(self, hash_value, nonce=None):
                raise RuntimeError("Failed")

        primary = FailingAuthority()
        fallback = FailingAuthority()

        manager = TimestampAnchorManager(
            primary=primary,
            fallbacks=[fallback],
            local_fallback=True,
        )

        response = await manager.anchor_hash(sample_hash)

        assert response.token.source == TimestampSource.LOCAL

    @pytest.mark.asyncio
    async def test_anchor_hash_no_fallback_raises(self, sample_hash):
        """TimestampAnchorManager raises when all fail without local fallback."""

        class FailingAuthority(LocalTimestampAuthority):
            async def get_timestamp(self, hash_value, nonce=None):
                raise RuntimeError("Failed")

        primary = FailingAuthority()

        manager = TimestampAnchorManager(
            primary=primary,
            fallbacks=[],
            local_fallback=False,
        )

        with pytest.raises(RuntimeError) as exc_info:
            await manager.anchor_hash(sample_hash)

        assert "All timestamp authorities failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_anchor_merkle_root(self, sample_merkle_tree):
        """TimestampAnchorManager anchors Merkle tree root."""
        manager = TimestampAnchorManager()

        response = await manager.anchor_merkle_root(sample_merkle_tree)

        assert response.token.hash_value == sample_merkle_tree.root_hash

    @pytest.mark.asyncio
    async def test_anchor_merkle_root_empty_tree_raises(self):
        """TimestampAnchorManager raises for empty Merkle tree."""
        manager = TimestampAnchorManager()
        empty_tree = MerkleTree()

        with pytest.raises(ValueError) as exc_info:
            await manager.anchor_merkle_root(empty_tree)

        assert "empty Merkle tree" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_anchor_valid(self, sample_hash):
        """TimestampAnchorManager verifies valid anchor."""
        local = LocalTimestampAuthority()
        manager = TimestampAnchorManager(primary=local)

        response = await manager.anchor_hash(sample_hash)
        is_valid = await manager.verify_anchor(response)

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_anchor_invalid(self, sample_hash):
        """TimestampAnchorManager rejects invalid anchor."""
        manager = TimestampAnchorManager()

        response = await manager.anchor_hash(sample_hash)

        # Tamper with token
        response.token.hash_value = "tampered"

        is_valid = await manager.verify_anchor(response)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_get_history(self, sample_hash):
        """TimestampAnchorManager tracks history."""
        manager = TimestampAnchorManager()

        await manager.anchor_hash(sample_hash)
        await manager.anchor_hash(sample_hash + "2")

        history = manager.get_history()

        assert len(history) == 2
        assert history[0].token.hash_value == sample_hash

    @pytest.mark.asyncio
    async def test_get_latest_anchor(self, sample_hash):
        """TimestampAnchorManager returns latest anchor."""
        manager = TimestampAnchorManager()

        await manager.anchor_hash(sample_hash)
        await manager.anchor_hash(sample_hash + "2")

        latest = manager.get_latest_anchor()

        assert latest is not None
        assert latest.token.hash_value == sample_hash + "2"

    @pytest.mark.asyncio
    async def test_get_latest_anchor_empty(self):
        """get_latest_anchor returns None when no history."""
        manager = TimestampAnchorManager()

        assert manager.get_latest_anchor() is None

    @pytest.mark.asyncio
    async def test_anchor_history_ordered(self, sample_hash):
        """Anchor history maintains chronological order."""
        manager = TimestampAnchorManager()

        hashes = [f"{sample_hash}_{i}" for i in range(5)]
        for h in hashes:
            await manager.anchor_hash(h)

        history = manager.get_history()

        for i, response in enumerate(history):
            assert response.token.hash_value == hashes[i]

    @pytest.mark.asyncio
    async def test_manager_properties(self):
        """TimestampAnchorManager exposes properties correctly."""
        primary = LocalTimestampAuthority()
        fallback = LocalTimestampAuthority()

        manager = TimestampAnchorManager(
            primary=primary,
            fallbacks=[fallback],
            local_fallback=True,
        )

        assert manager.primary_authority == primary
        assert len(manager.fallback_authorities) == 1
        assert manager.has_local_fallback is True


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for timestamping."""

    @pytest.mark.asyncio
    async def test_full_anchor_workflow(self, sample_hash):
        """Full workflow: anchor hash, verify, check history."""
        authority = LocalTimestampAuthority()
        manager = TimestampAnchorManager(primary=authority)

        # Anchor
        response = await manager.anchor_hash(sample_hash)
        assert response.token.hash_value == sample_hash

        # Verify
        is_valid = await manager.verify_anchor(response)
        assert is_valid is True

        # Check history
        history = manager.get_history()
        assert len(history) == 1
        assert history[0] == response

    @pytest.mark.asyncio
    async def test_merkle_root_anchoring(self, sample_hashes):
        """Build tree, anchor root, verify."""
        tree = MerkleTree(leaves=sample_hashes)
        manager = TimestampAnchorManager()

        # Anchor root
        response = await manager.anchor_merkle_root(tree)
        assert response.token.hash_value == tree.root_hash

        # Verify
        is_valid = await manager.verify_anchor(response)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_replay_prevention(self, sample_hash):
        """Different nonces produce different tokens."""
        authority = LocalTimestampAuthority()

        response1 = await authority.get_timestamp(sample_hash, nonce="nonce1")
        response2 = await authority.get_timestamp(sample_hash, nonce="nonce2")

        # Different nonces
        assert response1.token.nonce != response2.token.nonce

        # Different signatures (due to nonce)
        assert response1.token.signature != response2.token.signature

        # Both still valid
        assert await authority.verify_timestamp(response1.token) is True
        assert await authority.verify_timestamp(response2.token) is True

    @pytest.mark.asyncio
    async def test_timestamp_ordering(self, sample_hash):
        """Later anchors have later timestamps."""
        authority = LocalTimestampAuthority()

        response1 = await authority.get_timestamp(sample_hash)
        await asyncio.sleep(0.01)  # Small delay
        response2 = await authority.get_timestamp(sample_hash)

        assert response2.token.timestamp >= response1.token.timestamp


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    @pytest.mark.asyncio
    async def test_verify_timestamp_token_helper(self, local_authority, sample_hash):
        """verify_timestamp_token helper works correctly."""
        response = await local_authority.get_timestamp(sample_hash)

        is_valid = await verify_timestamp_token(response.token, local_authority)
        assert is_valid is True


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Tests for serialization and deserialization."""

    @pytest.mark.asyncio
    async def test_response_to_dict(self, local_authority, sample_hash):
        """TimestampResponse serializes correctly."""
        response = await local_authority.get_timestamp(sample_hash)
        data = response.to_dict()

        assert "request" in data
        assert "token" in data
        assert "verified" in data
        assert data["request"]["hash_value"] == sample_hash

    @pytest.mark.asyncio
    async def test_response_from_dict(self, local_authority, sample_hash):
        """TimestampResponse deserializes correctly."""
        response = await local_authority.get_timestamp(sample_hash)
        data = response.to_dict()

        restored = TimestampResponse.from_dict(data)

        assert restored.request.hash_value == response.request.hash_value
        assert restored.token.token_id == response.token.token_id
        assert restored.verified == response.verified

    @pytest.mark.asyncio
    async def test_serialized_response_round_trip(self, local_authority, sample_hash):
        """Serialized response can be restored and verified."""
        response = await local_authority.get_timestamp(sample_hash)

        # Serialize
        data = response.to_dict()

        # Deserialize
        restored = TimestampResponse.from_dict(data)

        # Verify
        is_valid = await local_authority.verify_timestamp(restored.token)
        assert is_valid is True


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Additional edge case tests."""

    @pytest.mark.asyncio
    async def test_empty_hash(self, local_authority):
        """Authority handles empty hash."""
        response = await local_authority.get_timestamp("")
        assert response.token.hash_value == ""

    @pytest.mark.asyncio
    async def test_long_hash(self, local_authority):
        """Authority handles long hash."""
        long_hash = "a" * 1000
        response = await local_authority.get_timestamp(long_hash)
        assert response.token.hash_value == long_hash

    def test_manager_clear_history(self):
        """Manager can clear history."""
        manager = TimestampAnchorManager()
        asyncio.run(manager.anchor_hash("test"))
        assert len(manager.get_history()) == 1

        manager.clear_history()
        assert len(manager.get_history()) == 0

    @pytest.mark.asyncio
    async def test_manager_with_only_local_fallback(self, sample_hash):
        """Manager works with only local fallback (no primary set)."""
        manager = TimestampAnchorManager()  # Uses LocalTimestampAuthority by default

        response = await manager.anchor_hash(sample_hash)
        assert response.token.source == TimestampSource.LOCAL

    @pytest.mark.asyncio
    async def test_multiple_fallbacks(self, sample_hash):
        """Manager tries multiple fallbacks."""

        class FailingAuthority(LocalTimestampAuthority):
            async def get_timestamp(self, hash_value, nonce=None):
                raise RuntimeError("Failed")

        class SuccessAuthority(LocalTimestampAuthority):
            async def get_timestamp(self, hash_value, nonce=None):
                response = await super().get_timestamp(hash_value, nonce)
                return response

        primary = FailingAuthority()
        fallback1 = FailingAuthority()
        fallback2 = SuccessAuthority()

        manager = TimestampAnchorManager(
            primary=primary,
            fallbacks=[fallback1, fallback2],
            local_fallback=False,
        )

        response = await manager.anchor_hash(sample_hash)
        assert response.token.hash_value == sample_hash

    @pytest.mark.asyncio
    async def test_verify_unknown_authority(self, sample_hash):
        """Manager returns False for unknown authority."""
        manager = TimestampAnchorManager()

        # Create token with unknown authority
        token = TimestampToken(
            token_id="tok-001",
            hash_value=sample_hash,
            timestamp=datetime.now(timezone.utc),
            source=TimestampSource.LOCAL,
            authority="unknown-authority",
            signature="sig",
        )

        response = TimestampResponse(
            request=TimestampRequest(hash_value=sample_hash),
            token=token,
        )

        is_valid = await manager.verify_anchor(response)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_public_key_property(self, local_authority, sample_hash):
        """LocalTimestampAuthority exposes public key."""
        assert local_authority.public_key is not None
        assert len(local_authority.public_key) > 0


# =============================================================================
# CARE-049: Production Warning and Clock Drift Detection Tests
# =============================================================================


class TestCARE049SecurityFeatures:
    """Tests for CARE-049: LocalTimestampAuthority production warning and clock drift detection."""

    def test_production_warning_logged_by_default(self, caplog):
        """LocalTimestampAuthority logs production warning by default."""
        import logging

        with caplog.at_level(logging.WARNING):
            authority = LocalTimestampAuthority()

        # Check that warning was logged
        assert len(caplog.records) >= 1
        warning_found = False
        for record in caplog.records:
            if "development and testing only" in record.message:
                warning_found = True
                assert record.levelno == logging.WARNING
                assert "ExternalTimestampAuthority" in record.message
                assert "RFC 3161" in record.message
                break
        assert warning_found, "Production warning not logged"

    def test_production_warning_suppressed_when_disabled(self, caplog):
        """LocalTimestampAuthority does not log warning when disabled."""
        import logging

        with caplog.at_level(logging.WARNING):
            authority = LocalTimestampAuthority(production_warning=False)

        # Check that no production warning was logged
        for record in caplog.records:
            assert "development and testing only" not in record.message

    @pytest.mark.asyncio
    async def test_clock_drift_backward_detection(self, sample_hash, caplog):
        """Clock going backwards triggers CRITICAL log."""
        import logging
        from unittest.mock import patch

        authority = LocalTimestampAuthority(production_warning=False)

        # First timestamp at a specific time
        time1 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # Second timestamp is BEFORE first (clock went backwards)
        time2 = datetime(2024, 1, 15, 11, 59, 55, tzinfo=timezone.utc)

        with caplog.at_level(logging.CRITICAL):
            with patch("kailash.trust.signing.timestamping.datetime") as mock_datetime:
                mock_datetime.now.return_value = time1
                mock_datetime.fromisoformat = datetime.fromisoformat
                await authority.get_timestamp(sample_hash)

                mock_datetime.now.return_value = time2
                await authority.get_timestamp(sample_hash)

        # Check that CRITICAL warning was logged
        critical_found = False
        for record in caplog.records:
            if (
                "CARE-049 SECURITY ALERT" in record.message
                and "backwards" in record.message
            ):
                critical_found = True
                assert record.levelno == logging.CRITICAL
                break
        assert critical_found, "Clock backward drift CRITICAL log not found"

    @pytest.mark.asyncio
    async def test_clock_drift_forward_detection(self, sample_hash, caplog):
        """Large clock jump forward triggers CRITICAL log."""
        import logging
        from unittest.mock import patch

        # Use a small threshold for testing
        authority = LocalTimestampAuthority(
            production_warning=False, clock_drift_threshold=1.0
        )

        # First timestamp
        time1 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # Second timestamp is 10 seconds later (exceeds 1.0s threshold)
        time2 = datetime(2024, 1, 15, 12, 0, 10, tzinfo=timezone.utc)

        with caplog.at_level(logging.CRITICAL):
            with patch("kailash.trust.signing.timestamping.datetime") as mock_datetime:
                mock_datetime.now.return_value = time1
                mock_datetime.fromisoformat = datetime.fromisoformat
                await authority.get_timestamp(sample_hash)

                mock_datetime.now.return_value = time2
                await authority.get_timestamp(sample_hash)

        # Check that CRITICAL warning was logged
        critical_found = False
        for record in caplog.records:
            if (
                "CARE-049 SECURITY ALERT" in record.message
                and "forward" in record.message
            ):
                critical_found = True
                assert record.levelno == logging.CRITICAL
                assert "jumped forward" in record.message
                break
        assert critical_found, "Clock forward drift CRITICAL log not found"

    @pytest.mark.asyncio
    async def test_no_drift_alert_within_threshold(self, sample_hash, caplog):
        """Normal timestamp intervals do not trigger CRITICAL log."""
        import logging
        from unittest.mock import patch

        # Default threshold is 5 seconds
        authority = LocalTimestampAuthority(production_warning=False)

        # First timestamp
        time1 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # Second timestamp is 2 seconds later (within 5s threshold)
        time2 = datetime(2024, 1, 15, 12, 0, 2, tzinfo=timezone.utc)

        with caplog.at_level(logging.CRITICAL):
            with patch("kailash.trust.signing.timestamping.datetime") as mock_datetime:
                mock_datetime.now.return_value = time1
                mock_datetime.fromisoformat = datetime.fromisoformat
                await authority.get_timestamp(sample_hash)

                mock_datetime.now.return_value = time2
                await authority.get_timestamp(sample_hash)

        # Check that no CRITICAL warning was logged
        for record in caplog.records:
            assert "CARE-049 SECURITY ALERT" not in record.message

    def test_custom_clock_drift_threshold(self):
        """Custom clock drift threshold is respected."""
        authority = LocalTimestampAuthority(
            production_warning=False, clock_drift_threshold=10.0
        )
        assert authority._clock_drift_threshold == 10.0

    def test_default_clock_drift_threshold(self):
        """Default clock drift threshold is set correctly."""
        from kailash.trust.signing.timestamping import (
            DEFAULT_CLOCK_DRIFT_THRESHOLD_SECONDS,
        )

        authority = LocalTimestampAuthority(production_warning=False)
        assert authority._clock_drift_threshold == DEFAULT_CLOCK_DRIFT_THRESHOLD_SECONDS
        assert authority._clock_drift_threshold == 5.0
