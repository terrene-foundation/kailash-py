"""
Unit tests for EATP Challenge-Response Protocol.

Tests the challenge-response protocol for live agent trust verification,
including challenge creation, response generation, response verification,
nonce replay protection, challenge expiration, and rate limiting.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from kailash.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.signing.crypto import generate_keypair, sign, verify_signature
from kailash.trust.enforce.challenge import (
    ChallengeError,
    ChallengeProtocol,
    ChallengeRequest,
    ChallengeResponse,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 key pair."""
    return generate_keypair()


@pytest.fixture
def another_keypair():
    """Generate a second Ed25519 key pair."""
    return generate_keypair()


@pytest.fixture
def protocol():
    """Create a ChallengeProtocol instance with default settings."""
    return ChallengeProtocol()


@pytest.fixture
def trust_chain(keypair):
    """Create a TrustLineageChain with an 'analyze_data' capability."""
    private_key, public_key = keypair
    now = datetime.now(timezone.utc)

    genesis = GenesisRecord(
        id="gen-test-001",
        agent_id="agent-target",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=now,
        signature=sign(
            {
                "id": "gen-test-001",
                "agent_id": "agent-target",
                "authority_id": "org-acme",
                "authority_type": "organization",
                "created_at": now.isoformat(),
                "expires_at": None,
                "metadata": {},
            },
            private_key,
        ),
    )

    capability = CapabilityAttestation(
        id="cap-test-001",
        capability="analyze_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only"],
        attester_id="org-acme",
        attested_at=now,
        signature=sign(
            {
                "id": "cap-test-001",
                "capability": "analyze_data",
                "capability_type": "action",
                "constraints": ["read_only"],
                "attester_id": "org-acme",
                "attested_at": now.isoformat(),
                "expires_at": None,
                "scope": None,
            },
            private_key,
        ),
    )

    return TrustLineageChain(
        genesis=genesis,
        capabilities=[capability],
    )


@pytest.fixture
def trust_chain_multi_cap(keypair):
    """Create a TrustLineageChain with multiple capabilities."""
    private_key, public_key = keypair
    now = datetime.now(timezone.utc)

    genesis = GenesisRecord(
        id="gen-test-002",
        agent_id="agent-multi",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=now,
        signature=sign({"id": "gen-test-002"}, private_key),
    )

    cap_analyze = CapabilityAttestation(
        id="cap-analyze",
        capability="analyze_data",
        capability_type=CapabilityType.ACTION,
        constraints=[],
        attester_id="org-acme",
        attested_at=now,
        signature=sign({"id": "cap-analyze"}, private_key),
    )

    cap_write = CapabilityAttestation(
        id="cap-write",
        capability="write_data",
        capability_type=CapabilityType.ACTION,
        constraints=["audit_required"],
        attester_id="org-acme",
        attested_at=now,
        signature=sign({"id": "cap-write"}, private_key),
    )

    return TrustLineageChain(
        genesis=genesis,
        capabilities=[cap_analyze, cap_write],
    )


# ---------------------------------------------------------------------------
# ChallengeRequest dataclass tests
# ---------------------------------------------------------------------------


