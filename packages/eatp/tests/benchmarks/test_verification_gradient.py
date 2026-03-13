"""
EATP Verification Gradient Benchmarks.

Benchmarks the three verification levels defined in the EATP spec:

- **QUICK**: Hash + expiration only (verify_basic)
- **STANDARD**: QUICK + capability matching + constraint tightening evaluation
- **FULL**: STANDARD + Ed25519 signature verification for every record in the chain

All chains use REAL Ed25519 signatures (not placeholder strings), giving
accurate measurements of cryptographic overhead at each verification tier.

Chain depths tested: 0, 1, 3, 5, 10

Run with:
    cd packages/eatp
    python -m pytest tests/benchmarks/test_verification_gradient.py -v \
        --benchmark-only \
        --benchmark-columns=min,max,mean,median,stddev,rounds
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import pytest

from eatp.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from eatp.constraint_validator import ConstraintValidator
from eatp.crypto import generate_keypair, sign, verify_signature


# ---------------------------------------------------------------------------
# Helpers — build chains with real Ed25519 signatures
# ---------------------------------------------------------------------------


def _sign_genesis(genesis: GenesisRecord, private_key: str) -> None:
    """Sign a GenesisRecord in place using its to_signing_payload()."""
    genesis.signature = sign(genesis.to_signing_payload(), private_key)


def _sign_capability(cap: CapabilityAttestation, private_key: str) -> None:
    """Sign a CapabilityAttestation in place using its to_signing_payload()."""
    cap.signature = sign(cap.to_signing_payload(), private_key)


def _sign_delegation(deleg: DelegationRecord, private_key: str) -> None:
    """Sign a DelegationRecord in place using its to_signing_payload()."""
    deleg.signature = sign(deleg.to_signing_payload(), private_key)


# Pre-generated constraint sets that form a valid tightening chain.
# Each successive delegation has strictly tighter constraints.
_CONSTRAINT_LEVELS: List[Dict[str, Any]] = [
    {
        "cost_limit": 10000,
        "rate_limit": 1000,
        "time_window": "06:00-22:00",
        "resources": ["data/**", "logs/**"],
    },
    {
        "cost_limit": 8000,
        "rate_limit": 800,
        "time_window": "07:00-21:00",
        "resources": ["data/**"],
    },
    {
        "cost_limit": 6000,
        "rate_limit": 600,
        "time_window": "08:00-20:00",
        "resources": ["data/users/**"],
    },
    {
        "cost_limit": 4000,
        "rate_limit": 400,
        "time_window": "09:00-19:00",
        "resources": ["data/users/read/*"],
    },
    {
        "cost_limit": 3000,
        "rate_limit": 300,
        "time_window": "09:00-18:00",
        "resources": ["data/users/read/*"],
    },
    {
        "cost_limit": 2000,
        "rate_limit": 200,
        "time_window": "09:30-17:30",
        "resources": ["data/users/read/*"],
    },
    {
        "cost_limit": 1500,
        "rate_limit": 150,
        "time_window": "10:00-17:00",
        "resources": ["data/users/read/*"],
    },
    {
        "cost_limit": 1000,
        "rate_limit": 100,
        "time_window": "10:00-16:30",
        "resources": ["data/users/read/*"],
    },
    {
        "cost_limit": 800,
        "rate_limit": 80,
        "time_window": "10:00-16:00",
        "resources": ["data/users/read/*"],
    },
    {
        "cost_limit": 500,
        "rate_limit": 50,
        "time_window": "10:00-15:00",
        "resources": ["data/users/read/*"],
    },
    {
        "cost_limit": 300,
        "rate_limit": 30,
        "time_window": "11:00-14:00",
        "resources": ["data/users/read/*"],
    },
]


def _make_signed_chain(
    depth: int,
) -> Tuple[
    TrustLineageChain,
    List[Tuple[str, str]],  # (private_key, public_key) per actor
    List[Dict[str, Any]],  # constraint dicts per delegation level
]:
    """
    Build a TrustLineageChain with *depth* delegation levels,
    all signed with real Ed25519 keys.

    Returns:
        (chain, keypairs, constraint_pairs) where
        - keypairs[0] = authority key (signs genesis + capability)
        - keypairs[1..depth] = delegator keys (sign their delegation)
        - constraint_pairs[i] = (parent_constraints, child_constraints) per level
    """
    now = datetime.now(timezone.utc)
    far_future = now + timedelta(days=365)

    # Authority keypair — signs genesis + capability
    auth_priv, auth_pub = generate_keypair()
    keypairs: List[Tuple[str, str]] = [(auth_priv, auth_pub)]

    # Genesis
    genesis = GenesisRecord(
        id=f"gen-vg-{depth}",
        agent_id=f"agent-vg-root-{depth}",
        authority_id="authority-vg",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=now,
        expires_at=far_future,
        signature="",  # will be signed below
    )
    _sign_genesis(genesis, auth_priv)

    # Capability
    capability = CapabilityAttestation(
        id=f"cap-vg-{depth}",
        capability="analyze_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only"],
        attester_id="authority-vg",
        attested_at=now,
        expires_at=far_future,
        signature="",  # will be signed below
    )
    _sign_capability(capability, auth_priv)

    # Delegations with tightening constraints
    delegations: List[DelegationRecord] = []
    constraint_pairs: List[Dict[str, Any]] = []

    for i in range(depth):
        # Each delegator gets its own keypair
        deleg_priv, deleg_pub = generate_keypair()
        keypairs.append((deleg_priv, deleg_pub))

        parent_id = delegations[-1].id if delegations else None
        delegator_id = f"agent-vg-{i}" if i > 0 else genesis.agent_id

        deleg = DelegationRecord(
            id=f"del-vg-{depth}-{i}",
            delegator_id=delegator_id,
            delegatee_id=f"agent-vg-{i + 1}",
            task_id=f"task-vg-{depth}-{i}",
            capabilities_delegated=["analyze_data"],
            constraint_subset=["read_only"],
            delegated_at=now,
            expires_at=far_future,
            signature="",  # will be signed below
            parent_delegation_id=parent_id,
        )
        _sign_delegation(deleg, deleg_priv)
        delegations.append(deleg)
        constraint_pairs.append(_CONSTRAINT_LEVELS[i])

    chain = TrustLineageChain(
        genesis=genesis,
        capabilities=[capability],
        delegations=delegations,
    )

    return chain, keypairs, constraint_pairs


# ---------------------------------------------------------------------------
# Verification functions that simulate each tier
# ---------------------------------------------------------------------------


def _verify_quick(chain: TrustLineageChain) -> bool:
    """QUICK verification: expiration + existence only."""
    result = chain.verify_basic()
    return result.valid


def _verify_standard(
    chain: TrustLineageChain,
    constraint_pairs: List[Dict[str, Any]],
    validator: ConstraintValidator,
) -> bool:
    """
    STANDARD verification:
    QUICK + capability matching + constraint tightening evaluation.
    """
    # 1. QUICK checks
    result = chain.verify_basic()
    if not result.valid:
        return False

    # 2. Capability matching — verify delegated capabilities exist
    for deleg in chain.delegations:
        for cap_name in deleg.capabilities_delegated:
            if not chain.has_capability(cap_name):
                return False

    # 3. Constraint tightening — validate each delegation level
    for i, constraints in enumerate(constraint_pairs):
        parent_constraints = _CONSTRAINT_LEVELS[i]
        child_constraints = (
            _CONSTRAINT_LEVELS[i + 1]
            if i + 1 < len(_CONSTRAINT_LEVELS)
            else constraints
        )
        val_result = validator.validate_tightening(
            parent_constraints, child_constraints
        )
        if not val_result.valid:
            return False

    return True


def _verify_full(
    chain: TrustLineageChain,
    constraint_pairs: List[Dict[str, Any]],
    validator: ConstraintValidator,
    keypairs: List[Tuple[str, str]],
) -> bool:
    """
    FULL verification:
    STANDARD + verify Ed25519 signatures on every record in the chain.
    """
    # 1. STANDARD checks
    if not _verify_standard(chain, constraint_pairs, validator):
        return False

    # 2. Verify genesis signature (signed by authority = keypairs[0])
    _, auth_pub = keypairs[0]
    if not verify_signature(
        chain.genesis.to_signing_payload(), chain.genesis.signature, auth_pub
    ):
        return False

    # 3. Verify capability signature(s) (also signed by authority)
    for cap in chain.capabilities:
        if not verify_signature(cap.to_signing_payload(), cap.signature, auth_pub):
            return False

    # 4. Verify each delegation signature (signed by delegator at keypairs[i+1])
    for i, deleg in enumerate(chain.delegations):
        _, deleg_pub = keypairs[i + 1]
        if not verify_signature(deleg.to_signing_payload(), deleg.signature, deleg_pub):
            return False

    return True


# ---------------------------------------------------------------------------
# Pre-build chains (expensive keygen should not be inside benchmark loop)
# ---------------------------------------------------------------------------


# Cache built chains so keygen happens once per session
_CHAIN_CACHE: Dict[
    int, Tuple[TrustLineageChain, List[Tuple[str, str]], List[Dict[str, Any]]]
] = {}


def _get_chain(depth: int):
    """Get or build a signed chain at the given depth (cached)."""
    if depth not in _CHAIN_CACHE:
        _CHAIN_CACHE[depth] = _make_signed_chain(depth)
    return _CHAIN_CACHE[depth]


# Shared validator instance
_VALIDATOR = ConstraintValidator()


# ---------------------------------------------------------------------------
# 1. QUICK Verification Benchmarks (verify_basic)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="verification_gradient_quick")
class TestQuickVerificationBenchmarks:
    """QUICK tier: expiration + existence checks only."""

    def test_quick_depth_0(self, benchmark):
        """QUICK verification on depth-0 chain (genesis + capability only)."""
        chain, _, _ = _get_chain(0)
        result = benchmark(_verify_quick, chain)
        assert result is True

    def test_quick_depth_1(self, benchmark):
        """QUICK verification on depth-1 chain."""
        chain, _, _ = _get_chain(1)
        result = benchmark(_verify_quick, chain)
        assert result is True

    def test_quick_depth_3(self, benchmark):
        """QUICK verification on depth-3 chain."""
        chain, _, _ = _get_chain(3)
        result = benchmark(_verify_quick, chain)
        assert result is True

    def test_quick_depth_5(self, benchmark):
        """QUICK verification on depth-5 chain."""
        chain, _, _ = _get_chain(5)
        result = benchmark(_verify_quick, chain)
        assert result is True

    def test_quick_depth_10(self, benchmark):
        """QUICK verification on depth-10 chain."""
        chain, _, _ = _get_chain(10)
        result = benchmark(_verify_quick, chain)
        assert result is True


# ---------------------------------------------------------------------------
# 2. STANDARD Verification Benchmarks (QUICK + capability + constraints)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="verification_gradient_standard")
class TestStandardVerificationBenchmarks:
    """STANDARD tier: QUICK + capability matching + constraint tightening."""

    def test_standard_depth_0(self, benchmark):
        """STANDARD verification on depth-0 chain (no delegations to check)."""
        chain, _, constraint_pairs = _get_chain(0)
        result = benchmark(_verify_standard, chain, constraint_pairs, _VALIDATOR)
        assert result is True

    def test_standard_depth_1(self, benchmark):
        """STANDARD verification on depth-1 chain."""
        chain, _, constraint_pairs = _get_chain(1)
        result = benchmark(_verify_standard, chain, constraint_pairs, _VALIDATOR)
        assert result is True

    def test_standard_depth_3(self, benchmark):
        """STANDARD verification on depth-3 chain."""
        chain, _, constraint_pairs = _get_chain(3)
        result = benchmark(_verify_standard, chain, constraint_pairs, _VALIDATOR)
        assert result is True

    def test_standard_depth_5(self, benchmark):
        """STANDARD verification on depth-5 chain."""
        chain, _, constraint_pairs = _get_chain(5)
        result = benchmark(_verify_standard, chain, constraint_pairs, _VALIDATOR)
        assert result is True

    def test_standard_depth_10(self, benchmark):
        """STANDARD verification on depth-10 chain."""
        chain, _, constraint_pairs = _get_chain(10)
        result = benchmark(_verify_standard, chain, constraint_pairs, _VALIDATOR)
        assert result is True


# ---------------------------------------------------------------------------
# 3. FULL Verification Benchmarks (STANDARD + all signature checks)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="verification_gradient_full")
class TestFullVerificationBenchmarks:
    """FULL tier: STANDARD + Ed25519 signature verification on every record."""

    def test_full_depth_0(self, benchmark):
        """FULL verification on depth-0 chain (genesis + 1 capability sig)."""
        chain, keypairs, constraint_pairs = _get_chain(0)
        result = benchmark(_verify_full, chain, constraint_pairs, _VALIDATOR, keypairs)
        assert result is True

    def test_full_depth_1(self, benchmark):
        """FULL verification on depth-1 chain (3 signatures total)."""
        chain, keypairs, constraint_pairs = _get_chain(1)
        result = benchmark(_verify_full, chain, constraint_pairs, _VALIDATOR, keypairs)
        assert result is True

    def test_full_depth_3(self, benchmark):
        """FULL verification on depth-3 chain (5 signatures total)."""
        chain, keypairs, constraint_pairs = _get_chain(3)
        result = benchmark(_verify_full, chain, constraint_pairs, _VALIDATOR, keypairs)
        assert result is True

    def test_full_depth_5(self, benchmark):
        """FULL verification on depth-5 chain (7 signatures total)."""
        chain, keypairs, constraint_pairs = _get_chain(5)
        result = benchmark(_verify_full, chain, constraint_pairs, _VALIDATOR, keypairs)
        assert result is True

    def test_full_depth_10(self, benchmark):
        """FULL verification on depth-10 chain (12 signatures total)."""
        chain, keypairs, constraint_pairs = _get_chain(10)
        result = benchmark(_verify_full, chain, constraint_pairs, _VALIDATOR, keypairs)
        assert result is True


# ---------------------------------------------------------------------------
# 4. Comparative: all three tiers at a single depth for direct comparison
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="verification_gradient_compare_depth5")
class TestVerificationGradientComparison:
    """Side-by-side comparison of all three tiers at depth=5."""

    def test_compare_quick_depth5(self, benchmark):
        """QUICK at depth 5 (baseline)."""
        chain, _, _ = _get_chain(5)
        result = benchmark(_verify_quick, chain)
        assert result is True

    def test_compare_standard_depth5(self, benchmark):
        """STANDARD at depth 5 (adds capability + constraint checks)."""
        chain, _, constraint_pairs = _get_chain(5)
        result = benchmark(_verify_standard, chain, constraint_pairs, _VALIDATOR)
        assert result is True

    def test_compare_full_depth5(self, benchmark):
        """FULL at depth 5 (adds 7 Ed25519 signature verifications)."""
        chain, keypairs, constraint_pairs = _get_chain(5)
        result = benchmark(_verify_full, chain, constraint_pairs, _VALIDATOR, keypairs)
        assert result is True
