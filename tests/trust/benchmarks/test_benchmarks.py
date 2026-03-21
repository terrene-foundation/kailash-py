"""
EATP SDK Performance Benchmarks.

Measures performance of core EATP operations:
1. Crypto operations (keygen, sign, verify, hash_chain)
2. Chain verification (verify_basic at various depths)
3. Store operations (InMemoryTrustStore write/read)
4. Constraint evaluation (multi-dimension evaluator)
5. Merkle tree (build, proof generation, proof verification)
6. Serialization (to_dict, from_dict)
7. End-to-end (full establish + verify flow)

Run with:
    cd src/kailash/trust
    python -m pytest tests/benchmarks/ -v --benchmark-only
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from kailash.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ConstraintEnvelope,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.constraint_validator import ConstraintValidator
from kailash.trust.constraints import (
    ConstraintDimensionRegistry,
    InteractionMode,
    MultiDimensionEvaluator,
)
from kailash.trust.constraints.builtin import (
    CostLimitDimension,
    RateLimitDimension,
    register_builtin_dimensions,
)
from kailash.trust.signing.crypto import (
    generate_keypair,
    hash_chain,
    sign,
    verify_signature,
)
from kailash.trust.signing.merkle import MerkleTree
from kailash.trust.chain_store.memory import InMemoryTrustStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_genesis(agent_id: str, authority_id: str = "auth-bench") -> GenesisRecord:
    """Build a minimal GenesisRecord for benchmarking."""
    return GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id=authority_id,
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        signature="benchmark-sig",
    )


def _make_capability(
    cap_id: str,
    capability: str = "analyze_data",
    attester_id: str = "auth-bench",
) -> CapabilityAttestation:
    """Build a minimal CapabilityAttestation for benchmarking."""
    return CapabilityAttestation(
        id=cap_id,
        capability=capability,
        capability_type=CapabilityType.ACTION,
        constraints=["read_only"],
        attester_id=attester_id,
        attested_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        signature="benchmark-sig",
    )


def _make_delegation(
    deleg_id: str,
    delegator_id: str,
    delegatee_id: str,
    parent_delegation_id: str | None = None,
) -> DelegationRecord:
    """Build a minimal DelegationRecord for benchmarking."""
    return DelegationRecord(
        id=deleg_id,
        delegator_id=delegator_id,
        delegatee_id=delegatee_id,
        task_id=f"task-{deleg_id}",
        capabilities_delegated=["analyze_data"],
        constraint_subset=["read_only"],
        delegated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        signature="benchmark-sig",
        parent_delegation_id=parent_delegation_id,
    )


def _make_chain(depth: int) -> TrustLineageChain:
    """
    Build a TrustLineageChain with *depth* levels of delegation.

    depth=0 means genesis + capability only (no delegations).
    depth=N means N delegation records chained together.
    """
    genesis = _make_genesis(f"agent-depth-{depth}")
    capabilities = [_make_capability(f"cap-depth-{depth}")]

    delegations: List[DelegationRecord] = []
    for i in range(depth):
        parent_id = delegations[-1].id if delegations else None
        delegations.append(
            _make_delegation(
                deleg_id=f"del-{depth}-{i}",
                delegator_id=f"agent-{i}" if i > 0 else genesis.agent_id,
                delegatee_id=f"agent-{i + 1}",
                parent_delegation_id=parent_id,
            )
        )

    return TrustLineageChain(
        genesis=genesis,
        capabilities=capabilities,
        delegations=delegations,
    )


def _run_async(coro):
    """Run an async coroutine synchronously for benchmark compatibility."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 1. Crypto Operations
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="crypto")
class TestCryptoBenchmarks:
    """Benchmarks for core cryptographic primitives."""

    def test_keygen_benchmark(self, benchmark):
        """Benchmark Ed25519 key pair generation."""
        benchmark(generate_keypair)

    def test_sign_benchmark(self, benchmark):
        """Benchmark Ed25519 signing of a dict payload."""
        priv, _pub = generate_keypair()
        payload = {"action": "test", "data": "benchmark"}
        benchmark(sign, payload, priv)

    def test_verify_benchmark(self, benchmark):
        """Benchmark Ed25519 signature verification."""
        priv, pub = generate_keypair()
        payload = {"action": "test", "data": "benchmark"}
        sig = sign(payload, priv)
        benchmark(verify_signature, payload, sig, pub)

    def test_hash_chain_dict_benchmark(self, benchmark):
        """Benchmark SHA-256 hash_chain with a dict input."""
        data = {
            "id": "test",
            "action": "benchmark",
            "timestamp": "2024-01-01T00:00:00Z",
        }
        benchmark(hash_chain, data)

    def test_hash_chain_string_benchmark(self, benchmark):
        """Benchmark SHA-256 hash_chain with a string input."""
        data = "the-quick-brown-fox-jumps-over-the-lazy-dog"
        benchmark(hash_chain, data)