class TestChallengeRequest:
    """Tests for the ChallengeRequest dataclass."""

    def test_fields_present(self):
        """ChallengeRequest must have all required fields."""
        now = datetime.now(timezone.utc)
        req = ChallengeRequest(
            challenger_id="verifier-001",
            target_agent_id="agent-001",
            nonce="abc123",
            timestamp=now,
            required_proof="analyze_data",
        )
        assert req.challenger_id == "verifier-001"
        assert req.target_agent_id == "agent-001"
        assert req.nonce == "abc123"
        assert req.timestamp == now
        assert req.required_proof == "analyze_data"

    def test_challenge_id_is_generated(self):
        """ChallengeRequest must have an auto-generated unique challenge_id."""
        now = datetime.now(timezone.utc)
        req = ChallengeRequest(
            challenger_id="verifier-001",
            target_agent_id="agent-001",
            nonce="abc123",
            timestamp=now,
            required_proof="analyze_data",
        )
        assert req.challenge_id is not None
        assert len(req.challenge_id) > 0

    def test_two_requests_have_different_ids(self):
        """Each ChallengeRequest must have a unique challenge_id."""
        now = datetime.now(timezone.utc)
        req1 = ChallengeRequest(
            challenger_id="v",
            target_agent_id="a",
            nonce="n1",
            timestamp=now,
            required_proof="x",
        )
        req2 = ChallengeRequest(
            challenger_id="v",
            target_agent_id="a",
            nonce="n2",
            timestamp=now,
            required_proof="x",
        )
        assert req1.challenge_id != req2.challenge_id

    def test_expires_at_computed(self):
        """ChallengeRequest must have an expires_at field."""
        now = datetime.now(timezone.utc)
        req = ChallengeRequest(
            challenger_id="v",
            target_agent_id="a",
            nonce="n",
            timestamp=now,
            required_proof="x",
            timeout_seconds=60,
        )
        assert req.expires_at is not None
        assert req.expires_at > now


# ---------------------------------------------------------------------------
# ChallengeResponse dataclass tests
# ---------------------------------------------------------------------------


class TestChallengeResponse:
    """Tests for the ChallengeResponse dataclass."""

    def test_fields_present(self):
        """ChallengeResponse must have all required fields."""
        now = datetime.now(timezone.utc)
        resp = ChallengeResponse(
            challenge_id="ch-001",
            agent_id="agent-001",
            signed_nonce="sig-data",
            capability_proof={
                "capability": "analyze_data",
                "attestation_id": "cap-001",
            },
            timestamp=now,
        )
        assert resp.challenge_id == "ch-001"
        assert resp.agent_id == "agent-001"
        assert resp.signed_nonce == "sig-data"
        assert resp.capability_proof["capability"] == "analyze_data"
        assert resp.timestamp == now


# ---------------------------------------------------------------------------
# ChallengeProtocol.create_challenge tests
# ---------------------------------------------------------------------------


class TestCreateChallenge:
    """Tests for ChallengeProtocol.create_challenge()."""

    def test_creates_valid_challenge(self, protocol):
        """create_challenge returns a ChallengeRequest with correct fields."""
        challenge = protocol.create_challenge(
            challenger_id="verifier-001",
            target_agent_id="agent-target",
            required_proof="analyze_data",
        )
        assert isinstance(challenge, ChallengeRequest)
        assert challenge.challenger_id == "verifier-001"
        assert challenge.target_agent_id == "agent-target"
        assert challenge.required_proof == "analyze_data"

    def test_nonce_is_random(self, protocol):
        """Each challenge must have a unique random nonce."""
        c1 = protocol.create_challenge("v", "a", "analyze_data")
        c2 = protocol.create_challenge("v", "a", "analyze_data")
        assert c1.nonce != c2.nonce

    def test_nonce_length(self, protocol):
        """Nonce must be at least 32 bytes (64 hex characters)."""
        challenge = protocol.create_challenge("v", "a", "analyze_data")
        # 32 bytes as hex = 64 characters
        assert len(challenge.nonce) >= 64

    def test_timestamp_is_utc(self, protocol):
        """Challenge timestamp must be UTC-aware."""
        challenge = protocol.create_challenge("v", "a", "analyze_data")
        assert challenge.timestamp.tzinfo is not None
        assert challenge.timestamp.tzinfo == timezone.utc

    def test_empty_challenger_id_raises(self, protocol):
        """Empty challenger_id must raise ChallengeError."""
        with pytest.raises(ChallengeError, match="challenger_id"):
            protocol.create_challenge("", "a", "analyze_data")

    def test_empty_target_agent_id_raises(self, protocol):
        """Empty target_agent_id must raise ChallengeError."""
        with pytest.raises(ChallengeError, match="target_agent_id"):
            protocol.create_challenge("v", "", "analyze_data")

    def test_empty_required_proof_raises(self, protocol):
        """Empty required_proof must raise ChallengeError."""
        with pytest.raises(ChallengeError, match="required_proof"):
            protocol.create_challenge("v", "a", "")

    def test_whitespace_only_challenger_id_raises(self, protocol):
        """Whitespace-only challenger_id must raise ChallengeError."""
        with pytest.raises(ChallengeError, match="challenger_id"):
            protocol.create_challenge("   ", "a", "analyze_data")

    def test_whitespace_only_target_agent_id_raises(self, protocol):
        """Whitespace-only target_agent_id must raise ChallengeError."""
        with pytest.raises(ChallengeError, match="target_agent_id"):
            protocol.create_challenge("v", "   ", "analyze_data")

    def test_whitespace_only_required_proof_raises(self, protocol):
        """Whitespace-only required_proof must raise ChallengeError."""
        with pytest.raises(ChallengeError, match="required_proof"):
            protocol.create_challenge("v", "a", "   ")


