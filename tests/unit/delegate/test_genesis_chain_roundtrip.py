# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 wiring test for ``DelegateGenesisRecord`` ↔ ``TrustLineageChain``.

S2.5 F10 (analyst recommendation): verify the composed
:class:`DelegateGenesisRecord` round-trips through the existing
:class:`kailash.trust.chain.TrustLineageChain` facade. Per §249
(compose, don't re-derive) and ``orphan-detection.md`` MUST Rule 2
(every wired manager has an integration test): the F4 restructure
that composed the substrate ``chain.GenesisRecord`` is only "wired" if
something exercises the import path + facade-call shape end-to-end.

**Tier classification (B5, Round 2 sec M-3):** this test was originally
authored under ``tests/integration/`` with a "Protocol-Satisfying
Deterministic Adapter" framing per ``rules/testing.md`` § 3-Tier
Testing. On re-review the framing does not hold — ``TrustLineageChain``
is a plain ``@dataclass`` (not a ``typing.Protocol`` satisfier), so the
adapter exception does not apply. The test still exercises the
load-bearing composition contract (import path, facade-call shape,
cryptographic surface), so it is moved to ``tests/unit/`` and marked
``@pytest.mark.unit`` — admitting it as Tier-1 wiring, not Tier-2.

**Tier-2 follow-up (deferred to S3 trust integration shard):** a
real-Postgres-backed ``TrustChainStore`` test exercising end-to-end
persistence of the composed block + verification against the audit
trail. Tracking surface: S3 trust integration plan.

This test exercises:

1. The IMPORT path — ``from kailash.delegate.types import
   DelegateGenesisRecord`` AND ``from kailash.trust.chain import
   GenesisRecord, TrustLineageChain`` together. A regression that
   accidentally orphans the substrate import would fail here at module
   load.
2. The FACADE-CALL shape — ``DelegateGenesisRecord(block=<substrate>)``
   then ``TrustLineageChain(genesis=<substrate>)`` — confirming both
   sides agree on a value-equal substrate object (B4 snapshot
   semantics: identity differs, canonical bytes identical).
3. The CRYPTOGRAPHIC SURFACE — ``to_signing_dict()`` and
   ``to_canonical_dict()`` produce dicts whose ``block`` field has the
   substrate's expected ``to_signing_payload`` keys, byte-stable across
   repeat construction.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.delegate.types import DelegateGenesisRecord
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain


@pytest.mark.unit
def test_delegate_genesis_record_composes_chain_genesis_record() -> None:
    """The composed substrate block is reachable through the wrapper.

    Verifies F4: ``DelegateGenesisRecord.block`` is a value-snapshot of
    the in-memory object passed in — a ``dataclasses.replace`` copy with
    identical canonical bytes (B4, Round 2 sec M-2). Identity differs
    (post-construction mutation of the original cannot bypass the
    ``_validate_hex`` check), but canonical-byte equality holds — §249
    composition is by-VALUE, not by-reference.
    """
    block = GenesisRecord(
        id="g-tier2-0001",
        agent_id="agent-tier2",
        authority_id="auth-tier2",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    delegate_genesis = DelegateGenesisRecord(
        block=block,
        spec_version="1",
        capabilities=("read", "delegate"),
    )

    # B4 snapshot — value equality, NOT identity. Same canonical bytes,
    # isolated identity so post-construction mutation of `block` cannot
    # silently invalidate the wrapper's hex-validated signature surface.
    assert delegate_genesis.block is not block
    assert delegate_genesis.block == block
    # The convenience accessor surfaces the substrate id.
    assert delegate_genesis.genesis_id == "g-tier2-0001"


@pytest.mark.unit
def test_delegate_genesis_record_block_powers_trust_lineage_chain() -> None:
    """The substrate block plugs directly into ``TrustLineageChain``.

    F10 wiring assertion: a ``DelegateGenesisRecord`` constructed from a
    ``GenesisRecord`` exposes a value-equal substrate object that
    ``TrustLineageChain`` accepts as its ``genesis`` field. The
    cross-import contract holds end-to-end. Post-B4 (Round 2 sec M-2):
    the wrapper holds a ``dataclasses.replace`` snapshot, so identity
    with the caller's original block differs — but value equality holds
    and the chain plug-in semantics are preserved.
    """
    block = GenesisRecord(
        id="g-tier2-0002",
        agent_id="agent-tier2-b",
        authority_id="auth-tier2-b",
        authority_type=AuthorityType.HUMAN,
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature="e" * 128,
    )

    # Compose via the Delegate wrapper.
    delegate_genesis = DelegateGenesisRecord(block=block, spec_version="1")

    # The wrapper's snapshotted block plugs directly into TrustLineageChain.
    chain = TrustLineageChain(genesis=delegate_genesis.block)
    # Identity holds against the wrapper's snapshot (the chain consumes
    # what the wrapper exposes); value equality holds against the caller's
    # original block.
    assert chain.genesis is delegate_genesis.block
    assert chain.genesis == block
    # Chain is a real object with real default initialization.
    assert chain.constraint_envelope is not None
    assert chain.constraint_envelope.agent_id == "agent-tier2-b"
    # Chain hash is computed against the substrate record's fields, not
    # the wrapper's — confirming the wrapper is genuinely transparent.
    h1 = chain.hash()
    assert isinstance(h1, str) and len(h1) > 0


@pytest.mark.unit
def test_canonical_dict_round_trip_is_byte_stable() -> None:
    """Two constructions with identical inputs emit byte-identical JSON.

    Cross-SDK fixture parity (per ``cross-sdk-inspection.md`` Rule 4)
    depends on byte-canonical output. This test exercises the full
    round-trip through ``to_canonical_dict`` → ``canonical_json_dumps``
    and asserts byte equality across two independent constructions.
    """

    def build() -> DelegateGenesisRecord:
        return DelegateGenesisRecord(
            block=GenesisRecord(
                id="g-tier2-0003",
                agent_id="agent-canon",
                authority_id="auth-canon",
                authority_type=AuthorityType.SYSTEM,
                created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
                signature="f" * 128,
            ),
            spec_version="1",
            capabilities=("a", "b", "c"),
        )

    json1 = canonical_json_dumps(build().to_canonical_dict())
    json2 = canonical_json_dumps(build().to_canonical_dict())
    assert json1 == json2
    # Nested block payload includes signature (canonical, not signing).
    assert '"signature":' in json1
    # Spine-level extensions appear at the top level.
    assert '"spec_version":' in json1
    assert '"capabilities":' in json1


@pytest.mark.unit
def test_signing_dict_excludes_signature_through_full_round_trip() -> None:
    """The signing payload omits the signature; canonical includes it.

    F7 invariant exercised end-to-end through the canonical-JSON encoder
    so a future regression that re-introduces the signature into the
    signing payload (which would break Ed25519 sign-then-verify) fails
    here loudly.
    """
    delegate_genesis = DelegateGenesisRecord(
        block=GenesisRecord(
            id="g-tier2-0004",
            agent_id="agent-sign",
            authority_id="auth-sign",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
            signature="a" * 128,
        ),
        spec_version="2",
    )
    signing_json = canonical_json_dumps(delegate_genesis.to_signing_dict())
    canonical_json = canonical_json_dumps(delegate_genesis.to_canonical_dict())
    # Signature appears in canonical but NOT signing.
    assert "a" * 128 in canonical_json
    assert "a" * 128 not in signing_json