# ---------------------------------------------------------------------------
# 2. Chain Verification (verify_basic)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="verify")
class TestVerifyBenchmarks:
    """Benchmarks for TrustLineageChain.verify_basic() at various depths."""

    def test_verify_0_level_chain(self, benchmark):
        """Benchmark verify_basic on a chain with no delegations."""
        chain = _make_chain(depth=0)
        result = benchmark(chain.verify_basic)
        assert result.valid is True

    def test_verify_1_level_chain(self, benchmark):
        """Benchmark verify_basic on a 1-delegation chain."""
        chain = _make_chain(depth=1)
        result = benchmark(chain.verify_basic)
        assert result.valid is True

    def test_verify_3_level_chain(self, benchmark):
        """Benchmark verify_basic on a 3-delegation chain."""
        chain = _make_chain(depth=3)
        result = benchmark(chain.verify_basic)
        assert result.valid is True

    def test_verify_5_level_chain(self, benchmark):
        """Benchmark verify_basic on a 5-delegation chain."""
        chain = _make_chain(depth=5)
        result = benchmark(chain.verify_basic)
        assert result.valid is True

    def test_verify_10_level_chain(self, benchmark):
        """Benchmark verify_basic on a 10-delegation chain."""
        chain = _make_chain(depth=10)
        result = benchmark(chain.verify_basic)
        assert result.valid is True

    def test_chain_hash_benchmark(self, benchmark):
        """Benchmark hash computation for a 5-level chain."""
        chain = _make_chain(depth=5)
        benchmark(chain.hash)


# ---------------------------------------------------------------------------
# 3. Store Operations (InMemoryTrustStore)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="store")
class TestStoreBenchmarks:
    """Benchmarks for InMemoryTrustStore read/write operations."""

    def test_memory_store_write(self, benchmark):
        """Benchmark storing a chain in InMemoryTrustStore."""
        store = InMemoryTrustStore()
        _run_async(store.initialize())
        chain = _make_chain(depth=2)

        async def _store():
            return await store.store_chain(chain)

        benchmark(lambda: _run_async(_store()))

    def test_memory_store_read(self, benchmark):
        """Benchmark reading a chain from InMemoryTrustStore by agent_id."""
        store = InMemoryTrustStore()
        _run_async(store.initialize())
        chain = _make_chain(depth=2)
        _run_async(store.store_chain(chain))
        agent_id = chain.genesis.agent_id

        async def _read():
            return await store.get_chain(agent_id)

        benchmark(lambda: _run_async(_read()))

    def test_memory_store_list(self, benchmark):
        """Benchmark listing chains from InMemoryTrustStore (10 chains)."""
        store = InMemoryTrustStore()
        _run_async(store.initialize())
        for i in range(10):
            chain = _make_chain(depth=1)
            # Override agent_id to make each unique
            chain.genesis.agent_id = f"list-agent-{i}"
            chain.genesis.id = f"gen-list-agent-{i}"
            _run_async(store.store_chain(chain))

        async def _list():
            return await store.list_chains()

        benchmark(lambda: _run_async(_list()))