# ---------------------------------------------------------------------------
# ChallengeProtocol.respond_to_challenge tests
# ---------------------------------------------------------------------------


class TestRespondToChallenge:
    """Tests for ChallengeProtocol.respond_to_challenge()."""

    def test_produces_valid_response(self, protocol, keypair, trust_chain):
        """respond_to_challenge returns a ChallengeResponse with correct fields."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")

        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        assert isinstance(response, ChallengeResponse)
        assert response.challenge_id == challenge.challenge_id
        assert response.agent_id == trust_chain.genesis.agent_id
        assert len(response.signed_nonce) > 0
        assert response.capability_proof is not None

    def test_signed_nonce_is_verifiable(self, protocol, keypair, trust_chain):
        """The signed_nonce must be verifiable with the corresponding public key."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")

        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        # The signed payload is the nonce + timestamp + challenger_id
        payload = f"{challenge.nonce}:{challenge.timestamp.isoformat()}:{challenge.challenger_id}"
        assert verify_signature(payload, response.signed_nonce, public_key) is True

    def test_capability_proof_contains_attestation_info(self, protocol, keypair, trust_chain):
        """capability_proof must contain proof from the trust chain."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")

        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        assert "capability" in response.capability_proof
        assert response.capability_proof["capability"] == "analyze_data"
        assert "attestation_id" in response.capability_proof
        assert response.capability_proof["attestation_id"] == "cap-test-001"

    def test_expired_challenge_rejected(self, protocol, keypair, trust_chain):
        """Responding to an expired challenge must raise ChallengeError."""
        private_key, public_key = keypair
        # Create a challenge with 0-second timeout (already expired)
        expired_protocol = ChallengeProtocol(challenge_timeout_seconds=0)
        challenge = expired_protocol.create_challenge("verifier", "agent-target", "analyze_data")

        # Small sleep to ensure expiration
        time.sleep(0.01)

        with pytest.raises(ChallengeError, match="expired"):
            protocol.respond_to_challenge(challenge, private_key, trust_chain)

    def test_missing_capability_raises(self, protocol, keypair, trust_chain):
        """Responding without required capability must raise ChallengeError."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "delete_everything")

        with pytest.raises(ChallengeError, match="capability"):
            protocol.respond_to_challenge(challenge, private_key, trust_chain)

    def test_response_timestamp_is_utc(self, protocol, keypair, trust_chain):
        """Response timestamp must be UTC-aware."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")

        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        assert response.timestamp.tzinfo is not None
        assert response.timestamp.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# ChallengeProtocol.verify_response tests
# ---------------------------------------------------------------------------


class TestVerifyResponse:
    """Tests for ChallengeProtocol.verify_response()."""

    def test_valid_response_verifies(self, protocol, keypair, trust_chain):
        """A correctly produced response must verify as True."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        result = protocol.verify_response(challenge, response, public_key)
        assert result is True

    def test_wrong_public_key_fails(self, protocol, keypair, another_keypair, trust_chain):
        """Response signed with one key must fail verification with a different key."""
        private_key, _ = keypair
        _, wrong_public_key = another_keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        result = protocol.verify_response(challenge, response, wrong_public_key)
        assert result is False

    def test_tampered_signed_nonce_fails(self, protocol, keypair, trust_chain):
        """A response with a tampered signed_nonce must fail verification."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        # Tamper with the signed nonce
        tampered_response = ChallengeResponse(
            challenge_id=response.challenge_id,
            agent_id=response.agent_id,
            signed_nonce="dGFtcGVyZWQ=",  # base64("tampered")
            capability_proof=response.capability_proof,
            timestamp=response.timestamp,
        )

        result = protocol.verify_response(challenge, tampered_response, public_key)
        assert result is False

    def test_mismatched_challenge_id_fails(self, protocol, keypair, trust_chain):
        """Response with wrong challenge_id must fail verification."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        # Change the challenge_id in the response
        mismatched_response = ChallengeResponse(
            challenge_id="wrong-challenge-id",
            agent_id=response.agent_id,
            signed_nonce=response.signed_nonce,
            capability_proof=response.capability_proof,
            timestamp=response.timestamp,
        )

        result = protocol.verify_response(challenge, mismatched_response, public_key)
        assert result is False

    def test_expired_challenge_verification_fails(self, protocol, keypair, trust_chain):
        """Verifying a response to an expired challenge must raise ChallengeError."""
        private_key, public_key = keypair
        short_protocol = ChallengeProtocol(challenge_timeout_seconds=0)
        challenge = short_protocol.create_challenge("verifier", "agent-target", "analyze_data")

        # Build a response manually since respond_to_challenge would reject it
        payload = f"{challenge.nonce}:{challenge.timestamp.isoformat()}:{challenge.challenger_id}"
        signed_nonce = sign(payload, private_key)
        response = ChallengeResponse(
            challenge_id=challenge.challenge_id,
            agent_id="agent-target",
            signed_nonce=signed_nonce,
            capability_proof={
                "capability": "analyze_data",
                "attestation_id": "cap-test-001",
            },
            timestamp=datetime.now(timezone.utc),
        )

        time.sleep(0.01)

        with pytest.raises(ChallengeError, match="expired"):
            short_protocol.verify_response(challenge, response, public_key)


