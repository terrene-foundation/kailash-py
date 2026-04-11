"""
Unit tests for CARE-001: Fix Static Salt in Key Derivation.

Tests cryptographic salt generation, key derivation with per-key salt,
and salted hash computation for trust chain state.
"""

import base64
import secrets

import pytest
from kailash.trust.signing.crypto import (
    NACL_AVAILABLE,
    SALT_LENGTH,
    derive_key_with_salt,
    generate_salt,
    hash_chain,
    hash_trust_chain_state,
    hash_trust_chain_state_salted,
)

pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not installed")


class TestSaltGeneration:
    """Tests for cryptographic salt generation."""

    def test_generate_salt_returns_bytes(self):
        """generate_salt() must return bytes."""
        salt = generate_salt()
        assert isinstance(salt, bytes)

    def test_generate_salt_correct_length(self):
        """Salt must be SALT_LENGTH (32) bytes."""
        salt = generate_salt()
        assert len(salt) == SALT_LENGTH

    def test_salt_uniqueness_no_collisions(self):
        """Each salt generation must be unique - no collisions in 1000 salts."""
        salts = [generate_salt() for _ in range(1000)]
        assert len(set(salts)) == 1000, "Salt collision detected"

    def test_salt_not_all_zeros(self):
        """Salt must not be all zeros (would indicate broken RNG)."""
        salt = generate_salt()
        assert salt != b"\x00" * SALT_LENGTH


class TestDeriveKeyWithSalt:
    """Tests for per-key salted key derivation."""

    def test_returns_tuple_of_bytes(self):
        """derive_key_with_salt returns (derived_key, salt_used)."""
        master = b"test_master_key"
        salt = generate_salt()
        result = derive_key_with_salt(master, salt)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bytes)
        assert isinstance(result[1], bytes)

    def test_derived_key_length(self):
        """Derived key must be 32 bytes by default."""
        master = b"test_master_key"
        salt = generate_salt()
        key, _ = derive_key_with_salt(master, salt)
        assert len(key) == 32

    def test_derived_keys_differ_with_different_salts(self):
        """Same master key with different salts produces different keys."""
        master = b"test_master_key"
        salt1 = generate_salt()
        salt2 = generate_salt()
        key1, _ = derive_key_with_salt(master, salt1)
        key2, _ = derive_key_with_salt(master, salt2)
        assert key1 != key2

    def test_same_salt_produces_same_key(self):
        """Same master key + same salt = same derived key (deterministic)."""
        master = b"test_master_key"
        salt = generate_salt()
        key1, _ = derive_key_with_salt(master, salt)
        key2, _ = derive_key_with_salt(master, salt)
        assert key1 == key2

    def test_different_master_keys_produce_different_keys(self):
        """Different master keys with same salt produce different keys."""
        salt = generate_salt()
        key1, _ = derive_key_with_salt(b"master_key_1", salt)
        key2, _ = derive_key_with_salt(b"master_key_2", salt)
        assert key1 != key2

    def test_custom_key_length(self):
        """Custom key_length parameter is respected."""
        master = b"test_master_key"
        salt = generate_salt()
        key, _ = derive_key_with_salt(master, salt, key_length=16)
        assert len(key) == 16

    def test_salt_returned_matches_input(self):
        """The salt returned must match the salt provided."""
        master = b"test_master_key"
        salt = generate_salt()
        _, returned_salt = derive_key_with_salt(master, salt)
        assert returned_salt == salt


class TestSaltedHashTrustChainState:
    """Tests for salted trust chain state hashing."""

    def test_returns_tuple_hash_and_salt(self):
        """hash_trust_chain_state_salted returns (hash_hex, salt_b64)."""
        result = hash_trust_chain_state_salted(
            genesis_id="gen-1",
            capability_ids=["cap-1"],
            delegation_ids=["del-1"],
            constraint_hash="abc",
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        hash_hex, salt_b64 = result
        assert isinstance(hash_hex, str)
        assert isinstance(salt_b64, str)
        assert len(hash_hex) == 64  # SHA-256 hex

    def test_hash_reproducible_with_same_salt(self):
        """Same inputs with same salt produce same hash."""
        salt = generate_salt()
        salt_b64 = base64.b64encode(salt).decode("utf-8")

        hash1, _ = hash_trust_chain_state_salted(
            "gen-1", ["cap-1"], ["del-1"], "abc", salt=salt_b64
        )
        hash2, _ = hash_trust_chain_state_salted(
            "gen-1", ["cap-1"], ["del-1"], "abc", salt=salt_b64
        )
        assert hash1 == hash2

    def test_hash_differs_with_different_salts(self):
        """Different salts produce different hashes even with same inputs."""
        salt1 = base64.b64encode(generate_salt()).decode("utf-8")
        salt2 = base64.b64encode(generate_salt()).decode("utf-8")

        hash1, _ = hash_trust_chain_state_salted(
            "gen-1", ["cap-1"], ["del-1"], "abc", salt=salt1
        )
        hash2, _ = hash_trust_chain_state_salted(
            "gen-1", ["cap-1"], ["del-1"], "abc", salt=salt2
        )
        assert hash1 != hash2

    def test_auto_generates_salt_when_none_provided(self):
        """When no salt provided, a new salt is generated automatically."""
        hash1, salt1 = hash_trust_chain_state_salted(
            "gen-1", ["cap-1"], ["del-1"], "abc"
        )
        hash2, salt2 = hash_trust_chain_state_salted(
            "gen-1", ["cap-1"], ["del-1"], "abc"
        )
        # Different salts should be generated
        assert salt1 != salt2
        # And therefore different hashes
        assert hash1 != hash2

    def test_includes_previous_state_hash(self):
        """Previous state hash changes the result (linked hashing)."""
        salt = base64.b64encode(generate_salt()).decode("utf-8")

        hash1, _ = hash_trust_chain_state_salted(
            "gen-1", ["cap-1"], ["del-1"], "abc", salt=salt, previous_state_hash=None
        )
        hash2, _ = hash_trust_chain_state_salted(
            "gen-1",
            ["cap-1"],
            ["del-1"],
            "abc",
            salt=salt,
            previous_state_hash="prev_hash_abc123",
        )
        assert hash1 != hash2

    def test_sorted_capability_ids(self):
        """Capability IDs are sorted before hashing (order independent)."""
        salt = base64.b64encode(generate_salt()).decode("utf-8")

        hash1, _ = hash_trust_chain_state_salted(
            "gen-1", ["cap-2", "cap-1"], ["del-1"], "abc", salt=salt
        )
        hash2, _ = hash_trust_chain_state_salted(
            "gen-1", ["cap-1", "cap-2"], ["del-1"], "abc", salt=salt
        )
        assert hash1 == hash2


class TestOriginalHashBackwardCompatibility:
    """Ensure original hash_trust_chain_state still works for legacy chains."""

    def test_original_function_still_works(self):
        """Original unsalted hash function must still work."""
        result = hash_trust_chain_state(
            genesis_id="gen-001",
            capability_ids=["cap-001"],
            delegation_ids=["del-001"],
            constraint_hash="abc123",
        )
        assert isinstance(result, str)
        assert len(result) == 64

    def test_original_function_deterministic(self):
        """Original function must remain deterministic."""
        hash1 = hash_trust_chain_state("gen-1", ["cap-1"], [], "abc")
        hash2 = hash_trust_chain_state("gen-1", ["cap-1"], [], "abc")
        assert hash1 == hash2