# ---------------------------------------------------------------------------
# 4. Constraint Evaluation
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="constraints")
class TestConstraintBenchmarks:
    """Benchmarks for constraint validation and multi-dimension evaluation."""

    def test_constraint_tightening_validation(self, benchmark):
        """Benchmark ConstraintValidator.validate_tightening with multiple fields."""
        validator = ConstraintValidator()
        parent = {
            "cost_limit": 10000,
            "rate_limit": 100,
            "time_window": "09:00-17:00",
            "resources": ["data/**", "logs/**"],
        }
        child = {
            "cost_limit": 5000,
            "rate_limit": 50,
            "time_window": "10:00-16:00",
            "resources": ["data/users/*"],
        }
        result = benchmark(validator.validate_tightening, parent, child)
        assert result.valid is True

    def test_constraint_inheritance_validation(self, benchmark):
        """Benchmark ConstraintValidator.validate_inheritance (CARE-009)."""
        validator = ConstraintValidator()
        parent = {
            "cost_limit": 10000,
            "rate_limit": 100,
            "budget_limit": 50000,
            "max_delegation_depth": 5,
            "allowed_actions": ["read", "write", "analyze"],
            "forbidden_actions": ["delete", "admin"],
        }
        child = {
            "cost_limit": 5000,
            "rate_limit": 50,
            "budget_limit": 25000,
            "max_delegation_depth": 3,
            "allowed_actions": ["read", "analyze"],
            "forbidden_actions": ["delete", "admin", "export"],
        }
        result = benchmark(validator.validate_inheritance, parent, child)
        assert result.valid is True

    def test_multi_dimension_evaluator_conjunctive(self, benchmark):
        """Benchmark MultiDimensionEvaluator with CONJUNCTIVE mode (2 dims)."""
        registry = ConstraintDimensionRegistry()
        registry.register(CostLimitDimension())
        registry.register(RateLimitDimension())
        evaluator = MultiDimensionEvaluator(registry, enable_anti_gaming=False)

        constraints = {"cost_limit": 1000, "rate_limit": 100}
        context = {"cost_used": 500, "requests_in_period": 50}

        result = benchmark(evaluator.evaluate, constraints, context, InteractionMode.CONJUNCTIVE)
        assert result.satisfied is True

    def test_multi_dimension_evaluator_all_builtins(self, benchmark):
        """Benchmark MultiDimensionEvaluator with all 6 built-in dimensions."""
        registry = ConstraintDimensionRegistry()
        register_builtin_dimensions(registry)
        evaluator = MultiDimensionEvaluator(registry, enable_anti_gaming=False)

        constraints = {
            "cost_limit": 10000,
            "rate_limit": 1000,
        }
        context = {
            "cost_used": 5000,
            "requests_in_period": 500,
        }

        result = benchmark(evaluator.evaluate, constraints, context, InteractionMode.CONJUNCTIVE)
        assert result.satisfied is True


# ---------------------------------------------------------------------------
# 5. Merkle Tree
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="merkle")
class TestMerkleBenchmarks:
    """Benchmarks for Merkle tree build, proof generation, and verification."""

    def test_merkle_build_10(self, benchmark):
        """Benchmark building a Merkle tree from 10 leaves."""
        hashes = [hash_chain(f"leaf-{i}") for i in range(10)]
        benchmark(MerkleTree, hashes)

    def test_merkle_build_100(self, benchmark):
        """Benchmark building a Merkle tree from 100 leaves."""
        hashes = [hash_chain(f"leaf-{i}") for i in range(100)]
        benchmark(MerkleTree, hashes)

    def test_merkle_build_1000(self, benchmark):
        """Benchmark building a Merkle tree from 1000 leaves."""
        hashes = [hash_chain(f"leaf-{i}") for i in range(1000)]
        benchmark(MerkleTree, hashes)

    def test_merkle_proof_generation_100(self, benchmark):
        """Benchmark generating a Merkle proof from a 100-leaf tree."""
        hashes = [hash_chain(f"leaf-{i}") for i in range(100)]
        tree = MerkleTree(hashes)
        benchmark(tree.generate_proof, 50)

    def test_merkle_proof_verification_100(self, benchmark):
        """Benchmark verifying a Merkle proof from a 100-leaf tree."""
        hashes = [hash_chain(f"leaf-{i}") for i in range(100)]
        tree = MerkleTree(hashes)
        proof = tree.generate_proof(50)
        assert proof is not None, "Proof must not be None for a non-empty tree"
        result = benchmark(tree.verify_proof, proof)
        assert result is True

    def test_merkle_proof_generation_1000(self, benchmark):
        """Benchmark generating a Merkle proof from a 1000-leaf tree."""
        hashes = [hash_chain(f"leaf-{i}") for i in range(1000)]
        tree = MerkleTree(hashes)
        benchmark(tree.generate_proof, 500)

    def test_merkle_proof_verification_1000(self, benchmark):
        """Benchmark verifying a Merkle proof from a 1000-leaf tree."""
        hashes = [hash_chain(f"leaf-{i}") for i in range(1000)]
        tree = MerkleTree(hashes)
        proof = tree.generate_proof(500)
        assert proof is not None, "Proof must not be None for a non-empty tree"
        result = benchmark(tree.verify_proof, proof)
        assert result is True


