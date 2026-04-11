"""
Security testing fixtures for Kaizen trust framework.

CARE-040: Provides fixtures for key extraction resistance testing.
These are Tier 1 (unit) tests - mocking is allowed for database access
but cryptographic operations use REAL keys.
"""

import pytest
from kailash.trust.key_manager import InMemoryKeyManager, KeyMetadata
from kailash.trust.signing.crypto import NACL_AVAILABLE, generate_keypair


@pytest.fixture
def trust_crypto():
    """
    Provide fresh crypto instance for security tests.

    Creates a real keypair for testing key extraction resistance.
    Uses actual Ed25519 cryptography - no mocking.
    """
    if not NACL_AVAILABLE:
        pytest.skip("PyNaCl not installed")

    private_key, public_key = generate_keypair()
    return {
        "private_key": private_key,
        "public_key": public_key,
    }


@pytest.fixture
def key_manager():
    """
    Provide fresh InMemoryKeyManager for security tests.

    Uses real key generation and cryptographic operations.
    """
    if not NACL_AVAILABLE:
        pytest.skip("PyNaCl not installed")

    return InMemoryKeyManager()


@pytest.fixture
def key_metadata():
    """
    Provide a KeyMetadata instance for testing.

    Does not contain actual key material - just metadata.
    """
    return KeyMetadata(
        key_id="test-key-001",
        algorithm="Ed25519",
        is_hardware_backed=False,
    )