# ---------------------------------------------------------------------------
# Nonce replay protection tests
# ---------------------------------------------------------------------------


class TestNonceReplayProtection:
    """Tests for nonce replay protection in ChallengeProtocol."""

    def test_nonce_cannot_be_reused(self, protocol, keypair, trust_chain):
        """After a successful verification, the same nonce must be rejected."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        # First verification succeeds
        result = protocol.verify_response(challenge, response, public_key)
        assert result is True

        # Second verification with same nonce must raise
        with pytest.raises(ChallengeError, match="[Rr]eplay|[Nn]once.*used|[Nn]once.*already"):
            protocol.verify_response(challenge, response, public_key)

    def test_different_nonces_both_succeed(self, protocol, keypair, trust_chain):
        """Two challenges with different nonces must both verify independently."""
        private_key, public_key = keypair

        challenge1 = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response1 = protocol.respond_to_challenge(challenge1, private_key, trust_chain)

        challenge2 = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response2 = protocol.respond_to_challenge(challenge2, private_key, trust_chain)

        assert protocol.verify_response(challenge1, response1, public_key) is True
        assert protocol.verify_response(challenge2, response2, public_key) is True

    def test_used_nonces_tracked(self, protocol, keypair, trust_chain):
        """Protocol must track used nonces."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        assert len(protocol.used_nonces) == 0
        protocol.verify_response(challenge, response, public_key)
        assert len(protocol.used_nonces) == 1
        assert challenge.nonce in protocol.used_nonces


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for rate limiting in ChallengeProtocol."""

    def test_rate_limit_enforced(self):
        """Exceeding the rate limit must raise ChallengeError."""
        protocol = ChallengeProtocol(
            max_challenges_per_agent=3,
            rate_limit_window_seconds=60,
        )

        # Create 3 challenges — all should succeed
        for i in range(3):
            protocol.create_challenge("verifier", f"agent-{i % 2}", "analyze_data")

        # The 4th challenge targeting agent-0 (already has 2) should not raise since
        # agent-0 only has 2 challenges. But let's create targeting agent-1 (already 1):
        # Actually, rate limiting is per target agent, so:
        limited_protocol = ChallengeProtocol(
            max_challenges_per_agent=2,
            rate_limit_window_seconds=60,
        )

        limited_protocol.create_challenge("verifier", "agent-target", "analyze_data")
        limited_protocol.create_challenge("verifier", "agent-target", "analyze_data")

        with pytest.raises(ChallengeError, match="[Rr]ate.limit"):
            limited_protocol.create_challenge("verifier", "agent-target", "analyze_data")

    def test_rate_limit_per_target_agent(self):
        """Rate limit must be per target agent, not global."""
        protocol = ChallengeProtocol(
            max_challenges_per_agent=1,
            rate_limit_window_seconds=60,
        )

        # One challenge per agent is allowed
        protocol.create_challenge("verifier", "agent-A", "analyze_data")
        protocol.create_challenge("verifier", "agent-B", "analyze_data")

        # But a second for agent-A must be rejected
        with pytest.raises(ChallengeError, match="[Rr]ate.limit"):
            protocol.create_challenge("verifier", "agent-A", "analyze_data")

    def test_rate_limit_window_expires(self):
        """Challenges outside the rate limit window must not count."""
        protocol = ChallengeProtocol(
            max_challenges_per_agent=1,
            rate_limit_window_seconds=0,  # 0-second window
        )

        protocol.create_challenge("verifier", "agent-target", "analyze_data")
        time.sleep(0.01)
        # After window expires, should allow another challenge
        protocol.create_challenge("verifier", "agent-target", "analyze_data")

    def test_default_rate_limit_is_generous(self):
        """Default rate limit must allow reasonable number of challenges."""
        protocol = ChallengeProtocol()
        # Default should allow at least 10 challenges
        for i in range(10):
            protocol.create_challenge("verifier", "agent-target", f"proof_{i}")


# ---------------------------------------------------------------------------
# Challenge timeout configuration tests
# ---------------------------------------------------------------------------


class TestChallengeTimeout:
    """Tests for configurable challenge timeout."""

    def test_default_timeout_is_30_seconds(self):
        """Default challenge timeout must be 30 seconds."""
        protocol = ChallengeProtocol()
        challenge = protocol.create_challenge("v", "a", "p")

        expected_expiry = challenge.timestamp + timedelta(seconds=30)
        # Allow small tolerance for computation time
        assert abs((challenge.expires_at - expected_expiry).total_seconds()) < 1.0

    def test_custom_timeout(self):
        """Custom timeout must be reflected in challenge expiration."""
        protocol = ChallengeProtocol(challenge_timeout_seconds=120)
        challenge = protocol.create_challenge("v", "a", "p")

        expected_expiry = challenge.timestamp + timedelta(seconds=120)
        assert abs((challenge.expires_at - expected_expiry).total_seconds()) < 1.0

    def test_zero_timeout_creates_immediately_expired_challenge(self):
        """A zero-second timeout must create an immediately expirable challenge."""
        protocol = ChallengeProtocol(challenge_timeout_seconds=0)
        challenge = protocol.create_challenge("v", "a", "p")
        time.sleep(0.01)
        assert challenge.expires_at <= datetime.now(timezone.utc)

    def test_negative_timeout_raises(self):
        """Negative timeout must raise ValueError."""
        with pytest.raises(ValueError, match="timeout"):
            ChallengeProtocol(challenge_timeout_seconds=-1)


# ---------------------------------------------------------------------------
# ChallengeError tests
# ---------------------------------------------------------------------------


class TestChallengeError:
    """Tests for the ChallengeError exception."""

    def test_is_exception(self):
        """ChallengeError must be an Exception subclass."""
        assert issubclass(ChallengeError, Exception)

    def test_message_preserved(self):
        """ChallengeError must preserve the error message."""
        err = ChallengeError("test error message")
        assert str(err) == "test error message"

    def test_details_accessible(self):
        """ChallengeError must support optional details dict."""
        err = ChallengeError("test", details={"key": "value"})
        assert err.details["key"] == "value"

    def test_inherits_from_trust_error(self):
        """ChallengeError must inherit from TrustError for consistent hierarchy."""
        from kailash.trust.exceptions import TrustError

        assert issubclass(ChallengeError, TrustError)


# ---------------------------------------------------------------------------
# Edge cases and security tests
# ---------------------------------------------------------------------------


class TestSecurityEdgeCases:
    """Security-focused edge case tests."""

    def test_response_from_different_agent_fails(self, protocol, keypair, trust_chain):
        """A response claiming to be from a different agent must fail."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        # Tamper with agent_id
        forged_response = ChallengeResponse(
            challenge_id=response.challenge_id,
            agent_id="agent-impersonator",
            signed_nonce=response.signed_nonce,
            capability_proof=response.capability_proof,
            timestamp=response.timestamp,
        )

        result = protocol.verify_response(challenge, forged_response, public_key)
        assert result is False

    def test_capability_proof_without_matching_capability_fails(self, protocol, keypair, trust_chain):
        """A response with a capability_proof that doesn't match required_proof must fail."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        # Tamper with capability proof
        forged_response = ChallengeResponse(
            challenge_id=response.challenge_id,
            agent_id=response.agent_id,
            signed_nonce=response.signed_nonce,
            capability_proof={
                "capability": "delete_everything",
                "attestation_id": "cap-fake",
            },
            timestamp=response.timestamp,
        )

        result = protocol.verify_response(challenge, forged_response, public_key)
        assert result is False

    def test_concurrent_challenges_are_independent(self, protocol, keypair, trust_chain):
        """Multiple active challenges for the same agent must not interfere."""
        private_key, public_key = keypair

        ch1 = protocol.create_challenge("verifier-A", "agent-target", "analyze_data")
        ch2 = protocol.create_challenge("verifier-B", "agent-target", "analyze_data")

        resp1 = protocol.respond_to_challenge(ch1, private_key, trust_chain)
        resp2 = protocol.respond_to_challenge(ch2, private_key, trust_chain)

        assert protocol.verify_response(ch1, resp1, public_key) is True
        assert protocol.verify_response(ch2, resp2, public_key) is True

    def test_cross_challenge_response_swap_fails(self, protocol, keypair, trust_chain):
        """A response to one challenge must not verify against a different challenge."""
        private_key, public_key = keypair

        ch1 = protocol.create_challenge("verifier-A", "agent-target", "analyze_data")
        ch2 = protocol.create_challenge("verifier-B", "agent-target", "analyze_data")

        resp1 = protocol.respond_to_challenge(ch1, private_key, trust_chain)

        # Try to verify response1 against challenge2
        result = protocol.verify_response(ch2, resp1, public_key)
        assert result is False

    def test_full_lifecycle(self, protocol, keypair, trust_chain):
        """Full challenge-response lifecycle: create, respond, verify."""
        private_key, public_key = keypair

        # Step 1: Verifier creates challenge
        challenge = protocol.create_challenge(
            challenger_id="security-verifier",
            target_agent_id="agent-target",
            required_proof="analyze_data",
        )

        # Step 2: Target agent responds
        response = protocol.respond_to_challenge(
            challenge=challenge,
            agent_key=private_key,
            chain=trust_chain,
        )

        # Step 3: Verifier verifies
        is_valid = protocol.verify_response(
            challenge=challenge,
            response=response,
            agent_public_key=public_key,
        )

        assert is_valid is True

    def test_clear_used_nonces(self, protocol, keypair, trust_chain):
        """Protocol must support clearing used nonces for maintenance."""
        private_key, public_key = keypair
        challenge = protocol.create_challenge("v", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, private_key, trust_chain)

        protocol.verify_response(challenge, response, public_key)
        assert len(protocol.used_nonces) == 1

        protocol.clear_used_nonces()
        assert len(protocol.used_nonces) == 0