# ---------------------------------------------------------------------------
# 6. Serialization
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="serialization")
class TestSerializationBenchmarks:
    """Benchmarks for TrustLineageChain to_dict/from_dict serialization."""

    def test_serialize_chain_0_depth(self, benchmark):
        """Benchmark to_dict on a chain with no delegations."""
        chain = _make_chain(depth=0)
        benchmark(chain.to_dict)

    def test_serialize_chain_5_depth(self, benchmark):
        """Benchmark to_dict on a 5-delegation chain."""
        chain = _make_chain(depth=5)
        benchmark(chain.to_dict)

    def test_deserialize_chain_0_depth(self, benchmark):
        """Benchmark from_dict on a chain with no delegations."""
        chain = _make_chain(depth=0)
        data = chain.to_dict()
        benchmark(TrustLineageChain.from_dict, data)

    def test_deserialize_chain_5_depth(self, benchmark):
        """Benchmark from_dict on a 5-delegation chain."""
        chain = _make_chain(depth=5)
        data = chain.to_dict()
        benchmark(TrustLineageChain.from_dict, data)

    def test_serialize_deserialize_roundtrip(self, benchmark):
        """Benchmark full serialize-then-deserialize roundtrip."""
        chain = _make_chain(depth=3)

        def _roundtrip():
            d = chain.to_dict()
            return TrustLineageChain.from_dict(d)

        benchmark(_roundtrip)


# ---------------------------------------------------------------------------
# 7. End-to-End (sync wrapper over async TrustOperations)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(group="e2e")
class TestEndToEndBenchmarks:
    """
    End-to-end benchmarks covering the full establish-then-verify flow.

    Uses synchronous wrappers around async operations since pytest-benchmark
    does not natively support async benchmarks.
    """

    def test_establish_and_verify_basic(self, benchmark):
        """Benchmark creating a chain and running verify_basic."""

        def _establish_and_verify():
            chain = _make_chain(depth=1)
            return chain.verify_basic()

        result = benchmark(_establish_and_verify)
        assert result.valid is True

    def test_full_chain_build_hash_verify(self, benchmark):
        """Benchmark building a 3-level chain, hashing it, and verifying."""

        def _build_hash_verify():
            chain = _make_chain(depth=3)
            chain_hash = chain.hash()
            verification = chain.verify_basic()
            return chain_hash, verification

        chain_hash, verification = benchmark(_build_hash_verify)
        assert verification.valid is True
        assert len(chain_hash) == 64  # SHA-256 hex digest

    def test_store_and_retrieve_flow(self, benchmark):
        """Benchmark the full store-then-retrieve flow with InMemoryTrustStore."""

        def _store_and_retrieve():
            store = InMemoryTrustStore()
            _run_async(store.initialize())
            chain = _make_chain(depth=2)
            _run_async(store.store_chain(chain))
            retrieved = _run_async(store.get_chain(chain.genesis.agent_id))
            return retrieved.verify_basic()

        result = benchmark(_store_and_retrieve)
        assert result.valid is True

    def test_constraint_then_verify(self, benchmark):
        """Benchmark evaluating constraints followed by chain verification."""
        validator = ConstraintValidator()
        parent = {"cost_limit": 10000, "rate_limit": 100}
        child = {"cost_limit": 5000, "rate_limit": 50}

        def _validate_and_verify():
            val_result = validator.validate_tightening(parent, child)
            chain = _make_chain(depth=2)
            verify_result = chain.verify_basic()
            return val_result, verify_result

        val_result, verify_result = benchmark(_validate_and_verify)
        assert val_result.valid is True
        assert verify_result.valid is True
